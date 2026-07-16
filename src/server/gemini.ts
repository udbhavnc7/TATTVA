import { GoogleGenAI, Type } from "@google/genai";

let aiInstance: GoogleGenAI | null = null;

// Lazy initialization of the Gemini SDK client
export function getGeminiClient(): GoogleGenAI {
  if (!aiInstance) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn("GEMINI_API_KEY is not configured. Falling back to offline simulator.");
    }
    aiInstance = new GoogleGenAI({
      apiKey: apiKey || "MOCK_API_KEY",
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        }
      }
    });
  }
  return aiInstance;
}

// Generate fallback embedding deterministically based on text hash
function getFallbackEmbedding(text: string): number[] {
  const vector: number[] = new Array(1536).fill(0);
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }
  for (let i = 0; i < 1536; i++) {
    const angle = (hash + i * 1337) % 360;
    vector[i] = Math.sin(angle);
  }
  // Normalize vector to magnitude = 1
  let sumSq = vector.reduce((sum, val) => sum + val * val, 0);
  if (sumSq === 0) sumSq = 1;
  const mag = Math.sqrt(sumSq);
  return vector.map(val => val / mag);
}

// Fetch embeddings using gemini-embedding-2-preview
export async function getEmbedding(text: string): Promise<number[]> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return getFallbackEmbedding(text);
  }
  try {
    const ai = getGeminiClient();
    const response: any = await ai.models.embedContent({
      model: "gemini-embedding-2-preview",
      contents: text
    });
    if (response && response.embedding && response.embedding.values) {
      return response.embedding.values;
    }
    throw new Error("Empty embedding returned");
  } catch (error) {
    console.error("Embedding API error, falling back to simulator:", error);
    return getFallbackEmbedding(text);
  }
}

// C1. Classification Prompt Implementation
export async function classifyDocument(extractedHeadings: string, existingTaxonomyJson: string) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    // Return mock classification for local testing
    return {
      subject: "Computer Networks",
      module_number: 3,
      topic: "Link State Routing vs Distance Vector Routing",
      is_new_topic: false,
      confidence: "high" as const,
      note: "Simulated classification since API key is missing."
    };
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `You classify academic PDF content into a subject/module/topic taxonomy.
You will be given the existing taxonomy for this student's course and the
extracted headings/text of a new document. Output ONLY valid JSON, no
preamble.

Rules:
- Match to an EXISTING subject/module if it clearly fits.
- Only propose a NEW module/topic if nothing existing fits — do not
  silently merge distinct topics to avoid creating a new entry.
- If uncertain, set "confidence": "low" and explain why in "note".

Existing taxonomy:
${existingTaxonomyJson}

Document headings/content sample:
${extractedHeadings}`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: "Classify the uploaded document text based on the provided existing course taxonomy.",
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            subject: { type: Type.STRING, description: "Name of the academic subject" },
            module_number: { type: Type.INTEGER, description: "Module number (e.g., 1, 2, 3)" },
            topic: { type: Type.STRING, description: "Name of the topic matching or being proposed" },
            is_new_topic: { type: Type.BOOLEAN, description: "Whether this represents a new topic to add" },
            confidence: { type: Type.STRING, enum: ["high", "medium", "low"] },
            note: { type: Type.STRING, description: "Explanation of matching logic" }
          },
          required: ["subject", "module_number", "topic", "is_new_topic", "confidence", "note"]
        }
      }
    });

    const text = response.text?.trim() || "{}";
    return JSON.parse(text);
  } catch (error) {
    console.error("Classification API error:", error);
    return {
      subject: "Computer Networks",
      module_number: 1,
      topic: "Transmission Media & Nyquist Theorem",
      is_new_topic: false,
      confidence: "medium" as const,
      note: "Classification failed, returned fallback."
    };
  }
}

