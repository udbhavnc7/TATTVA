"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Depth = "2mark" | "6mark" | "10mark";
type ConfidenceBadge = "grounded" | "partial" | "needs_review";

interface Subject { id: string; name: string; code: string; }
interface Module { id: string; subject_id: string; number: number; title: string; }
interface Topic { id: string; module_id: string; name: string; version: number; }
interface Note {
    note_id: string; topic_id: string; depth: Depth;
    version: number; confidence: ConfidenceBadge; content_md: string; generated_at: string;
}

const BADGE_LABELS: Record<ConfidenceBadge, string> = {
    grounded: "Grounded",
    partial: "Partially Grounded",
    needs_review: "Needs Review",
};
const BADGE_STYLES: Record<ConfidenceBadge, string> = {
    grounded: "bg-green-900 text-green-300 border border-green-700",
    partial: "bg-yellow-900 text-yellow-300 border border-yellow-700",
    needs_review: "bg-red-900 text-red-300 border border-red-700",
};

function ConfidenceBadgeChip({ badge }: { badge: ConfidenceBadge }) {
    return (
        <span className={`text-xs px-2 py-0.5 rounded ${BADGE_STYLES[badge]}`} data-testid="confidence-badge">
            {BADGE_LABELS[badge]}
        </span>
    );
}

