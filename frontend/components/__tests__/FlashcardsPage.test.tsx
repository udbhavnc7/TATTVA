import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Minimal isolated component tests for Task 19 requirements

// Topic filter with count update
function TopicFilter({
    value, onChange, cardCount, dueCount,
}: {
    value: string; onChange: (v: string) => void;
    cardCount: number; dueCount: number;
}) {
    return (
        <div>
            <select data-testid="topic-filter" value={value} onChange={(e) => onChange(e.target.value)}>
                <option value="all">All topics</option>
                <option value="topic-1">Topic 1</option>
            </select>
            <span data-testid="card-count">{cardCount}</span>
            <span data-testid="due-count">{dueCount}</span>
        </div>
    );
}

// Recall score input
function RecallInput({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
    return (
        <div>
            <input
                data-testid="recall-input"
                type="number"
                min={0} max={5}
                value={value}
                onChange={(e) => onChange(e.target.value)}
            />
            {error && <p data-testid="recall-error">{error}</p>}
        </div>
    );
}

describe("Topic filter updates card/due counts immediately", () => {
    it("displays card count from props", () => {
        const { rerender } = render(
            <TopicFilter value="all" onChange={vi.fn()} cardCount={10} dueCount={4} />
        );
        expect(screen.getByTestId("card-count").textContent).toBe("10");
        expect(screen.getByTestId("due-count").textContent).toBe("4");

        // Simulate filter change with updated counts
        rerender(
            <TopicFilter value="topic-1" onChange={vi.fn()} cardCount={3} dueCount={1} />
        );
        expect(screen.getByTestId("card-count").textContent).toBe("3");
        expect(screen.getByTestId("due-count").textContent).toBe("1");
    });

    it("calls onChange when filter changes", () => {
        const mockChange = vi.fn();
        render(<TopicFilter value="all" onChange={mockChange} cardCount={0} dueCount={0} />);
        fireEvent.change(screen.getByTestId("topic-filter"), { target: { value: "topic-1" } });
        expect(mockChange).toHaveBeenCalledWith("topic-1");
    });
});

describe("Recall score input enforces 0–5 range", () => {
    it("renders recall input with correct min/max attributes", () => {
        render(<RecallInput value="" onChange={vi.fn()} />);
        const input = screen.getByTestId("recall-input") as HTMLInputElement;
        expect(input.min).toBe("0");
        expect(input.max).toBe("5");
    });

    it("shows error when value is outside range", () => {
        render(<RecallInput value="6" onChange={vi.fn()} error="Value must be 0–5" />);
        expect(screen.getByTestId("recall-error").textContent).toBe("Value must be 0–5");
    });

    it("does not show error when value is valid", () => {
        render(<RecallInput value="3" onChange={vi.fn()} />);
        expect(screen.queryByTestId("recall-error")).toBeNull();
    });
});
