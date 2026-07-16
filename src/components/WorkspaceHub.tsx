import React, { useState, useEffect, useMemo } from 'react';
import { 
  Cloud, BookOpen, GraduationCap, CheckCircle2, 
  RefreshCw, FileText, ArrowRight, Check, AlertCircle, 
  ExternalLink, UserCheck, ShieldAlert, Link2, FolderPlus, 
  FolderSymlink, Trash2, FolderOpen, CheckSquare, FileUp
} from 'lucide-react';
import { Subject } from '../types';
import { ClassroomIntegrationService } from '../services/ClassroomIntegrationService';

interface WorkspaceHubProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
  user: any;
  accessToken: string | null;
  onLogin: () => void;
  onLogout: () => void;
  onRefreshSubjects: () => void;
}

interface ClassroomCourse {
  id: string;
  name: string;
  section?: string;
  descriptionHeading?: string;
}

interface ClassroomMaterial {
  id: string;
  title: string;
  type: 'material' | 'coursework';
  mimeType?: string;
  alternateLink?: string;
  source: string;
  description?: string;
}

interface ClassroomMapping {
  id: string;
  course_id: string;
  course_name: string;
  subject_id: string;
  folder_id?: string;
  folder_name?: string;
}

interface ClassroomFolder {
  id: string;
  name: string;
  mimeType: string;
}

