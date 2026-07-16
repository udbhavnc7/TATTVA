import fs from 'fs';
import path from 'path';

// TS Interfaces matching Postgres Spec in Part B
export interface Subject {
  id: string;
  name: string;
  code: string;
}

export interface Module {
  id: string;
  subject_id: string;
  number: number;
  title: string;
}

export interface Topic {
  id: string;
  module_id: string;
  name: string;
  content_hash: string;
  version: number;
  last_updated: string;
}

export interface Document {
  id: string;
  subject_id: string;
  source_type: 'upload' | 'drive' | 'classroom';
  source_id?: string;
  filename: string;
  uploaded_at: string;
  content_hash: string;
}

export interface Chunk {
  id: string;
  topic_id: string;
  document_id: string;
  page_number: number;
  text: string;
  embedding: number[]; // 1536 float array
}

export interface Note {
  id: string;
  topic_id: string;
  version: number;
  depth: '2mark' | '6mark' | '10mark';
  content_md: string;
  confidence: 'grounded' | 'partial' | 'needs_review';
  generated_at: string;
  summary_md?: string;
  tags?: string[];
}

export interface PYQ {
  id: string;
  subject_id: string;
  year: number;
  question_text: string;
  topic_id: string;
  marks: number;
  difficulty: 'easy' | 'medium' | 'hard';
}

export interface TopicImportance {
  topic_id: string;
  frequency_count: number;
  difficulty_avg: number; // 1 = easy, 2 = medium, 3 = hard
  last_recalculated: string;
}

export interface Flashcard {
  id: string;
  topic_id: string;
  question: string;
  answer: string;
  ease_factor: number;
  next_review_at: string;
  interval_days: number;
  repetitions: number;
}

export interface ClassroomMapping {
  id: string;
  course_id: string;
  course_name: string;
  subject_id: string;
  folder_id?: string;
  folder_name?: string;
}

// Full DB representation
export interface TattvaDB {
  subjects: Subject[];
  modules: Module[];
  topics: Topic[];
  documents: Document[];
  chunks: Chunk[];
  notes: Note[];
  pyqs: PYQ[];
  topic_importance: TopicImportance[];
  flashcards: Flashcard[];
  classroom_mappings?: ClassroomMapping[];
}

const DB_DIR = path.resolve(process.cwd(), 'data');
const DB_FILE = path.join(DB_DIR, 'db.json');

// Helper to calculate cosine similarity
export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) return 0;
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

