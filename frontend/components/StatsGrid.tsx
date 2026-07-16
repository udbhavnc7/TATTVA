interface StatsGridProps {
    grounded: number;
    partial: number;
    needsReview: number;
    noNotes: number;
}

interface StatCardProps {
    label: string;
    count: number;
    color: string;
}

function StatCard({ label, count, color }: StatCardProps) {
    return (
        <div
            className="bg-[#1a1a1a] rounded-lg p-4 flex flex-col gap-1 border border-[#222]"
            data-testid={`stat-card-${label.toLowerCase().replace(/\s+/g, "-")}`}
        >
            <span className={`text-2xl font-bold ${color}`} data-testid="stat-count">{count}</span>
            <span className="text-xs text-gray-400">{label}</span>
        </div>
    );
}

export default function StatsGrid({ grounded, partial, needsReview, noNotes }: StatsGridProps) {
    return (
        <div className="grid grid-cols-2 gap-3" data-testid="stats-grid">
            <StatCard label="Grounded" count={grounded} color="text-green-400" />
            <StatCard label="Partially Grounded" count={partial} color="text-[#C9A84C]" />
            <StatCard label="Needs Review" count={needsReview} color="text-red-400" />
            <StatCard label="No Notes" count={noNotes} color="text-gray-500" />
        </div>
    );
}
