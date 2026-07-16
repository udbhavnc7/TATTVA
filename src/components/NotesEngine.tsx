import React, { useState, useEffect, useRef } from 'react';
import { 
  BookOpen, Brain, Settings, Download, Copy, Check, Clipboard, AlertCircle, 
  HelpCircle, Sparkles, ChevronRight, FileText, CheckCircle2, AlertTriangle, Play,
  GitFork, RefreshCw, ChevronDown, FileSpreadsheet, Database, WifiOff,
  PenSquare, Save, XCircle, Trash2
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import mermaid from 'mermaid';
import { Subject, Module, Topic, Note } from '../types';
import { generateMermaidDiagram } from '../utils/diagramGenerator';
import { exportNoteToMarkdown, exportFlashcardsToAnkiCSV, exportNoteToPDF } from '../utils/exportManager';
import { saveNotesToCache, saveNoteToCache, getNoteFromCache, getCachedTopicIdsMap } from '../utils/indexedDB';

// A highly reliable React wrapper component that renders Mermaid charts asynchronously
function Mermaid({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const uniqueId = `mermaid-${Math.random().toString(36).substring(2, 11)}`;
    
    const renderChart = async () => {
      try {
        setError(null);
        const { svg: renderedSvg } = await mermaid.render(uniqueId, chart);
        if (isMounted) {
          setSvg(renderedSvg);
        }
      } catch (err: any) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError(err.message || 'Failed to parse and render diagram');
        }
      }
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [chart]);

  if (error) {
    return (
      <div className="p-3.5 bg-rose-950/20 border border-rose-900/40 rounded-xl text-rose-400 text-xs font-mono space-y-1">
        <p className="font-bold">Mermaid Syntax/Parse Error:</p>
        <pre className="text-[10px] bg-slate-950 p-2 rounded overflow-x-auto select-all max-h-40">{chart}</pre>
        <p className="opacity-80 text-[10px]">Error message: {error}</p>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-slate-500 text-xs font-mono gap-2">
        <div className="h-4 w-4 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
        <span className="animate-pulse">Rendering flowchart...</span>
      </div>
    );
  }

  return (
    <div 
      className="flex justify-center bg-slate-950 p-4 rounded-xl overflow-x-auto w-full select-none" 
      dangerouslySetInnerHTML={{ __html: svg }} 
    />
  );
}

interface NotesEngineProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
}

