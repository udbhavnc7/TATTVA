import React, { useState, useEffect } from 'react';
import { FileText, RefreshCw, Sparkles, Brain, Download, HelpCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Subject } from '../types';
import { exportFormulaSheetToMarkdown } from '../utils/exportManager';

interface FormulaSheetProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
}

export default function FormulaSheet({ subjects, selectedSubject }: FormulaSheetProps) {
  const [sheetMd, setSheetMd] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selectedSubject) {
      fetchFormulaSheet();
    }
  }, [selectedSubject]);

  const fetchFormulaSheet = async () => {
    if (!selectedSubject) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/formulas?subjectId=${selectedSubject.id}`);
      const data = await res.json();
      setSheetMd(data.formula_sheet_md);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const downloadSheet = () => {
    if (!sheetMd || !selectedSubject) return;
    exportFormulaSheetToMarkdown(selectedSubject.code, selectedSubject.name, sheetMd);
  };

  return (
    <div id="formula-sheet" className="grid grid-cols-1 xl:grid-cols-4 gap-6">
      
      {/* 1. Sidebar guidelines (1/4 space) */}
      <div className="xl:col-span-1 space-y-4">
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
          <div className="flex items-center gap-2 text-white">
            <Brain className="h-4 w-4 text-accent-blue" />
            <h3 className="text-sm font-mono font-bold uppercase tracking-wider">Formula Scanner</h3>
          </div>
          <p className="text-xs text-slate-400 font-sans leading-relaxed">
            The formula scanner scans through your course lecture chunks and extracts mathematical formulas, networking models, signal rates, or algorithm pseudocode using the **C4 Prompt pipeline**.
          </p>
          <div className="border-t border-slate-800/80 pt-3 flex items-center gap-2">
            <button
              onClick={fetchFormulaSheet}
              disabled={loading || !selectedSubject}
              className="w-full py-2 bg-slate-950 hover:bg-slate-850 disabled:bg-slate-900 text-slate-300 hover:text-white border border-slate-800 rounded-lg text-xs font-mono font-medium transition-colors flex items-center justify-center gap-1.5"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
              Re-Scan Textbooks
            </button>
          </div>
        </div>

        {selectedSubject && sheetMd && (
          <button
            onClick={downloadSheet}
            className="w-full py-3 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-mono font-semibold transition-colors flex items-center justify-center gap-2 shadow-sm"
          >
            <Download className="h-4 w-4 text-accent-teal" />
            Export Equation Table
          </button>
        )}
      </div>

      {/* 2. Main Formula Table display (3/4 space) */}
      <div className="xl:col-span-3 space-y-4">
        
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl min-h-[500px]">
          {loading ? (
            /* SHIMMER LOADING EFFECT FOR EQUATION EXTRACTION */
            <div className="space-y-6">
              <div className="border-b border-slate-800 pb-3 flex flex-col gap-2">
                <div className="h-5 w-48 bg-slate-800 rounded animate-shimmer" />
                <div className="h-3 w-36 bg-slate-800/60 rounded animate-shimmer" />
              </div>
              <div className="flex items-center gap-2 text-xs font-mono text-slate-500 py-1 bg-slate-950/40 p-3 rounded-lg border border-slate-800/30">
                <RefreshCw className="h-3.5 w-3.5 text-accent-teal animate-spin" />
                <span>Running C4 extraction regex against material nodes...</span>
              </div>
              
              <div className="space-y-4 pt-2">
                {/* Simulated Table Rows */}
                <div className="grid grid-cols-3 gap-4 border-b border-slate-800 pb-3">
                  <div className="h-4 bg-slate-850 rounded w-2/3 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-11/12 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-1/2 animate-shimmer" />
                </div>
                <div className="grid grid-cols-3 gap-4 border-b border-slate-800 pb-3">
                  <div className="h-4 bg-slate-850 rounded w-3/4 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-5/6 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-2/3 animate-shimmer" />
                </div>
                <div className="grid grid-cols-3 gap-4 border-b border-slate-800 pb-3">
                  <div className="h-4 bg-slate-850 rounded w-1/2 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-full animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-1/3 animate-shimmer" />
                </div>
                <div className="grid grid-cols-3 gap-4 border-b border-slate-800 pb-3">
                  <div className="h-4 bg-slate-850 rounded w-2/3 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-10/12 animate-shimmer" />
                  <div className="h-4 bg-slate-850 rounded w-1/2 animate-shimmer" />
                </div>
              </div>
            </div>
          ) : selectedSubject ? (
            sheetMd ? (
              <div className="space-y-6">
                <div className="border-b border-slate-800 pb-3">
                  <h2 className="text-base font-display font-semibold text-white">Equation & Algorithm Sheet</h2>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">{selectedSubject.code} — {selectedSubject.name}</p>
                </div>

                {/* Structured Table Container */}
                <div className="prose prose-invert prose-sm max-w-none text-slate-300 font-sans overflow-x-auto">
                  <ReactMarkdown>{sheetMd}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center text-slate-500 font-mono text-xs">
                Formula sheet data could not be compiled. Trigger an active Textbook scan.
              </div>
            )
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center text-slate-500 font-mono text-xs">
              Select a subject to begin scanning.
            </div>
          )}
        </div>

      </div>

    </div>
  );
}