const formatSyncTime = (date: Date | null) => {
  if (!date) return 'Never synced';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' on ' + date.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

export default function WorkspaceHub({
  subjects,
  selectedSubject,
  user,
  accessToken,
  onLogin,
  onLogout,
  onRefreshSubjects
}: WorkspaceHubProps) {
  // Target Subject State for imports
  const [importSubjectId, setImportSubjectId] = useState<string>('');

  // Sync Status States
  const [lastSyncTime, setLastSyncTime] = useState<Date | null>(new Date());
  const [syncState, setSyncState] = useState<'idle' | 'syncing' | 'success' | 'failed'>('success');

  // Classroom States
  const [courses, setCourses] = useState<ClassroomCourse[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<string>('');
  const [courseMaterials, setCourseMaterials] = useState<ClassroomMaterial[]>([]);
  const [loadingCourses, setLoadingCourses] = useState<boolean>(false);
  const [loadingMaterials, setLoadingMaterials] = useState<boolean>(false);

  // Ingestion States
  const [ingestionStatus, setIngestionStatus] = useState<string>('');
  const [ingestingId, setIngestingId] = useState<string | null>(null);
  const [importLogs, setImportLogs] = useState<Array<{ name: string; type: string; time: string; status: 'success' | 'failed' }>>([]);

  // Mapping States
  const [mappings, setMappings] = useState<ClassroomMapping[]>([]);
  const [loadingMappings, setLoadingMappings] = useState<boolean>(false);
  const [subfolders, setSubfolders] = useState<ClassroomFolder[]>([]);
  const [loadingFolders, setLoadingFolders] = useState<boolean>(false);

  // New Mapping Creation States
  const [selectedMappingCourseId, setSelectedMappingCourseId] = useState<string>('');
  const [selectedMappingSubjectId, setSelectedMappingSubjectId] = useState<string>('');
  const [selectedMappingFolderId, setSelectedMappingFolderId] = useState<string>('');
  const [savingMapping, setSavingMapping] = useState<boolean>(false);

  // Expanded mapping details
  const [expandedMappingId, setExpandedMappingId] = useState<string | null>(null);
  const [expandedMappingFiles, setExpandedMappingFiles] = useState<any[]>([]);
  const [loadingExpandedFiles, setLoadingExpandedFiles] = useState<boolean>(false);

  // Instantiate the Classroom API Service
  const classroomService = useMemo(() => new ClassroomIntegrationService(accessToken), [accessToken]);

  const fetchMappings = async () => {
    setLoadingMappings(true);
    try {
      const data = await ClassroomIntegrationService.fetchMappings();
      setMappings(data);
    } catch (e) {
      console.error('Failed to fetch mappings:', e);
    } finally {
      setLoadingMappings(false);
    }
  };

  useEffect(() => {
    if (user) {
      fetchMappings();
    } else {
      setMappings([]);
    }
  }, [user]);

  const fetchCourseFolders = async (courseId: string) => {
    if (!accessToken) return;
    setLoadingFolders(true);
    try {
      const data = await classroomService.fetchCourseFolders(courseId);
      setSubfolders(data);
    } catch (e) {
      console.error('Failed to fetch course folders:', e);
      setSubfolders([]);
    } finally {
      setLoadingFolders(false);
    }
  };

  useEffect(() => {
    if (selectedMappingCourseId && accessToken) {
      fetchCourseFolders(selectedMappingCourseId);
      setSelectedMappingFolderId('');
    } else {
      setSubfolders([]);
    }
  }, [selectedMappingCourseId]);

  useEffect(() => {
    if (courses.length > 0 && !selectedMappingCourseId) {
      setSelectedMappingCourseId(courses[0].id);
    }
  }, [courses]);

  useEffect(() => {
    if (subjects.length > 0 && !selectedMappingSubjectId) {
      setSelectedMappingSubjectId(subjects[0].id);
    }
  }, [subjects]);

  const handleSaveMapping = async () => {
    if (!selectedMappingCourseId || !selectedMappingSubjectId) {
      alert("Please select a Classroom course and a Tattva Subject.");
      return;
    }
    setSavingMapping(true);
    try {
      const course = courses.find(c => c.id === selectedMappingCourseId);
      const folder = subfolders.find(f => f.id === selectedMappingFolderId);

      await ClassroomIntegrationService.createMapping({
        course_id: selectedMappingCourseId,
        course_name: course ? course.name : 'Unknown Course',
        subject_id: selectedMappingSubjectId,
        folder_id: selectedMappingFolderId || undefined,
        folder_name: folder ? folder.name : (selectedMappingFolderId ? 'Mapped Subfolder' : undefined)
      });
      
      await fetchMappings();
      
      setIngestionStatus(`Successfully mapped "${course?.name || 'Classroom Course'}" to Academic Subject.`);
    } catch (e: any) {
      console.error(e);
      alert('Failed to save mapping: ' + e.message);
    } finally {
      setSavingMapping(false);
    }
  };

  const handleDeleteMapping = async (id: string) => {
    try {
      await ClassroomIntegrationService.deleteMapping(id);
      setMappings(prev => prev.filter(m => m.id !== id));
      if (expandedMappingId === id) {
        setExpandedMappingId(null);
        setExpandedMappingFiles([]);
      }
      setIngestionStatus("Classroom-to-Subject mapping successfully removed.");
    } catch (e: any) {
      console.error(e);
      alert('Failed to delete mapping: ' + e.message);
    }
  };

  const fetchExpandedMappingFiles = async (mappingId: string) => {
    if (!accessToken) return;
    setLoadingExpandedFiles(true);
    try {
      const data = await classroomService.fetchMappedFiles(mappingId);
      setExpandedMappingFiles(data);
    } catch (e) {
      console.error('Failed to fetch files in mapped folder:', e);
      setExpandedMappingFiles([]);
    } finally {
      setLoadingExpandedFiles(false);
    }
  };

  useEffect(() => {
    if (expandedMappingId && accessToken) {
      fetchExpandedMappingFiles(expandedMappingId);
    } else {
      setExpandedMappingFiles([]);
    }
  }, [expandedMappingId]);

  const handleSyncMappedFile = async (mapping: ClassroomMapping, fileId: string, filename: string, mimeType: string) => {
    setIngestionStatus(`Importing and chunking "${filename}" into subject...`);
    setIngestingId(fileId);
    try {
      const res = await fetch('/api/drive/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fileId,
          filename,
          mimeType,
          subject_id: mapping.subject_id,
          accessToken
        })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      setImportLogs(prev => [
        { name: filename, type: 'Sync Folder File', time: new Date().toLocaleTimeString(), status: 'success' },
        ...prev
      ]);
      setIngestionStatus(`Success! Synced "${filename}" and created ${data.chunks_created} vector chunks.`);
      onRefreshSubjects();
    } catch (err: any) {
      console.error(err);
      setImportLogs(prev => [
        { name: filename, type: 'Sync Folder File', time: new Date().toLocaleTimeString(), status: 'failed' },
        ...prev
      ]);
      setIngestionStatus(`Sync failed: ${err.message}`);
    } finally {
      setIngestingId(null);
    }
  };

  // Default target subject
  useEffect(() => {
    if (selectedSubject && !importSubjectId) {
      setImportSubjectId(selectedSubject.id);
    }
  }, [selectedSubject]);

  // Fetch Classroom courses once token is available
  useEffect(() => {
    if (accessToken) {
      setSyncState('syncing');
      Promise.all([fetchCourses(), fetchMappings()])
        .then(() => {
          setLastSyncTime(new Date());
          setSyncState('success');
        })
        .catch((err) => {
          console.error('Initial sync failed:', err);
          setSyncState('failed');
        });
    } else {
      setCourses([]);
      setSelectedCourseId('');
      setCourseMaterials([]);
    }
  }, [accessToken]);

  // Fetch course materials when a course is selected
  useEffect(() => {
    if (selectedCourseId && accessToken) {
      fetchCourseMaterials(selectedCourseId);
    } else {
      setCourseMaterials([]);
    }
  }, [selectedCourseId]);

  const fetchCourses = async () => {
    setLoadingCourses(true);
    try {
      const data = await classroomService.fetchCourses();
      setCourses(data);
      if (data.length > 0) {
        setSelectedCourseId(data[0].id);
      }
    } catch (e: any) {
      console.error('Failed to fetch Classroom courses:', e);
    } finally {
      setLoadingCourses(false);
    }
  };

  const fetchCourseMaterials = async (courseId: string) => {
    setLoadingMaterials(true);
    try {
      const data = await classroomService.fetchCourseMaterials(courseId);
      setCourseMaterials(data);
    } catch (e: any) {
      console.error('Failed to fetch course materials:', e);
    } finally {
      setLoadingMaterials(false);
    }
  };

  // Google Picker Implementation
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
          reject(new Error('Google Client API (gapi) script could not be loaded. Please reload the page.'));
        }, 6000);
      }
    });
  };

  const handleOpenPicker = async () => {
    if (!accessToken) {
      alert("Please sign in to Google Workspace first.");
      return;
    }
    if (!importSubjectId) {
      alert("Please select a target subject to import files into.");
      return;
    }

    try {
      setIngestionStatus('Opening Google Picker...');
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
            
            await handleImportDriveFile(fileId, filename, mimeType);
          } else if (data.action === anyWin.google.picker.Action.CANCEL) {
            setIngestionStatus('');
          }
        })
        .build();
      picker.setVisible(true);
    } catch (err: any) {
      console.error('Picker initialization failed:', err);
      alert('Could not initialize Google Picker: ' + err.message);
      setIngestionStatus('');
    }
  };

  // Google Drive File Ingestion
  const handleImportDriveFile = async (fileId: string, filename: string, mimeType: string) => {
    setIngestionStatus(`Downloading and chunking "${filename}"...`);
    setIngestingId(fileId);
    try {
      const res = await fetch('/api/drive/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fileId,
          filename,
          mimeType,
          subject_id: importSubjectId,
          accessToken
        })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      
      // Log successful import
      setImportLogs(prev => [
        { name: filename, type: 'Drive File', time: new Date().toLocaleTimeString(), status: 'success' },
        ...prev
      ]);
      setIngestionStatus(`Success! Ingested ${data.pages_processed} pages and created ${data.chunks_created} vectors.`);
      onRefreshSubjects();
    } catch (err: any) {
      console.error(err);
      setImportLogs(prev => [
        { name: filename, type: 'Drive File', time: new Date().toLocaleTimeString(), status: 'failed' },
        ...prev
      ]);
      setIngestionStatus(`Import failed: ${err.message}`);
    } finally {
      setIngestingId(null);
    }
  };

  // Classroom Coursework to PYQ Exam Questions
  const handleImportCoursework = async (material: ClassroomMaterial) => {
    if (!importSubjectId) {
      alert("Please select a target subject to import questions into.");
      return;
    }
    const targetSubject = subjects.find(s => s.id === importSubjectId);
    if (!targetSubject) return;

    setIngestionStatus(`Parsing and mapping classroom assignment to ${targetSubject.code}...`);
    setIngestingId(material.id);

    try {
      const questionText = `${material.title}\n\nDescription:\n${material.description || 'No supplementary details provided.'}\n\n*Source: Google Classroom / Coursework Assignment*`;
      
      const res = await fetch('/api/pyqs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: importSubjectId,
          year: new Date().getFullYear(),
          question_text: questionText,
          marks: 10 // Assignments maps to a 10-mark complex item by default
        })
      });

      if (!res.ok) throw new Error(await res.text());
      
      setImportLogs(prev => [
        { name: material.title, type: 'Classroom Assignment', time: new Date().toLocaleTimeString(), status: 'success' },
        ...prev
      ]);
      setIngestionStatus(`Success! Added "${material.title}" as an active exam question in ${targetSubject.code}.`);
    } catch (err: any) {
      console.error(err);
      setImportLogs(prev => [
        { name: material.title, type: 'Classroom Assignment', time: new Date().toLocaleTimeString(), status: 'failed' },
        ...prev
      ]);
      setIngestionStatus(`Mapping coursework failed: ${err.message}`);
    } finally {
      setIngestingId(null);
    }
  };

  const handleManualSync = async () => {
    if (syncState === 'syncing') return;
    setSyncState('syncing');
    setIngestionStatus('Initiating full academic workspace synchronization...');
    try {
      if (accessToken) {
        await fetchCourses();
        if (selectedCourseId) {
          await fetchCourseMaterials(selectedCourseId);
        }
      }
      await fetchMappings();
      if (expandedMappingId && accessToken) {
        await fetchExpandedMappingFiles(expandedMappingId);
      }
      onRefreshSubjects();
      setLastSyncTime(new Date());
      setSyncState('success');
      setIngestionStatus('Workspace synchronization completed successfully.');
      setImportLogs(prev => [
        { name: 'Full Workspace Sync', type: 'Manual Sync', time: new Date().toLocaleTimeString(), status: 'success' },
        ...prev
      ]);
    } catch (err: any) {
      console.error('Workspace sync failed:', err);
      setSyncState('failed');
      setIngestionStatus(`Workspace sync failed: ${err.message}`);
      setImportLogs(prev => [
        { name: 'Full Workspace Sync', type: 'Manual Sync', time: new Date().toLocaleTimeString(), status: 'failed' },
        ...prev
      ]);
    }
  };

  return (
    <div id="workspace-hub" className="space-y-6">
      
      {/* Target Subject Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-lg">
        <div className="space-y-1">
          <label className="text-xs font-mono text-accent-teal uppercase tracking-wider">Target Academic Course</label>
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-accent-blue" />
            <select 
              value={importSubjectId} 
              onChange={(e) => setImportSubjectId(e.target.value)}
              className="bg-slate-950 text-white font-display text-base font-semibold border-0 outline-none focus:ring-0 cursor-pointer pr-10"
            >
              <option value="" disabled>-- Select Subject for Imports --</option>
              {subjects.map(s => (
                <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
              ))}
            </select>
          </div>
        </div>

        {user && (
          <div className="flex items-center gap-3 bg-slate-950 border border-slate-800/80 p-2.5 rounded-xl">
            <div className="text-right">
              <p className="text-[10px] font-mono text-[#D4AF37] uppercase tracking-wider font-bold">Workspace Active</p>
              <p className="text-xs text-slate-300 font-medium truncate max-w-[180px]">{user.email}</p>
            </div>
            <button 
              onClick={onLogout}
              className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[10px] font-mono text-slate-400 rounded-lg transition-colors"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {!user ? (
        /* Landing/Auth Required State */
        <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-8 md:p-12 text-center max-w-2xl mx-auto space-y-6 shadow-xl animate-fade-in">
          <div className="w-16 h-16 bg-gradient-to-br from-[#D4AF37] to-amber-600 rounded-2xl flex items-center justify-center mx-auto shadow-lg shadow-amber-500/10">
            <Cloud className="h-8 w-8 text-black" />
          </div>
          
          <div className="space-y-2">
            <h2 className="text-xl font-serif text-white tracking-wide">Sync Your Academic Workspace</h2>
            <p className="text-sm text-slate-400 leading-relaxed font-sans max-w-md mx-auto">
              Link Tattva with Google Workspace to automatically fetch reference coursework, parse lecture slides via Google Picker, and import homework assignments from Google Classroom.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3 max-w-md mx-auto py-2">
            <div className="p-3 bg-slate-950/60 border border-slate-800/50 rounded-xl space-y-1">
              <Cloud className="h-4 w-4 text-accent-blue mx-auto" />
              <p className="text-[10px] font-mono text-slate-300">Google Drive</p>
            </div>
            <div className="p-3 bg-slate-950/60 border border-slate-800/50 rounded-xl space-y-1">
              <FileText className="h-4 w-4 text-accent-teal mx-auto" />
              <p className="text-[10px] font-mono text-slate-300">Google Picker</p>
            </div>
            <div className="p-3 bg-slate-950/60 border border-slate-800/50 rounded-xl space-y-1">
              <GraduationCap className="h-4 w-4 text-[#D4AF37] mx-auto" />
              <p className="text-[10px] font-mono text-slate-300">Classroom Sync</p>
            </div>
          </div>

          <div className="pt-2">
            <button 
              onClick={onLogin}
              className="inline-flex items-center gap-3 px-6 py-3 bg-white hover:bg-slate-100 text-slate-900 rounded-xl font-mono text-xs font-bold transition-all shadow-lg shadow-white/5 active:scale-[0.98]"
            >
              <svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" className="h-4 w-4">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"></path>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"></path>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"></path>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"></path>
              </svg>
              Sign in with Google
            </button>
          </div>
        </div>
      ) : (
        /* Workspace Connected Workspace View */
        <div className="space-y-6 animate-fade-in">
          {/* Quick Sync Status Dashboard Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg">
            <div className="flex items-center gap-3">
              <div className="relative flex items-center justify-center">
                <div className={`w-3.5 h-3.5 rounded-full ${
                  syncState === 'syncing' 
                    ? 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse' 
                    : syncState === 'success' 
                    ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)] animate-pulse' 
                    : syncState === 'failed' 
                    ? 'bg-rose-500 shadow-[0_0_8px_rgba(239,68,68,0.6)] animate-pulse' 
                    : 'bg-slate-700'
                }`} />
              </div>
              <div>
                <p className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Workspace Sync Status</p>
                <div className="text-xs font-semibold text-white flex items-center gap-1.5 flex-wrap">
                  <span className={syncState === 'syncing' ? 'text-blue-400' : syncState === 'success' ? 'text-emerald-400' : 'text-rose-400'}>
                    {syncState === 'syncing' ? 'Syncing Classroom & Drive...' : syncState === 'success' ? 'Synchronized' : 'Sync Error'}
                  </span>
                  <span className="text-slate-500 font-normal hidden sm:inline">•</span>
                  <span className="text-slate-400 font-normal">Last Refreshed: {formatSyncTime(lastSyncTime)}</span>
                </div>
              </div>
            </div>
            <button
              onClick={handleManualSync}
              disabled={syncState === 'syncing'}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-slate-950 hover:bg-slate-800 border border-slate-850 hover:border-slate-750 disabled:opacity-40 text-xs font-mono text-slate-300 hover:text-white rounded-lg transition-all active:scale-[0.98] cursor-pointer"
            >
              <RefreshCw className={`h-3 w-3 text-accent-teal ${syncState === 'syncing' ? 'animate-spin' : ''}`} />
              Manual Sync
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Main Controls Panel (Left Col) */}
          <div className="lg:col-span-8 space-y-6">
            
            {/* INGESTION PROGRESS DISPLAYER */}
            {ingestionStatus && (
              <div className="bg-slate-900 border border-accent-blue/30 p-4 rounded-xl flex items-center justify-between gap-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <RefreshCw className="h-4 w-4 text-accent-teal animate-spin" />
                  <span className="text-xs font-mono text-slate-300">{ingestionStatus}</span>
                </div>
                <button 
                  onClick={() => setIngestionStatus('')}
                  className="text-[10px] font-mono text-slate-500 hover:text-slate-300"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Google Drive & Picker Module */}
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4 shadow-lg">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-accent-blue/10 text-accent-blue rounded-xl">
                  <Cloud className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold font-mono text-white">Google Drive Importer</h3>
                  <p className="text-[11px] text-slate-400 font-sans">Pick textbook guides or lecture slides using Google Picker</p>
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-850 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="space-y-1 max-w-md">
                  <p className="text-xs text-white font-medium">Browse files securely on Google Drive</p>
                  <p className="text-[10px] text-slate-400 font-sans">Imports PDFs or native Google Docs directly into the RAG vector store for the selected subject.</p>
                </div>
                <button 
                  onClick={handleOpenPicker}
                  className="w-full sm:w-auto px-4 py-2.5 bg-accent-blue hover:bg-accent-blue/80 text-white font-mono text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-2 shrink-0"
                >
                  <Cloud className="h-3.5 w-3.5" />
                  Open Google Picker
                </button>
              </div>
            </div>

            {/* Google Classroom Integration Module */}
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-5 shadow-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-xl">
                    <GraduationCap className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold font-mono text-white">Google Classroom Syllabi Sync</h3>
                    <p className="text-[11px] text-slate-400 font-sans">Pull course reference notes, lecture slide attachments, or coursework assignments</p>
                  </div>
                </div>

                <button 
                  onClick={fetchCourses}
                  disabled={loadingCourses}
                  className="p-1.5 bg-slate-950 hover:bg-slate-800 text-slate-400 rounded-lg transition-colors border border-slate-850"
                  title="Reload Google Classroom courses"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingCourses ? 'animate-spin text-accent-teal' : ''}`} />
                </button>
              </div>

              {loadingCourses ? (
                <div className="flex flex-col items-center justify-center py-8 space-y-2">
                  <RefreshCw className="h-5 w-5 text-slate-400 animate-spin" />
                  <p className="text-xs text-slate-500 font-mono">Syncing Class rosters & courses...</p>
                </div>
              ) : courses.length === 0 ? (
                <div className="p-4 bg-slate-950 border border-slate-850 rounded-xl text-center space-y-2">
                  <ShieldAlert className="h-5 w-5 text-slate-500 mx-auto" />
                  <p className="text-xs text-slate-400 font-mono">No active Google Classroom courses detected.</p>
                  <p className="text-[10px] text-slate-500 font-sans">Ensure you are logged in with the student/teacher email linked to Google Classroom classes.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Classroom Course Dropdown */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Connected Classroom Course</label>
                    <select
                      value={selectedCourseId}
                      onChange={(e) => setSelectedCourseId(e.target.value)}
                      className="w-full bg-slate-950 text-white border border-slate-800 rounded-xl p-3 text-xs focus:border-accent-blue focus:ring-0 cursor-pointer"
                    >
                      {courses.map(c => (
                        <option key={c.id} value={c.id}>{c.name} {c.section ? `(${c.section})` : ''}</option>
                      ))}
                    </select>
                  </div>

                  {/* Materials / Coursework Feed */}
                  <div className="space-y-2">
                    <h4 className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Classroom Academic Resources Feed</h4>
                    
                    {loadingMaterials ? (
                      <div className="flex flex-col items-center justify-center py-10 space-y-2 bg-slate-950/40 rounded-xl border border-slate-850">
                        <RefreshCw className="h-5 w-5 text-slate-400 animate-spin" />
                        <p className="text-xs text-slate-500 font-mono">Fetching announcements, materials & courseworks...</p>
                      </div>
                    ) : courseMaterials.length === 0 ? (
                      <p className="text-xs text-slate-500 italic font-sans p-4 bg-slate-950/40 rounded-xl text-center border border-slate-850">
                        No drive files or coursework assignments uploaded in this Classroom course yet.
                      </p>
                    ) : (
                      <div className="divide-y divide-slate-800/60 bg-slate-950/40 border border-slate-850 rounded-xl max-h-80 overflow-y-auto pr-1">
                        {courseMaterials.map(item => (
                          <div key={item.id} className="p-3.5 hover:bg-slate-950/80 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="space-y-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                                  item.type === 'material' ? 'bg-accent-teal/15 text-accent-teal' : 'bg-[#D4AF37]/15 text-[#D4AF37]'
                                }`}>
                                  {item.type === 'material' ? 'Lecture Slide / Material' : 'Coursework Assignment'}
                                </span>
                                <span className="text-[9px] font-mono text-slate-500">{item.source}</span>
                              </div>
                              <h5 className="text-xs font-semibold text-slate-200 truncate pr-4">{item.title}</h5>
                              {item.description && (
                                <p className="text-[10px] text-slate-400 truncate max-w-xl">{item.description}</p>
                              )}
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              {item.alternateLink && (
                                <a 
                                  href={item.alternateLink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="p-2 bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition-colors"
                                  title="View on Google Classroom"
                                >
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </a>
                              )}
                              
                              {item.type === 'material' ? (
                                <button
                                  onClick={() => handleImportDriveFile(item.id, item.title, item.mimeType || 'application/pdf')}
                                  disabled={ingestingId === item.id}
                                  className="px-3 py-1.5 bg-accent-teal/10 hover:bg-accent-teal text-accent-teal hover:text-slate-950 border border-accent-teal/20 text-[10px] font-mono font-bold rounded-lg transition-all"
                                >
                                  {ingestingId === item.id ? 'Syncing...' : 'Import to Syllabus'}
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleImportCoursework(item)}
                                  disabled={ingestingId === item.id}
                                  className="px-3 py-1.5 bg-[#D4AF37]/10 hover:bg-[#D4AF37] text-[#D4AF37] hover:text-slate-950 border border-[#D4AF37]/20 text-[10px] font-mono font-bold rounded-lg transition-all"
                                >
                                  {ingestingId === item.id ? 'Mapping...' : 'Map to PYQ'}
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Google Classroom Folder Mapping Service Card */}
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-6 shadow-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-accent-blue/10 text-accent-blue rounded-xl">
                    <FolderSymlink className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold font-mono text-white">Classroom Folder & Subject Mapper</h3>
                    <p className="text-[11px] text-slate-400 font-sans">Map specific Google Classroom courses/folders to Tattva subjects for easy document synchronisation</p>
                  </div>
                </div>
                
                <button 
                  onClick={fetchMappings}
                  disabled={loadingMappings}
                  className="p-1.5 bg-slate-950 hover:bg-slate-800 text-slate-400 rounded-lg transition-colors border border-slate-850"
                  title="Reload Mappings"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingMappings ? 'animate-spin text-accent-teal' : ''}`} />
                </button>
              </div>

              {/* Create New Mapping Form */}
              <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-850 space-y-4">
                <h4 className="text-xs font-mono font-bold text-accent-teal uppercase tracking-wider flex items-center gap-1.5">
                  <FolderPlus className="h-3.5 w-3.5" />
                  Create Academic Mapping
                </h4>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Select Course */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono text-slate-400 uppercase">1. Google Classroom Course</label>
                    <select
                      value={selectedMappingCourseId}
                      onChange={(e) => setSelectedMappingCourseId(e.target.value)}
                      className="w-full bg-slate-900 text-white border border-slate-800 rounded-lg p-2.5 text-xs focus:border-accent-blue focus:ring-0 cursor-pointer"
                    >
                      <option value="" disabled>-- Select Course --</option>
                      {courses.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>

                  {/* Select Tattva Subject */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono text-slate-400 uppercase">2. Tattva Academic Subject</label>
                    <select
                      value={selectedMappingSubjectId}
                      onChange={(e) => setSelectedMappingSubjectId(e.target.value)}
                      className="w-full bg-slate-900 text-white border border-slate-800 rounded-lg p-2.5 text-xs focus:border-accent-blue focus:ring-0 cursor-pointer"
                    >
                      <option value="" disabled>-- Select Subject --</option>
                      {subjects.map(s => (
                        <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Select Specific Folder */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono text-slate-400 uppercase">
                    3. Specific Google Drive Folder (Optional)
                  </label>
                  {loadingFolders ? (
                    <div className="flex items-center gap-2 py-2 text-xs text-slate-500 font-mono">
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      Loading folders...
                    </div>
                  ) : subfolders.length === 0 ? (
                    <div className="text-[11px] text-slate-500 italic p-2 bg-slate-900 rounded-lg">
                      No nested folders found in course folder. Will map to default Class Course folder.
                    </div>
                  ) : (
                    <select
                      value={selectedMappingFolderId}
                      onChange={(e) => setSelectedMappingFolderId(e.target.value)}
                      className="w-full bg-slate-900 text-white border border-slate-800 rounded-lg p-2.5 text-xs focus:border-accent-blue focus:ring-0 cursor-pointer"
                    >
                      <option value="">Course Root Folder (Default)</option>
                      {subfolders.map(f => (
                        <option key={f.id} value={f.id}>{f.name}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleSaveMapping}
                    disabled={savingMapping}
                    className="px-4 py-2 bg-accent-blue hover:bg-accent-blue/85 text-white font-mono text-xs font-bold rounded-lg transition-colors flex items-center gap-2 cursor-pointer"
                  >
                    <Link2 className="h-3.5 w-3.5" />
                    {savingMapping ? 'Linking...' : 'Establish Connection Mapping'}
                  </button>
                </div>
              </div>

              {/* Active Mappings List */}
              <div className="space-y-3">
                <h4 className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Active Folder Mappings ({mappings.length})</h4>
                
                {loadingMappings ? (
                  <div className="flex flex-col items-center justify-center py-6 space-y-2">
                    <RefreshCw className="h-5 w-5 text-slate-400 animate-spin" />
                    <p className="text-xs text-slate-500 font-mono">Loading active mappings...</p>
                  </div>
                ) : mappings.length === 0 ? (
                  <div className="p-4 bg-slate-950/40 border border-dashed border-slate-800 rounded-xl text-center">
                    <p className="text-xs text-slate-500 font-sans">No classroom folders mapped yet.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {mappings.map(map => {
                      const subject = subjects.find(s => s.id === map.subject_id);
                      const isExpanded = expandedMappingId === map.id;
                      
                      return (
                        <div key={map.id} className="border border-slate-800 bg-slate-950/40 rounded-xl overflow-hidden transition-all">
                          <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-950/60">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] font-mono font-bold bg-[#D4AF37]/10 text-[#D4AF37] px-2 py-0.5 rounded">
                                  Classroom
                                </span>
                                <ArrowRight className="h-3 w-3 text-slate-500" />
                                <span className="text-[10px] font-mono font-bold bg-accent-blue/10 text-accent-blue px-2 py-0.5 rounded">
                                  {subject ? subject.code : 'Unknown Subject'}
                                </span>
                              </div>
                              <h5 className="text-xs font-semibold text-white">
                                {map.course_name}
                              </h5>
                              <p className="text-[10px] text-slate-400 font-sans">
                                Folder: <span className="text-slate-300 font-mono font-medium">{map.folder_name || 'Course Root Folder'}</span>
                              </p>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              <button
                                onClick={() => {
                                  if (isExpanded) {
                                    setExpandedMappingId(null);
                                  } else {
                                    setExpandedMappingId(map.id);
                                  }
                                }}
                                className={`px-3 py-1.5 border rounded-lg text-[10px] font-mono font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
                                  isExpanded 
                                    ? 'bg-slate-800 border-slate-700 text-white' 
                                    : 'bg-slate-900 border-slate-800 hover:bg-slate-800 text-slate-300'
                                }`}
                              >
                                <FolderOpen className="h-3 w-3" />
                                {isExpanded ? 'Close Browser' : 'Browse Folder Files'}
                              </button>
                              
                              <button
                                onClick={() => handleDeleteMapping(map.id)}
                                className="p-2 bg-rose-500/10 hover:bg-rose-500 border border-rose-500/20 text-rose-400 hover:text-white rounded-lg transition-colors cursor-pointer"
                                title="Remove Mapping"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>

                          {/* Expanded File Browser Panel */}
                          {isExpanded && (
                            <div className="p-4 border-t border-slate-800/60 bg-slate-950/80 space-y-3">
                              <div className="flex items-center justify-between border-b border-slate-900 pb-2">
                                <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex items-center gap-1">
                                  <FileText className="h-3 w-3 text-accent-teal" />
                                  Classroom Drive files available
                                </span>
                                <button 
                                  onClick={() => fetchExpandedMappingFiles(map.id)}
                                  className="text-[9px] font-mono text-accent-teal hover:underline flex items-center gap-1"
                                >
                                  <RefreshCw className="h-2.5 w-2.5" />
                                  Refresh List
                                </button>
                              </div>

                              {loadingExpandedFiles ? (
                                <div className="flex items-center justify-center py-6 gap-2 text-xs text-slate-500 font-mono">
                                  <RefreshCw className="h-4 w-4 animate-spin text-accent-teal" />
                                  Scanning classroom folder...
                                </div>
                              ) : expandedMappingFiles.length === 0 ? (
                                <p className="text-xs text-slate-500 italic text-center py-4">
                                  No supported documents (PDFs or Google Docs) found in this mapped classroom folder yet.
                                </p>
                              ) : (
                                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                                  {expandedMappingFiles.map(file => (
                                    <div key={file.id} className="p-2.5 bg-slate-900/60 border border-slate-850 rounded-lg flex items-center justify-between gap-3 hover:bg-slate-900 transition-colors">
                                      <div className="flex items-center gap-2.5 min-w-0">
                                        <FileText className="h-4 w-4 text-accent-teal shrink-0" />
                                        <div className="min-w-0">
                                          <p className="text-xs text-slate-200 truncate font-sans font-medium" title={file.name}>
                                            {file.name}
                                          </p>
                                          <p className="text-[9px] text-slate-500 font-mono">
                                            {file.mimeType === 'application/pdf' ? 'PDF Guide' : 'Google Doc'}
                                          </p>
                                        </div>
                                      </div>

                                      <button
                                        onClick={() => handleSyncMappedFile(map, file.id, file.name, file.mimeType)}
                                        disabled={ingestingId === file.id}
                                        className="px-2.5 py-1 bg-accent-teal/10 hover:bg-accent-teal text-accent-teal hover:text-slate-950 border border-accent-teal/20 hover:border-transparent text-[10px] font-mono font-bold rounded transition-all shrink-0 cursor-pointer"
                                      >
                                        {ingestingId === file.id ? 'Syncing...' : 'Sync to Tattva'}
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

          </div>

          {/* Import Logs / Activity History Panel (Right Col) */}
          <div className="lg:col-span-4 space-y-6">
            
            {/* Sync Engine Control Center Card */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4 shadow-lg">
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)] animate-pulse" />
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-300">Sync Engine status</span>
                </div>
                <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${
                  syncState === 'syncing' 
                    ? 'bg-blue-500/15 text-blue-400' 
                    : syncState === 'success' 
                    ? 'bg-emerald-500/15 text-emerald-400' 
                    : syncState === 'failed' 
                    ? 'bg-rose-500/15 text-rose-400' 
                    : 'bg-slate-800 text-slate-400'
                }`}>
                  {syncState === 'syncing' ? 'SYNCING...' : syncState === 'success' ? 'SYNCHRONIZED' : syncState === 'failed' ? 'ERROR' : 'IDLE'}
                </span>
              </div>

              <div className="space-y-3">
                <div className="space-y-1">
                  <p className="text-[10px] font-mono text-slate-500 uppercase">Last Workspace Sync</p>
                  <p className="text-xs font-semibold text-white flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5 text-slate-400" />
                    {formatSyncTime(lastSyncTime)}
                  </p>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl space-y-2">
                  <p className="text-[10px] text-slate-400 leading-relaxed">
                    Tattva continuously pulls mapped classroom materials, reference handouts, and syllabus documents automatically. Press manual sync to force pull now.
                  </p>
                  
                  <button
                    onClick={handleManualSync}
                    disabled={syncState === 'syncing'}
                    className="w-full py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 disabled:opacity-40 text-slate-200 font-mono text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 text-accent-teal ${syncState === 'syncing' ? 'animate-spin' : ''}`} />
                    {syncState === 'syncing' ? 'Syncing Workspace...' : 'Manual Sync Refresh'}
                  </button>
                </div>
              </div>
            </div>

            {/* Subject Link Status Card */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4 shadow-lg">
              <h4 className="text-xs font-mono font-bold text-slate-300 uppercase">Selected Target Status</h4>
              
              {subjects.find(s => s.id === importSubjectId) ? (
                <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl space-y-3">
                  <div className="flex items-start gap-2.5">
                    <UserCheck className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-white">
                        {subjects.find(s => s.id === importSubjectId)?.code}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {subjects.find(s => s.id === importSubjectId)?.name}
                      </p>
                    </div>
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 border-t border-slate-900 pt-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                    Workspace pipelines calibrated
                  </div>
                </div>
              ) : (
                <div className="p-3.5 bg-slate-950/60 border border-dashed border-slate-800 rounded-xl flex items-center gap-2.5">
                  <AlertCircle className="h-4 w-4 text-orange-400 shrink-0" />
                  <p className="text-xs text-slate-400 font-sans">No subject target selected for sync import. Select above.</p>
                </div>
              )}
            </div>

            {/* Sync Activity Log */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4 shadow-lg">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-mono font-bold text-slate-300 uppercase">Live Import logs</h4>
                <span className="px-2 py-0.5 bg-slate-800 text-[10px] text-slate-400 rounded-full font-mono">{importLogs.length} synced</span>
              </div>

              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {importLogs.length === 0 ? (
                  <p className="text-xs text-slate-500 italic py-6 text-center font-sans">No recent workspace imports. Select a file or assignment to begin.</p>
                ) : (
                  importLogs.map((log, index) => (
                    <div key={index} className="p-2.5 bg-slate-950/60 border border-slate-850 rounded-xl space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[9px] font-mono text-slate-500">{log.time} · {log.type}</span>
                        <span className={`text-[9px] font-mono font-bold px-1 rounded ${
                          log.status === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                        }`}>
                          {log.status.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs font-medium text-slate-200 truncate" title={log.name}>{log.name}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

          </div>

        </div>
      </div>
      )}

    </div>
  );
}