export default function NotesEngine({ subjects, selectedSubject }: NotesEngineProps) {
  const [modules, setModules] = useState<Module[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  
  const [activeModule, setActiveModule] = useState<Module | null>(null);
  const [activeTopic, setActiveTopic] = useState<Topic | null>(null);
  const [depth, setDepth] = useState<'2mark' | '6mark' | '10mark'>('6mark');

  const [note, setNote] = useState<Note | null>(null);
  const [unsupportedSentences, setUnsupportedSentences] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [generatingDiagram, setGeneratingDiagram] = useState(false);
  const [copied, setCopied] = useState(false);
  const [autoFcStatus, setAutoFcStatus] = useState<'idle' | 'generating' | 'success'>('idle');
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  const [exportingAnki, setExportingAnki] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // C9. Summarize Note states
  const [summarizeEnabled, setSummarizeEnabled] = useState(false);
  const [summarizing, setSummarizing] = useState(false);

  // C10. Categorization Tag states
  const [tagSuggesting, setTagSuggesting] = useState(false);
  const [customTagInput, setCustomTagInput] = useState('');

  // Note Draft Editing states
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [hasDraft, setHasDraft] = useState(false);
  const [draftContent, setDraftContent] = useState('');

  const mermaidRef = useRef<HTMLDivElement>(null);
  const notesContentRef = useRef<HTMLDivElement>(null);
  const [scrollProgress, setScrollProgress] = useState(0);

  // Offline-first caching states
  const [isOfflineLoaded, setIsOfflineLoaded] = useState(false);
  const [cachedTopicIds, setCachedTopicIds] = useState<Record<string, boolean>>({});
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);

  // Monitor online status
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Update list of cached topics from IndexedDB
  const refreshCachedTopics = async () => {
    const cacheMap = await getCachedTopicIdsMap();
    setCachedTopicIds(cacheMap);
  };

  useEffect(() => {
    refreshCachedTopics();
  }, [topics, note]);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose'
    });
  }, []);

  useEffect(() => {
    if (selectedSubject) {
      fetchModules();
    } else {
      setModules([]);
      setTopics([]);
      setActiveModule(null);
      setActiveTopic(null);
    }
  }, [selectedSubject]);

  useEffect(() => {
    if (activeModule) {
      fetchTopics();
    } else {
      setTopics([]);
      setActiveTopic(null);
    }
  }, [activeModule]);

  useEffect(() => {
    if (activeTopic) {
      fetchNotes();
    } else {
      setNote(null);
    }
  }, [activeTopic, depth]);

  // Hook to process any inline mermaid diagrams after the notes render
  useEffect(() => {
    if (note) {
      const timer = setTimeout(() => {
        try {
          mermaid.contentLoaded();
        } catch (e) {
          console.error("Mermaid graph render error:", e);
        }
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [note]);

  // Hook to calculate scroll progress of active study notes
  useEffect(() => {
    const handleScroll = () => {
      const element = notesContentRef.current;
      if (!element) {
        setScrollProgress(0);
        return;
      }
      const rect = element.getBoundingClientRect();
      const elementHeight = rect.height;
      const viewHeight = window.innerHeight;
      
      // Top of the notes content relative to viewport
      const elementTop = rect.top;
      
      // The scrollable range for the note content:
      // Starts at the top of viewport (rect.top <= 0), ends when the bottom of the content hits the bottom of the viewport
      const totalScrollableDistance = elementHeight - viewHeight;
      
      if (totalScrollableDistance <= 0) {
        setScrollProgress(100);
      } else {
        const scrolled = -elementTop;
        const progress = Math.min(Math.max((scrolled / totalScrollableDistance) * 100, 0), 100);
        setScrollProgress(progress);
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleScroll);
    
    // Initial evaluation
    handleScroll();

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleScroll);
    };
  }, [note, depth]);

  // C9. Summarize Note Toggle Effect
  useEffect(() => {
    const fetchSummaryIfNeeded = async () => {
      if (!summarizeEnabled || !note || note.summary_md || isOfflineLoaded || !isOnline) return;
      
      setSummarizing(true);
      try {
        const res = await fetch('/api/summarize-note', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ noteText: note.content_md })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.summary) {
            const updatedNote = { ...note, summary_md: data.summary };
            setNote(updatedNote);
            
            // Cache updated note (with its summary) to local storage
            await saveNoteToCache(updatedNote);
            
            // Save updated note with summary to backend database
            await fetch('/api/notes/update', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                topicId: activeTopic!.id,
                depth,
                content_md: note.content_md,
                confidence: note.confidence,
                summary_md: data.summary
              })
            });
            
            // Also refresh cached topics map in UI
            refreshCachedTopics();
          }
        }
      } catch (error) {
        console.error("Failed to generate note key takeaway summary:", error);
      } finally {
        setSummarizing(false);
      }
    };

    fetchSummaryIfNeeded();
  }, [summarizeEnabled, note?.id, note?.content_md, isOfflineLoaded, isOnline]);

  // Auto-save editContent to localStorage as draft
  useEffect(() => {
    if (isEditing && activeTopic) {
      const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
      if (editContent) {
        localStorage.setItem(draftKey, editContent);
        setHasDraft(true);
        setDraftContent(editContent);
      } else {
        localStorage.removeItem(draftKey);
        setHasDraft(false);
        setDraftContent('');
      }
    }
  }, [editContent, isEditing, activeTopic, depth]);

  const handleSaveNote = async () => {
    if (!activeTopic) return;
    setGenerating(true);
    try {
      if (!isOnline || isOfflineLoaded) {
        // Save note offline inside local cache (IndexedDB)
        const localNote: Note = note ? {
          ...note,
          content_md: editContent,
          generated_at: new Date().toISOString(),
          version: note.version + 1
        } : {
          id: `local-${activeTopic.id}-${depth}`,
          topic_id: activeTopic.id,
          depth,
          content_md: editContent,
          confidence: 'grounded',
          version: 1,
          generated_at: new Date().toISOString()
        };
        
        await saveNoteToCache(localNote);
        setNote(localNote);
        setIsOfflineLoaded(true);
        await refreshCachedTopics();
        
        // Clear local storage draft
        const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
        localStorage.removeItem(draftKey);
        setHasDraft(false);
        setDraftContent('');
        setIsEditing(false);
        return;
      }

      // Save note to the database on the server
      const response = await fetch('/api/notes/update', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topicId: activeTopic.id,
          depth,
          content_md: editContent,
          confidence: note ? note.confidence : 'grounded',
          summary_md: note?.summary_md
        }),
      });
      
      if (response.ok) {
        const savedNote = await response.json();
        setNote(savedNote);
        
        // Save to local cache
        await saveNoteToCache(savedNote);
        await refreshCachedTopics();
        
        // Clear local storage draft
        const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
        localStorage.removeItem(draftKey);
        setHasDraft(false);
        setDraftContent('');
        setIsEditing(false);
      } else {
        console.error("Failed to save changes to the server.");
      }
    } catch (err) {
      console.error("Failed to save edited note:", err);
    } finally {
      setGenerating(false);
    }
  };

  const fetchModules = async () => {
    if (!selectedSubject) return;
    try {
      const res = await fetch(`/api/modules?subjectId=${selectedSubject.id}`);
      const data = await res.json();
      setModules(data);
      if (data.length > 0) {
        setActiveModule(data[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchTopics = async () => {
    if (!activeModule) return;
    try {
      const res = await fetch(`/api/topics?moduleId=${activeModule.id}`);
      const data = await res.json();
      setTopics(data);
      if (data.length > 0) {
        setActiveTopic(data[0]);
      } else {
        setActiveTopic(null);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchNotes = async () => {
    if (!activeTopic) return;
    
    // Reset editing state and check for local draft
    setIsEditing(false);
    const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
    const savedDraft = localStorage.getItem(draftKey);
    if (savedDraft) {
      setHasDraft(true);
      setDraftContent(savedDraft);
    } else {
      setHasDraft(false);
      setDraftContent('');
    }

    try {
      const res = await fetch(`/api/notes?topicId=${activeTopic.id}`);
      if (!res.ok) {
        throw new Error('Network response was not ok');
      }
      const notesList: Note[] = await res.json();
      
      // Save all notes for this topic into the local IndexedDB cache
      if (notesList && notesList.length > 0) {
        await saveNotesToCache(notesList);
      }
      
      const match = notesList.find(n => n.depth === depth);
      setNote(match || null);
      setUnsupportedSentences([]);
      setIsOfflineLoaded(false);
      setAutoFcStatus('idle');
    } catch (e) {
      console.warn('Network fetch failed, attempting to load from local IndexedDB cache...', e);
      // Fallback: load note from IndexedDB
      const cachedNote = await getNoteFromCache(activeTopic.id, depth);
      if (cachedNote) {
        setNote(cachedNote);
        setUnsupportedSentences([]);
        setIsOfflineLoaded(true);
        setAutoFcStatus('idle');
      } else {
        setNote(null);
        setIsOfflineLoaded(false);
      }
    }
  };

  const handleGenerateNotes = async () => {
    if (!activeTopic) return;
    setGenerating(true);
    try {
      const res = await fetch('/api/generate-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topicId: activeTopic.id,
          depth
        })
      });
      const data = await res.json();
      setNote(data.note);
      setUnsupportedSentences(data.unsupported_sentences || []);
      setIsOfflineLoaded(false);

      // Save generated note to IndexedDB cache
      if (data.note) {
        await saveNoteToCache(data.note);
        await refreshCachedTopics();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleAutoGenerateFlashcards = async () => {
    if (!activeTopic || !note) return;
    setAutoFcStatus('generating');
    try {
      const res = await fetch('/api/flashcards/auto-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topicId: activeTopic.id,
          noteText: note.content_md
        })
      });
      if (res.ok) {
        setAutoFcStatus('success');
        setTimeout(() => setAutoFcStatus('idle'), 3000);
      }
    } catch (e) {
      console.error(e);
      setAutoFcStatus('idle');
    }
  };

  const handleSuggestTags = async () => {
    if (!note || !activeTopic) return;
    setTagSuggesting(true);
    try {
      const res = await fetch('/api/notes/suggest-tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ noteText: note.content_md })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.tags && data.tags.length > 0) {
          const updatedNote = { ...note, tags: data.tags };
          setNote(updatedNote);
          
          // Save to backend database
          await fetch('/api/notes/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              topicId: activeTopic.id,
              depth,
              content_md: note.content_md,
              confidence: note.confidence,
              summary_md: note.summary_md,
              tags: data.tags
            })
          });
          
          // Cache updated note
          await saveNoteToCache(updatedNote);
          refreshCachedTopics();
        }
      }
    } catch (error) {
      console.error("Failed to suggest tags:", error);
    } finally {
      setTagSuggesting(false);
    }
  };

  const handleAddTag = async (newTag: string) => {
    if (!note || !activeTopic || !newTag.trim()) return;
    const trimmed = newTag.trim();
    const currentTags = note.tags || [];
    if (currentTags.includes(trimmed)) return;
    
    const updatedTags = [...currentTags, trimmed];
    const updatedNote = { ...note, tags: updatedTags };
    setNote(updatedNote);
    
    try {
      if (isOnline && !isOfflineLoaded) {
        await fetch('/api/notes/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topicId: activeTopic.id,
            depth,
            content_md: note.content_md,
            confidence: note.confidence,
            summary_md: note.summary_md,
            tags: updatedTags
          })
        });
      }
      await saveNoteToCache(updatedNote);
      refreshCachedTopics();
    } catch (e) {
      console.error("Failed to add tag:", e);
    }
  };

  const handleRemoveTag = async (tagToRemove: string) => {
    if (!note || !activeTopic) return;
    const currentTags = note.tags || [];
    const updatedTags = currentTags.filter(t => t !== tagToRemove);
    const updatedNote = { ...note, tags: updatedTags };
    setNote(updatedNote);
    
    try {
      if (isOnline && !isOfflineLoaded) {
        await fetch('/api/notes/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topicId: activeTopic.id,
            depth,
            content_md: note.content_md,
            confidence: note.confidence,
            summary_md: note.summary_md,
            tags: updatedTags
          })
        });
      }
      await saveNoteToCache(updatedNote);
      refreshCachedTopics();
    } catch (e) {
      console.error("Failed to remove tag:", e);
    }
  };

  const copyToClipboard = () => {
    if (!note) return;
    navigator.clipboard.writeText(note.content_md);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadMarkdown = () => {
    if (!note || !activeTopic) return;
    exportNoteToMarkdown(activeTopic.name, depth, note.content_md);
    setShowExportDropdown(false);
  };

  const downloadPDF = () => {
    if (!note || !activeTopic) return;
    exportNoteToPDF(activeTopic.name, depth, note.content_md);
    setShowExportDropdown(false);
  };

  const handleExportFlashcardsToAnki = async () => {
    if (!activeTopic) return;
    setExportingAnki(true);
    setExportError(null);
    try {
      // Fetch flashcards specifically for this active topic
      const res = await fetch(`/api/flashcards?topicId=${activeTopic.id}`);
      if (res.ok) {
        const cards = await res.json();
        if (cards && cards.length > 0) {
          exportFlashcardsToAnkiCSV(cards, activeTopic.name);
          setShowExportDropdown(false);
        } else {
          setExportError("No flashcards found for this topic yet! Auto-generate flashcards first.");
          setTimeout(() => setExportError(null), 5000);
        }
      } else {
        setExportError("Failed to fetch flashcards for export.");
        setTimeout(() => setExportError(null), 5000);
      }
    } catch (err) {
      console.error("Anki export error:", err);
      setExportError("Export failed. Please try again.");
      setTimeout(() => setExportError(null), 5000);
    } finally {
      setExportingAnki(false);
    }
  };

  const handleGenerateDiagram = async () => {
    if (!note || !activeTopic) return;
    setGeneratingDiagram(true);
    try {
      const diagramCode = await generateMermaidDiagram(note.content_md);
      
      let cleanedContent = note.content_md;
      
      // If there is already a process flow visualizer header, let's append neatly, or just append a new section
      const appendMarkdown = `\n\n### Process Flow Visualizer\n\n\`\`\`mermaid\n${diagramCode}\n\`\`\`\n`;
      const newContent = cleanedContent + appendMarkdown;
      
      const response = await fetch('/api/notes/update', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topicId: activeTopic.id,
          depth,
          content_md: newContent,
          confidence: note.confidence,
        }),
      });
      
      if (response.ok) {
        const updatedNote = await response.json();
        setNote(updatedNote);
      } else {
        setNote(prev => prev ? { ...prev, content_md: newContent } : null);
      }
    } catch (err) {
      console.error("Failed to generate or save diagram:", err);
    } finally {
      setGeneratingDiagram(false);
    }
  };

  // Extract pure mermaid blocks out of markdown content to render cleanly
  const renderNoteMarkdown = (markdown: string) => {
    const parts = markdown.split(/```mermaid([\s\S]*?)```/);
    if (parts.length === 1) {
      return <ReactMarkdown>{markdown}</ReactMarkdown>;
    }

    return (
      <div className="space-y-6">
        {parts.map((part, index) => {
          // Odd indices represent mermaid matches
          if (index % 2 === 1) {
            return (
              <div key={index} className="my-6 p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <p className="text-[10px] font-mono text-accent-teal uppercase tracking-wider mb-2">Process Flowchart (Rendered Inline)</p>
                <Mermaid chart={part.trim()} />
              </div>
            );
          }
          return <ReactMarkdown key={index}>{part}</ReactMarkdown>;
        })}
      </div>
    );
  };

  // Retrieve cited sources to list on side panel
  const extractCitations = (md: string) => {
    const matches = md.match(/\(Source:\s*([^,]+),\s*p\.(\d+)\)/g);
    if (!matches) return [];
    return Array.from(new Set(matches)).map(m => {
      const clean = m.replace(/^\(Source:\s*/, '').replace(/\)$/, '');
      const parts = clean.split(', p.');
      return { file: parts[0], page: parts[1] };
    });
  };

  const citations = note ? extractCitations(note.content_md) : [];

  return (
    <div id="notes-engine" className="grid grid-cols-1 xl:grid-cols-4 gap-6">
      
      {/* 1. Left Selection Column (1/4 space) */}
      <div className="xl:col-span-1 space-y-4">
        
        {/* Module Selection */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
          <h3 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">Select Module</h3>
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
            {modules.map(mod => (
              <button
                key={mod.id}
                onClick={() => setActiveModule(mod)}
                className={`w-full text-left p-2.5 rounded-lg text-xs font-medium transition-all flex items-center justify-between ${
                  activeModule?.id === mod.id 
                    ? 'bg-accent-blue/10 text-white border border-accent-blue/30' 
                    : 'bg-slate-950/40 hover:bg-slate-950 border border-slate-800/40 text-slate-400'
                }`}
              >
                <span className="truncate pr-2">M{mod.number}: {mod.title}</span>
                <ChevronRight className="h-3 w-3 text-slate-500 shrink-0" />
              </button>
            ))}
          </div>
        </div>

        {/* Topics Selection */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">Select Topic</h3>
            {!isOnline && (
              <span className="flex items-center gap-1 text-[10px] font-mono text-amber-500 uppercase">
                <WifiOff className="h-3 w-3 animate-pulse" /> Offline
              </span>
            )}
          </div>
          <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
            {topics.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2 font-mono">No topics. Ingest syllabus first.</p>
            ) : (
              topics.map(t => (
                <button
                  key={t.id}
                  onClick={() => setActiveTopic(t)}
                  className={`w-full text-left p-2.5 rounded-lg text-xs font-medium transition-all flex items-center justify-between gap-2 ${
                    activeTopic?.id === t.id 
                      ? 'bg-accent-teal/15 text-white border border-accent-teal/40' 
                      : 'bg-slate-950/40 hover:bg-slate-950 border border-slate-800/40 text-slate-400'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className={`h-3.5 w-3.5 shrink-0 ${activeTopic?.id === t.id ? 'text-accent-teal' : 'text-slate-500'}`} />
                    <span className="truncate">{t.name}</span>
                  </div>
                  {cachedTopicIds[t.id] && (
                    <span title="Cached Offline" className="shrink-0">
                      <Database className="h-3.5 w-3.5 text-emerald-400 ml-1.5" />
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
        </div>

      </div>

      {/* 2. Main Note workspace (3/4 space) */}
      <div className="xl:col-span-3 grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Workspace Display Area */}
        <div className="lg:col-span-2 space-y-4">
          
          {/* Depth / Toolbar controls */}
          {!isEditing && (
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            
            <div className="flex flex-wrap items-center gap-3">
              {/* Exam Depth Level Toggles */}
              <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 p-1 rounded-lg self-start">
                {(['2mark', '6mark', '10mark'] as const).map(lvl => (
                  <button
                    key={lvl}
                    onClick={() => setDepth(lvl)}
                    className={`px-3 py-1.5 rounded-md text-xs font-mono transition-all uppercase ${
                      depth === lvl 
                        ? 'bg-accent-blue text-white shadow' 
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {lvl === '2mark' ? '2-Mark' : lvl === '6mark' ? '6-Mark' : '10-Mark'}
                  </button>
                ))}
              </div>

              {/* C9. Summarize Note Toggle */}
              {note && (
                <button
                  onClick={() => setSummarizeEnabled(!summarizeEnabled)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center gap-2 border ${
                    summarizeEnabled 
                      ? 'bg-accent-blue/15 border-accent-blue/40 text-accent-blue font-semibold shadow-[0_0_12px_rgba(56,189,248,0.15)]' 
                      : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-300'
                  }`}
                  title="Toggle AI-powered key takeaway summary for this study note"
                >
                  <Sparkles className={`h-3.5 w-3.5 ${summarizeEnabled ? 'text-accent-teal animate-pulse' : 'text-slate-500'}`} />
                  <span>Summarize Note</span>
                </button>
              )}
            </div>

            {/* Note Utility Actions */}
            {note && (
              <div className="flex items-center gap-2 self-end flex-wrap">
                <button 
                  onClick={() => {
                    setEditContent(note.content_md);
                    setIsEditing(true);
                  }}
                  className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 transition-colors flex items-center gap-1.5 text-xs font-mono"
                  title="Edit study note content manually"
                >
                  <PenSquare className="h-3.5 w-3.5 text-accent-blue" />
                  <span>Edit Note</span>
                </button>
                <button 
                  onClick={handleGenerateDiagram}
                  disabled={generatingDiagram || isOfflineLoaded}
                  className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 transition-colors flex items-center gap-1.5 text-xs font-mono disabled:opacity-50"
                  title={isOfflineLoaded ? "Diagram drawing is unavailable offline" : "AI Generate process flowchart diagram (Prompt C3)"}
                >
                  {generatingDiagram ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin text-accent-teal" />
                  ) : (
                    <GitFork className={`h-3.5 w-3.5 ${isOfflineLoaded ? 'text-slate-500' : 'text-accent-teal'}`} />
                  )}
                  {generatingDiagram ? 'Drawing Diagram...' : 'Draw Diagram'}
                </button>
                <button 
                  onClick={copyToClipboard}
                  className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 transition-colors flex items-center gap-1.5 text-xs font-mono"
                  title="Copy notes to clipboard"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <div className="relative">
                  <button 
                    onClick={() => setShowExportDropdown(!showExportDropdown)}
                    className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 transition-colors flex items-center gap-1.5 text-xs font-mono"
                    title="Export study assets (Markdown/Anki CSV)"
                  >
                    <Download className="h-3.5 w-3.5 text-accent-teal" />
                    <span>Export</span>
                    <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${showExportDropdown ? 'rotate-180' : ''}`} />
                  </button>

                  {showExportDropdown && (
                    <>
                      {/* Backdrop to automatically dismiss on outer clicks */}
                      <div 
                        className="fixed inset-0 z-40" 
                        onClick={() => setShowExportDropdown(false)}
                      />
                      
                      <div className="absolute right-0 mt-2 w-56 bg-slate-950 border border-slate-800 rounded-xl shadow-2xl z-50 py-1.5 divide-y divide-slate-900 animate-fade-in">
                        <div className="px-3 py-1.5 text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                          Export Options
                        </div>
                        
                        <button
                          onClick={downloadMarkdown}
                          className="w-full text-left px-3.5 py-2.5 text-xs font-mono text-slate-300 hover:text-white hover:bg-slate-900 transition-colors flex items-center gap-2"
                        >
                          <FileText className="h-3.5 w-3.5 text-accent-blue" />
                          <span>Export Note (.md)</span>
                        </button>

                        <button
                          onClick={downloadPDF}
                          className="w-full text-left px-3.5 py-2.5 text-xs font-mono text-slate-300 hover:text-white hover:bg-slate-900 transition-colors flex items-center gap-2"
                        >
                          <FileText className="h-3.5 w-3.5 text-rose-500" />
                          <span>Export Note (.pdf)</span>
                        </button>
                        
                        <button
                          onClick={handleExportFlashcardsToAnki}
                          disabled={exportingAnki || isOfflineLoaded}
                          className="w-full text-left px-3.5 py-2.5 text-xs font-mono text-slate-300 hover:text-white hover:bg-slate-900 transition-colors flex items-center gap-2 disabled:opacity-50 disabled:hover:bg-transparent"
                          title={isOfflineLoaded ? "Anki export is unavailable offline" : ""}
                        >
                          {exportingAnki ? (
                            <RefreshCw className="h-3.5 w-3.5 text-accent-teal animate-spin" />
                          ) : (
                            <FileSpreadsheet className={`h-3.5 w-3.5 ${isOfflineLoaded ? 'text-slate-500' : 'text-accent-teal'}`} />
                          )}
                          <span>
                            {isOfflineLoaded ? 'Anki Export (Offline)' : exportingAnki ? 'Preparing CSV...' : 'Export Deck (Anki CSV)'}
                          </span>
                        </button>

                        {exportError && (
                          <div className="px-3 py-2 text-[10px] font-mono text-rose-400 bg-rose-950/15 border-t border-rose-950 leading-relaxed">
                            {exportError}
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
            </div>
          )}

          {/* Core Notes Viewer Area */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl min-h-[500px] shadow-xl space-y-6 relative">
            
            {/* Subtle Scroll Progress Bar at the top of notes display area */}
            {note && !generating && (
              <div className="sticky top-0 -mx-6 -mt-6 mb-6 z-30 h-1 bg-slate-950 rounded-t-2xl overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-accent-blue to-accent-teal transition-all duration-150 ease-out shadow-[0_0_8px_rgba(56,189,248,0.6)]" 
                  style={{ width: `${scrollProgress}%` }}
                />
              </div>
            )}

            {/* C10. Draft restoration alert banner */}
            {hasDraft && !isEditing && !generating && activeTopic && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 bg-accent-blue/10 border border-accent-blue/30 rounded-xl text-slate-200 text-xs font-mono leading-relaxed animate-fade-in shadow-md">
                <div className="flex items-start gap-2.5">
                  <Sparkles className="h-4 w-4 text-accent-blue animate-pulse shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-accent-blue uppercase tracking-wider block mb-0.5">Unsaved Draft Detected</span>
                    You have an unsaved note draft saved in your browser's local storage for this topic.
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                  <button 
                    onClick={() => {
                      setEditContent(draftContent);
                      setIsEditing(true);
                    }}
                    className="px-3 py-1.5 bg-accent-blue hover:bg-accent-blue/80 text-white rounded-lg transition-all font-semibold hover:scale-[1.02]"
                  >
                    Resume Draft
                  </button>
                  <button 
                    onClick={() => {
                      const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
                      localStorage.removeItem(draftKey);
                      setHasDraft(false);
                      setDraftContent('');
                    }}
                    className="px-3 py-1.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}

            {isEditing && activeTopic ? (
              /* MARKDOWN DRAFT EDITOR */
              <div className="space-y-4 animate-fade-in">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-4 gap-3">
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono text-accent-teal uppercase tracking-widest">
                      Drafting Study Note ({depth === '2mark' ? '2-Mark' : depth === '6mark' ? '6-Mark' : '10-Mark'})
                    </span>
                    <h2 className="text-xl font-display font-bold text-white tracking-tight">
                      {activeTopic.name}
                    </h2>
                  </div>
                  
                  <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400 bg-slate-950 px-3 py-1.5 border border-slate-800 rounded-lg">
                    <RefreshCw className="h-3.5 w-3.5 text-accent-blue animate-pulse shrink-0" />
                    <span>Draft auto-saving to local storage...</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-mono text-slate-400 block uppercase tracking-wider font-semibold">Note Body (Markdown)</label>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {editContent.length} characters
                    </span>
                  </div>
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    placeholder="Type or paste your study notes content here using standard Markdown formatting..."
                    className="w-full min-h-[420px] bg-slate-950 border border-slate-800 text-slate-100 text-sm font-mono p-5 rounded-xl focus:outline-none focus:ring-2 focus:ring-accent-blue/50 focus:border-accent-blue transition-all resize-y leading-relaxed"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                  <div className="text-[10px] text-slate-500 font-sans max-w-md leading-relaxed">
                    Formatting features: You can use headers (`#`), bullet lists (`-`), bold text (`**`), code blocks, process flow charts (with inline ```mermaid blocks), and citations.
                  </div>
                  
                  <div className="flex items-center gap-2.5">
                    <button
                      onClick={() => {
                        setEditContent(note?.content_md || '');
                        setIsEditing(false);
                      }}
                      className="px-4 py-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1.5"
                    >
                      <XCircle className="h-4 w-4 text-rose-500" />
                      <span>Cancel</span>
                    </button>
                    
                    <button
                      onClick={() => {
                        const draftKey = `tattva_draft_${activeTopic.id}_${depth}`;
                        localStorage.removeItem(draftKey);
                        setHasDraft(false);
                        setDraftContent('');
                        setEditContent(note?.content_md || '');
                        setIsEditing(false);
                      }}
                      className="px-4 py-2 bg-slate-950 hover:bg-rose-950/20 border border-rose-900/30 text-rose-400 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1.5"
                      title="Discard current unsaved draft and restore saved version"
                    >
                      <Trash2 className="h-4 w-4" />
                      <span>Discard Draft</span>
                    </button>

                    <button
                      onClick={handleSaveNote}
                      disabled={generating}
                      className="px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 text-white rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {generating ? (
                        <RefreshCw className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                      <span>{generating ? 'Saving Changes...' : 'Save Note'}</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : generating ? (
              /* SHIMMER LOADING EFFECT FOR NOTES GENERATION */
              <div className="space-y-6">
                {/* Header Shimmer */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-4 gap-3">
                  <div className="space-y-2.5 w-full max-w-sm">
                    <div className="h-3 w-28 bg-slate-800/80 rounded animate-shimmer" />
                    <div className="h-6 w-56 bg-slate-800/80 rounded animate-shimmer" />
                  </div>
                  <div className="h-8 w-24 bg-slate-800/80 rounded-full animate-shimmer" />
                </div>
                
                {/* Body Shimmer lines */}
                <div className="space-y-4">
                  <div className="h-4 w-full bg-slate-800/60 rounded animate-shimmer" />
                  <div className="h-4 w-11/12 bg-slate-800/60 rounded animate-shimmer" />
                  <div className="h-4 w-10/12 bg-slate-800/60 rounded animate-shimmer" />
                </div>
                
                <div className="space-y-4 pt-4">
                  <div className="h-4 w-full bg-slate-800/60 rounded animate-shimmer" />
                  <div className="h-4 w-9/12 bg-slate-800/60 rounded animate-shimmer" />
                  <div className="h-32 w-full bg-slate-950/80 rounded-xl border border-slate-800/40 p-4 flex flex-col justify-between items-center py-6">
                     <div className="h-3 w-1/4 bg-slate-800/50 rounded animate-shimmer" />
                     <div className="h-8 w-2/3 bg-slate-800/50 rounded animate-shimmer" />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="h-4 w-11/12 bg-slate-800/60 rounded animate-shimmer" />
                  <div className="h-4 w-8/12 bg-slate-800/60 rounded animate-shimmer" />
                </div>
              </div>
            ) : activeTopic ? (
              note ? (
                // NOTES CONTENT FOUND
                <div ref={notesContentRef} className="space-y-6">
                  
                  {isOfflineLoaded && (
                    <div className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400 text-xs font-mono leading-relaxed">
                      <WifiOff className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-bold uppercase tracking-wider block mb-1">Offline Cache Mode</span>
                        You are viewing locally stored notes cached in your browser's database. AI generation, real-time diagram drawing, and flashcard generation are unavailable offline, but you can copy and export these notes as Markdown at any time!
                      </div>
                    </div>
                  )}

                  {/* Topic Metadata & Confidence Banner */}
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-4 gap-3">
                    <div className="space-y-1">
                      <span className="text-[10px] font-mono text-accent-teal uppercase tracking-widest">{activeModule?.title}</span>
                      <h2 className="text-xl font-display font-bold text-white tracking-tight">{activeTopic.name}</h2>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-400">RAG VERDICT:</span>
                      <span className={`px-3 py-1 rounded-full text-xs font-mono flex items-center gap-1 capitalize ${
                        note.confidence === 'grounded' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        note.confidence === 'partial' ? 'bg-teal-500/10 text-teal-300 border border-teal-500/20' :
                        'bg-orange-500/10 text-orange-400 border border-orange-500/20'
                      }`}>
                        {note.confidence === 'grounded' ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                        {note.confidence}
                      </span>
                    </div>
                  </div>

                  {/* C10. Categorization Tags Section */}
                  <div className="bg-slate-950/40 border border-slate-800/60 p-4 rounded-xl space-y-3.5 shadow">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider text-slate-300">
                        <BookOpen className="h-4 w-4 text-accent-teal" />
                        <span>Categorization Tags</span>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        {isOnline && !isOfflineLoaded && (
                          <button
                            onClick={handleSuggestTags}
                            disabled={tagSuggesting}
                            className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-mono text-accent-blue hover:text-accent-blue/80 transition-all flex items-center gap-1.5 disabled:opacity-50"
                            title="Automatically suggest tags based on note content using Gemini"
                          >
                            <Sparkles className={`h-3.5 w-3.5 ${tagSuggesting ? 'animate-spin' : ''}`} />
                            {tagSuggesting ? 'Analyzing...' : 'AI Suggest Tags'}
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 min-h-[32px]">
                      {note.tags && note.tags.length > 0 ? (
                        note.tags.map((tag, i) => (
                          <span 
                            key={i} 
                            className="inline-flex items-center gap-1 px-3 py-1 bg-accent-teal/10 hover:bg-accent-teal/15 text-accent-teal hover:text-accent-teal/95 border border-accent-teal/20 hover:border-accent-teal/40 rounded-full text-xs font-mono transition-all group"
                          >
                            <span>#{tag}</span>
                            <button
                              onClick={() => handleRemoveTag(tag)}
                              className="text-slate-500 hover:text-rose-400 focus:outline-none shrink-0"
                              title={`Remove tag: ${tag}`}
                            >
                              <XCircle className="h-3.5 w-3.5 opacity-60 group-hover:opacity-100 transition-opacity" />
                            </button>
                          </span>
                        ))
                      ) : (
                        <p className="text-xs text-slate-500 italic font-mono py-1">No tags assigned. Click "AI Suggest Tags" or enter a custom tag below.</p>
                      )}
                    </div>

                    {/* Add Custom Tag Form */}
                    <form 
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (customTagInput.trim()) {
                          handleAddTag(customTagInput);
                          setCustomTagInput('');
                        }
                      }}
                      className="flex items-center gap-2 max-w-sm"
                    >
                      <input
                        type="text"
                        value={customTagInput}
                        onChange={(e) => setCustomTagInput(e.target.value)}
                        placeholder="Add custom tag (e.g. Thermodynamics)..."
                        className="w-full bg-slate-950/80 border border-slate-800 text-slate-300 text-xs font-mono px-3.5 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-accent-blue/50 focus:border-accent-blue transition-all"
                      />
                      <button
                        type="submit"
                        className="px-4 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-xs font-mono font-semibold rounded-lg transition-colors shrink-0"
                      >
                        Add
                      </button>
                    </form>
                  </div>

                  {/* Hallucination Guardrail Unsupported Warning Alert */}
                  {unsupportedSentences.length > 0 && (
                    <div className="p-4 bg-orange-500/10 border border-orange-500/30 rounded-xl space-y-2">
                      <div className="flex items-center gap-2 text-orange-400 text-xs font-mono font-bold uppercase">
                        <AlertTriangle className="h-4 w-4" />
                        Hallucination Guardrail Check Flagged ({unsupportedSentences.length}) Claims
                      </div>
                      <p className="text-[11px] text-slate-300 leading-relaxed font-sans">
                        Our post-generation safety model (C8 Prompt) cross-referenced this generated study note with the source text chunk embeddings and flagged the following claims as lacking direct proof:
                      </p>
                      <ul className="list-disc pl-5 text-[11px] text-slate-400 font-mono space-y-1.5">
                        {unsupportedSentences.map((sent, i) => (
                          <li key={i}>{sent}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* C9. Key Takeaways Summary Section */}
                  {summarizeEnabled && (
                    <div className="bg-slate-950/65 border border-accent-blue/20 rounded-xl p-5 space-y-3.5 shadow-lg relative overflow-hidden">
                      {/* Decorative Accent Glow */}
                      <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-accent-blue to-accent-teal" />
                      
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider text-accent-blue">
                          <Sparkles className="h-4 w-4 animate-pulse text-accent-teal" />
                          Key Takeaways
                        </div>
                        {summarizing && (
                          <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
                            <RefreshCw className="h-3 w-3 animate-spin text-accent-teal" />
                            Summarizing note...
                          </div>
                        )}
                        {!isOnline && !note.summary_md && (
                          <div className="text-[10px] font-mono text-amber-500 flex items-center gap-1">
                            <WifiOff className="h-3 w-3" />
                            Offline Mode
                          </div>
                        )}
                      </div>

                      {summarizing ? (
                        /* Takeaways Shimmer Loader */
                        <div className="space-y-3 pl-2.5">
                          <div className="flex items-center gap-2.5">
                            <div className="h-1.5 w-1.5 rounded-full bg-accent-blue/30 animate-pulse" />
                            <div className="h-3 w-5/6 bg-slate-800/80 rounded animate-shimmer" />
                          </div>
                          <div className="flex items-center gap-2.5">
                            <div className="h-1.5 w-1.5 rounded-full bg-accent-blue/30 animate-pulse" />
                            <div className="h-3 w-3/4 bg-slate-800/80 rounded animate-shimmer" />
                          </div>
                          <div className="flex items-center gap-2.5">
                            <div className="h-1.5 w-1.5 rounded-full bg-accent-blue/30 animate-pulse" />
                            <div className="h-3 w-4/5 bg-slate-800/80 rounded animate-shimmer" />
                          </div>
                        </div>
                      ) : note.summary_md ? (
                        /* Render Bullet Takeaways */
                        <div className="prose prose-invert max-w-none text-xs text-slate-300 leading-relaxed pl-1">
                          <ReactMarkdown>{note.summary_md}</ReactMarkdown>
                        </div>
                      ) : !isOnline ? (
                        <p className="text-xs text-slate-400 italic pl-1 font-mono">
                          Takeaways summary not cached. Connect online to generate.
                        </p>
                      ) : (
                        <p className="text-xs text-slate-400 italic pl-1 font-mono">
                          Ready to summarize notes. Toggle to active.
                        </p>
                      )}
                    </div>
                  )}

                  {/* Rendered Study Note Content */}
                  <div className="prose prose-invert prose-slate max-w-none text-slate-300 text-sm leading-relaxed space-y-4">
                    {renderNoteMarkdown(note.content_md)}
                  </div>

                  {/* Auto-Generate Spaced Repetition Decks */}
                  <div className="border-t border-slate-800/80 pt-6 mt-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-950/30 -mx-6 -mb-6 p-6 rounded-b-2xl">
                    <div className="space-y-1">
                      <p className="text-xs font-mono font-semibold text-white">Generate Spaced Repetition flashcards</p>
                      <p className="text-[10px] text-slate-400">Instantly convert these RAG study notes into flashcards with SM-2 scheduling</p>
                    </div>
                    <button
                      onClick={handleAutoGenerateFlashcards}
                      disabled={autoFcStatus === 'generating' || isOfflineLoaded}
                      className={`px-4 py-2.5 rounded-xl text-xs font-mono font-semibold transition-all flex items-center gap-2 ${
                        isOfflineLoaded ? 'bg-slate-850 text-slate-500 cursor-not-allowed border border-slate-800' :
                        autoFcStatus === 'success' ? 'bg-emerald-500 text-slate-950' :
                        autoFcStatus === 'generating' ? 'bg-slate-800 text-slate-500 cursor-not-allowed' :
                        'bg-accent-blue hover:bg-accent-blue/80 text-white shadow-md'
                      }`}
                    >
                      <Brain className="h-4 w-4" />
                      {isOfflineLoaded ? 'Unavailable Offline' :
                       autoFcStatus === 'generating' ? 'AI Analyzing...' :
                       autoFcStatus === 'success' ? 'Spaced Deck Created!' : 'Auto-Generate Spaced Cards'}
                    </button>
                  </div>

                </div>
              ) : (
                // NO NOTE GENERATED FOR THIS DEPTH LEVEL
                <div className="absolute inset-0 flex flex-col items-center justify-center p-8 text-center space-y-4">
                  <div className="p-4 bg-slate-950 border border-slate-800 text-accent-blue rounded-2xl shadow">
                    <Brain className="h-8 w-8" />
                  </div>
                  <div className="space-y-1.5 max-w-sm">
                    <h3 className="text-sm font-mono font-bold text-slate-200">No {depth === '2mark' ? '2-Mark' : depth === '6mark' ? '6-Mark' : '10-Mark'} Study Notes Available</h3>
                    <p className="text-xs text-slate-400 font-sans">
                      This topic doesn't have study notes cached at this exam depth. Trigger our grounding generation pipelines using parsed PDF chunks.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center justify-center gap-3">
                    <button
                      onClick={handleGenerateNotes}
                      disabled={generating || !isOnline}
                      className="px-5 py-2.5 bg-accent-blue hover:bg-accent-blue/80 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-xl text-xs font-mono font-bold transition-all shadow-md flex items-center gap-2 hover:scale-[1.01]"
                    >
                      {!isOnline ? (
                        <>
                          <WifiOff className="h-4 w-4 text-slate-500" />
                          Generation Offline
                        </>
                      ) : generating ? (
                        <>
                          <Sparkles className="h-4 w-4 animate-spin" />
                          Generating RAG Notes...
                        </>
                      ) : (
                        <>
                          <Play className="h-4 w-4" />
                          Assemble Grounded Study Notes
                        </>
                      )}
                    </button>

                    <button
                      onClick={() => {
                        setEditContent('');
                        setIsEditing(true);
                      }}
                      className="px-5 py-2.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-mono font-bold transition-all shadow-md flex items-center gap-2 hover:scale-[1.01]"
                    >
                      <PenSquare className="h-4 w-4 text-accent-blue" />
                      Write Custom Note
                    </button>
                  </div>
                </div>
              )
            ) : (
              // NO TOPIC SELECTED
              <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 font-mono text-xs">
                Select a module and topic to begin.
              </div>
            )}

          </div>

        </div>

        {/* 3. Citations & References Panel (Right column inside 3/4 workspace) */}
        <div className="lg:col-span-1 space-y-4">
          
          {/* Active Citations List */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-4 shadow-lg min-h-[300px]">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider pb-2 border-b border-slate-800">Verified Sources</h3>
            
            {citations.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2 font-mono">
                No citations found. Factual claims require document matching.
              </p>
            ) : (
              <div className="space-y-2">
                <p className="text-[10px] text-slate-400 font-sans leading-relaxed">
                  Every factual paragraph generated in Tattva is strictly cited to ensure academic integrity:
                </p>
                {citations.map((cite, i) => (
                  <div key={i} className="p-2.5 bg-slate-950 border border-slate-800 rounded-lg space-y-1">
                    <p className="text-xs font-medium text-slate-200 truncate">{cite.file}</p>
                    <div className="flex items-center justify-between text-[10px] font-mono text-accent-teal">
                      <span>Engineering Reference</span>
                      <span>Page {cite.page}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Generation Pipeline Context Panel */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3 shadow-lg">
            <h3 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">Note Architecture Rules</h3>
            <div className="space-y-2.5 text-[11px] leading-relaxed text-slate-400">
              <div className="p-2 bg-slate-950 rounded border border-slate-800/60 font-mono text-[10px]">
                <strong className="text-slate-200">2-Mark Depth:</strong> Focused definition/formula in 2-4 sentences max.
              </div>
              <div className="p-2 bg-slate-950 rounded border border-slate-800/60 font-mono text-[10px]">
                <strong className="text-slate-200">6-Mark Depth:</strong> Definition + detailed explanation + one real example or diagram reference.
              </div>
              <div className="p-2 bg-slate-950 rounded border border-slate-800/60 font-mono text-[10px]">
                <strong className="text-slate-200">10-Mark Depth:</strong> Full comprehensive breakdown, sub-points, advantage/disadvantage comparisons, and process flowchart.
              </div>
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