// Initial seed data for CS / Engineering student
const initialDB: TattvaDB = {
  subjects: [
    { id: 'sub-cn', name: 'Computer Networks', code: 'CS301' },
    { id: 'sub-db', name: 'Database Management Systems', code: 'CS302' },
  ],
  modules: [
    // Computer Networks Modules
    { id: 'mod-cn-1', subject_id: 'sub-cn', number: 1, title: 'Introduction and Physical Layer' },
    { id: 'mod-cn-2', subject_id: 'sub-cn', number: 2, title: 'Data Link Layer and MAC Sublayer' },
    { id: 'mod-cn-3', subject_id: 'sub-cn', number: 3, title: 'Network Layer Routing and IP' },
    
    // DBMS Modules
    { id: 'mod-db-1', subject_id: 'sub-db', number: 1, title: 'Introduction and E-R Model' },
    { id: 'mod-db-2', subject_id: 'sub-db', number: 2, title: 'Relational Model and SQL' },
    { id: 'mod-db-3', subject_id: 'sub-db', number: 3, title: 'Normalization and Transaction Control' },
  ],
  topics: [
    // CN Topics
    { id: 'top-cn-transmission', module_id: 'mod-cn-1', name: 'Transmission Media & Nyquist Theorem', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
    { id: 'top-cn-framing', module_id: 'mod-cn-2', name: 'Framing, Error Detection & Correction (CRC)', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
    { id: 'top-cn-routing', module_id: 'mod-cn-3', name: 'Link State Routing vs Distance Vector Routing', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
    
    // DBMS Topics
    { id: 'top-db-er', module_id: 'mod-db-1', name: 'ER Diagrams and Mapping to Tables', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
    { id: 'top-db-sql', module_id: 'mod-db-2', name: 'SQL Joins, Subqueries and Relational Algebra', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
    { id: 'top-db-normal', module_id: 'mod-db-3', name: 'Functional Dependencies, 3NF and BCNF', content_hash: 'seed', version: 1, last_updated: new Date().toISOString() },
  ],
  documents: [],
  chunks: [],
  notes: [
    {
      id: 'note-1',
      topic_id: 'top-cn-routing',
      version: 1,
      depth: '2mark',
      content_md: `### Concept of Routing Algorithms\n\nRouting algorithms determine the optimal path for transferring packet data from a source router to a destination router across a network. Standard models include **Distance Vector Routing** (based on localized Bellman-Ford node updates) and **Link State Routing** (where each node maintains complete, global topological maps via link-state packets).\n\n*(Source: CN_Syllabus_Guide.pdf, p.14)*`,
      confidence: 'grounded',
      generated_at: new Date().toISOString()
    },
    {
      id: 'note-2',
      topic_id: 'top-cn-routing',
      version: 1,
      depth: '6mark',
      content_md: `### Link State vs Distance Vector Routing\n\nThere are two primary algorithms used for path selection in the Network Layer:\n\n1. **Distance Vector Routing (DVR)**:\n   - Each router maintains a table (Vector) of minimum distances to all known destinations.\n   - Routers periodically exchange routing tables with direct neighbors only.\n   - Suffers from the **Count-to-Infinity problem** during link failures.\n   \n2. **Link State Routing (LSR)**:\n   - Each router builds and floods Link State Packets (LSPs) across the network.\n   - Every node independently calculates the shortest path tree using **Dijkstra\'s Algorithm**.\n   - High memory requirements but resolves topology changes instantly with zero convergence loops.\n\n*(Source: CN_Syllabus_Guide.pdf, p.14)*`,
      confidence: 'grounded',
      generated_at: new Date().toISOString()
    }
  ],
  pyqs: [
    // Computer Networks Past Questions
    { id: 'pyq-1', subject_id: 'sub-cn', year: 2024, question_text: 'Differentiate between Distance Vector Routing and Link State Routing. Explain Dijkstra\'s path calculations.', topic_id: 'top-cn-routing', marks: 10, difficulty: 'hard' },
    { id: 'pyq-2', subject_id: 'sub-cn', year: 2023, question_text: 'What is the count-to-infinity problem in routing? How does split-horizon mitigate it?', topic_id: 'top-cn-routing', marks: 6, difficulty: 'medium' },
    { id: 'pyq-3', subject_id: 'sub-cn', year: 2024, question_text: 'Calculate the CRC checksum for a bit frame 1101011011 using polynomial x^4 + x + 1.', topic_id: 'top-cn-framing', marks: 10, difficulty: 'hard' },
    { id: 'pyq-4', subject_id: 'sub-cn', year: 2022, question_text: 'Explain the difference between guided and unguided transmission media.', topic_id: 'top-cn-transmission', marks: 6, difficulty: 'easy' },
    { id: 'pyq-5', subject_id: 'sub-cn', year: 2021, question_text: 'What is the maximum channel capacity of a noiseless 4kHz channel according to Nyquist?', topic_id: 'top-cn-transmission', marks: 2, difficulty: 'easy' },

    // DBMS Past Questions
    { id: 'pyq-6', subject_id: 'sub-db', year: 2023, question_text: 'Explain 3NF and BCNF with a suitable example. Why is BCNF stricter than 3NF?', topic_id: 'top-db-normal', marks: 10, difficulty: 'hard' },
    { id: 'pyq-7', subject_id: 'sub-db', year: 2024, question_text: 'Write SQL queries to join student and course tables and fetch department averages.', topic_id: 'top-db-sql', marks: 6, difficulty: 'medium' },
    { id: 'pyq-8', subject_id: 'sub-db', year: 2024, question_text: 'Map a Weak Entity set with discriminator attributes to database tables.', topic_id: 'top-db-er', marks: 6, difficulty: 'medium' },
    { id: 'pyq-9', subject_id: 'sub-db', year: 2022, question_text: 'Define primary key, candidate key, and foreign key.', topic_id: 'top-db-er', marks: 2, difficulty: 'easy' }
  ],
  topic_importance: [
    { topic_id: 'top-cn-routing', frequency_count: 2, difficulty_avg: 2.5, last_recalculated: new Date().toISOString() },
    { topic_id: 'top-cn-framing', frequency_count: 1, difficulty_avg: 3.0, last_recalculated: new Date().toISOString() },
    { topic_id: 'top-cn-transmission', frequency_count: 2, difficulty_avg: 1.0, last_recalculated: new Date().toISOString() },
    { topic_id: 'top-db-normal', frequency_count: 1, difficulty_avg: 3.0, last_recalculated: new Date().toISOString() },
    { topic_id: 'top-db-sql', frequency_count: 1, difficulty_avg: 2.0, last_recalculated: new Date().toISOString() },
    { topic_id: 'top-db-er', frequency_count: 2, difficulty_avg: 1.5, last_recalculated: new Date().toISOString() }
  ],
  flashcards: [
    {
      id: 'fc-1',
      topic_id: 'top-cn-routing',
      question: 'What algorithm is used in Link State Routing to calculate the shortest path?',
      answer: 'Dijkstra\'s Algorithm, which creates a shortest path tree by scanning global topological data flooded via Link State Packets.',
      ease_factor: 2.5,
      next_review_at: new Date().toISOString(),
      interval_days: 1,
      repetitions: 0
    },
    {
      id: 'fc-2',
      topic_id: 'top-cn-routing',
      question: 'What major convergence routing error occurs in Distance Vector Routing?',
      answer: 'The Count-to-Infinity problem, where routers repeatedly increments cost hops in a loop when a link goes completely down.',
      ease_factor: 2.5,
      next_review_at: new Date().toISOString(),
      interval_days: 1,
      repetitions: 0
    },
    {
      id: 'fc-3',
      topic_id: 'top-db-normal',
      question: 'What makes BCNF stricter than 3NF?',
      answer: 'BCNF requires that for every functional dependency X -> Y, X must be a super key. 3NF relaxes this by allowing Y to be a prime attribute.',
      ease_factor: 2.5,
      next_review_at: new Date().toISOString(),
      interval_days: 1,
      repetitions: 0
    }
  ],
  classroom_mappings: []
};

class DatabaseManager {
  private data: TattvaDB = { ...initialDB };

  constructor() {
    this.load();
  }

  // Load from file if exists, or write initial seed
  private load() {
    try {
      if (!fs.existsSync(DB_DIR)) {
        fs.mkdirSync(DB_DIR, { recursive: true });
      }
      if (fs.existsSync(DB_FILE)) {
        const fileContent = fs.readFileSync(DB_FILE, 'utf-8');
        this.data = JSON.parse(fileContent);
        if (!this.data.classroom_mappings) {
          this.data.classroom_mappings = [];
        }
      } else {
        this.save();
      }
    } catch (e) {
      console.error('Error initializing database file, using in-memory backup:', e);
    }
  }

  // Write current data to file
  public save() {
    try {
      if (!fs.existsSync(DB_DIR)) {
        fs.mkdirSync(DB_DIR, { recursive: true });
      }
      fs.writeFileSync(DB_FILE, JSON.stringify(this.data, null, 2), 'utf-8');
    } catch (e) {
      console.error('Error saving database to file:', e);
    }
  }

  // GET ALL DATA
  public getDB(): TattvaDB {
    return this.data;
  }

  // CORE SUBJECTS
  public getSubjects(): Subject[] {
    return this.data.subjects;
  }

  public addSubject(name: string, code: string): Subject {
    const id = `sub-${Date.now()}`;
    const newSubject: Subject = { id, name, code };
    this.data.subjects.push(newSubject);
    this.save();
    return newSubject;
  }

  // CORE MODULES
  public getModules(subjectId?: string): Module[] {
    if (subjectId) {
      return this.data.modules.filter(m => m.subject_id === subjectId);
    }
    return this.data.modules;
  }

  public addModule(subject_id: string, number: number, title: string): Module {
    const id = `mod-${Date.now()}`;
    const newModule: Module = { id, subject_id, number, title };
    this.data.modules.push(newModule);
    // Sort modules by number
    this.data.modules.sort((a, b) => a.number - b.number);
    this.save();
    return newModule;
  }

  // CORE TOPICS
  public getTopics(moduleId?: string): Topic[] {
    if (moduleId) {
      return this.data.topics.filter(t => t.module_id === moduleId);
    }
    return this.data.topics;
  }

  public getTopicById(topicId: string): Topic | undefined {
    return this.data.topics.find(t => t.id === topicId);
  }

  public addTopic(module_id: string, name: string, content_hash: string = ''): Topic {
    const id = `top-${Date.now()}`;
    const newTopic: Topic = {
      id,
      module_id,
      name,
      content_hash,
      version: 1,
      last_updated: new Date().toISOString()
    };
    this.data.topics.push(newTopic);
    this.save();
    return newTopic;
  }

  public updateTopicHash(topicId: string, content_hash: string): Topic | undefined {
    const topic = this.data.topics.find(t => t.id === topicId);
    if (topic) {
      if (topic.content_hash !== content_hash) {
        topic.content_hash = content_hash;
        topic.version += 1;
        topic.last_updated = new Date().toISOString();
        this.save();
      }
      return topic;
    }
    return undefined;
  }

  // CORE DOCUMENTS
  public getDocuments(subjectId?: string): Document[] {
    if (subjectId) {
      return this.data.documents.filter(d => d.subject_id === subjectId);
    }
    return this.data.documents;
  }

  public addDocument(subject_id: string, filename: string, content_hash: string, source_type: 'upload' | 'drive' | 'classroom', source_id?: string): Document {
    const id = `doc-${Date.now()}`;
    const newDoc: Document = {
      id,
      subject_id,
      filename,
      source_type,
      source_id,
      uploaded_at: new Date().toISOString(),
      content_hash
    };
    this.data.documents.push(newDoc);
    this.save();
    return newDoc;
  }

  // CORE CHUNKS
  public getChunks(topicId?: string): Chunk[] {
    if (topicId) {
      return this.data.chunks.filter(c => c.topic_id === topicId);
    }
    return this.data.chunks;
  }

  public addChunk(topic_id: string, document_id: string, page_number: number, text: string, embedding: number[]): Chunk {
    const id = `chk-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const newChunk: Chunk = {
      id,
      topic_id,
      document_id,
      page_number,
      text,
      embedding
    };
    this.data.chunks.push(newChunk);
    this.save();
    return newChunk;
  }

  public clearChunksForTopic(topicId: string) {
    this.data.chunks = this.data.chunks.filter(c => c.topic_id !== topicId);
    this.save();
  }

  // CORE NOTES
  public getNotes(topicId?: string): Note[] {
    if (topicId) {
      return this.data.notes.filter(n => n.topic_id === topicId);
    }
    return this.data.notes;
  }

  public getNoteByTopicAndDepth(topicId: string, depth: '2mark' | '6mark' | '10mark'): Note | undefined {
    return this.data.notes.find(n => n.topic_id === topicId && n.depth === depth);
  }

  public upsertNote(
    topic_id: string,
    depth: '2mark' | '6mark' | '10mark',
    content_md: string,
    confidence: 'grounded' | 'partial' | 'needs_review',
    summary_md?: string,
    tags?: string[]
  ): Note {
    const existing = this.data.notes.find(n => n.topic_id === topic_id && n.depth === depth);
    if (existing) {
      existing.content_md = content_md;
      existing.confidence = confidence;
      existing.version += 1;
      existing.generated_at = new Date().toISOString();
      if (summary_md !== undefined) {
        existing.summary_md = summary_md;
      }
      if (tags !== undefined) {
        existing.tags = tags;
      }
      this.save();
      return existing;
    } else {
      const id = `note-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
      const newNote: Note = {
        id,
        topic_id,
        depth,
        content_md,
        confidence,
        version: 1,
        generated_at: new Date().toISOString(),
        summary_md,
        tags
      };
      this.data.notes.push(newNote);
      this.save();
      return newNote;
    }
  }

  // PYQs
  public getPYQs(subjectId?: string): PYQ[] {
    if (subjectId) {
      return this.data.pyqs.filter(p => p.subject_id === subjectId);
    }
    return this.data.pyqs;
  }

  public getPYQsByTopic(topicId: string): PYQ[] {
    return this.data.pyqs.filter(p => p.topic_id === topicId);
  }

  public addPYQ(subject_id: string, year: number, question_text: string, topic_id: string, marks: number, difficulty: 'easy' | 'medium' | 'hard'): PYQ {
    const id = `pyq-${Date.now()}`;
    const newPYQ: PYQ = {
      id,
      subject_id,
      year,
      question_text,
      topic_id,
      marks,
      difficulty
    };
    this.data.pyqs.push(newPYQ);
    this.recalculateTopicImportance(topic_id);
    this.save();
    return newPYQ;
  }

  // TOPIC IMPORTANCE
  public getTopicImportance(topicId?: string): TopicImportance[] {
    if (topicId) {
      return this.data.topic_importance.filter(ti => ti.topic_id === topicId);
    }
    return this.data.topic_importance;
  }

  public recalculateTopicImportance(topicId: string) {
    const topicPYQs = this.data.pyqs.filter(p => p.topic_id === topicId);
    const count = topicPYQs.length;
    if (count === 0) {
      this.data.topic_importance = this.data.topic_importance.filter(ti => ti.topic_id !== topicId);
      this.save();
      return;
    }

    const diffMap = { easy: 1, medium: 2, hard: 3 };
    const totalDiff = topicPYQs.reduce((sum, p) => sum + diffMap[p.difficulty], 0);
    const avgDiff = totalDiff / count;

    const existing = this.data.topic_importance.find(ti => ti.topic_id === topicId);
    if (existing) {
      existing.frequency_count = count;
      existing.difficulty_avg = avgDiff;
      existing.last_recalculated = new Date().toISOString();
    } else {
      this.data.topic_importance.push({
        topic_id: topicId,
        frequency_count: count,
        difficulty_avg: avgDiff,
        last_recalculated: new Date().toISOString()
      });
    }
    this.save();
  }

  // FLASHCARDS
  public getFlashcards(topicId?: string): Flashcard[] {
    if (topicId) {
      return this.data.flashcards.filter(f => f.topic_id === topicId);
    }
    return this.data.flashcards;
  }

  public addFlashcard(topic_id: string, question: string, answer: string): Flashcard {
    const id = `fc-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const newCard: Flashcard = {
      id,
      topic_id,
      question,
      answer,
      ease_factor: 2.5,
      next_review_at: new Date().toISOString(),
      interval_days: 0,
      repetitions: 0
    };
    this.data.flashcards.push(newCard);
    this.save();
    return newCard;
  }

  public reviewFlashcard(id: string, rating: number): Flashcard | undefined {
    const card = this.data.flashcards.find(f => f.id === id);
    if (!card) return undefined;

    // Standard SuperMemo-2 Spaced Repetition logic (0 to 5 rating)
    // 0 = blackout, 1 = wrong, 2 = correct with extreme difficulty,
    // 3 = correct with significant effort, 4 = correct with simple review, 5 = perfect recall.
    if (rating >= 3) {
      if (card.repetitions === 0) {
        card.interval_days = 1;
      } else if (card.repetitions === 1) {
        card.interval_days = 6;
      } else {
        card.interval_days = Math.round(card.interval_days * card.ease_factor);
      }
      card.repetitions += 1;
    } else {
      card.repetitions = 0;
      card.interval_days = 1;
    }

    // Update ease factor (min 1.3)
    card.ease_factor = card.ease_factor + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02));
    if (card.ease_factor < 1.3) card.ease_factor = 1.3;

    // Calculate next review timestamp
    const nextDate = new Date();
    nextDate.setDate(nextDate.getDate() + card.interval_days);
    card.next_review_at = nextDate.toISOString();

    this.save();
    return card;
  }

  // Vector Search (RAG)
  public vectorSearch(subjectId: string, queryEmbedding: number[], limit: number = 5): Array<{ chunk: Chunk, docName: string, similarity: number }> {
    const docIds = this.data.documents.filter(d => d.subject_id === subjectId).map(d => d.id);
    
    // Find matching chunks
    const matches: Array<{ chunk: Chunk, docName: string, similarity: number }> = [];
    
    for (const chunk of this.data.chunks) {
      // Must belong to the documents in this subject
      if (docIds.includes(chunk.document_id)) {
        const doc = this.data.documents.find(d => d.id === chunk.document_id);
        const sim = cosineSimilarity(queryEmbedding, chunk.embedding);
        matches.push({
          chunk,
          docName: doc ? doc.filename : 'Document',
          similarity: sim
        });
      }
    }

    // Sort descending by similarity
    matches.sort((a, b) => b.similarity - a.similarity);
    return matches.slice(0, limit);
  }

  // CLASSROOM MAPPINGS
  public getClassroomMappings(): ClassroomMapping[] {
    return this.data.classroom_mappings || [];
  }

  public addClassroomMapping(course_id: string, course_name: string, subject_id: string, folder_id?: string, folder_name?: string): ClassroomMapping {
    const id = `map-${Date.now()}`;
    if (!this.data.classroom_mappings) {
      this.data.classroom_mappings = [];
    }
    // Remove any existing mapping for this exact course/subject combination to prevent duplicates
    this.data.classroom_mappings = this.data.classroom_mappings.filter(
      m => !(m.course_id === course_id && m.subject_id === subject_id)
    );
    const newMapping: ClassroomMapping = {
      id,
      course_id,
      course_name,
      subject_id,
      folder_id,
      folder_name
    };
    this.data.classroom_mappings.push(newMapping);
    this.save();
    return newMapping;
  }

  public deleteClassroomMapping(id: string): boolean {
    if (!this.data.classroom_mappings) return false;
    const initialLength = this.data.classroom_mappings.length;
    this.data.classroom_mappings = this.data.classroom_mappings.filter(m => m.id !== id);
    const deleted = this.data.classroom_mappings.length < initialLength;
    if (deleted) {
      this.save();
    }
    return deleted;
  }
}

export const db = new DatabaseManager();
