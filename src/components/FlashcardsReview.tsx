import React, { useState, useEffect } from 'react';
import { Brain, Star, CheckCircle, RefreshCw, HelpCircle, Layers, ArrowRight, FileSpreadsheet } from 'lucide-react';
import { Subject, Flashcard, Topic } from '../types';
import { exportFlashcardsToAnkiCSV } from '../utils/exportManager';

interface FlashcardsReviewProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
}

export default function FlashcardsReview({ subjects, selectedSubject }: FlashcardsReviewProps) {
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeTopicId, setActiveTopicId] = useState<string>('all');
  const [loading, setLoading] = useState(false);

  // Active Review States
  const [reviewQueue, setReviewQueue] = useState<Flashcard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [reviewedCount, setReviewedCount] = useState(0);

  // Stats
  const [showSummary, setShowSummary] = useState(false);

  // Form
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [addingCard, setAddingCard] = useState(false);

  // AI Auto-Generation States
  const [generatingAI, setGeneratingAI] = useState(false);
  const [aiSuccessMessage, setAiSuccessMessage] = useState<string | null>(null);
  const [aiErrorMessage, setAiErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (selectedSubject) {
      fetchFlashcards();
      fetchTopics();
    }
  }, [selectedSubject, activeTopicId]);

  const fetchFlashcards = async () => {
    if (!selectedSubject) return;
    setLoading(true);
    try {
      const topicParam = activeTopicId !== 'all' ? `&topicId=${activeTopicId}` : '';
      const res = await fetch(`/api/flashcards?subjectId=${selectedSubject.id}${topicParam}`);
      const data: Flashcard[] = await res.json();
      setFlashcards(data);
      
      // Filter for due cards: next_review_at is in the past, or repetitions = 0
      const now = new Date();
      const due = data.filter(fc => {
        return new Date(fc.next_review_at) <= now || fc.repetitions === 0;
      });
      setReviewQueue(due);
      setCurrentIndex(0);
      setIsFlipped(false);
      setShowSummary(false);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchTopics = async () => {
    if (!selectedSubject) return;
    try {
      const res = await fetch(`/api/topics`);
      const data = await res.json();
      setTopics(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (activeTopicId === 'all' || !newQuestion || !newAnswer) return;
    setAddingCard(true);
    try {
      const res = await fetch('/api/flashcards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic_id: activeTopicId,
          question: newQuestion,
          answer: newAnswer
        })
      });
      if (res.ok) {
        setNewQuestion('');
        setNewAnswer('');
        fetchFlashcards();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setAddingCard(false);
    }
  };

  const handleAIGenerateCards = async () => {
    if (activeTopicId === 'all') return;
    setGeneratingAI(true);
    setAiSuccessMessage(null);
    setAiErrorMessage(null);
    try {
      const resNotes = await fetch(`/api/notes?topicId=${activeTopicId}`);
      if (!resNotes.ok) {
        throw new Error("Failed to search study notes for this topic.");
      }
      const notesList = await resNotes.json();
      if (!notesList || notesList.length === 0) {
        setAiErrorMessage("No study notes exist for this topic yet! Generate notes in the Notes Engine first.");
        return;
      }
      const noteToUse = notesList.find((n: any) => n.depth === 'comprehensive') || notesList[0];
      if (!noteToUse || !noteToUse.content_md) {
        setAiErrorMessage("Note content is empty. Please regenerate notes.");
        return;
      }

      const resGen = await fetch('/api/flashcards/auto-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topicId: activeTopicId,
          noteText: noteToUse.content_md
        })
      });

      if (!resGen.ok) {
        const errorData = await resGen.json();
        throw new Error(errorData.error || "Failed to auto-generate flashcards.");
      }

      const genData = await resGen.json();
      setAiSuccessMessage(genData.message || "Generated flashcards successfully!");
      fetchFlashcards();
    } catch (err: any) {
      console.error(err);
      setAiErrorMessage(err.message || "Flashcard generation failed.");
    } finally {
      setGeneratingAI(false);
    }
  };

  const handleRateCard = async (rating: number) => {
    if (reviewQueue.length === 0) return;
    const currentCard = reviewQueue[currentIndex];
    
    try {
      const res = await fetch('/api/flashcards/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: currentCard.id,
          rating
        })
      });
      if (res.ok) {
        setReviewedCount(prev => prev + 1);
        setIsFlipped(false);
        setTimeout(() => {
          if (currentIndex + 1 < reviewQueue.length) {
            setCurrentIndex(prev => prev + 1);
          } else {
            setShowSummary(true);
          }
        }, 150);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const getTopicName = (topicId: string) => {
    const t = topics.find(topic => topic.id === topicId);
    return t ? t.name : 'Engineering Core';
  };

  return (
    <div id="flashcards-review" className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      
      {/* 1. Left controls (1/3 space) */}
      <div className="xl:col-span-1 space-y-6">
        
        {/* Topic Filter */}
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-3">
          <h3 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">Select Deck Topic</h3>
          <select
            value={activeTopicId}
            onChange={(e) => setActiveTopicId(e.target.value)}
            className="w-full bg-slate-950 text-white border border-slate-800 rounded-lg p-2.5 text-xs font-mono focus:border-accent-blue focus:outline-none cursor-pointer"
          >
            <option value="all">All Topics (Combined Decks)</option>
            {topics.map(t => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>

          {/* Quick status counts */}
          <div className="grid grid-cols-2 gap-2 pt-2">
            <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800 text-center">
              <span className="block text-xl font-bold font-mono text-accent-blue">{flashcards.length}</span>
              <span className="text-[10px] text-slate-400 font-mono">Total Cards</span>
            </div>
            <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800 text-center">
              <span className="block text-xl font-bold font-mono text-accent-teal">{reviewQueue.length}</span>
              <span className="text-[10px] text-slate-400 font-mono">Due for Review</span>
            </div>
          </div>

          {/* Export Deck to Anki CSV */}
          {flashcards.length > 0 && (
            <button
              onClick={() => {
                const deckName = activeTopicId === 'all' 
                  ? (selectedSubject?.name || "Subject_Combined") 
                  : getTopicName(activeTopicId);
                exportFlashcardsToAnkiCSV(flashcards, deckName);
              }}
              className="w-full mt-2 py-2.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white rounded-xl text-xs font-mono font-bold transition-all flex items-center justify-center gap-1.5 shadow-md active:scale-95"
              title="Download flashcards in Anki CSV format"
            >
              <FileSpreadsheet className="h-3.5 w-3.5 text-accent-teal" />
              <span>Export to Anki</span>
            </button>
          )}
        </div>

        {/* AI Flashcard Generator Card */}
        {activeTopicId !== 'all' && (
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
            <div className="flex items-center gap-2 text-white">
              <Brain className="h-4 w-4 text-accent-teal" />
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider">AI Auto-Generate Deck</h3>
            </div>
            <p className="text-[11px] text-slate-400 font-sans leading-relaxed">
              Instantly create a flashcard deck calibrated with spaced-repetition tags based on your generated study notes for this topic.
            </p>
            
            <button
              onClick={handleAIGenerateCards}
              disabled={generatingAI}
              className="w-full py-2.5 bg-accent-teal hover:bg-accent-teal/80 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 rounded-xl text-xs font-mono font-bold transition-all shadow flex items-center justify-center gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${generatingAI ? 'animate-spin' : ''}`} />
              {generatingAI ? 'Analyzing Notes...' : 'AI Auto-Generate Deck'}
            </button>

            {aiSuccessMessage && (
              <p className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 p-2 rounded-lg border border-emerald-500/20">
                {aiSuccessMessage}
              </p>
            )}
            {aiErrorMessage && (
              <p className="text-[10px] font-mono text-amber-500 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                {aiErrorMessage}
              </p>
            )}
          </div>
        )}

        {/* Custom Flashcard Creator (only active if a specific topic is selected) */}
        {activeTopicId !== 'all' && (
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider pb-2 border-b border-slate-800">Create Custom Card</h3>
            
            <form onSubmit={handleAddCard} className="space-y-4">
              <div>
                <label className="block text-[10px] font-mono text-slate-400 mb-1">Front Question</label>
                <textarea
                  placeholder="e.g., What is sliding window utilization formula?"
                  value={newQuestion}
                  onChange={(e) => setNewQuestion(e.target.value)}
                  rows={2}
                  className="w-full bg-slate-950 text-slate-200 border border-slate-800 rounded-lg p-2 text-xs focus:border-accent-blue focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-mono text-slate-400 mb-1">Back Answer</label>
                <textarea
                  placeholder="e.g., U = N * (1 - p) / (N * (1 - p) + 2a)"
                  value={newAnswer}
                  onChange={(e) => setNewAnswer(e.target.value)}
                  rows={3}
                  className="w-full bg-slate-950 text-slate-200 border border-slate-800 rounded-lg p-2 text-xs focus:border-accent-blue focus:outline-none"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={addingCard}
                className="w-full py-2 bg-slate-950 hover:bg-slate-800 disabled:bg-slate-900 border border-slate-800 text-white rounded-lg text-xs font-mono font-bold transition-all"
              >
                {addingCard ? 'Creating...' : '+ Create Flashcard'}
              </button>
            </form>
          </div>
        )}

      </div>

      {/* 2. Right Workspace Display (2/3 space) */}
      <div className="xl:col-span-2 space-y-6">
        
        {/* Active Spaced-Repetition Review Arena */}
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl min-h-[450px] flex flex-col justify-between">
          
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-mono text-xs text-slate-400">
            <span>SPACED REPETITION STUDY CENTER</span>
            <span>Card {reviewQueue.length > 0 && !showSummary ? `${currentIndex + 1} of ${reviewQueue.length}` : '0 of 0'}</span>
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-2">
              <RefreshCw className="h-6 w-6 text-slate-400 animate-spin" />
              <p className="text-xs text-slate-500 font-mono">Calibrating interval records...</p>
            </div>
          ) : showSummary ? (
            /* Summary Completed Display */
            <div className="flex flex-col items-center justify-center text-center space-y-4 py-12">
              <div className="p-4 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-2xl shadow">
                <CheckCircle className="h-8 w-8" />
              </div>
              <div className="space-y-1.5 max-w-sm">
                <h3 className="text-base font-mono font-bold text-slate-200">Session Review Completed!</h3>
                <p className="text-xs text-slate-400">
                  You reviewed {reviewedCount} flashcards in this deck. The SuperMemo SM-2 interval logs have calculated next review triggers for optimal brain retention.
                </p>
              </div>
              <button 
                onClick={fetchFlashcards}
                className="px-5 py-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-mono text-slate-200 transition-colors"
              >
                Review Decks Again
              </button>
            </div>
          ) : reviewQueue.length === 0 ? (
            /* Empty state (No due cards) */
            <div className="flex flex-col items-center justify-center text-center space-y-4 py-16">
              <div className="p-4 bg-slate-950 text-slate-400 border border-slate-800 rounded-2xl shadow">
                <Brain className="h-8 w-8 text-accent-teal" />
              </div>
              <div className="space-y-1 max-w-xs">
                <h3 className="text-xs font-mono font-bold text-slate-200">Decks Are Clear!</h3>
                <p className="text-[11px] text-slate-400">
                  There are no flashcards due for spaced repetition right now. Browse your study notes to auto-generate card items or check back later!
                </p>
              </div>
            </div>
          ) : (
            /* ACTIVE CARD IN REVIEW WITH 3D FLIP */
            <div className="my-6 flex flex-col items-center justify-center flex-1">
              
              {/* Flip Card Wrapper */}
              <div 
                onClick={() => setIsFlipped(!isFlipped)}
                className="w-full max-w-lg h-60 cursor-pointer select-none [perspective:1000px]"
              >
                <div className={`relative w-full h-full transition-transform duration-500 [transform-style:preserve-3d] ${isFlipped ? '[transform:rotateY(180deg)]' : ''}`}>
                  
                  {/* CARD FRONT (Question) */}
                  <div className="absolute inset-0 w-full h-full bg-slate-950 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between [backface-visibility:hidden]">
                    <div className="space-y-2">
                      <span className="text-[9px] font-mono text-accent-blue uppercase font-bold tracking-widest bg-accent-blue/10 px-2 py-0.5 rounded">FRONT (QUESTION)</span>
                      <p className="text-slate-100 text-sm font-semibold leading-relaxed pt-2">
                        {reviewQueue[currentIndex].question}
                      </p>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 flex justify-between items-center border-t border-slate-800/60 pt-2.5">
                      <span>Topic: {getTopicName(reviewQueue[currentIndex].topic_id)}</span>
                      <span className="text-slate-400 font-bold">CLICK TO FLIP ANATOMY</span>
                    </div>
                  </div>

                  {/* CARD BACK (Answer) */}
                  <div className="absolute inset-0 w-full h-full bg-slate-950 border border-accent-teal/40 rounded-2xl p-6 flex flex-col justify-between [backface-visibility:hidden] [transform:rotateY(180deg)]">
                    <div className="space-y-2">
                      <span className="text-[9px] font-mono text-accent-teal uppercase font-bold tracking-widest bg-accent-teal/10 px-2 py-0.5 rounded">BACK (VERIFIED ANSWER)</span>
                      <p className="text-slate-200 text-xs font-mono leading-relaxed pt-2 max-h-32 overflow-y-auto pr-1">
                        {reviewQueue[currentIndex].answer}
                      </p>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 flex justify-between items-center border-t border-slate-800/60 pt-2.5">
                      <span className="text-emerald-400">Recall Score Rating: 1 to 5</span>
                      <span className="text-slate-400 font-bold">CLICK TO FLIP QUESTIONS</span>
                    </div>
                  </div>

                </div>
              </div>

              {/* Recall SM-2 Rating Controls */}
              <div className="w-full max-w-lg mt-6 space-y-4">
                {isFlipped ? (
                  <div className="space-y-3">
                    <p className="text-center text-[10px] font-mono text-slate-400">Rate your mental recall capability for interval adjustment:</p>
                    <div className="grid grid-cols-5 gap-1.5 text-center">
                      {[
                        { val: 1, label: 'Forgot', style: 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30' },
                        { val: 2, label: 'Struggled', style: 'bg-orange-500/10 hover:bg-orange-500/20 text-orange-400 border border-orange-500/30' },
                        { val: 3, label: 'Effort', style: 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30' },
                        { val: 4, label: 'Correct', style: 'bg-teal-500/10 hover:bg-teal-500/20 text-teal-300 border border-teal-500/30' },
                        { val: 5, label: 'Perfect', style: 'bg-emerald-500/15 hover:bg-emerald-500/35 text-emerald-400 border border-emerald-500/30' }
                      ].map(r => (
                        <button
                          key={r.val}
                          onClick={() => handleRateCard(r.val)}
                          className={`py-2 rounded-xl text-xs font-mono font-bold transition-all flex flex-col items-center justify-center gap-1 leading-none ${r.style}`}
                        >
                          <span className="text-lg font-bold">{r.val}</span>
                          <span className="text-[8px] font-normal uppercase tracking-wider">{r.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setIsFlipped(true)}
                    className="w-full py-3 bg-accent-blue hover:bg-accent-blue/80 text-white rounded-xl text-xs font-mono font-bold transition-all flex items-center justify-center gap-2 shadow-lg"
                  >
                    <HelpCircle className="h-4 w-4" />
                    Reveal Spaced repetition Answer
                  </button>
                )}
              </div>

            </div>
          )}

          {/* SM-2 calibration instructions */}
          <div className="text-[10px] font-mono text-slate-500 border-t border-slate-800/60 pt-3 leading-relaxed">
            <strong>Calibrated with SuperMemo-2 Spaced scheduling:</strong> Scores &lt; 3 trigger same-day reviews. Perfect recall scores (5) adjust multiplier weights (ease_factor) to trigger cards weeks in advance, optimizing memory traces.
          </div>

        </div>

      </div>

    </div>
  );
}
