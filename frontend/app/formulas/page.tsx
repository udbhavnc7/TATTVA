"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface FormulaItem {
    formula_or_algorithm: string;
    variables: string;
    source: string;
}
interface Subject { id: string; name: string; code: string; }

export default function FormulasPage() {
    const [subjects, setSubjects] = useState<Subject[]>([]);
    const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
    const [formulas, setFormulas] = useState<FormulaItem[]>([]);
    const [renderedTable, setRenderedTable] = useState<string>("");
    const [scanning, setScanning] = useState(false);
    const [scanDone, setScanDone] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetch(`${API}/subjects`).then((r) => r.json()).then(setSubjects).catch(() => { });
    }, []);

    // 20.1 — On subject select, fetch formulas
    const handleSubjectChange = useCallback(async (subjectId: string) => {
        setSelectedSubjectId(subjectId);
        setFormulas([]);
        setRenderedTable("");
        setScanDone(false);
        if (!subjectId) return;
        try {
            const res = await fetch(`${API}/formulas/${subjectId}`);
            if (!res.ok) throw new Error("Failed to fetch formulas");
            const data = await res.json();
            setFormulas(data.formulas ?? []);
            setRenderedTable(data.rendered_table ?? "");
        } catch (e) {
            setError((e as Error).message);
        }
    }, []);

    // 20.3 — Re-scan
    const handleRescan = async () => {
        if (!selectedSubjectId) return;
        setScanning(true);
        setScanDone(false);
        try {
            await fetch(`${API}/formulas/${selectedSubjectId}/scan`, { method: "POST" });
            // Refresh after scan
            await handleSubjectChange(selectedSubjectId);
            setScanDone(true);
            setTimeout(() => setScanDone(false), 3000);
        } catch { } finally {
            setScanning(false);
        }
    };

    // 20.4 — Export
    const handleExport = async () => {
        if (!selectedSubjectId) return;
        const res = await fetch(`${API}/formulas/${selectedSubjectId}/export`);
        if (!res.ok) return;
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `formulas_${selectedSubjectId}.md`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="min-h-screen bg-background text-foreground p-6 max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold text-[#C9A84C]">Formula Sheet</h1>
                <div className="flex gap-3">
                    {/* 20.3 — Re-scan */}
                    <button
                        onClick={handleRescan}
                        disabled={!selectedSubjectId || scanning}
                        className="px-4 py-2 rounded text-sm font-medium min-h-[44px] bg-[#1a1a1a] text-gray-300 border border-[#333] hover:border-[#C9A84C] hover:text-[#C9A84C] transition-colors disabled:opacity-50"
                    >
                        {scanning ? "Scanning…" : "Re-Scan Textbooks"}
                    </button>
                    {/* 20.4 — Export */}
                    <button
                        onClick={handleExport}
                        disabled={!selectedSubjectId || formulas.length === 0}
                        className="px-4 py-2 rounded text-sm font-medium min-h-[44px] bg-[#1a1a1a] text-gray-300 border border-[#333] hover:border-[#C9A84C] hover:text-[#C9A84C] transition-colors disabled:opacity-50"
                    >
                        Export Equation Table
                    </button>
                </div>
            </div>

            {scanDone && (
                <div className="mb-4 rounded bg-green-900/30 border border-green-700 px-4 py-2 text-green-300 text-sm">
                    Scan complete. Formula table updated.
                </div>
            )}

            {/* 20.1 — Subject selector */}
            <div className="mb-6">
                <select
                    value={selectedSubjectId}
                    onChange={(e) => handleSubjectChange(e.target.value)}
                    className="bg-[#1a1a1a] border border-[#333] rounded px-3 py-2 text-sm text-white min-h-[44px] w-full max-w-sm"
                >
                    <option value="">Select a subject…</option>
                    {subjects.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
                </select>
            </div>

            {error && (
                <div className="mb-4 rounded bg-red-900/30 border border-red-700 px-4 py-2 text-red-300 text-sm">
                    {error}
                </div>
            )}

            {/* 20.2 — Formula table with KaTeX-like rendering */}
            {formulas.length > 0 ? (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                        <thead>
                            <tr className="text-gray-400 text-left border-b border-[#222]">
                                <th className="py-2 pr-6">Formula / Algorithm</th>
                                <th className="py-2 pr-6">Variables</th>
                                <th className="py-2">Source</th>
                            </tr>
                        </thead>
                        <tbody>
                            {formulas.map((f, i) => (
                                <tr key={i} className="border-b border-[#1a1a1a]">
                                    {/* 20.2 — Render formula — in production use KaTeX; here render as code */}
                                    <td className="py-3 pr-6">
                                        <code className="bg-[#1a1a1a] text-[#C9A84C] px-2 py-0.5 rounded text-xs font-mono">
                                            {f.formula_or_algorithm}
                                        </code>
                                    </td>
                                    <td className="py-3 pr-6 text-gray-400 text-xs">{f.variables || "—"}</td>
                                    <td className="py-3 text-gray-500 text-xs">{f.source}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : selectedSubjectId ? (
                <p className="text-gray-500 text-sm">No formulas found for this subject.</p>
            ) : (
                <p className="text-gray-600 text-sm">Select a subject to view its formula sheet.</p>
            )}
        </div>
    );
}