// C2. Note Generation Prompt Implementation
export async function generateNotes(params: {
  topicName: string;
  moduleNumber: number;
  subjectName: string;
  depth: '2mark' | '6mark' | '10mark';
  retrievedChunks: string;
}) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return {
      content_md: `### ${params.topicName} (${params.depth} Study Note)\n\nThis is a high-quality simulated study note for **${params.topicName}** (${params.subjectName} Module ${params.moduleNumber}).\n\n- **Core definition**: Engineering concepts surrounding this field cover structural behaviors and protocol mechanisms.\n- **Depth details**: At ${params.depth} depth, we provide essential definitions, illustrations, and formulas.\n\n*(Source: Simulated_Syllabus.pdf, p.1)*\n\nCONFIDENCE: grounded`,
      confidence: 'grounded' as const
    };
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `You write exam-focused study notes for an engineering student. You must
use ONLY the retrieved context below — do not add facts from your own
training data. Every factual claim must be traceable to a chunk in the
context. If the context doesn't cover something needed at this depth,
say "Not covered in provided material" instead of filling the gap.

Depth level for this generation: ${params.depth}   // "2mark" | "6mark" | "10mark"

Depth instructions:
- 2mark: a crisp definition/answer, 2-4 sentences max.
- 6mark: definition + explanation + one example or diagram reference.
- 10mark: full explanation, all sub-points, at least one diagram
  reference, advantages/disadvantages or comparison if applicable.

For every paragraph, append a citation in the form:
  (Source: document_filename, p.page_number)

Retrieved context (chunks, each tagged with source + page):
${params.retrievedChunks}

Topic: ${params.topicName}
Module: ${params.moduleNumber} — ${params.subjectName}

Output the notes in Markdown. End with a line exactly like:
CONFIDENCE: grounded | partial | needs_review
(grounded = every claim cited and directly supported;
 partial = some claims inferred/combined across chunks but still
 source-consistent; needs_review = context was thin or ambiguous)`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: `Generate a comprehensive exam-focused note at ${params.depth} depth for topic "${params.topicName}".`,
      config: {
        systemInstruction: systemPrompt,
        temperature: 0.2 // Lower temperature for high factual accuracy (RAG)
      }
    });

    const markdown = response.text || "";
    
    // Parse the confidence badge from the markdown
    let confidence: 'grounded' | 'partial' | 'needs_review' = 'grounded';
    if (markdown.toLowerCase().includes("confidence: partial")) {
      confidence = 'partial';
    } else if (markdown.toLowerCase().includes("confidence: needs_review") || markdown.toLowerCase().includes("confidence: needs-review")) {
      confidence = 'needs_review';
    }

    return {
      content_md: markdown,
      confidence
    };
  } catch (error) {
    console.error("Note Generation API error:", error);
    return {
      content_md: "Failed to generate study notes due to API service disruption.",
      confidence: 'needs_review' as const
    };
  }
}

// C3. Diagram Generation Prompt Implementation
export async function generateDiagram(generatedNoteText: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    // Return standard fallback Mermaid code
    return `graph TD
    A[Start Process] --> B[Execute Algorithms]
    B --> C{Decision Path}
    C -->|Success| D[Final Output]
    C -->|Failure| E[Review Logs]`;
  }

  try {
    const ai = getGeminiClient();
    const systemInstruction = `Generate a Mermaid diagram (flowchart, sequence, or state diagram —
choose the type that fits) that visually represents the process or
relationship described below. Use ONLY the concepts present in the
provided notes — do not invent steps that aren't in the source text.
Keep node labels short (under 6 words).

Output ONLY the Mermaid code block, nothing else. Do not wrap in backticks unless they are mermaid block bounds, but standard is returning just the code. If you use backticks, make sure to prefix with \`\`\`mermaid.`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: `Generate a Mermaid diagram code block based on this study note:\n\n${generatedNoteText}`,
      config: {
        systemInstruction
      }
    });

    let text = response.text || "";
    // Sanitize to extract the raw mermaid block if wrapped
    if (text.includes("```mermaid")) {
      text = text.split("```mermaid")[1].split("```")[0].trim();
    } else if (text.includes("```")) {
      text = text.split("```")[1].split("```")[0].trim();
    }
    return text.trim();
  } catch (error) {
    console.error("Diagram Generation API error:", error);
    return `graph TD
    A[Start Process] --> B[Data Engine]`;
  }
}

// C4. Formula Sheet Extraction Prompt Implementation
export async function extractFormulaSheet(retrievedChunks: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return `| Formula/Algorithm | Variables | Source (file, page) |\n|---|---|---|\n| $$C = B \\log_2(1 + \\text{SNR})$$ | C = Capacity, B = Bandwidth, SNR = Signal-to-Noise Ratio | (CN_Guide.pdf, p.5) |\n| $$d(x, y) = \\sum |x_i - y_i|$$ | Manhattan distance between vectors | (Math_Review.pdf, p.2) |`;
  }

  try {
    const ai = getGeminiClient();
    const systemInstruction = `Extract every formula, equation, or algorithm pseudocode present in the
context below. Do not derive or complete partial formulas — if a formula
is incomplete in the source, flag it as "[incomplete in source]" rather
than finishing it yourself.

Output as a Markdown table: | Formula/Algorithm | Variables | Source (file, page) |`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: `Extract all formulas from the provided chunks:\n\n${retrievedChunks}`,
      config: {
        systemInstruction
      }
    });

    return response.text || "No formulas found in retrieved chunks.";
  } catch (error) {
    console.error("Formula Extraction API error:", error);
    return "Error extracting formulas.";
  }
}

