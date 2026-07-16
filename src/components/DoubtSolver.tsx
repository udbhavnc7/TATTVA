import React, { useState, useRef, useEffect } from 'react';
import { Send, Brain, Bot, User, RefreshCw, Sparkles, BookOpen, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Subject } from '../types';

interface Message {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  timestamp: string;
  citations?: Array<{
    filename: string;
    page_number: number;
    similarity: number;
  }>;
}

interface DoubtSolverProps {
  subjects: Subject[];
  selectedSubject: Subject | null;
}

export default function DoubtSolver({ subjects, selectedSubject }: DoubtSolverProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'bot',
      text: "Hello! I am your Tattva academic Socratic assistant. I resolve doubts **ONLY** using your uploaded lecture PDFs and textbooks.\n\nAsk me any concept, equation, or process in your course, and I will find the source material, quote the exact page references, and check your understanding with Socratic check-ins!",
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [querying, setQuerying] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollToBottom();
  }, [messages, querying]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !selectedSubject) return;

    const userText = inputText.trim();
    setInputText('');

    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setQuerying(true);

    try {
      const res = await fetch('/api/query-doubt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subjectId: selectedSubject.id,
          question: userText
        })
      });

      if (res.ok) {
        const data = await res.json();
        const botMsg: Message = {
          id: `bot-${Date.now()}`,
          sender: 'bot',
          text: data.answer,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          citations: data.citations
        };
        setMessages(prev => [...prev, botMsg]);
      } else {
        throw new Error(await res.text());
      }
    } catch (e: any) {
      console.error(e);
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        sender: 'bot',
        text: `Error contacting Socratic doubt solver: ${e.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setQuerying(false);
    }
  };

  return (
    <div id="doubt-solver" className="grid grid-cols-1 xl:grid-cols-4 gap-6 h-[600px]">
      
      {/* 1. Left Guidelines Column (1/4 space) */}
      <div className="xl:col-span-1 space-y-4 flex flex-col justify-between h-full">
        
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg space-y-4">
          <div className="flex items-center gap-2 text-white">
            <Brain className="h-4 w-4 text-accent-teal" />
            <h3 className="text-sm font-mono font-bold uppercase tracking-wider">Socratic Solver Core</h3>
          </div>
          
          <div className="space-y-3 text-xs leading-relaxed text-slate-400 font-sans">
            <p>
              Traditional AI chatbot answers include generalized public data. The **Tattva Socratic Check Solver** is strictly bounded:
            </p>
            <ul className="list-disc pl-5 space-y-1.5 font-mono text-[10px]">
              <li>Searches knowledge store vectors</li>
              <li>Pins response directly to text chunks</li>
              <li>Quotes PDF filenames and page citations</li>
              <li>Initiates Socratic follow-ups to calibration checks</li>
            </ul>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl shadow-lg">
          <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400 uppercase">
            <BookOpen className="h-4 w-4 text-accent-blue" />
            Active Syllabus:
          </div>
          <p className="text-xs font-semibold text-slate-200 mt-1 font-display">
            {selectedSubject ? `${selectedSubject.code} — ${selectedSubject.name}` : 'No Subject Selected'}
          </p>
        </div>

      </div>

      {/* 2. Main Chat Workspace (3/4 space) */}
      <div className="xl:col-span-3 flex flex-col bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden h-full">
        
        {/* Chat Messages Log */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 scroll-smooth">
          {messages.map(msg => (
            <div 
              key={msg.id} 
              className={`flex items-start gap-3.5 max-w-3xl ${msg.sender === 'user' ? 'ml-auto flex-row-reverse' : ''}`}
            >
              {/* Avatar Icon */}
              <div className={`p-2 rounded-xl border shrink-0 ${
                msg.sender === 'user' 
                  ? 'bg-accent-blue/15 border-accent-blue/40 text-accent-blue' 
                  : 'bg-accent-teal/15 border-accent-teal/40 text-accent-teal'
              }`}>
                {msg.sender === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>

              {/* Message Bubble */}
              <div className="space-y-2 max-w-xl">
                <div className={`p-4 rounded-2xl border text-sm leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-accent-blue/10 border-accent-blue/20 text-slate-200 rounded-tr-none'
                    : 'bg-slate-950 border-slate-800/80 text-slate-300 rounded-tl-none'
                }`}>
                  <div className="prose prose-invert prose-sm max-w-none space-y-2">
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                  </div>
                </div>

                {/* Citations Attached to Bot Message */}
                {msg.sender === 'bot' && msg.citations && msg.citations.length > 0 && (
                  <div className="space-y-1.5 pl-2 border-l-2 border-accent-teal/30">
                    <p className="text-[10px] font-mono text-slate-500 uppercase font-bold tracking-wider">Semantic Sources Cited ({msg.citations.length}):</p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((cite, i) => (
                        <div key={i} className="px-2 py-1 bg-slate-950 border border-slate-850 rounded text-[10px] font-mono text-slate-400 flex items-center gap-1 shadow-sm">
                          <span className="text-slate-500 truncate max-w-32">{cite.filename}</span>
                          <span className="text-accent-teal font-semibold">p.{cite.page_number}</span>
                          <span className="text-slate-600">({cite.similarity}%)</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <span className={`block text-[10px] font-mono text-slate-500 ${msg.sender === 'user' ? 'text-right' : ''}`}>
                  {msg.timestamp}
                </span>
              </div>
            </div>
          ))}

          {/* Loader Bubble with Shimmer Skeleton */}
          {querying && (
            <div className="flex items-start gap-3.5">
              <div className="p-2 rounded-xl border shrink-0 bg-accent-teal/15 border-accent-teal/40 text-accent-teal">
                <Bot className="h-4 w-4" />
              </div>
              <div className="space-y-2 w-full max-w-md">
                <div className="p-4 bg-slate-950 border border-slate-800/80 rounded-2xl rounded-tl-none space-y-3">
                  <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500 pb-2 border-b border-slate-900">
                    <Sparkles className="h-3.5 w-3.5 text-accent-teal animate-spin" />
                    Consulting course syllabus & textbooks...
                  </div>
                  <div className="h-3 w-11/12 bg-slate-900 rounded animate-shimmer" />
                  <div className="h-3 w-10/12 bg-slate-900 rounded animate-shimmer" />
                  <div className="h-3 w-3/4 bg-slate-900 rounded animate-shimmer" />
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Question Inputs */}
        <form onSubmit={handleSendMessage} className="p-4 bg-slate-950 border-t border-slate-800 flex gap-3">
          <input
            type="text"
            placeholder={selectedSubject ? `Ask a doubt about ${selectedSubject.name}...` : 'Select a course syllabus first'}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={querying || !selectedSubject}
            className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-3 text-sm text-white placeholder-slate-500 focus:border-accent-teal focus:outline-none focus:ring-0 disabled:bg-slate-900/40 disabled:text-slate-600 disabled:cursor-not-allowed"
            required
          />
          <button
            type="submit"
            disabled={querying || !inputText.trim() || !selectedSubject}
            className="px-4 py-3 bg-accent-teal hover:bg-accent-teal/80 disabled:bg-slate-800 disabled:text-slate-600 rounded-xl text-slate-950 flex items-center justify-center transition-all shadow"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>

      </div>

    </div>
  );
}
