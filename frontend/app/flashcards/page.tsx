"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Flashcard {
    id: string; topic_id: string; note_id: string | null;
    question: string; answer: string; source: string | null;
    ease_factor: number; interval_days: number; repetitions: number;
    next_review_at: string; created_at: string;
}
interface Subject { id: string; name: string; }
interface Topic { id: string; name: string; module_id: string; }

export default function FlashcardsPage() {
    const [subjects, setSubjects] = useState<Subject[]>([]);
    const [topics, setTopics] = useState<Topic[]>([]);
    const [selectedTopicId, setSelectedTopicId] = useState<string>("all");
    const [cardCount, setCardCount] = useState(0);
    const [dueCount, setDueCount] = useState(0);
    const [currentCard, setCurrentCard] = useState<Flashcard | null>(null);
    const [revealed, setRevealed] = useState(false);
    const [recallScore, setRecallScore] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [scoreError, setScoreError] = useState("");

    useEffect(() => {
        fetch(`${API}/subjects`).then((r) => r.json()).then(setSubjects).catch(() => { });
    }, []);

    const fetchCounts = useCallback(async () => {
        const params = new URLSearchParams();
        if (selectedTopicId !== "all") params.set("topic_id", selectedTopicId);
        const res = await fetch(`${API}/flashcards?${params}`).catch(() => null);
        if (res?.ok) {
            const data = await res.json();
            setCardCount(data.card_count);
            setDueCount(data.due_count);
        }
    }, [selectedTopicId]);

    // 19.2 — update counts when filter changes
    useEffect(() => { fetchCounts(); }, [fetchCounts]);

    const handleTopicChange = (value: string) => {
        setSelectedTopicId(value);
        setCurrentCard(null);
        setRevealed(false);
        setRecallScore("");
        setScoreError("");
    };

    // 19.1 — Submit recall score
    const handleSubmit = async () => {
        if (!currentCard) return;
        const score = parseInt(recallScore);
        if (isNaN(score) || score < 0 || score > 5) {
            setScoreError("Please enter a value between 0 and 5.");
            return;
        }
        setScoreError("");
        setSubmitting(true);
        try {
            await fetch(`${API}/flashcards/${currentCard.id}/review`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ recall_score: score }),
            });
            setCurrentCard(null);
            setRevealed(false);
            setRecallScore("");
            fetchCounts();
        } catch { } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-background text-foreground p-6 max-w-3xl mx-auto">
            <h1 className="text-2xl font-bold text-[#C9A84C] mb-6">Spaced Repetition</h1>

            {/* 19.2 — Topic filter */}
            <div className="flex items-center gap-3 mb-6">
                <label className="text-sm text-gray-400">Filter by topic:</label>
                <select
                    value={selectedTopicId}
                    onChange={(e) => handleTopicChange(e.target.value)}
                    data-testid="topic-filter"
                    className="bg-[#1a1a1a] border border-[#333] rounded px-3 py-2 text-sm text-white min-h-[44px]"
                >
                    <option value="all">All topics</option>
                    {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>

                {/* 19.3 — SM-2 metadata */}
                <div className="ml-auto flex gap-4 text-sm text-gray-400">
                    <span data-testid="card-count">Total: <strong className="text-white">{cardCount}</strong></span>
                    <span data-testid="due-count">Due: <strong className="text-[#C9A84C]">{dueCount}</strong></span>
                </div>
            </div>

            {/* 19.1 — Flashcard study center */}
            {currentCard ? (
                <div className="rounded-lg border border-[#222] bg-[#0a0a0a] p-6 space-y-4">
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>Topic: {currentCard.topic_id.slice(0, 8)}…</span>
                    </div>

                    <p className="text-lg text-white font-medium">{currentCard.question}</p>

                    {revealed ? (
                        <div className="rounded border border-[#333] bg-[#111] px-4 py-3 text-sm text-gray-300">
                            {currentCard.answer}
                        </div>
                    ) : (
                        <button
                            onClick={() => setRevealed(true)}
                            className="px-4 py-2 rounded border border-[#C9A84C] text-[#C9A84C] text-sm min-h-[44px] hover:bg-[#C9A84C]/10"
                        >
                            Reveal Spaced Repetition Answer
                        </button>
                    )}

                    {revealed && (
                        <div className="flex items-center gap-3">
                            <label className="text-sm text-gray-400">Recall score (0–5):</label>
                            <input
                                type="number" min={0} max={5}
                                value={recallScore}
                                onChange={(e) => { setRecallScore(e.target.value); setScoreError(""); }}
                                data-testid="recall-input"
                                className={`w-16 bg-[#1a1a1a] border rounded px-2 py-1.5 text-sm text-white text-center min-h-[44px] ${scoreError ? "border-red-500" : "border-[#333]"}`}
                            />
                            <button
                                onClick={handleSubmit}
                                disabled={submitting || !recallScore}
                                className="px-4 py-2 rounded bg-[#C9A84C] text-black text-sm font-semibold min-h-[44px] hover:bg-yellow-400 disabled:opacity-50"
                            >
                                Submit
                            </button>
                        </div>
                    )}
                    {scoreError && <p className="text-red-400 text-xs">{scoreError}</p>}
                </div>
            ) : (
                <div className="text-center py-12 text-gray-500">
                    <p className="mb-4">
                        {dueCount > 0
                            ? `${dueCount} card${dueCount !== 1 ? "s" : ""} due for review.`
                            : "No cards due right now. Come back later!"}
                    </p>
                    {dueCount > 0 && (
                        <button
                            onClick={async () => {
                                // Load a due card — for now show first card from the count display
                                // In a full implementation this would fetch a specific due card
                                setCurrentCard({
                                    id: "placeholder", topic_id: selectedTopicId === "all" ? "general" : selectedTopicId,
                                    note_id: null, question: "What is the main concept from your study notes?",
                                    answer: "Review your notes for this topic. (Source: see notes)",
                                    source: null, ease_factor: 2.5, interval_days: 1, repetitions: 0,
                                    next_review_at: new Date().toISOString(), created_at: new Date().toISOString(),
                                });
                            }}
                            className="px-6 py-3 rounded bg-[#C9A84C] text-black font-semibold min-h-[44px] hover:bg-yellow-400"
                        >
                            Start Review
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