// C5. PYQ Topic-Matching Prompt Implementation
export async function matchPYQToTopic(params: {
  topicListJson: string;
  pyqText: string;
  marks: number;
  year: number;
}) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return {
      primary_topic: "Link State Routing vs Distance Vector Routing",
      secondary_topics: [],
      estimated_difficulty: "medium" as const,
      reasoning: "Offline model selected default routing topic mapping."
    };
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `Match the following exam question to ONE topic from the taxonomy below.
If it spans multiple topics, pick the primary one and list secondary
topics separately. Output JSON only.

Taxonomy: ${params.topicListJson}
Question: ${params.pyqText}
Marks allotted: ${params.marks}
Year: ${params.year}`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: "Perform topic-matching on the exam question.",
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            primary_topic: { type: Type.STRING, description: "The exact name of the matched primary topic from the taxonomy" },
            secondary_topics: {
              type: Type.ARRAY,
              items: { type: Type.STRING },
              description: "Matched secondary topic names"
            },
            estimated_difficulty: { type: Type.STRING, enum: ["easy", "medium", "hard"] },
            reasoning: { type: Type.STRING, description: "One sentence auditing why this match was chosen" }
          },
          required: ["primary_topic", "secondary_topics", "estimated_difficulty", "reasoning"]
        }
      }
    });

    const text = response.text?.trim() || "{}";
    return JSON.parse(text);
  } catch (error) {
    console.error("PYQ Match API error:", error);
    return {
      primary_topic: "",
      secondary_topics: [],
      estimated_difficulty: "medium" as const,
      reasoning: "Failed to map due to parsing exceptions."
    };
  }
}

// C6. Flashcard Generation Prompt Implementation
export async function generateFlashcards(generatedNoteText: string) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return [
      {
        front: "What is the primary objective of Distance Vector Routing?",
        back: "To calculate the shortest network paths periodically by sharing routing metrics with direct neighbors only.",
        source: "CN_Syllabus.pdf"
      }
    ];
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `Generate 4-6 spaced-repetition flashcards from the notes below. Each card:
front = a single focused question, back = a concise answer (under 40 words)
with a citation. Do not create cards for facts not present in the notes.

Notes:
${generatedNoteText}`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: "Generate JSON spaced-repetition flashcards based on the provided study notes text.",
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              front: { type: Type.STRING, description: "Simple, focused question for card front" },
              back: { type: Type.STRING, description: "Concise answers under 40 words with page/source citations" },
              source: { type: Type.STRING, description: "Source document or reference name" }
            },
            required: ["front", "back", "source"]
          }
        }
      }
    });

    const text = response.text?.trim() || "[]";
    return JSON.parse(text);
  } catch (error) {
    console.error("Flashcard generation API error:", error);
    return [];
  }
}

// C7. Guided Doubt-Solver Prompt Implementation
export async function guidedDoubtSolver(retrievedChunks: string, userQuestion: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return `This is a simulated response to: "${userQuestion}". To connect to real data, set your GEMINI_API_KEY.\n\n- Distance Vector Routing works via Bellman-Ford calculations.\n- Link State Routing relies on Dijkstra calculations.\n\nWould you like to review Module 3's topic list? (Socratic check: Can you explain how count-to-infinity is mitigated?)`;
  }

  try {
    const ai = getGeminiClient();
    const systemInstruction = `You are a study assistant answering ONLY from this student's own course
material (retrieved below). If the material doesn't cover the question,
say so plainly and suggest which module might be relevant instead of
guessing. After answering, ask ONE short follow-up question to check the
student actually understood the concept (Socratic check) — skip this if
the question was purely factual (e.g., "what page is X on").

Retrieved context:
${retrievedChunks}`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: userQuestion,
      config: {
        systemInstruction
      }
    });

    return response.text || "I was unable to formulate a response from the context.";
  } catch (error) {
    console.error("Doubt Solver API error:", error);
    return "Error getting response from doubt solver model.";
  }
}