export default function NotesPage() {
    const [subjects, setSubjects] = useState<Subject[]>([]);
    const [modules, setModules] = useState<Module[]>([]);
    const [topics, setTopics] = useState<Topic[]>([]);
    const [selectedModule, setSelectedModule] = useState<string | null>(null);
    const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
    const [notes, setNotes] = useState<Note[]>([]);
    const [activeDepth, setActiveDepth] = useState<Depth>("2mark");
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 17.1 — Load subjects then modules
    useEffect(() => {
        fetch(`${API}/subjects`)
            .then((r) => r.json())
            .then((data: Subject[]) => {
                setSubjects(data);
                if (data.length > 0) {
                    return fetch(`${API}/subjects/${data[0].id}/modules`).then((r) => r.json());
                }
                return [];
            })
            .then((mods: Module[]) => setModules(mods))
            .catch(() => setError("Failed to load syllabus"));
    }, []);

    const selectModule = useCallback(async (moduleId: string) => {
        setSelectedModule(moduleId);
        setSelectedTopic(null);
        setNotes([]);
        // Get topics from coverage endpoint (per-topic list)
        try {
            const res = await fetch(`${API}/coverage`);
            const data = await res.json();
            // Filter topics belonging to this module
            const allTopics: Array<{ topic_id: string; topic_name: string; module_id: string }> = data.topics ?? [];
            const moduleTopics = allTopics
                .filter((t) => t.module_id === moduleId)
                .map((t) => ({ id: t.topic_id, module_id: t.module_id, name: t.topic_name, version: 1 }));
            setTopics(moduleTopics);
        } catch {
            setTopics([]);
        }
    }, []);

    const selectTopic = useCallback(async (topic: Topic) => {
        setSelectedTopic(topic);
        try {
            const res = await fetch(`${API}/notes/${topic.id}`);
            const data: Note[] = await res.json();
            setNotes(data);
        } catch {
            setNotes([]);
        }
    }, []);

    // 17.3 — Generate grounded study notes
    const handleGenerate = async () => {
        if (!selectedTopic) return;
        setGenerating(true);
        setError(null);
        try {
            const res = await fetch(`${API}/generate-notes`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic_id: selectedTopic.id, depth: activeDepth }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err?.detail?.detail ?? "Generation failed");
            }
            // Refresh notes
            const noteRes = await fetch(`${API}/notes/${selectedTopic.id}`);
            setNotes(await noteRes.json());
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setGenerating(false);
        }
    };

    const activeNote = notes.find((n) => n.depth === activeDepth);

    return (
        <div className="flex min-h-screen bg-background text-foreground">
            {/* 17.1 — Left panel: modules + topics */}
            <aside className="w-64 border-r border-[#222] bg-[#0a0a0a] flex flex-col p-4 gap-2 overflow-y-auto">
                <h2 className="text-[#C9A84C] font-semibold mb-2">Modules</h2>
                {modules.map((mod) => (
                    <div key={mod.id}>
                        <button
                            onClick={() => selectModule(mod.id)}
                            className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${selectedModule === mod.id
                                    ? "bg-[#C9A84C]/20 text-[#C9A84C]"
                                    : "text-gray-400 hover:text-white hover:bg-[#1a1a1a]"
                                }`}
                        >
                            Module {mod.number}: {mod.title}
                        </button>
                        {selectedModule === mod.id && topics.map((topic) => (
                            <button
                                key={topic.id}
                                onClick={() => selectTopic(topic)}
                                className={`w-full text-left pl-6 pr-3 py-1.5 rounded text-xs transition-colors ${selectedTopic?.id === topic.id
                                        ? "text-white font-semibold"
                                        : "text-gray-500 hover:text-gray-300"
                                    }`}
                            >
                                {topic.name}
                            </button>
                        ))}
                    </div>
                ))}
                {modules.length === 0 && (
                    <p className="text-gray-600 text-xs">No modules found.</p>
                )}
            </aside>

            {/* 17.2 — Right panel: depth tabs + note */}
            <main className="flex-1 p-6 overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                    <h1 className="text-2xl font-bold text-[#C9A84C]">
                        {selectedTopic ? selectedTopic.name : "Grounded Notes"}
                    </h1>
                    {/* 17.3 — Generate button */}
                    <button
                        onClick={handleGenerate}
                        disabled={!selectedTopic || generating}
                        data-testid="generate-button"
                        className={`px-4 py-2 rounded text-sm font-medium min-h-[44px] min-w-[44px] transition-colors ${selectedTopic && !generating
                                ? "bg-[#C9A84C] text-black hover:bg-yellow-400"
                                : "bg-[#2a2a2a] text-gray-600 cursor-not-allowed"
                            }`}
                    >
                        {generating ? "Generating…" : "Generate Grounded Study Notes"}
                    </button>
                </div>

                {error && (
                    <div className="mb-4 rounded bg-red-900/30 border border-red-700 px-4 py-2 text-red-300 text-sm">
                        {error}
                    </div>
                )}

                {/* Depth tabs */}
                <div className="flex gap-2 mb-4">
                    {(["2mark", "6mark", "10mark"] as Depth[]).map((d) => (
                        <button
                            key={d}
                            onClick={() => setActiveDepth(d)}
                            className={`px-4 py-2 rounded text-sm min-h-[44px] ${activeDepth === d
                                    ? "bg-[#C9A84C] text-black font-semibold"
                                    : "bg-[#1a1a1a] text-gray-400 hover:text-white"
                                }`}
                        >
                            {d}
                        </button>
                    ))}
                </div>

                {/* Note content or empty state */}
                {!selectedTopic ? (
                    <div className="text-gray-500 text-sm mt-8">
                        Select a topic from the left panel to view or generate notes.
                    </div>
                ) : activeNote ? (
                    <div
                        className={`rounded-lg p-5 border ${activeNote.confidence === "needs_review"
                                ? "border-amber-500 ring-1 ring-amber-500"
                                : "border-[#222]"
                            } bg-[#111] relative`}
                        data-testid="note-card"
                    >
                        {/* 17.7 — Amber warning for needs_review */}
                        {activeNote.confidence === "needs_review" && (
                            <div className="flex items-center gap-2 text-amber-400 text-xs mb-3" data-testid="needs-review-warning">
                                ⚠️ This note needs review — some content may not be fully grounded.
                            </div>
                        )}

                        {/* 17.4 — Confidence badge */}
                        <div className="flex items-center gap-2 mb-3">
                            <ConfidenceBadgeChip badge={activeNote.confidence} />
                            <span className="text-gray-500 text-xs">v{activeNote.version}</span>
                        </div>

                        {/* Note body */}
                        <pre className="whitespace-pre-wrap text-sm text-gray-200 font-sans leading-relaxed">
                            {activeNote.content_md}
                        </pre>

                        {/* 17.5 — Verified Sources */}
                        <div className="mt-4 pt-3 border-t border-[#222]">
                            <h4 className="text-xs font-semibold text-gray-400 mb-1">Verified Sources</h4>
                            {activeNote.confidence === "needs_review" ? (
                                <p className="text-xs text-gray-600">No verified sources available.</p>
                            ) : (
                                <p className="text-xs text-gray-400">
                                    Sources embedded in note citations above.
                                </p>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="mt-8 text-gray-500 text-sm">
                        No {activeDepth} note available for this topic. Click "Generate" to create one.
                    </div>
                )}

                {/* 17.6 — Note Architecture Rules */}
                {selectedTopic && (
                    <aside className="mt-6 p-4 rounded border border-[#222] bg-[#0a0a0a] text-xs text-gray-500">
                        <h4 className="text-gray-300 font-semibold mb-2">Note Architecture Rules</h4>
                        <ol className="list-decimal list-inside space-y-1">
                            <li>Every claim must trace to a cited source page.</li>
                            <li>The system refuses to fill gaps from LLM training data.</li>
                            <li>Confidence Validator reviews every note before storage.</li>
                        </ol>
                    </aside>
                )}
            </main>
        </div>
    );
}
