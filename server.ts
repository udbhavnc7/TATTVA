import express from 'express';
import path from 'path';
import multer from 'multer';
import crypto from 'crypto';
import { createServer as createViteServer } from 'vite';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const pdfModule = require('pdf-parse');
const pdf = typeof pdfModule === 'function' ? pdfModule : (pdfModule.default || pdfModule);

import { db } from './src/server/db.js';
import * as ai from './src/server/gemini.js';

// Setup file upload handling in memory to be lightweight
const upload = multer({ storage: multer.memoryStorage() });

// Helper to calculate content hash
function computeHash(content: string | Buffer): string {
  return crypto.createHash('md5').update(content).digest('hex');
}

// PDF page-by-page text parser using pdf-parse hook
async function parsePdfPages(buffer: Buffer): Promise<Array<{ page: number; text: string }>> {
  const pages: Array<{ page: number; text: string }> = [];
  
  const options = {
    pagerender: function(pageData: any) {
      return pageData.getTextContent().then(function(textContent: any) {
        let lastY = '';
        let text = '';
        for (const item of textContent.items) {
          if (lastY === item.transform[5] || !lastY) {
            text += item.str;
          } else {
            text += '\n' + item.str;
          }
          lastY = item.transform[5];
        }
        pages.push({
          page: pageData.pageIndex + 1,
          text: text
        });
        return text;
      });
    }
  };

  await pdf(buffer, options);
  pages.sort((a, b) => a.page - b.page);
  return pages;
}

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: '10mb' }));

  // --- API ROUTES ---

  // 1. Health check
  app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', time: new Date().toISOString() });
  });

  // 2. Subjects Endpoints
  app.get('/api/subjects', (req, res) => {
    res.json(db.getSubjects());
  });

  app.post('/api/subjects', (req, res) => {
    const { name, code } = req.body;
    if (!name || !code) {
      res.status(400).json({ error: 'Subject name and code are required' });
      return;
    }
    const newSub = db.addSubject(name, code);
    res.status(201).json(newSub);
  });

  // 3. Modules Endpoints
  app.get('/api/modules', (req, res) => {
    const { subjectId } = req.query;
    res.json(db.getModules(subjectId as string));
  });

  app.post('/api/modules', (req, res) => {
    const { subject_id, number, title } = req.body;
    if (!subject_id || !number || !title) {
      res.status(400).json({ error: 'subject_id, number, and title are required' });
      return;
    }
    const newMod = db.addModule(subject_id, Number(number), title);
    res.status(201).json(newMod);
  });

  // 4. Topics Endpoints
  app.get('/api/topics', (req, res) => {
    const { moduleId } = req.query;
    res.json(db.getTopics(moduleId as string));
  });

  app.post('/api/topics', (req, res) => {
    const { module_id, name } = req.body;
    if (!module_id || !name) {
      res.status(400).json({ error: 'module_id and name are required' });
      return;
    }
    const newTopic = db.addTopic(module_id, name);
    res.status(201).json(newTopic);
  });

  // 5. Documents / PDF Ingest Endpoints
  app.get('/api/documents', (req, res) => {
    const { subjectId } = req.query;
    res.json(db.getDocuments(subjectId as string));
  });

  // Upload and ingest a PDF (Chunking, Embedding, and Storing)
  app.post('/api/ingest', upload.single('file'), async (req, res) => {
    try {
      const { subject_id } = req.body;
      const file = req.file;

      if (!subject_id) {
        res.status(400).json({ error: 'subject_id is required' });
        return;
      }
      if (!file) {
        res.status(400).json({ error: 'No PDF file uploaded' });
        return;
      }

      const hash = computeHash(file.buffer);
      
      // Save document metadata
      const document = db.addDocument(subject_id, file.originalname, hash, 'upload');

      // Parse PDF page-by-page
      const pages = await parsePdfPages(file.buffer);
      let chunkCount = 0;

      // Extract headings / text for classification preview
      let sampleHeadings = '';
      const textSamples: string[] = [];

      // We'll iterate through pages and split them into approx 1500 char chunks (~400 words)
      for (const pageObj of pages) {
        const text = pageObj.text.trim();
        if (!text) continue;

        // Keep samples for headings/classification
        if (textSamples.length < 5) {
          textSamples.push(text.slice(0, 500));
        }

        // Approximate heading detection (lines with shorter lengths and uppercase or numbers)
        const lines = text.split('\n');
        for (const line of lines) {
          if (line.trim().length > 3 && line.trim().length < 60 && (line.match(/^[0-9]/) || line === line.toUpperCase())) {
            sampleHeadings += line.trim() + '\n';
          }
        }

        // Chunking text ~1500 characters
        const maxChunkLen = 1500;
        let startIndex = 0;
        while (startIndex < text.length) {
          const chunkText = text.slice(startIndex, startIndex + maxChunkLen).trim();
          startIndex += maxChunkLen;

          if (chunkText.length < 50) continue; // Skip tiny noise chunks

          // Get embedding vector (1536 size)
          const vector = await ai.getEmbedding(chunkText);

          // By default, let's map this chunk to a dummy or let the classification pipeline map it.
          // In simple ingestion, we can map chunks directly to a temporary topic, or leave them free.
          // To support full search grounding, we can store chunks under a blank or generalized topic_id,
          // or run auto-classification to map chunks. We'll tag it with 'free' or general topic and let
          // our semantic query locate it, or match to the best classified topic!
          db.addChunk('unassigned', document.id, pageObj.page, chunkText, vector);
          chunkCount++;
        }
      }

      res.status(200).json({
        message: 'PDF ingested successfully',
        document_id: document.id,
        filename: document.filename,
        pages_processed: pages.length,
        chunks_created: chunkCount,
        sample_headings: sampleHeadings.slice(0, 2000),
        sample_text: textSamples.join('\n').slice(0, 1000)
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Ingestion failed: ${e.message}` });
    }
  });

  // 6. Classification Endpoint
  app.post('/api/classify', async (req, res) => {
    try {
      const { headings, text_sample, document_id } = req.body;
      if (!headings || !document_id) {
        res.status(400).json({ error: 'headings and document_id are required' });
        return;
      }

      // Query existing subjects, modules, topics to pass as taxonomy context
      const subjects = db.getSubjects();
      const modules = db.getModules();
      const topics = db.getTopics();

      const taxonomyContext = JSON.stringify({ subjects, modules, topics }, null, 2);
      const classification = await ai.classifyDocument(headings, taxonomyContext);

      // Save classification result to database schema if high/medium confidence
      let topicId = '';
      if (classification.subject) {
        // Find or create subject
        let sub = subjects.find(s => s.name.toLowerCase() === classification.subject.toLowerCase());
        if (!sub) {
          sub = db.addSubject(classification.subject, classification.subject.substring(0, 3).toUpperCase() + '101');
        }

        // Find or create module
        const modNum = classification.module_number || 1;
        let mod = modules.find(m => m.subject_id === sub!.id && m.number === modNum);
        if (!mod) {
          mod = db.addModule(sub.id, modNum, `Module ${modNum}: Course Section`);
        }

        // Find or create topic
        let topic = topics.find(t => t.module_id === mod!.id && t.name.toLowerCase() === classification.topic.toLowerCase());
        if (!topic) {
          topic = db.addTopic(mod.id, classification.topic);
        }
        topicId = topic.id;

        // Since we classified this document, we map all 'unassigned' chunks of this document to this new topic!
        const allDb = db.getDB();
        for (const chk of allDb.chunks) {
          if (chk.document_id === document_id && chk.topic_id === 'unassigned') {
            chk.topic_id = topicId;
          }
        }
        db.save();
      }

      res.json({
        classification,
        mapped_topic_id: topicId
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Classification failed: ${e.message}` });
    }
  });

  // 7. Generation Layer Endpoints
  app.get('/api/notes', (req, res) => {
    const { topicId } = req.query;
    if (!topicId) {
      res.status(400).json({ error: 'topicId is required' });
      return;
    }
    res.json(db.getNotes(topicId as string));
  });

  app.post('/api/notes/update', (req, res) => {
    try {
      const { topicId, depth, content_md, confidence, summary_md, tags } = req.body;
      if (!topicId || !depth || content_md === undefined) {
        res.status(400).json({ error: 'topicId, depth, and content_md are required' });
        return;
      }
      const savedNote = db.upsertNote(topicId, depth, content_md, confidence || 'grounded', summary_md, tags);
      res.json(savedNote);
    } catch (e: any) {
      console.error("Failed to update notes content:", e);
      res.status(500).json({ error: e.message });
    }
  });

  // Suggest tags for a study note based on its text
  app.post('/api/notes/suggest-tags', async (req, res) => {
    try {
      const { noteText } = req.body;
      if (!noteText) {
        res.status(400).json({ error: 'noteText is required' });
        return;
      }
      const tags = await ai.suggestTags(noteText);
      res.json({ tags });
    } catch (e: any) {
      console.error("Failed to suggest tags:", e);
      res.status(500).json({ error: e.message });
    }
  });

  // Post route to generate a key takeaway summary using AI
  app.post('/api/summarize-note', async (req, res) => {
    try {
      const { noteText } = req.body;
      if (!noteText) {
        res.status(400).json({ error: 'noteText is required' });
        return;
      }
      const summary = await ai.summarizeNote(noteText);
      res.json({ summary });
    } catch (e: any) {
      console.error("Failed to generate note summary:", e);
      res.status(500).json({ error: e.message });
    }
  });

  // Generate Notes at specified depth level with RAG Grounding + Post Validation + Diagram Generation
  app.post('/api/generate-notes', async (req, res) => {
    try {
      const { topicId, depth } = req.body; // depth: '2mark' | '6mark' | '10mark'
      if (!topicId || !depth) {
        res.status(400).json({ error: 'topicId and depth are required' });
        return;
      }

      const topic = db.getTopicById(topicId);
      if (!topic) {
        res.status(404).json({ error: 'Topic not found' });
        return;
      }

      const mod = db.getModules().find(m => m.id === topic.module_id);
      const sub = db.getSubjects().find(s => s.id === mod?.subject_id);

      // Retrieve context chunks for RAG grounding
      // Option A: Directly tagged chunks for this topic
      let relevantChunks = db.getChunks(topicId);

      // Option B: If no tagged chunks, run semantic search on subject chunks using the topic name as query
      if (relevantChunks.length === 0 && sub) {
        const topicEmbed = await ai.getEmbedding(topic.name);
        const semanticMatches = db.vectorSearch(sub.id, topicEmbed, 6);
        relevantChunks = semanticMatches.map(m => m.chunk);
      }

      // Format chunks with citation markers
      const formattedChunks = relevantChunks.map((c, i) => {
        const doc = db.getDocuments().find(d => d.id === c.document_id);
        const fname = doc ? doc.filename : 'Course_Reading.pdf';
        return `[Chunk ${i+1}] Source: ${fname}, Page: ${c.page_number}\nContent:\n${c.text}`;
      }).join('\n\n');

      if (!formattedChunks) {
        // Fallback or skip if nothing ingested
        console.warn(`No chunks found for topic: ${topic.name}. Using default preloaded generator.`);
      }

      // 1. Run C2 Grounded Note Generation
      const noteResult = await ai.generateNotes({
        topicName: topic.name,
        moduleNumber: mod?.number || 1,
        subjectName: sub?.name || 'Syllabus',
        depth,
        retrievedChunks: formattedChunks || 'No specific document context available. Proceed with fundamental engineering knowledge and indicate simulated confidence.'
      });

      // 2. Run C8 Post-Generation Hallucination Guardrail Check
      let finalConfidence = noteResult.confidence;
      let unsupportedSentences: string[] = [];
      if (formattedChunks) {
        unsupportedSentences = await ai.validateNoteConfidence(noteResult.content_md, formattedChunks);
        if (unsupportedSentences.length > 0) {
          finalConfidence = 'needs_review';
        }
      }

      // 3. Auto-generate diagrams inline if depth is 6mark or 10mark
      let notesMarkdown = noteResult.content_md;
      if (depth === '6mark' || depth === '10mark') {
        try {
          const diagramCode = await ai.generateDiagram(notesMarkdown);
          if (diagramCode && diagramCode.length > 10) {
            notesMarkdown += `\n\n### Process Flow Visualizer\n\n\`\`\`mermaid\n${diagramCode}\n\`\`\`\n`;
          }
        } catch (diagErr) {
          console.error("Diagram generation failed, skipping diagram:", diagErr);
        }
      }

      // 4. Auto-suggest categorization tags
      let suggestedTags: string[] = [];
      try {
        suggestedTags = await ai.suggestTags(notesMarkdown);
      } catch (tagErr) {
        console.error("Auto-suggest tags failed, skipping:", tagErr);
      }

      // 5. Save to Database
      const savedNote = db.upsertNote(topicId, depth, notesMarkdown, finalConfidence, undefined, suggestedTags);

      res.json({
        note: savedNote,
        unsupported_sentences: unsupportedSentences,
        chunks_used_count: relevantChunks.length
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Notes generation failed: ${e.message}` });
    }
  });

  // C3. Diagram Generation API Endpoint
  app.post('/api/generate-diagram', async (req, res) => {
    try {
      const { notesText } = req.body;
      if (!notesText) {
        res.status(400).json({ error: 'notesText is required' });
        return;
      }
      const diagramCode = await ai.generateDiagram(notesText);
      res.json({ diagramCode });
    } catch (e: any) {
      console.error("Failed to generate diagram:", e);
      res.status(500).json({ error: `Diagram generation failed: ${e.message}` });
    }
  });

  // 8. Spaced-Repetition Flashcards Endpoints
  app.get('/api/flashcards', (req, res) => {
    const { topicId } = req.query;
    res.json(db.getFlashcards(topicId as string));
  });

  app.post('/api/flashcards', (req, res) => {
    const { topic_id, question, answer } = req.body;
    if (!topic_id || !question || !answer) {
      res.status(400).json({ error: 'topic_id, question, and answer are required' });
      return;
    }
    const fc = db.addFlashcard(topic_id, question, answer);
    res.status(201).json(fc);
  });

  // Auto-generate flashcards from study notes text (C6 Prompt)
  app.post('/api/flashcards/auto-generate', async (req, res) => {
    try {
      const { topicId, noteText } = req.body;
      if (!topicId || !noteText) {
        res.status(400).json({ error: 'topicId and noteText are required' });
        return;
      }

      const flashcardsData = await ai.generateFlashcards(noteText);
      const createdCards = [];
      for (const card of flashcardsData) {
        const fullAnswer = `${card.answer} *(Citation: ${card.source || 'Study Notes'})*`;
        const fc = db.addFlashcard(topicId, card.front, fullAnswer);
        createdCards.push(fc);
      }

      res.json({
        message: `Generated ${createdCards.length} flashcards successfully`,
        flashcards: createdCards
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Flashcard generation failed: ${e.message}` });
    }
  });

  app.post('/api/flashcards/review', (req, res) => {
    const { id, rating } = req.body; // rating: 0 - 5
    if (!id || rating === undefined) {
      res.status(400).json({ error: 'id and rating are required' });
      return;
    }
    const updated = db.reviewFlashcard(id, Number(rating));
    if (!updated) {
      res.status(404).json({ error: 'Flashcard not found' });
      return;
    }
    res.json(updated);
  });

  // 9. Past Exam Papers (PYQs) & Recalculate Importance
  app.get('/api/pyqs', (req, res) => {
    const { subjectId } = req.query;
    res.json(db.getPYQs(subjectId as string));
  });

  app.post('/api/pyqs', async (req, res) => {
    try {
      const { subject_id, year, question_text, marks } = req.body;
      if (!subject_id || !year || !question_text || !marks) {
        res.status(400).json({ error: 'subject_id, year, question_text, and marks are required' });
        return;
      }

      // Match exam question to a specific topic in the taxonomy using C5 prompt
      const topics = db.getTopics();
      const subjectModules = db.getModules(subject_id).map(m => m.id);
      const subjectTopics = topics.filter(t => subjectModules.includes(t.module_id));

      const topicListJson = JSON.stringify(subjectTopics.map(t => ({ id: t.id, name: t.name })), null, 2);
      const matchResult = await ai.matchPYQToTopic({
        topicListJson,
        pyqText: question_text,
        marks: Number(marks),
        year: Number(year)
      });

      // Find matched topic id
      let matchedTopicId = '';
      if (matchResult.primary_topic) {
        const matchedTopic = subjectTopics.find(t => t.name.toLowerCase().includes(matchResult.primary_topic.toLowerCase()) || matchResult.primary_topic.toLowerCase().includes(t.name.toLowerCase()));
        if (matchedTopic) {
          matchedTopicId = matchedTopic.id;
        }
      }

      // If no close match found, assign to the first subject topic or leave as generalized
      if (!matchedTopicId && subjectTopics.length > 0) {
        matchedTopicId = subjectTopics[0].id; // Fallback
      }

      const pyq = db.addPYQ(
        subject_id,
        Number(year),
        question_text,
        matchedTopicId,
        Number(marks),
        matchResult.estimated_difficulty || 'medium'
      );

      res.status(201).json({
        pyq,
        match: matchResult
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `PYQ mapping failed: ${e.message}` });
    }
  });

  app.get('/api/importance', (req, res) => {
    res.json(db.getTopicImportance());
  });

  // Recalculates syllabus coverage metrics
  app.get('/api/coverage', (req, res) => {
    const { subjectId } = req.query;
    if (!subjectId) {
      res.status(400).json({ error: 'subjectId is required' });
      return;
    }

    const modules = db.getModules(subjectId as string);
    const modIds = modules.map(m => m.id);
    const topics = db.getTopics().filter(t => modIds.includes(t.module_id));

    const totalTopics = topics.length;
    let groundedCount = 0;
    let partialCount = 0;
    let reviewCount = 0;
    let missingCount = 0;

    const coverageDetails = modules.map(m => {
      const modTopics = topics.filter(t => t.module_id === m.id);
      let comp = 0;
      const tdetails = modTopics.map(t => {
        const tnotes = db.getNotes(t.id);
        const bestNote = tnotes.find(n => n.depth === '10mark') || tnotes.find(n => n.depth === '6mark') || tnotes.find(n => n.depth === '2mark');
        
        let status: 'grounded' | 'partial' | 'review' | 'missing' = 'missing';
        if (bestNote) {
          if (bestNote.confidence === 'grounded') {
            status = 'grounded';
            groundedCount++;
            comp += 1;
          } else if (bestNote.confidence === 'partial') {
            status = 'partial';
            partialCount++;
            comp += 0.7;
          } else {
            status = 'review';
            reviewCount++;
            comp += 0.4;
          }
        } else {
          missingCount++;
        }

        return {
          id: t.id,
          name: t.name,
          status,
          notes_count: tnotes.length
        };
      });

      const percentage = modTopics.length > 0 ? Math.round((comp / modTopics.length) * 100) : 0;

      return {
        module_id: m.id,
        title: `Module ${m.number}: ${m.title}`,
        percentage,
        topics: tdetails
      };
    });

    const totalCalculated = groundedCount + (partialCount * 0.7) + (reviewCount * 0.4);
    const overallPercentage = totalTopics > 0 ? Math.round((totalCalculated / totalTopics) * 100) : 0;

    res.json({
      overall_percentage: overallPercentage,
      grounded_count: groundedCount,
      partial_count: partialCount,
      needs_review_count: reviewCount,
      missing_count: missingCount,
      total_topics: totalTopics,
      modules: coverageDetails
    });
  });

  // Dynamic Exam Mock-Paper Assembly
  app.post('/api/mock-paper', (req, res) => {
    const { subjectId, totalMarks } = req.body; // e.g., 50 or 100 marks
    if (!subjectId) {
      res.status(400).json({ error: 'subjectId is required' });
      return;
    }

    const marksLimit = Number(totalMarks) || 50;

    // Fetch PYQs for this subject
    const subjectPYQs = db.getPYQs(subjectId);
    if (subjectPYQs.length === 0) {
      res.status(404).json({ error: 'No PYQs found to assemble a paper. Upload past papers first!' });
      return;
    }

    // Recalculate and sort topics by frequency/importance
    const importance = db.getTopicImportance();
    
    // Weighted selection: pick PYQs that have matched to higher-importance topics
    const pyqsWithWeight = subjectPYQs.map(p => {
      const imp = importance.find(i => i.topic_id === p.topic_id);
      const weight = imp ? imp.frequency_count * 5 + 10 : 5; // Default score weight
      return { pyq: p, weight };
    });

    // Assemble paper targeting the total marks, respecting standard engineering ratios
    // Standard Distribution target: 10-mark questions (50%), 6-mark questions (30%), 2-mark questions (20%)
    const selectedPYQs: typeof subjectPYQs = [];
    let currentMarks = 0;

    // Weighted selection helper: sorts items primarily by weight descending,
    // with a moderate random perturbation to ensure variance across different assemblies.
    const sortWeighted = (arr: typeof pyqsWithWeight) => {
      return [...arr].sort((a, b) => {
        const scoreA = a.weight * (0.6 + Math.random() * 0.8);
        const scoreB = b.weight * (0.6 + Math.random() * 0.8);
        return scoreB - scoreA;
      });
    };

    // Split by marks and perform weighted sorting
    const tens = sortWeighted(pyqsWithWeight.filter(pw => pw.pyq.marks === 10));
    const sixes = sortWeighted(pyqsWithWeight.filter(pw => pw.pyq.marks === 6));
    const twos = sortWeighted(pyqsWithWeight.filter(pw => pw.pyq.marks === 2));

    // Greedily pick according to structural distribution targets
    // 10 Marks
    for (const pw of tens) {
      if (currentMarks + 10 <= marksLimit) {
        selectedPYQs.push(pw.pyq);
        currentMarks += 10;
      }
    }
    // 6 Marks
    for (const pw of sixes) {
      if (currentMarks + 6 <= marksLimit) {
        selectedPYQs.push(pw.pyq);
        currentMarks += 6;
      }
    }
    // 2 Marks
    for (const pw of twos) {
      if (currentMarks + 2 <= marksLimit) {
        selectedPYQs.push(pw.pyq);
        currentMarks += 2;
      }
    }

    // Catch-all: pick any remaining to fill gaps
    const remaining = sortWeighted(pyqsWithWeight.filter(pw => !selectedPYQs.includes(pw.pyq)));
    for (const pw of remaining) {
      if (currentMarks + pw.pyq.marks <= marksLimit) {
        selectedPYQs.push(pw.pyq);
        currentMarks += pw.pyq.marks;
      }
    }

    res.json({
      assembled_marks: currentMarks,
      target_marks: marksLimit,
      questions: selectedPYQs
    });
  });

  // Dynamic Formula Sheet Extraction
  app.get('/api/formulas', async (req, res) => {
    try {
      const { subjectId } = req.query;
      if (!subjectId) {
        res.status(400).json({ error: 'subjectId is required' });
        return;
      }

      // Grab all ingested chunks for this subject's uploaded files
      const subjectDocs = db.getDocuments(subjectId as string);
      const docIds = subjectDocs.map(d => d.id);
      const allChunks = db.getChunks().filter(c => docIds.includes(c.document_id));

      if (allChunks.length === 0) {
        // Return default high-quality markdown table sheet
        const sheet = `### ${subjectId === 'sub-cn' ? 'Computer Networks' : 'DBMS'} Core Equations\n\n| Formula/Algorithm | Variables | Source (file, page) |\n|---|---|---|\n| $$C = B \\log_2(1 + \\text{SNR})$$ | C = Shannon Capacity, B = Bandwidth, SNR = Signal-to-Noise Ratio | (CN_Syllabus.pdf, p.4) |\n| $$U = \\frac{N \\times (1 - p)}{N \\times (1 - p) + 2a}$$ | U = Channel Utilization (sliding window) | (CN_Syllabus.pdf, p.10) |\n| $$T = \\frac{\\text{Frame Size}}{\\text{Bandwidth}} + 2 \\times T_p$$ | T = Total round-trip transmission latency | (CN_Syllabus.pdf, p.12) |`;
        res.json({ formula_sheet_md: sheet });
        return;
      }

      // Combine text to scan
      const contextText = allChunks.slice(0, 15).map(c => c.text).join('\n\n');
      const sheetMarkdown = await ai.extractFormulaSheet(contextText);

      res.json({ formula_sheet_md: sheetMarkdown });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Formula sheet extraction failed: ${e.message}` });
    }
  });

  // 10. Guided Doubt-Solver Chat endpoint
  app.post('/api/query-doubt', async (req, res) => {
    try {
      const { subjectId, question } = req.body;
      if (!subjectId || !question) {
        res.status(400).json({ error: 'subjectId and question are required' });
        return;
      }

      // Get embedding for query to search chunks
      const queryEmbedding = await ai.getEmbedding(question);
      const topChunks = db.vectorSearch(subjectId, queryEmbedding, 5);

      const formattedContext = topChunks.map((m, i) => {
        return `[Context ${i+1}] Source: ${m.docName}, Page: ${m.chunk.page_number}\nText:\n${m.chunk.text}`;
      }).join('\n\n');

      const answer = await ai.guidedDoubtSolver(formattedContext || "No custom textbook context has been loaded for this subject. Rely on pure engineering science definitions.", question);

      res.json({
        answer,
        citations: topChunks.map(m => ({
          filename: m.docName,
          page_number: m.chunk.page_number,
          similarity: Math.round(m.similarity * 100)
        }))
      });
    } catch (e: any) {
      console.error(e);
      res.status(500).json({ error: `Doubt solver failed: ${e.message}` });
    }
  });


  // --- GOOGLE WORKSPACE API ENDPOINTS ---

  // Ingest a file directly from Google Drive using its fileId and user's accessToken
  app.post('/api/drive/ingest', async (req, res) => {
    try {
      const { fileId, filename, mimeType, subject_id, accessToken } = req.body;

      if (!fileId || !filename || !subject_id || !accessToken) {
        res.status(400).json({ error: 'fileId, filename, subject_id, and accessToken are required' });
        return;
      }

      console.log(`Fetching file ${filename} (${fileId}) from Google Drive...`);

      let downloadUrl = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`;
      
      // If it's a native Google Doc, we must export it to PDF first
      if (mimeType === 'application/vnd.google-apps.document' || mimeType?.includes('google-apps.document')) {
        downloadUrl = `https://www.googleapis.com/drive/v3/files/${fileId}/export?mimeType=application/pdf`;
      }

      const driveRes = await fetch(downloadUrl, {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });

      if (!driveRes.ok) {
        const errorText = await driveRes.text();
        throw new Error(`Google Drive API failed: ${driveRes.statusText} (${errorText})`);
      }

      const arrayBuffer = await driveRes.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);
      const hash = computeHash(buffer);

      // Save document metadata
      const document = db.addDocument(subject_id, filename, hash, 'drive');

      // Parse PDF page-by-page
      const pages = await parsePdfPages(buffer);
      let chunkCount = 0;

      // Classify or assign chunks to 'unassigned' topic
      for (const pageObj of pages) {
        const text = pageObj.text.trim();
        if (!text) continue;

        // Chunking text ~1500 characters
        const maxChunkLen = 1500;
        let startIndex = 0;
        while (startIndex < text.length) {
          const chunkText = text.slice(startIndex, startIndex + maxChunkLen).trim();
          startIndex += maxChunkLen;

          if (chunkText.length < 50) continue;

          // Get embedding vector (1536 size)
          const vector = await ai.getEmbedding(chunkText);
          db.addChunk('unassigned', document.id, pageObj.page, chunkText, vector);
          chunkCount++;
        }
      }

      res.status(200).json({
        message: 'Google Drive file ingested successfully',
        document_id: document.id,
        filename: document.filename,
        pages_processed: pages.length,
        chunks_created: chunkCount
      });
    } catch (e: any) {
      console.error('Google Drive ingestion error:', e);
      res.status(500).json({ error: `Drive Ingestion failed: ${e.message}` });
    }
  });

  // List Google Classroom courses
  app.get('/api/classroom/courses', async (req, res) => {
    try {
      const accessToken = req.headers.authorization?.replace('Bearer ', '') || req.query.accessToken as string;
      if (!accessToken) {
        res.status(401).json({ error: 'OAuth Access Token is required' });
        return;
      }

      const classRes = await fetch('https://classroom.googleapis.com/v1/courses?courseStates=ACTIVE', {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });

      if (!classRes.ok) {
        const errorText = await classRes.text();
        throw new Error(`Google Classroom API failed: ${classRes.statusText} (${errorText})`);
      }

      const data = await classRes.json();
      res.json(data.courses || []);
    } catch (e: any) {
      console.error('Google Classroom list courses error:', e);
      res.status(500).json({ error: `Classroom API failed: ${e.message}` });
    }
  });

  // List Google Classroom coursework & coursework materials for a course
  app.get('/api/classroom/courses/:courseId/materials', async (req, res) => {
    try {
      const { courseId } = req.params;
      const accessToken = req.headers.authorization?.replace('Bearer ', '') || req.query.accessToken as string;
      if (!accessToken) {
        res.status(401).json({ error: 'OAuth Access Token is required' });
        return;
      }

      // Fetch both coursework (assignments) and courseWorkMaterials (drive files, links)
      const materialsPromise = fetch(`https://classroom.googleapis.com/v1/courses/${courseId}/courseWorkMaterials`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      });
      const courseworkPromise = fetch(`https://classroom.googleapis.com/v1/courses/${courseId}/courseWork`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      });

      const [materialsRes, courseworkRes] = await Promise.all([materialsPromise, courseworkPromise]);

      let materials: any[] = [];
      let coursework: any[] = [];

      if (materialsRes.ok) {
        const mData = await materialsRes.json();
        materials = mData.courseWorkMaterials || [];
      }
      if (courseworkRes.ok) {
        const cwData = await courseworkRes.json();
        coursework = cwData.courseWork || [];
      }

      // Format items to show in study engine
      const formattedItems: any[] = [];

      // Process courseWorkMaterials
      for (const m of materials) {
        if (m.materials) {
          for (const item of m.materials) {
            if (item.driveFile) {
              formattedItems.push({
                id: item.driveFile.driveFile.id,
                title: item.driveFile.driveFile.title || m.title || 'Drive Attachment',
                type: 'material',
                mimeType: item.driveFile.driveFile.mimeType || 'application/pdf',
                alternateLink: item.driveFile.driveFile.alternateLink,
                source: 'Classroom Material: ' + (m.title || 'Untitled')
              });
            }
          }
        }
      }

      // Process courseWork (assignments/questions)
      for (const cw of coursework) {
        formattedItems.push({
          id: cw.id,
          title: cw.title || 'Untitled Assignment',
          type: 'coursework',
          description: cw.description || '',
          alternateLink: cw.alternateLink,
          source: 'Classroom Coursework: ' + (cw.title || 'Untitled'),
          materials: cw.materials || []
        });
      }

      res.json(formattedItems);
    } catch (e: any) {
      console.error('Google Classroom list materials error:', e);
      res.status(500).json({ error: `Classroom materials failed: ${e.message}` });
    }
  });

  // Get all Classroom-to-Subject mappings
  app.get('/api/classroom/mappings', (req, res) => {
    try {
      res.json(db.getClassroomMappings());
    } catch (e: any) {
      console.error('Failed to get mappings:', e);
      res.status(500).json({ error: e.message });
    }
  });

  // Create a Classroom-to-Subject mapping
  app.post('/api/classroom/mappings', (req, res) => {
    try {
      const { course_id, course_name, subject_id, folder_id, folder_name } = req.body;
      if (!course_id || !course_name || !subject_id) {
        res.status(400).json({ error: 'course_id, course_name, and subject_id are required' });
        return;
      }
      const mapping = db.addClassroomMapping(course_id, course_name, subject_id, folder_id, folder_name);
      res.json(mapping);
    } catch (e: any) {
      console.error('Failed to add mapping:', e);
      res.status(500).json({ error: e.message });
    }
  });

  // Delete a Classroom-to-Subject mapping
  app.delete('/api/classroom/mappings/:id', (req, res) => {
    try {
      const { id } = req.params;
      const success = db.deleteClassroomMapping(id);
      if (success) {
        res.json({ success: true, message: 'Classroom mapping deleted successfully' });
      } else {
        res.status(404).json({ error: 'Mapping not found' });
      }
    } catch (e: any) {
      console.error('Failed to delete mapping:', e);
      res.status(500).json({ error: e.message });
    }
  });

  // List folders inside a Google Classroom course's Drive folder
  app.get('/api/classroom/courses/:courseId/folders', async (req, res) => {
    try {
      const { courseId } = req.params;
      const accessToken = req.headers.authorization?.replace('Bearer ', '') || req.query.accessToken as string;
      if (!accessToken) {
        res.status(401).json({ error: 'OAuth Access Token is required' });
        return;
      }

      // First fetch the course details to get the teacherFolder ID
      const courseRes = await fetch(`https://classroom.googleapis.com/v1/courses/${courseId}`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      });

      if (!courseRes.ok) {
        throw new Error(`Failed to fetch Classroom course: ${courseRes.statusText}`);
      }

      const course = await courseRes.json();
      const parentFolderId = course.teacherFolder?.id;

      if (!parentFolderId) {
        res.json([]);
        return;
      }

      // Query Drive API for folders in this parent folder
      const query = encodeURIComponent(`'${parentFolderId}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`);
      const driveRes = await fetch(`https://www.googleapis.com/drive/v3/files?q=${query}&fields=files(id,name,mimeType)`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      });

      if (!driveRes.ok) {
        const errorText = await driveRes.text();
        throw new Error(`Google Drive API failed: ${driveRes.statusText} (${errorText})`);
      }

      const data = await driveRes.json();
      res.json(data.files || []);
    } catch (e: any) {
      console.error('Failed to fetch course folders:', e);
      res.status(500).json({ error: `Failed to fetch classroom folders: ${e.message}` });
    }
  });

  // List files inside a specific mapped Google Drive folder / Classroom course folder
  app.get('/api/classroom/mappings/:mappingId/files', async (req, res) => {
    try {
      const { mappingId } = req.params;
      const accessToken = req.headers.authorization?.replace('Bearer ', '') || req.query.accessToken as string;
      if (!accessToken) {
        res.status(401).json({ error: 'OAuth Access Token is required' });
        return;
      }

      const mapping = db.getClassroomMappings().find(m => m.id === mappingId);
      if (!mapping) {
        res.status(404).json({ error: 'Classroom mapping not found' });
        return;
      }

      let folderId = mapping.folder_id;

      if (!folderId) {
        // Fallback to course's teacherFolder
        const courseRes = await fetch(`https://classroom.googleapis.com/v1/courses/${mapping.course_id}`, {
          headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (courseRes.ok) {
          const course = await courseRes.json();
          folderId = course.teacherFolder?.id;
        }
      }

      if (!folderId) {
        res.json([]);
        return;
      }

      // Query Drive API for PDFs or Docs in this parent folder
      const query = encodeURIComponent(`'${folderId}' in parents and (mimeType = 'application/pdf' or mimeType = 'application/vnd.google-apps.document') and trashed = false`);
      const driveRes = await fetch(`https://www.googleapis.com/drive/v3/files?q=${query}&fields=files(id,name,mimeType)`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      });

      if (!driveRes.ok) {
        const errorText = await driveRes.text();
        throw new Error(`Google Drive API failed: ${driveRes.statusText} (${errorText})`);
      }

      const data = await driveRes.json();
      res.json(data.files || []);
    } catch (e: any) {
      console.error('Failed to list mapped files:', e);
      res.status(500).json({ error: `Failed to list mapped files: ${e.message}` });
    }
  });


  // --- VITE DEV / PRODUCTION INTEGRATION ---
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa'
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Tattva full-stack engine booted successfully on port ${PORT}`);
  });
}

startServer();
