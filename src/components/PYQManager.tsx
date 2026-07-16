import React, { useState, useEffect } from 'react';
import { 
  FileText, Plus, RefreshCw, Award, Filter, Play, CheckCircle2, 
  HelpCircle, Printer, Sparkles, Brain, GraduationCap 
} from 'lucide-react';
import { Subject, PYQ, Topic, TopicImportance } from '../types';

interface PYQManagerProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
}

interface MockPaper {
  assembled_marks: number;
  target_marks: number;
  questions: PYQ[];
}

export default function PYQManager({ subjects, selectedSubject }: PYQManagerProps) {
  const [pyqs, setPyqs] = useState<PYQ[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [importance, setImportance] = useState<TopicImportance[]>([]);
  const [loading, setLoading] = useState(false);

  // Form states
  const [year, setYear] = useState(2025);
  const [questionText, setQuestionText] = useState('');
  const [marks, setMarks] = useState(10);
  const [adding, setAdding] = useState(false);

  // Mock paper states
  const [assemblerSubjectId, setAssemblerSubjectId] = useState<string>('');
  const [modules, setModules] = useState<any[]>([]);
  const [mockMarks, setMockMarks] = useState(50);
  const [mockPaper, setMockPaper] = useState<MockPaper | null>(null);
  const [assembling, setAssembling] = useState(false);

  // Sync assemblerSubjectId with selectedSubject from parent if provided
  useEffect(() => {
    if (selectedSubject) {
      setAssemblerSubjectId(selectedSubject.id);
    } else if (subjects.length > 0 && !assemblerSubjectId) {
      setAssemblerSubjectId(subjects[0].id);
    }
  }, [selectedSubject, subjects]);

  // Fetch data specifically for the selected assemblerSubjectId
  useEffect(() => {
    if (assemblerSubjectId) {
      fetchPYQs(assemblerSubjectId);
      fetchModules(assemblerSubjectId);
      fetchImportance();
      fetchTopics();
      setMockPaper(null); // Clear previous assembled paper when subject changes
    }
  }, [assemblerSubjectId]);

  const fetchPYQs = async (subId: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/pyqs?subjectId=${subId}`);
      const data = await res.json();
      setPyqs(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchModules = async (subId: string) => {
    try {
      const res = await fetch(`/api/modules?subjectId=${subId}`);
      const data = await res.json();
      setModules(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchTopics = async () => {
    try {
      const res = await fetch(`/api/topics`);
      const data = await res.json();
      setTopics(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchImportance = async () => {
    try {
      const res = await fetch('/api/importance');
      const data = await res.json();
      setImportance(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddPYQ = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assemblerSubjectId || !questionText) return;
    setAdding(true);
    try {
      const res = await fetch('/api/pyqs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: assemblerSubjectId,
          year,
          question_text: questionText,
          marks
        })
      });
      if (res.ok) {
        setQuestionText('');
        fetchPYQs(assemblerSubjectId);
        fetchImportance();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setAdding(false);
    }
  };

  const handleAssembleMock = async () => {
    if (!assemblerSubjectId) return;
    setAssembling(true);
    try {
      const res = await fetch('/api/mock-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subjectId: assemblerSubjectId,
          totalMarks: mockMarks
        })
      });
      if (res.ok) {
        const data = await res.json();
        setMockPaper(data);
      } else {
        alert(await res.text());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setAssembling(false);
    }
  };

  // Helper to map topic_id to name
  const getTopicName = (topicId: string) => {
    const t = topics.find(topic => topic.id === topicId);
    return t ? t.name : 'General Uncategorized Concept';
  };

  // print mock paper
  const printPaper = () => {
    window.print();
  };

  // Filter importance to include only topics belonging to this active subject
  const filteredImportance = importance.filter(imp => {
    const topic = topics.find(t => t.id === imp.topic_id);
    if (!topic) return false;
    if (modules.length === 0) return true;
    return modules.some(m => m.id === topic.module_id);
  });

  const currentAssemblerSubject = subjects.find(s => s.id === assemblerSubjectId) || selectedSubject;

  return (
    <div id="pyq-manager" className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      
      {/* Column 1: Topic Importance & Questions Add Form (1/3 space) */}
      <div className="xl:col-span-1 space-y-6">
        
        {/* PYQ Manual Upload Form */}
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
          <div className="flex items-center gap-2 text-white">
            <Plus className="h-4 w-4 text-accent-blue" />
            <h3 className="text-sm font-mono font-bold uppercase tracking-wider">
              Ingest Past Question {currentAssemblerSubject ? `(${currentAssemblerSubject.code})` : ''}
            </h3>
          </div>

          <form onSubmit={handleAddPYQ} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-mono text-slate-400 mb-1">Exam Year</label>
                <select 
                  value={year} 
                  onChange={(e) => setYear(Number(e.target.value))}
                  className="w-full bg-slate-950 text-white border border-slate-800 rounded-lg p-2 text-xs font-mono focus:border-accent-blue focus:outline-none"
                >
                  {[2025, 2024, 2023, 2022, 2021, 2020].map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-mono text-slate-400 mb-1">Allotted Marks</label>
                <select 
                  value={marks} 
                  onChange={(e) => setMarks(Number(e.target.value))}
                  className="w-full bg-slate-950 text-white border border-slate-800 rounded-lg p-2 text-xs font-mono focus:border-accent-blue focus:outline-none"
                >
                  <option value={2}>2 Marks (Core Concept)</option>
                  <option value={6}>6 Marks (Explanation)</option>
                  <option value={10}>10 Marks (Full Essay)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-mono text-slate-400 mb-1">Question Text</label>
              <textarea
                placeholder="Differentiate between Distance Vector Routing and Link State Routing. Explain Dijkstra's shortest path calculations."
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                rows={4}
                className="w-full bg-slate-950 text-slate-200 border border-slate-800 rounded-lg p-2 text-xs focus:border-accent-blue focus:outline-none leading-relaxed"
                required
              />
            </div>

            <button
              type="submit"
              disabled={adding}
              className="w-full py-2.5 bg-slate-950 hover:bg-slate-800 disabled:bg-slate-900 border border-slate-800 text-white rounded-xl text-xs font-mono font-bold transition-all shadow flex items-center justify-center gap-2"
            >
              {adding ? (
                <>
                  <Sparkles className="h-4 w-4 animate-spin" />
                  Mapping and recalculating...
                </>
              ) : (
                <>
                  <Brain className="h-4 w-4 text-accent-blue" />
                  Map & Recalculate Importance
                </>
              )}
            </button>
          </form>
        </div>

        {/* Topic Frequency Distribution (Asked Count) */}
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">Topic Frequency Analysis</h3>
            <span className="px-1.5 py-0.5 bg-slate-800 text-[9px] text-slate-400 rounded-full font-mono">Calibrated Weights</span>
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {filteredImportance.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2 font-mono">No analysis data. Ingest exam questions first.</p>
            ) : (
              // Filter to include only topics belonging to this subject
              filteredImportance.map((imp, idx) => {
                const topicName = getTopicName(imp.topic_id);
                // Calculate percentage-like display bar size
                const barWidth = Math.min(imp.frequency_count * 20, 100);

                return (
                  <div key={idx} className="space-y-1.5">
                    <div className="flex justify-between text-xs font-medium">
                      <span className="text-slate-200 truncate pr-2" title={topicName}>{topicName}</span>
                      <span className="text-accent-teal shrink-0 font-mono font-semibold">Asked {imp.frequency_count}x</span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[10px] text-slate-400">
                      <div className="flex-1 bg-slate-950 h-2 rounded overflow-hidden">
                        <div 
                          className={`h-full ${imp.difficulty_avg > 2.5 ? 'bg-red-500' : imp.difficulty_avg > 1.5 ? 'bg-amber-500' : 'bg-emerald-500'}`} 
                          style={{ width: `${barWidth}%` }} 
                        />
                      </div>
                      <span className="w-16 text-right truncate">
                        Diff: {imp.difficulty_avg > 2.5 ? 'Hard' : imp.difficulty_avg > 1.5 ? 'Medium' : 'Easy'}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

      </div>

      {/* Column 2 & 3: PYQ List & Mock Exam Paper Assembler (2/3 space) */}
      <div className="xl:col-span-2 space-y-6">
        
        {/* Mock Exam Paper Assembler Workspace */}
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl space-y-6">
          
          <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between border-b border-slate-800/80 pb-4 gap-4">
            <div className="space-y-1">
              <span className="text-[10px] font-mono text-accent-teal uppercase tracking-widest">Syllabus-Weighted Calibration</span>
              <h2 className="text-lg font-display font-bold text-white tracking-tight">Mock Exam Paper Assembler</h2>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Subject Selector */}
              <select
                value={assemblerSubjectId}
                onChange={(e) => setAssemblerSubjectId(e.target.value)}
                className="bg-slate-950 text-slate-300 border border-slate-800 rounded-lg p-2 text-xs font-mono focus:border-accent-blue focus:outline-none cursor-pointer min-w-[130px]"
              >
                <option value="" disabled>Select Subject</option>
                {subjects.map(sub => (
                  <option key={sub.id} value={sub.id}>{sub.code} - {sub.name}</option>
                ))}
              </select>

              {/* Target Marks Selector */}
              <select
                value={mockMarks}
                onChange={(e) => setMockMarks(Number(e.target.value))}
                className="bg-slate-950 text-slate-300 border border-slate-800 rounded-lg p-2 text-xs font-mono focus:border-accent-blue focus:outline-none cursor-pointer"
              >
                <option value={20}>20 Marks (Internal Assessment)</option>
                <option value={50}>50 Marks (Mid-Term Assessment)</option>
                <option value={100}>100 Marks (End Semester Exam)</option>
              </select>

              <button
                onClick={handleAssembleMock}
                disabled={assembling || !assemblerSubjectId}
                className="px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 disabled:bg-slate-800 disabled:text-slate-500 text-white font-mono text-xs font-bold rounded-lg transition-all shadow flex items-center gap-1.5 shrink-0"
              >
                <Play className="h-3.5 w-3.5" />
                {assembling ? 'Assembling...' : 'Assemble Paper'}
              </button>
            </div>
          </div>

          {/* Render Assembled Paper */}
          {assembling ? (
            /* SHIMMER LOADING EFFECT FOR EXAM PAPER ASSEMBLY */
            <div className="bg-slate-950 p-8 border border-slate-800/80 rounded-xl space-y-6 max-w-2xl mx-auto">
              {/* Paper Header Shimmer */}
              <div className="text-center space-y-3 pb-6 border-b border-slate-800/60">
                <div className="h-7 w-2/3 bg-slate-900 rounded mx-auto animate-shimmer" />
                <div className="h-4 w-1/2 bg-slate-900 rounded mx-auto animate-shimmer" />
                <div className="flex justify-between max-w-xs mx-auto pt-2">
                  <div className="h-3 w-16 bg-slate-900 rounded mx-auto animate-shimmer" />
                  <div className="h-3 w-16 bg-slate-900 rounded mx-auto animate-shimmer" />
                </div>
              </div>
              
              {/* Instructions Shimmer */}
              <div className="space-y-2 pb-4 border-b border-slate-800/40">
                <div className="h-3.5 w-full bg-slate-900/60 rounded animate-shimmer" />
                <div className="h-3.5 w-5/6 bg-slate-900/60 rounded animate-shimmer" />
              </div>

              {/* Sections Shimmer */}
              <div className="space-y-4 pt-2">
                <div className="h-4.5 w-1/3 bg-slate-900 rounded animate-shimmer" />
                <div className="space-y-2.5">
                  <div className="h-3.5 w-11/12 bg-slate-900/50 rounded animate-shimmer" />
                  <div className="h-3.5 w-4/5 bg-slate-900/50 rounded animate-shimmer" />
                  <div className="h-3.5 w-10/12 bg-slate-900/50 rounded animate-shimmer" />
                </div>
              </div>

              <div className="space-y-4 pt-4">
                <div className="h-4.5 w-1/3 bg-slate-900 rounded animate-shimmer" />
                <div className="space-y-2.5">
                  <div className="h-3.5 w-11/12 bg-slate-900/50 rounded animate-shimmer" />
                  <div className="h-3.5 w-3/4 bg-slate-900/50 rounded animate-shimmer" />
                </div>
              </div>
            </div>
          ) : mockPaper ? (
            <div className="bg-white text-slate-900 p-8 rounded-xl shadow-2xl border-4 border-slate-900 relative space-y-6 print:p-0 print:border-0 print:shadow-none font-serif max-w-2xl mx-auto">
              
              {/* Paper Header */}
              <div className="text-center space-y-1 border-b-2 border-slate-900 pb-4 relative">
                <GraduationCap className="h-8 w-8 text-slate-800 mx-auto print:hidden" />
                <h1 className="text-lg font-bold uppercase tracking-wide">TATTVA ENGINEERING INSTITUTE</h1>
                <p className="text-xs uppercase font-medium">{currentAssemblerSubject?.code} — {currentAssemblerSubject?.name} Mock Assessment</p>
                <div className="flex justify-between text-xs font-mono font-bold pt-2 px-1 text-slate-600">
                  <span>TIME: {mockPaper.target_marks === 100 ? '3 Hours' : mockPaper.target_marks === 50 ? '2 Hours' : '1 Hour'}</span>
                  <span>MAX MARKS: {mockPaper.target_marks}</span>
                </div>
                
                <button 
                  onClick={printPaper}
                  className="absolute -top-2 -right-2 p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 rounded print:hidden transition-colors"
                  title="Print Question Paper"
                >
                  <Printer className="h-4 w-4" />
                </button>
              </div>

              {/* General Instructions */}
              <div className="text-xs italic leading-relaxed border-b border-slate-300 pb-3">
                <strong>General Instructions:</strong> All questions are compulsory. Section parts carry designated marks. Show clean flowcharts or equations where applicable. Factual citations refer to course manuals.
              </div>

              {/* Sections Breakdown */}
              <div className="space-y-6">
                
                {/* SECTION A: 2 Marks */}
                {mockPaper.questions.some(q => q.marks === 2) && (
                  <div className="space-y-3">
                    <h3 className="font-bold border-b border-slate-400 pb-1 uppercase tracking-wide text-sm">SECTION A (Answer all short concept questions)</h3>
                    <div className="space-y-3 font-sans">
                      {mockPaper.questions.filter(q => q.marks === 2).map((q, idx) => (
                        <div key={q.id} className="flex justify-between items-start gap-4 text-xs">
                          <span>Q{idx+1}. {q.question_text}</span>
                          <span className="font-bold text-slate-700 font-mono shrink-0">[2 Marks]</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* SECTION B: 6 Marks */}
                {mockPaper.questions.some(q => q.marks === 6) && (
                  <div className="space-y-3 pt-4">
                    <h3 className="font-bold border-b border-slate-400 pb-1 uppercase tracking-wide text-sm">SECTION B (Answer all explanation questions)</h3>
                    <div className="space-y-3 font-sans">
                      {mockPaper.questions.filter(q => q.marks === 6).map((q, idx) => (
                        <div key={q.id} className="flex justify-between items-start gap-4 text-xs">
                          <span>Q{idx+1}. {q.question_text}</span>
                          <span className="font-bold text-slate-700 font-mono shrink-0">[6 Marks]</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* SECTION C: 10 Marks */}
                {mockPaper.questions.some(q => q.marks === 10) && (
                  <div className="space-y-3 pt-4">
                    <h3 className="font-bold border-b border-slate-400 pb-1 uppercase tracking-wide text-sm">SECTION C (Answer all detailed essays)</h3>
                    <div className="space-y-3 font-sans">
                      {mockPaper.questions.filter(q => q.marks === 10).map((q, idx) => (
                        <div key={q.id} className="flex justify-between items-start gap-4 text-xs">
                          <span>Q{idx+1}. {q.question_text}</span>
                          <span className="font-bold text-slate-700 font-mono shrink-0">[10 Marks]</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              </div>

              {/* End Note */}
              <div className="text-center font-bold text-xs uppercase border-t border-slate-400 pt-4 font-mono text-slate-500">
                ****** END OF ASSESSMENT PAPER (Assembled Calibrated Marks: {mockPaper.assembled_marks}) ******
              </div>

            </div>
          ) : (
            <div className="border border-slate-800/80 bg-slate-950/40 p-12 text-center rounded-xl text-slate-500 font-mono text-xs">
              Configure marks threshold and click "Assemble Paper" to generate a weighted exam questionnaire based on historical topic frequencies.
            </div>
          )}

        </div>

        {/* past questions library */}
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">Historical Question Library</h3>
            <span className="px-2 py-0.5 bg-slate-800 text-[10px] text-slate-400 rounded-full font-mono">{pyqs.length} questions mapped</span>
          </div>

          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {loading ? (
              <div className="flex justify-center py-6">
                <RefreshCw className="h-5 w-5 text-slate-400 animate-spin" />
              </div>
            ) : pyqs.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2 font-mono">No past questions loaded yet.</p>
            ) : (
              pyqs.map(q => (
                <div key={q.id} className="p-3 bg-slate-950/60 border border-slate-800/40 rounded-xl space-y-2 text-xs">
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="text-accent-teal uppercase font-semibold">Asked in {q.year}</span>
                    <span className="text-slate-400 font-bold bg-slate-900 px-1.5 py-0.5 border border-slate-800 rounded">{q.marks} Marks · {q.difficulty}</span>
                  </div>
                  <p className="text-slate-200 leading-relaxed font-sans">{q.question_text}</p>
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-400 border-t border-slate-800/50 pt-1.5">
                    <span className="font-mono uppercase text-[9px] text-slate-500 shrink-0">Topic:</span>
                    <span className="truncate">{getTopicName(q.topic_id)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

    </div>
  );
}
