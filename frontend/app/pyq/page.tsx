"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PyqEntry {
    id: string; subject_id: string; year: number;
    question_text: string; marks: number;
    topic_id: string | null; is_unmatched: boolean;
    difficulty: "easy" | "medium" | "hard" | null;
    difficulty_note: string | null; created_at: string;
}
interface TopicImportance {
    topic_id: string; frequency_count: number;
    difficulty_avg: number | null; last_recalculated: string | null;
}
interface Subject { id: string; name: string; code: string; }

const DIFFICULTY_COLORS = {
    hard: "bg-red-900 text-red-300 border-red-700",
    medium: "bg-yellow-900 text-yellow-300 border-yellow-700",
    easy: "bg-green-900 text-green-300 border-green-700",
};

export default function PYQPage() {
    const [subjects, setSubjects] = useState<Subject[]>([]);
    const [pyqs, setPyqs] = useState<PyqEntry[]>([]);
    const [recalculating, setRecalculating] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
    const [form, setForm] = useState({ subject_id: "", year: "", question_text: "", marks: "" });

    useEffect(() => {
        fetch(`${API}/subjects`).then((r) => r.json()).then(setSubjects).catch(() => { });
        fetchPyqs();
    }, []);

    const fetchPyqs = async () => {
        try {
            const res = await fetch(`${API}/pyqs`);
            setPyqs(await res.json());
        } catch { }
    };

    // 18.1 — Form submission with per-field validation errors
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFieldErrors({});
        setSubmitting(true);
        try {
            const res = await fetch(`${API}/pyqs`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    subject_id: form.subject_id,
                    year: parseInt(form.year),
                    question_text: form.question_text,
                    marks: parseInt(form.marks),
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                if (err?.detail?.field) {
                    setFieldErrors({ [err.detail.field]: err.detail.detail });
                }
                return;
            }
            setForm({ subject_id: form.subject_id, year: "", question_text: "", marks: "" });
            fetchPyqs();
        } catch { } finally {
            setSubmitting(false);
        }
    };

    // 18.4 — Map & Recalculate
    const handleRecalculate = async () => {
        setRecalculating(true);
        try {
            await fetch(`${API}/pyqs/recalculate`, { method: "POST" });
            fetchPyqs();
        } catch { } finally {
            setRecalculating(false);
        }
    };

    // Group PYQs by topic for frequency table
    const topicFrequency = Object.entries(
        pyqs.reduce<Record<string, { count: number; difficulties: string[] }>>((acc, pyq) => {
            const key = pyq.topic_id ?? "__unmatched__";
            if (!acc[key]) acc[key] = { count: 0, difficulties: [] };
            acc[key].count++;
            if (pyq.difficulty) acc[key].difficulties.push(pyq.difficulty);
            return acc;
        }, {})
    );

    return (
        <div className="min-h-screen bg-background text-foreground p-6 max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold text-[#C9A84C]">PYQ Exam Paper</h1>
                {/* 18.4 — Recalculate button */}
                <button
                    onClick={handleRecalculate}
                    disabled={recalculating}
                    className="px-4 py-2 rounded text-sm font-medium min-h-[44px] bg-[#1a1a1a] text-gray-300 border border-[#333] hover:border-[#C9A84C] hover:text-[#C9A84C] transition-colors disabled:opacity-50"
                >
                    {recalculating ? "Recalculating…" : "Map & Recalculate Importance"}
                </button>
            </div>

            {/* 18.1 — Ingest form */}
            <section className="mb-8 p-5 rounded-lg border border-[#222] bg-[#0a0a0a]">
                <h2 className="text-lg font-semibold text-white mb-4">Ingest Past Question</h2>
                <form onSubmit={handleSubmit} className="space-y-3">
                    <div>
                        <select
                            value={form.subject_id}
                            onChange={(e) => setForm({ ...form, subject_id: e.target.value })}
                            className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-2 text-sm text-white min-h-[44px]"
                            required
                        >
                            <option value="">Select subject…</option>
                            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                    </div>
                    <div className="flex gap-3">
                        <div className="flex-1">
                            <input
                                type="number" placeholder="Year (2000–present)" value={form.year}
                                onChange={(e) => setForm({ ...form, year: e.target.value })}
                                className={`w-full bg-[#1a1a1a] border rounded px-3 py-2 text-sm text-white min-h-[44px] ${fieldErrors.year ? "border-red-500" : "border-[#333]"}`}
                                required
                            />
                            {fieldErrors.year && <p className="text-red-400 text-xs mt-1">{fieldErrors.year}</p>}
                        </div>
                        <div className="flex-1">
                            <input
                                type="number" placeholder="Marks (1–100)" value={form.marks}
                                onChange={(e) => setForm({ ...form, marks: e.target.value })}
                                className={`w-full bg-[#1a1a1a] border rounded px-3 py-2 text-sm text-white min-h-[44px] ${fieldErrors.marks ? "border-red-500" : "border-[#333]"}`}
                                required
                            />
                            {fieldErrors.marks && <p className="text-red-400 text-xs mt-1">{fieldErrors.marks}</p>}
                        </div>
                    </div>
                    <div>
                        <textarea
                            placeholder="Question text (10–2000 characters)" value={form.question_text}
                            onChange={(e) => setForm({ ...form, question_text: e.target.value })}
                            rows={3}
                            className={`w-full bg-[#1a1a1a] border rounded px-3 py-2 text-sm text-white ${fieldErrors.question_text ? "border-red-500" : "border-[#333]"}`}
                            required
                        />
                        {fieldErrors.question_text && <p className="text-red-400 text-xs mt-1">{fieldErrors.question_text}</p>}
                    </div>
                    <button
                        type="submit" disabled={submitting}
                        className="px-4 py-2 rounded bg-[#C9A84C] text-black text-sm font-semibold min-h-[44px] hover:bg-yellow-400 disabled:opacity-50"
                    >
                        {submitting ? "Saving…" : "Add Past Question"}
                    </button>
                </form>
            </section>

            {/* 18.2 — Topic Frequency Analysis table */}
            <section className="mb-8">
                <h2 className="text-lg font-semibold text-white mb-3">Topic Frequency Analysis</h2>
                <table className="w-full text-sm border-collapse">
                    <thead>
                        <tr className="text-gray-400 text-left border-b border-[#222]">
                            <th className="py-2 pr-4">Topic</th>
                            <th className="py-2 pr-4">Asked</th>
                            <th className="py-2 pr-4">Difficulty</th>
                            <th className="py-2">Reference Weight</th>
                        </tr>
                    </thead>
                    <tbody>
                        {topicFrequency.map(([topicId, data]) => {
                            const majorityDiff = data.difficulties.sort(
                                (a, b) => data.difficulties.filter(d => d === b).length - data.difficulties.filter(d => d === a).length
                            )[0] as keyof typeof DIFFICULTY_COLORS | undefined;
                            return (
                                <tr key={topicId} className="border-b border-[#1a1a1a]">
                                    <td className="py-2 pr-4 text-gray-300">{topicId === "__unmatched__" ? "Unmatched" : topicId.slice(0, 8) + "…"}</td>
                                    <td className="py-2 pr-4 text-white font-semibold">{data.count}</td>
                                    <td className="py-2 pr-4">
                                        {majorityDiff ? (
                                            <span className={`text-xs px-2 py-0.5 rounded border ${DIFFICULTY_COLORS[majorityDiff]}`}>
                                                {majorityDiff}
                                            </span>
                                        ) : <span className="text-gray-600">—</span>}
                                    </td>
                                    <td className="py-2 text-gray-400">{data.count}</td>
                                </tr>
                            );
                        })}
                        {topicFrequency.length === 0 && (
                            <tr><td colSpan={4} className="py-4 text-gray-600 text-center">No PYQs ingested yet.</td></tr>
                        )}
                    </tbody>
                </table>
            </section>

            {/* 18.3 — Historical Question Library */}
            <section>
                <h2 className="text-lg font-semibold text-white mb-3">Historical Question Library</h2>
                <div className="space-y-2">
                    {pyqs.map((pyq) => (
                        <div key={pyq.id} className="flex items-start gap-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded px-4 py-3">
                            <span className="text-[#C9A84C] font-semibold text-sm w-12 shrink-0">{pyq.year}</span>
                            <p className="flex-1 text-sm text-gray-300">{pyq.question_text}</p>
                            <div className="flex flex-col items-end gap-1 shrink-0">
                                <span className="text-xs text-gray-500">{pyq.marks}m</span>
                                {pyq.difficulty && (
                                    <span className={`text-xs px-2 py-0.5 rounded border ${DIFFICULTY_COLORS[pyq.difficulty]}`}>
                                        {pyq.difficulty}
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                    {pyqs.length === 0 && <p className="text-gray-600 text-sm">No questions yet.</p>}
                </div>
            </section>
        </div>
    );
}
