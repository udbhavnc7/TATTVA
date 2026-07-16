"use client";

interface CircularGaugeProps {
    percentage: number; // 0–100
    size?: number;
}

export default function CircularGauge({ percentage, size = 140 }: CircularGaugeProps) {
    const radius = (size - 20) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percentage / 100) * circumference;
    const cx = size / 2;
    const cy = size / 2;

    return (
        <div className="flex flex-col items-center gap-2" data-testid="circular-gauge">
            <svg width={size} height={size} aria-label={`Coverage: ${percentage}%`}>
                {/* Background circle */}
                <circle
                    cx={cx}
                    cy={cy}
                    r={radius}
                    fill="none"
                    stroke="#1a1a1a"
                    strokeWidth={12}
                />
                {/* Progress arc */}
                <circle
                    cx={cx}
                    cy={cy}
                    r={radius}
                    fill="none"
                    stroke="#C9A84C"
                    strokeWidth={12}
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    transform={`rotate(-90 ${cx} ${cy})`}
                    data-testid="gauge-arc"
                />
                {/* Percentage text */}
                <text
                    x={cx}
                    y={cy + 6}
                    textAnchor="middle"
                    fill="white"
                    fontSize={size / 5}
                    fontWeight="bold"
                    data-testid="gauge-percentage"
                >
                    {percentage}%
                </text>
            </svg>
            <p className="text-sm text-gray-400">AI-Grounded Coverage</p>
        </div>
    );
}