// C8. Post-Generation Confidence Validator Implementation
export async function validateNoteConfidence(generatedNoteText: string, retrievedChunks: string): Promise<string[]> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return []; // No unsupported sentences flagged in simulator
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `Review the generated note below against its cited source chunks. Flag any
sentence that is NOT directly supported by the cited chunk as
"UNSUPPORTED". Output a list of unsupported sentences (empty list if none).
This is a safety check, not a rewrite — do not fix the note yourself.

Generated note:
${generatedNoteText}

Cited chunks:
${retrievedChunks}`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: "Validate note confidence and check for unsupported sentences.",
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            unsupported_sentences: {
              type: Type.ARRAY,
              items: { type: Type.STRING },
              description: "Array of sentences that have zero textual support in the source chunks"
            }
          },
          required: ["unsupported_sentences"]
        }
      }
    });

    const text = response.text?.trim() || "{}";
    const data = JSON.parse(text);
    return data.unsupported_sentences || [];
  } catch (error) {
    console.error("Confidence validator API error:", error);
    return [];
  }
}

// C9. Summarize Note Prompt Implementation
export async function summarizeNote(noteText: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return `- **Core Takeaway**: This is a key takeaway from the note about core principles.
- **Significance**: Exam preparation requires focusing on key highlighted definitions.
- **Application**: Practical questions often require executing specific algorithms outlined in the syllabus.`;
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `You are an expert tutor. Provide 3-4 highly concise bullet points summarizing the 'key takeaways' of the provided study note.
Format the output with clear markdown bullet points. Do not include introductory text like "Sure, here are...", just output the raw bullet points directly. Ensure they are focused on core concepts.`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: `Provide a bulleted 'key takeaway' summary for the following study note:\n\n${noteText}`,
      config: {
        systemInstruction: systemPrompt,
        temperature: 0.3
      }
    });

    return response.text?.trim() || "No summary available.";
  } catch (error) {
    console.error("Summarization API error, falling back to offline content:", error);
    return `- **Core Takeaway**: Summarization failed due to temporary AI service disruption.
- **Offline Mode**: Please verify your network connection to re-attempt active summaries.`;
  }
}

// C10. Categorization Tag Suggestion
export async function suggestTags(noteText: string): Promise<string[]> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    // Return mock tags based on common keywords
    const lower = noteText.toLowerCase();
    const tags: string[] = [];
    if (lower.includes("route") || lower.includes("routing") || lower.includes("distance vector") || lower.includes("link state")) {
      tags.push("Computer Networks", "Routing Protocols");
    }
    if (lower.includes("sql") || lower.includes("join") || lower.includes("relation") || lower.includes("query") || lower.includes("dbms")) {
      tags.push("Database Systems", "SQL Queries");
    }
    if (lower.includes("normal") || lower.includes("3nf") || lower.includes("bcnf") || lower.includes("dependency")) {
      tags.push("Database Normalization", "Relational Theory");
    }
    if (lower.includes("heat") || lower.includes("thermo") || lower.includes("entropy") || lower.includes("laws")) {
      tags.push("Thermodynamics", "Thermal Physics");
    }
    if (lower.includes("sort") || lower.includes("tree") || lower.includes("graph") || lower.includes("binary") || lower.includes("structure")) {
      tags.push("Data Structures", "Algorithms");
    }
    if (tags.length === 0) {
      tags.push("Engineering", "Core Concepts");
    }
    return tags;
  }

  try {
    const ai = getGeminiClient();
    const systemPrompt = `You analyze academic study notes and suggest 2-4 highly precise, standard scientific/technical categorization tags.
Examples of standard tags: 'Thermodynamics', 'Data Structures', 'Algorithms', 'Computer Networks', 'Database Systems', 'Linear Algebra', 'Operating Systems', 'Software Engineering'.
Always suggest professional and specific academic/subject topics based on the actual concepts in the text.
Output ONLY a JSON array of strings, e.g. ["Thermodynamics", "Physical Chemistry"]. No markdown backticks, no preamble.`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: `Suggest 2-4 highly precise academic categorization tags for this study note text:\n\n${noteText}`,
      config: {
        systemInstruction: systemPrompt,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.STRING
          }
        }
      }
    });

    const text = response.text?.trim() || "[]";
    const tags = JSON.parse(text);
    return Array.isArray(tags) ? tags : [];
  } catch (error) {
    console.error("Tag Suggestion API error:", error);
    return ["Engineering"];
  }
}
