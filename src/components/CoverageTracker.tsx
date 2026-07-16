import React, { useState, useEffect } from 'react';
import { Upload, BookOpen, AlertCircle, CheckCircle, HelpCircle, ArrowRight, Brain, RefreshCw, Layers, Cloud } from 'lucide-react';
import { Subject, CoverageSummary, Document } from '../types';

interface CoverageTrackerProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
  onSelectSubject: (sub: Subject) => void;
  onRefreshSubjects: () => void;
  accessToken?: string | null;
}

export default function CoverageTracker({
  subjects,
  selectedSubject,
  onSelectSubject,
  onRefreshSubjects,
  accessToken
}: CoverageTrackerProps) {
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [newSubName, setNewSubName] = useState('');
  const [newSubCode, setNewSubCode] = useState('');
  const [showAddSubject, setShowAddSubject] = useState(false);

  // Upload & Pipeline States
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [pipelineStep, setPipelineStep] = useState<'idle' | 'ingesting' | 'classifying' | 'review'>('idle');
  const [ingestionResult, setIngestionResult] = useState<{
    document_id: string;
    filename: string;
    pages_processed: number;
    chunks_created: number;
    sample_headings: string;
  } | null>(null);
  
  const [classificationResult, setClassificationResult] = useState<{
    subject: string;
    module_number: number;
    topic: string;
    is_new_topic: boolean;
    confidence: 'high' | 'medium' | 'low';
    note: string;
  } | null>(null);

  useEffect(() => {
    if (selectedSubject) {
      fetchCoverage();
      fetchDocuments();
    }
  }, [selectedSubject]);

  const fetchCoverage = async () => {
    if (!selectedSubject) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/coverage?subjectId=${selectedSubject.id}`);
      const data = await res.json();
      setCoverage(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchDocuments = async () => {
    if (!selectedSubject) return;
    try {
      const res = await fetch(`/api/documents?subjectId=${selectedSubject.id}`);
      const data = await res.json();
      setDocuments(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddSubject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubName || !newSubCode) return;
    try {
      const res = await fetch('/api/subjects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newSubName, code: newSubCode })
      });
      if (res.ok) {
        setNewSubName('');
        setNewSubCode('');
        setShowAddSubject(false);
        onRefreshSubjects();
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Drag & Drop Handlers
  const loadPickerLibrary = (): Promise<void> => {
    return new Promise((resolve, reject) => {
      const anyWin = window as any;
      if (anyWin.gapi && anyWin.gapi.load) {
        anyWin.gapi.load('picker', {
          callback: resolve,
          onerror: reject
        });
      } else {
        const checkGapi = setInterval(() => {
          if (anyWin.gapi && anyWin.gapi.load) {
            clearInterval(checkGapi);
            anyWin.gapi.load('picker', {
              callback: resolve,
              onerror: reject
            });
          }
        }, 100);
        setTimeout(() => {
          clearInterval(checkGapi);
          reject(new Error('Google Picker library load failed'));
        }, 6000);
      }
    });
  };

  const handleOpenPicker = async () => {
    if (!accessToken || !selectedSubject) return;
    try {
      setUploading(true);
      setPipelineStep('ingesting');
      setUploadProgress('Opening Google Drive Picker...');
      await loadPickerLibrary();
      
      const anyWin = window as any;
      const pickerOrigin =
        window.location.ancestorOrigins && window.location.ancestorOrigins.length > 0
          ? window.location.ancestorOrigins[window.location.ancestorOrigins.length - 1]
          : window.location.origin;

      const picker = new anyWin.google.picker.PickerBuilder()
        .addView(anyWin.google.picker.ViewId.DOCS)
        .setOAuthToken(accessToken)
        .setOrigin(pickerOrigin)
        .setCallback(async (data: any) => {
          if (data.action === anyWin.google.picker.Action.PICKED) {
            const file = data.docs[0];
            const fileId = file.id;
            const filename = file.name;
            const mimeType = file.mimeType;
            
            setUploadProgress(`Downloading and parsing "${filename}" via Google Drive API...`);
            
            const res = await fetch('/api/drive/ingest', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                fileId,
                filename,
                mimeType,
                subject_id: selectedSubject.id,
                accessToken
              })
            });

            if (!res.ok) throw new Error(await res.text());
            const ingestData = await res.json();
            
            setIngestionResult(ingestData);
            setPipelineStep('review');
            
            // Set mock/sample heading for classification review
            setClassificationResult({
              subject: selectedSubject.name,
              module_number: 1,
              topic: 'Imported from Google Drive',
              is_new_topic: false,
              confidence: 'high',
              note: `This document "${filename}" was imported and RAG-chunked directly from Google Drive.`
            });
          } else if (data.action === anyWin.google.picker.Action.CANCEL) {
            setPipelineStep('idle');
            setUploading(false);
          }
        })
        .build();
      picker.setVisible(true);
    } catch (err: any) {
      console.error(err);
      alert('Failed to import file via Google Picker: ' + err.message);
      setPipelineStep('idle');
      setUploading(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
      uploadFile(files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const uploadFile = async (file: File) => {
    if (!selectedSubject) return;
    setUploading(true);
    setPipelineStep('ingesting');
    setUploadProgress('Extracting text and calculating page indexes (PyMuPDF hook)...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('subject_id', selectedSubject.id);

    try {
      const res = await fetch('/api/ingest', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setIngestionResult(data);

      // Trigger auto classification
      setPipelineStep('classifying');
      setUploadProgress('Running C1 classification prompt against taxonomy schema...');
      
      const classifyRes = await fetch('/api/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: data.document_id,
          headings: data.sample_headings || 'Engineering course syllabus outline'
        })
      });
      if (!classifyRes.ok) throw new Error(await classifyRes.text());
      const cData = await classifyRes.json();
      setClassificationResult(cData.classification);
      setPipelineStep('review');
    } catch (err: any) {
      console.error(err);
      setPipelineStep('idle');
      alert(`Pipeline error: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const commitToKnowledgeStore = async () => {
    // Already committed on classify API call, just reset UI and refresh
    setPipelineStep('idle');
    setIngestionResult(null);
    setClassificationResult(null);
    fetchCoverage();
    fetchDocuments();
  };

  return (
    <div id="coverage-tracker" className="space-y-6">
      
      {/* Subject Selection Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
        <div className="space-y-1">
          <label className="text-xs font-mono text-accent-teal uppercase tracking-wider">Select Course Syllabus</label>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-accent-blue" />
            <select 
              value={selectedSubject?.id || ''} 
              onChange={(e) => {
                const sub = subjects.find(s => s.id === e.target.value);
                if (sub) onSelectSubject(sub);
              }}
              className="bg-slate-950 text-white font-display text-lg font-semibold border-0 outline-none focus:ring-0 cursor-pointer pr-10"
            >
              <option value="" disabled>-- Select Subject --</option>
              {subjects.map(s => (
                <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <button 
            onClick={() => setShowAddSubject(!showAddSubject)}
            className="px-4 py-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-medium font-mono text-slate-300 transition-colors"
          >
            {showAddSubject ? 'Cancel' : '+ Add Subject'}
          </button>
          {selectedSubject && (
            <button 
              onClick={fetchCoverage}
              className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 transition-colors"
              title="Refresh syllabus coverage"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Add Subject Section */}
      {showAddSubject && (
        <form onSubmit={handleAddSubject} className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-4 max-w-md">
          <h3 className="text-sm font-mono text-accent-teal">Add New Subject</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1 font-mono">Code (e.g. CS302)</label>
              <input 
                type="text" 
                placeholder="CS302"
                value={newSubCode} 
                onChange={(e) => setNewSubCode(e.target.value)}
                className="w-full bg-slate-950 text-white border border-slate-800 rounded-lg p-2 text-sm focus:border-accent-blue focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1 font-mono">Subject Name</label>
              <input 
                type="text" 
                placeholder="Compiler Design"
                value={newSubName} 
                onChange={(e) => setNewSubName(e.target.value)}
                className="w-full bg-slate-950 text-white border border-slate-800 rounded-lg p-2 text-sm focus:border-accent-blue focus:outline-none"
                required
              />
            </div>
          </div>
          <button 
            type="submit" 
            className="w-full py-2 bg-accent-blue hover:bg-accent-blue/80 text-white rounded-lg text-xs font-semibold font-mono transition-all"
          >
            Save Subject
          </button>
        </form>
      )}

      {selectedSubject && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Syllabus Progress Card (Left Column) */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl flex flex-col items-center justify-center text-center space-y-4 shadow-lg">
              <h3 className="text-sm font-mono text-slate-400 uppercase tracking-wider">Overall Syllabus Coverage</h3>
              
              {/* Radial Circle */}
              <div className="relative w-40 h-40 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="40" stroke="rgba(30, 41, 59, 1)" strokeWidth="8" fill="transparent" />
                  <circle 
                    cx="50" 
                    cy="50" 
                    r="40" 
                    stroke="url(#progress-gradient)" 
                    strokeWidth="8" 
                    fill="transparent" 
                    strokeDasharray={2 * Math.PI * 40}
                    strokeDashoffset={2 * Math.PI * 40 * (1 - (coverage?.overall_percentage || 0) / 100)}
                    strokeLinecap="round"
                    className="transition-all duration-1000 ease-out"
                  />
                  <defs>
                    <linearGradient id="progress-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#14b8a6" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-3xl font-display font-bold text-white">{coverage?.overall_percentage || 0}%</span>
                  <span className="text-xs font-mono text-slate-400">calibrated completeness</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 w-full pt-4 border-t border-slate-800/60">
                <div className="text-center p-2 bg-slate-950/40 rounded-lg">
                  <div className="text-lg font-bold font-mono text-accent-teal">{coverage?.grounded_count || 0}</div>
                  <div className="text-[10px] text-slate-400 font-mono">Grounded Notes</div>
                </div>
                <div className="text-center p-2 bg-slate-950/40 rounded-lg">
                  <div className="text-lg font-bold font-mono text-accent-blue">{coverage?.partial_count || 0}</div>
                  <div className="text-[10px] text-slate-400 font-mono">Partial Grounding</div>
                </div>
                <div className="text-center p-2 bg-slate-950/40 rounded-lg">
                  <div className="text-lg font-bold font-mono text-orange-400">{coverage?.needs_review_count || 0}</div>
                  <div className="text-[10px] text-slate-400 font-mono">Needs Review</div>
                </div>
                <div className="text-center p-2 bg-slate-950/40 rounded-lg">
                  <div className="text-lg font-bold font-mono text-slate-500">{coverage?.missing_count || 0}</div>
                  <div className="text-[10px] text-slate-400 font-mono">Unmapped Topics</div>
                </div>
              </div>
            </div>

            {/* Document Library List */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4 shadow-lg">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-mono font-bold text-slate-300 uppercase">Knowledge Store Files</h4>
                <span className="px-2 py-0.5 bg-slate-800 text-[10px] text-slate-400 rounded-full font-mono">{documents.length} ingested</span>
              </div>
              <div className="space-y-2 max-h-56 overflow-y-auto pr-2">
                {documents.length === 0 ? (
                  <p className="text-xs text-slate-500 italic py-2">No PDF lecture slides uploaded yet.</p>
                ) : (
                  documents.map(doc => (
                    <div key={doc.id} className="flex items-start justify-between p-2.5 bg-slate-950/50 hover:bg-slate-950 border border-slate-800/40 rounded-lg transition-colors">
                      <div className="space-y-1 min-w-0 pr-2">
                        <p className="text-xs font-medium text-slate-200 truncate" title={doc.filename}>{doc.filename}</p>
                        <p className="text-[10px] text-slate-500 font-mono">{new Date(doc.uploaded_at).toLocaleDateString()} · MD5: {doc.content_hash.slice(0, 8)}</p>
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded uppercase">{doc.source_type}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* PDF Ingestion Area & Syllabus Details (Right Columns) */}
          <div className="lg:col-span-2 space-y-6">
            
            {/* INGESTION & PIPELINE ACTIVE DISPLAY */}
            {pipelineStep !== 'idle' ? (
              <div className="bg-slate-900 border border-accent-blue/40 p-6 rounded-2xl space-y-5 shadow-2xl relative overflow-hidden animate-fade-in">
                {/* Visual Accent */}
                <div className="absolute top-0 right-0 bg-accent-blue/10 px-3 py-1 text-[10px] font-mono text-accent-blue border-l border-b border-accent-blue/30 rounded-bl-lg">
                  AI Pipeline Active
                </div>

                <div className="flex items-start gap-4">
                  <div className="p-3 bg-accent-blue/15 text-accent-blue rounded-xl animate-pulse">
                    <Brain className="h-6 w-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-sm font-mono font-semibold text-white">Tattva Ingestion & Classification Pipeline</h3>
                    <p className="text-xs text-slate-400 font-sans">{uploadProgress}</p>
                  </div>
                </div>

                {/* Progress Indicators */}
                <div className="grid grid-cols-4 gap-2 text-center text-[10px] font-mono">
                  <div className={`p-2 rounded border ${pipelineStep === 'ingesting' ? 'bg-accent-blue/10 border-accent-blue text-white' : 'bg-slate-950 border-slate-800 text-slate-500'}`}>
                    1. PDF Parse & Chunk
                  </div>
                  <div className={`p-2 rounded border ${pipelineStep === 'classifying' ? 'bg-accent-blue/10 border-accent-blue text-white' : 'bg-slate-950 border-slate-800 text-slate-500'}`}>
                    2. Vector Embed
                  </div>
                  <div className={`p-2 rounded border ${pipelineStep === 'review' ? 'bg-accent-teal/15 border-accent-teal text-white' : 'bg-slate-950 border-slate-800 text-slate-500'}`}>
                    3. Taxonomy Classify
                  </div>
                  <div className="p-2 rounded border bg-slate-950 border-slate-800 text-slate-500">
                    4. Grounded Notes
                  </div>
                </div>

                {/* Show Classification Result for Review */}
                {pipelineStep === 'review' && classificationResult && (
                  <div className="space-y-4 border-t border-slate-800/80 pt-4">
                    <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-accent-teal">CLASSIFICATION OUTPUT (C1 PROMPT JSON)</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${classificationResult.confidence === 'high' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                          Confidence: {classificationResult.confidence}
                        </span>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-4 text-xs">
                        <div className="space-y-1">
                          <p className="text-slate-400 font-mono">Target Subject:</p>
                          <p className="text-white font-medium">{classificationResult.subject}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-slate-400 font-mono">Matched Module:</p>
                          <p className="text-white font-medium">Module {classificationResult.module_number}</p>
                        </div>
                        <div className="col-span-2 space-y-1">
                          <p className="text-slate-400 font-mono">Identified Topic Name:</p>
                          <p className="text-accent-blue font-semibold">{classificationResult.topic}</p>
                        </div>
                        <div className="col-span-2 space-y-1 border-t border-slate-800/60 pt-2">
                          <p className="text-slate-400 font-mono">Classification Reasoning:</p>
                          <p className="text-slate-300 italic text-[11px] leading-relaxed">"{classificationResult.note}"</p>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <button 
                        onClick={commitToKnowledgeStore}
                        className="flex-1 py-3 bg-accent-teal hover:bg-accent-teal/80 text-slate-950 text-xs font-mono font-bold rounded-xl transition-all shadow-md hover:scale-[1.01]"
                      >
                        Approve & Commit {ingestionResult?.chunks_created} Page Chunks
                      </button>
                      <button 
                        onClick={() => {
                          setPipelineStep('idle');
                          setIngestionResult(null);
                          setClassificationResult(null);
                        }}
                        className="px-4 py-3 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-mono text-slate-400 transition-colors"
                      >
                        Discard
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* Drag & Drop Upload Zone */
              <div 
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-2xl p-6 text-center space-y-3 transition-all ${
                  isDragging ? 'border-accent-blue bg-accent-blue/5' : 'border-slate-800 bg-slate-900/40 hover:bg-slate-900'
                }`}
              >
                <div className="p-3 bg-slate-950 w-12 h-12 rounded-xl flex items-center justify-center mx-auto border border-slate-800">
                  <Upload className="h-5 w-5 text-slate-400" />
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-white font-medium">Drag & Drop Syllabus or Lecture Notes PDF</p>
                  <p className="text-[10px] text-slate-400 font-mono">Accepts native exam guides & textbook slide materials</p>
                </div>
                <div className="flex items-center justify-center gap-3">
                  <label className="inline-flex items-center px-4 py-2.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-mono font-medium text-slate-200 cursor-pointer transition-colors shadow-sm">
                    Browse Local File
                    <input type="file" accept="application/pdf" onChange={handleFileChange} className="hidden" />
                  </label>
                  {accessToken && (
                    <button
                      onClick={handleOpenPicker}
                      className="inline-flex items-center gap-2 px-4 py-2.5 bg-accent-blue/10 hover:bg-accent-blue text-accent-blue hover:text-white border border-accent-blue/20 rounded-xl text-xs font-mono font-medium transition-all shadow-sm cursor-pointer"
                    >
                      <Cloud className="h-3.5 w-3.5" />
                      Google Drive Picker
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Modules & Syllabus Breakdown */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4 shadow-lg">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">Course Syllabus Outline</h3>
                <span className="text-[10px] font-mono text-slate-400">RAG page-citations ready</span>
              </div>

              {loading ? (
                <div className="flex flex-col items-center justify-center py-10 space-y-2">
                  <RefreshCw className="h-6 w-6 text-slate-400 animate-spin" />
                  <p className="text-xs text-slate-500 font-mono">Mapping module coverage...</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {coverage?.modules.map(mod => {
                    const totalModTopics = mod.topics.length;
                    const groundedCount = mod.topics.filter(t => t.status === 'grounded').length;
                    const partialCount = mod.topics.filter(t => t.status === 'partial').length;
                    const reviewCount = mod.topics.filter(t => t.status === 'review').length;
                    
                    const groundedPartialCount = groundedCount + partialCount;
                    const groundedPartialPercent = totalModTopics > 0 ? Math.round((groundedPartialCount / totalModTopics) * 100) : 0;

                    return (
                      <div key={mod.module_id} className="border border-slate-800/80 bg-slate-950/40 rounded-xl overflow-hidden transition-all hover:border-slate-700/80">
                        {/* Module Header */}
                        <div className="p-4 bg-slate-950/80 border-b border-slate-800/60 flex flex-col md:flex-row md:items-center justify-between gap-4">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <BookOpen className="h-5 w-5 text-accent-blue shrink-0" />
                            <div className="min-w-0">
                              <span className="text-xs font-semibold text-slate-100 block truncate" title={mod.title}>{mod.title}</span>
                              <span className="text-[10px] text-slate-500 font-mono">Module Syllabus Coverage</span>
                            </div>
                          </div>
                          
                          {/* Syllabus Coverage Progress Section */}
                          <div className="flex flex-col md:items-end gap-1.5 shrink-0 w-full md:w-60">
                            <div className="flex justify-between items-center text-[10px] font-mono text-slate-400 w-full">
                              <span>Coverage Status:</span>
                              <span className="text-emerald-400 font-bold">{groundedPartialPercent}%</span>
                            </div>
                            
                            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden relative shadow-inner" title="Grounded or Partial Notes Coverage">
                              <div 
                                className="bg-emerald-500 h-full rounded-full transition-all duration-1000 ease-out" 
                                style={{ width: `${groundedPartialPercent}%` }} 
                              />
                            </div>
                            
                            <div className="flex justify-between items-center text-[9px] font-mono text-slate-400 w-full">
                              <span className="flex items-center gap-1">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                                {groundedPartialCount} of {totalModTopics} Topics Ready
                              </span>
                              {reviewCount > 0 && (
                                <span className="flex items-center gap-1 text-amber-500">
                                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block" />
                                  {reviewCount} Review
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                      {/* Topic Lists */}
                      <div className="divide-y divide-slate-900/60 p-2.5 space-y-1 bg-slate-900/10">
                        {mod.topics.length === 0 ? (
                          <p className="text-[11px] text-slate-500 italic p-2 font-mono">No mapped topics in this module. Upload syllabus slides to populate.</p>
                        ) : (
                          mod.topics.map(topic => (
                            <div key={topic.id} className="flex items-center justify-between p-2 hover:bg-slate-900/40 rounded-lg transition-colors">
                              <span className="text-xs text-slate-300 font-sans truncate pr-2">{topic.name}</span>
                              <div className="flex items-center gap-2 shrink-0">
                                {topic.notes_count > 0 && (
                                  <span className="px-1.5 py-0.5 bg-accent-blue/10 text-accent-blue border border-accent-blue/20 rounded-[4px] text-[9px] font-mono">
                                    {topic.notes_count} Notes
                                  </span>
                                )}
                                <span className={`flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full capitalize ${
                                  topic.status === 'grounded' ? 'bg-emerald-500/15 text-emerald-400' :
                                  topic.status === 'partial' ? 'bg-teal-500/15 text-teal-300' :
                                  topic.status === 'review' ? 'bg-orange-500/15 text-orange-400' :
                                  'bg-slate-800/60 text-slate-500'
                                }`}>
                                  {topic.status === 'grounded' && <CheckCircle className="h-3 w-3" />}
                                  {topic.status === 'partial' && <CheckCircle className="h-3 w-3" />}
                                  {topic.status === 'review' && <AlertCircle className="h-3 w-3" />}
                                  {topic.status === 'missing' && <HelpCircle className="h-3 w-3" />}
                                  {topic.status === 'review' ? 'Needs Review' : topic.status}
                                </span>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  );
                })}
                </div>
              )}
            </div>

          </div>
          
        </div>
      )}

    </div>
  );
}
