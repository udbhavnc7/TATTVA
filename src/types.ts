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
  difficulty_avg: number;
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

export interface ModuleCoverage {
  module_id: string;
  title: string;
  percentage: number;
  topics: Array<{
    id: string;
    name: string;
    status: 'grounded' | 'partial' | 'review' | 'missing';
    notes_count: number;
  }>;
}

export interface CoverageSummary {
  overall_percentage: number;
  grounded_count: number;
  partial_count: number;
  needs_review_count: number;
  missing_count: number;
  total_topics: number;
  modules: ModuleCoverage[];
}
