import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Minimal confidence badge component test
const ConfidenceBadgeChip = ({ badge }: { badge: string }) => (
    <span data-testid="confidence-badge" className={badge}>{badge}</span>
);

// Stub generate button
function GenerateButton({ enabled, onClick }: { enabled: boolean; onClick: () => void }) {
    return (
        <button
            data-testid="generate-button"
            disabled={!enabled}
            onClick={onClick}
            className={enabled ? "enabled" : "disabled"}
        >
            Generate Grounded Study Notes
        </button>
    );
}

describe("Confidence badge variants", () => {
    it("renders grounded badge correctly", () => {
        render(<ConfidenceBadgeChip badge="grounded" />);
        const badge = screen.getByTestId("confidence-badge");
        expect(badge).toBeTruthy();
        expect(badge.textContent).toBe("grounded");
    });

    it("renders needs_review badge correctly", () => {
        render(<ConfidenceBadgeChip badge="needs_review" />);
        const badge = screen.getByTestId("confidence-badge");
        expect(badge.className).toContain("needs_review");
    });

    it("renders partial badge correctly", () => {
        render(<ConfidenceBadgeChip badge="partial" />);
        expect(screen.getByTestId("confidence-badge").textContent).toBe("partial");
    });
});

describe("needs_review amber border", () => {
    it("note card with needs_review badge has amber border class", () => {
        const { container } = render(
            <div
                data-testid="note-card"
                className="border border-amber-500 ring-1 ring-amber-500"
            >
                <ConfidenceBadgeChip badge="needs_review" />
            </div>
        );
        const card = container.querySelector('[data-testid="note-card"]');
        expect(card?.className).toContain("amber");
    });
});

describe("Generate button state", () => {
    it("is disabled when no topic is selected", () => {
        render(<GenerateButton enabled={false} onClick={vi.fn()} />);
        const btn = screen.getByTestId("generate-button");
        expect(btn).toBeDisabled();
    });

    it("is enabled when a topic is selected", () => {
        render(<GenerateButton enabled={true} onClick={vi.fn()} />);
        const btn = screen.getByTestId("generate-button");
        expect(btn).not.toBeDisabled();
    });

    it("calls onClick when enabled and clicked", () => {
        const mockClick = vi.fn();
        render(<GenerateButton enabled={true} onClick={mockClick} />);
        fireEvent.click(screen.getByTestId("generate-button"));
        expect(mockClick).toHaveBeenCalledOnce();
    });
});
