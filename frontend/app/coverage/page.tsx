"use client";

import { useEffect, useState, useCallback } from "react";
import CircularGauge from "@/components/CircularGauge";
import StatsGrid from "@/components/StatsGrid";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_INTERVAL = 5000; // 5 seconds

interface TopicBadge {
    topic_id: string;
    topic_name: string;
    module_id: string;
    badge: "grounded" | "partial" | "needs_review" | null;
}

interface CoverageData {
    grounded_count: number;
    partial_count: number;
    needs_review_count: number;
    no_notes_count: number;
    total_topics: number;
    coverage_percentage: number;
    topics: TopicBadge[];
}

interface Document {
    id: string;
    filename: string;
    uploaded_at: string;
    source_type: string;
}

const BADGE_STYLES: Record<string, string> = {
    grounded: "bg-green-900 text-green-300 border border-green-700",
    partial: "bg-yellow-900 text-yellow-300 border border-yellow-700",
    needs_review: "bg-red-900 text-red-300 border border-red-700",
};

function BadgeChip({ badge }: { badge: TopicBadge["badge"] }) {
    if (!badge) {
        return (
            <span className="text-xs px-2 py-0.5 rounded bg-[#1a1a1a] text-gray-500 border border-[#333]">
                No notes
            </span>
        );
    }
    return (
        <span className={`text-xs px-2 py-0.5 rounded capitalize ${BADGE_STYLES[badge]}`}>
            {badge.replace("_", " ")}
        </span>
    );
}

export default function CoveragePage() {
    const [coverage, setCoverage] = useState<CoverageData | null>(null);
    const [documents, setDocuments] = useState<Document[]>([]);
    const [error, setError] = useState<string | null>(null);

    const fetchCoverage = useCallback(async () => {
        try {
            const res = await fetch(`${API}/coverage`);
            if (!res.ok) throw new Error(`Coverage fetch failed: ${res.status}`);
            const data: CoverageData = await res.json();
            setCoverage(data);
        } catch (e) {
            setError((e as Error).message);
        }
    }, []);

    const fetchDocuments = useCallback(async () => {
        try {
            const res = await fetch(`${API}/documents`);
            if (!res.ok) return;
            const data: Document[] = await res.json();
            setDocuments(data);
        } catch {
            // non-critical; don't update error state
        }
    }, []);

    useEffect(() => {
        fetchCoverage();
        fetchDocuments();

        // 9.2 — live refresh every 5 seconds (no manual page refresh needed)
        const id = setInterval(() => {
            fetchCoverage();
        }, POLL_INTERVAL);

        return () => clearInterval(id);
    }, [fetchCoverage, fetchDocuments]);

    return (
        <div className="min-h-screen bg-background text-foreground p-6 max-w-5xl mx-auto">
            <h1 className="text-2xl font-bold text-[#C9A84C] mb-6">Syllabus Coverage</h1>

            {error && (
                <div className="mb-4 rounded bg-red-900/30 border border-red-700 px-4 py-2 text-red-300 text-sm">
                    {error}
                </div>
            )}

            {/* Top row: gauge + stats */}
            <div className="flex flex-wrap gap-8 mb-8">
                {/* 16.1 — Circular gauge */}
                <CircularGauge percentage={coverage?.coverage_percentage ?? 0} />

                {/* 16.2 — Stats grid */}
                {coverage && (
                    <StatsGrid
                        grounded={coverage.grounded_count}
                        partial={coverage.partial_count}
                        needsReview={coverage.needs_review_count}
                        noNotes={coverage.no_notes_count}
                    />
                )}
            </div>

            {/* 16.3 — File panel */}
            <section className="mb-8">
                <h2 className="text-lg font-semibold text-white mb-3">Knowledge Store Files</h2>
                {documents.length === 0 ? (
                    <p className="text-gray-500 text-sm">No documents uploaded yet.</p>
                ) : (
                    <ul className="space-y-1">
                        {documents.map((doc) => (
                            <li
                                key={doc.id}
                                className="flex items-center gap-2 text-sm text-gray-300 bg-[#1a1a1a] px-3 py-2 rounded border border-[#222]"
                            >
                                <span className="text-[#C9A84C]">📄</span>
                                {doc.filename}
                                <span className="ml-auto text-gray-500 text-xs">
                                    {new Date(doc.uploaded_at).toLocaleDateString()}
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </section>

            {/* 16.4 — Syllabus outline */}
            <section>
                <h2 className="text-lg font-semibold text-white mb-3">Syllabus Outline</h2>
                {!coverage || coverage.topics.length === 0 ? (
                    <p className="text-gray-500 text-sm">No topics found.</p>
                ) : (
                    <ul className="space-y-2">
                        {coverage.topics.map((topic) => (
                            <li
                                key={topic.topic_id}
                                className="flex items-center justify-between bg-[#1a1a1a] px-4 py-3 rounded border border-[#222]"
                            >
                                <span className="text-sm text-gray-200">{topic.topic_name}</span>
                                <BadgeChip badge={topic.badge} />
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}
