import { useState, useEffect } from 'react';
import { 
  Layers, BookOpen, GraduationCap, Brain, HelpCircle, 
  FileText, Activity, Compass, Settings, Sparkles, Globe,
  Sun, Moon
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

import { Subject } from './types';
import CoverageTracker from './components/CoverageTracker';
import NotesEngine from './components/NotesEngine';
import PYQManager from './components/PYQManager';
import FlashcardsReview from './components/FlashcardsReview';
import DoubtSolver from './components/DoubtSolver';
import FormulaSheet from './components/FormulaSheet';
import WorkspaceHub from './components/WorkspaceHub';
import { initAuth, googleSignIn, logout } from './auth';

export default function App() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<Subject | null>(null);
  const [activeTab, setActiveTab] = useState<'coverage' | 'notes' | 'pyqs' | 'flashcards' | 'doubt' | 'formulas' | 'workspace'>('coverage');

  // Theme Management
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('theme') as 'dark' | 'light') || 'dark';
    }
    return 'dark';
  });

  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.classList.add('light');
    } else {
      document.documentElement.classList.remove('light');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Firebase Google Workspace Auth States
  const [user, setUser] = useState<any>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  useEffect(() => {
    fetchSubjects();

    // Initialize the Firebase auth state listener
    const unsubscribe = initAuth(
      (currentUser, token) => {
        setUser(currentUser);
        setAccessToken(token);
      },
      () => {
        setUser(null);
        setAccessToken(null);
      }
    );
    return () => unsubscribe();
  }, []);

  const fetchSubjects = async () => {
    try {
      const res = await fetch('/api/subjects');
      const data = await res.json();
      setSubjects(data);
      if (data.length > 0 && !selectedSubject) {
        setSelectedSubject(data[0]);
      }
    } catch (e) {
      console.error('Failed to fetch subjects:', e);
    }
  };

  const handleLogin = async () => {
    try {
      const result = await googleSignIn();
      if (result) {
        setUser(result.user);
        setAccessToken(result.accessToken);
      }
    } catch (err: any) {
      console.error("Login failed:", err);
      alert("Sign-in failed. Please verify popup blocks are disabled.");
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      setUser(null);
      setAccessToken(null);
    } catch (err: any) {
      console.error("Logout failed:", err);
    }
  };

  return (
    <div id="tattva-app" className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col md:flex-row">
      
      {/* 1. SIDEBAR NAVIGATION */}
      <aside className="w-full md:w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between shrink-0">
        <div className="p-6 space-y-6">
          
          {/* Brand Identity / Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-[#D4AF37] to-[#8A6D3B] rounded-xl flex items-center justify-center shadow-lg shadow-[#D4AF37]/15">
              <span className="text-black font-serif font-bold text-lg">T</span>
            </div>
            <div className="space-y-0.5">
              <h1 className="font-serif font-light text-xl leading-none text-slate-100 tracking-widest">TATTVA</h1>
              <p className="text-[9px] font-mono text-[#D4AF37] uppercase tracking-[0.2em] font-bold">Exam Engine</p>
            </div>
          </div>
 
          {/* Nav Links */}
          <nav className="space-y-1">
            <h2 className="text-[10px] font-mono text-slate-500 uppercase tracking-widest px-2.5 pb-2">Academic Core</h2>
            {[
              { id: 'coverage', label: 'Syllabus Coverage', icon: Layers },
              { id: 'notes', label: 'Grounded Notes', icon: BookOpen },
              { id: 'pyqs', label: 'PYQ Exam Paper', icon: GraduationCap },
              { id: 'flashcards', label: 'Spaced Repetition', icon: Brain },
              { id: 'doubt', label: 'Socratic Q&A', icon: HelpCircle },
              { id: 'formulas', label: 'Formula Sheet', icon: FileText }
            ].map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold font-mono transition-all ${
                    activeTab === tab.id 
                      ? 'bg-slate-950 border border-slate-800 text-slate-100 shadow-inner shadow-black/40' 
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-950/20'
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${activeTab === tab.id ? 'text-accent-teal' : 'text-slate-500'}`} />
                  {tab.label}
                </button>
              );
            })}

            <h2 className="text-[10px] font-mono text-slate-500 uppercase tracking-widest px-2.5 pt-4 pb-2">Integrations</h2>
            {[
              { id: 'workspace', label: 'Google Workspace', icon: Globe }
            ].map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold font-mono transition-all ${
                    activeTab === tab.id 
                      ? 'bg-slate-950 border border-slate-800 text-slate-100 shadow-inner shadow-black/40' 
                      : 'text-[#D4AF37] hover:text-[#D4AF37]/85 hover:bg-slate-950/20'
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${activeTab === tab.id ? 'text-[#D4AF37]' : 'text-[#8A6D3B]'}`} />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User Identity profile & Instance State */}
        <div className="p-5 border-t border-slate-800 space-y-4">
          {user ? (
            <div className="p-3 bg-slate-950/50 rounded-xl border border-slate-800/40 space-y-2">
              <div className="flex items-center gap-2">
                {user.photoURL ? (
                  <img 
                    src={user.photoURL} 
                    alt="avatar" 
                    referrerPolicy="no-referrer" 
                    className="w-7 h-7 rounded-full border border-slate-700 shrink-0" 
                  />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-slate-800 flex items-center justify-center text-xs font-mono font-bold text-slate-300 shrink-0 border border-slate-700">
                    {user.email?.charAt(0).toUpperCase() || 'U'}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] font-mono text-slate-500 uppercase">Workspace Connected</p>
                  <p className="text-xs font-semibold text-slate-200 truncate">{user.displayName || user.email}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-3 bg-slate-950/50 rounded-xl border border-slate-800/40 space-y-2">
              <p className="text-[10px] font-mono text-slate-500 uppercase">Current User</p>
              <div className="flex items-center justify-between gap-1">
                <p className="text-xs font-medium text-slate-400 truncate max-w-[120px]">Local Mode</p>
                <button 
                  onClick={handleLogin}
                  className="px-2 py-1 bg-accent-blue hover:bg-accent-blue/80 text-[9px] font-mono font-bold text-white rounded transition-colors"
                >
                  Link Google
                </button>
              </div>
            </div>
          )}

          {/* Theme Mode Toggle */}
          <div className="pt-2 border-t border-slate-800/40 flex items-center justify-between">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Appearance</span>
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-950 hover:bg-slate-850 text-[10px] font-mono font-bold text-slate-300 hover:text-white rounded-lg border border-slate-800 transition-all active:scale-95 shadow-sm"
              title="Toggle between Sophisticated Dark and Classic Light modes"
            >
              {theme === 'dark' ? (
                <>
                  <Sun className="h-3.5 w-3.5 text-amber-400" />
                  <span>Classic Light</span>
                </>
              ) : (
                <>
                  <Moon className="h-3.5 w-3.5 text-indigo-400" />
                  <span>Sophisticated Dark</span>
                </>
              )}
            </button>
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 px-1 pt-1">
            <span>Calibrated Engine</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)] animate-pulse" />
              v3.0.0
            </span>
          </div>
        </div>
      </aside>

      {/* 2. MAIN APPLICATION WORKSPACE */}
      <main className="flex-1 p-6 md:p-8 space-y-6 overflow-x-hidden">
        
        {/* Dynamic Section Contents based on activeTab with smooth Framer Motion transition */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="w-full"
          >
            {activeTab === 'coverage' && (
              <CoverageTracker 
                subjects={subjects}
                selectedSubject={selectedSubject}
                onSelectSubject={setSelectedSubject}
                onRefreshSubjects={fetchSubjects}
              />
            )}

            {activeTab === 'notes' && (
              <NotesEngine 
                subjects={subjects}
                selectedSubject={selectedSubject}
              />
            )}

            {activeTab === 'pyqs' && (
              <PYQManager 
                subjects={subjects}
                selectedSubject={selectedSubject}
              />
            )}

            {activeTab === 'flashcards' && (
              <FlashcardsReview 
                subjects={subjects}
                selectedSubject={selectedSubject}
              />
            )}

            {activeTab === 'doubt' && (
              <DoubtSolver 
                subjects={subjects}
                selectedSubject={selectedSubject}
              />
            )}

            {activeTab === 'formulas' && (
              <FormulaSheet 
                subjects={subjects}
                selectedSubject={selectedSubject}
              />
            )}

            {activeTab === 'workspace' && (
              <WorkspaceHub 
                subjects={subjects}
                selectedSubject={selectedSubject}
                user={user}
                accessToken={accessToken}
                onLogin={handleLogin}
                onLogout={handleLogout}
                onRefreshSubjects={fetchSubjects}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

    </div>
  );
}
