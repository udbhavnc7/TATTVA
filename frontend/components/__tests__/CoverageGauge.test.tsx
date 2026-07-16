import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import CircularGauge from "../CircularGauge";
import StatsGrid from "../StatsGrid";

describe("CircularGauge", () => {
    it("renders the correct percentage number", () => {
        render(<CircularGauge percentage={72} />);
        expect(screen.getByTestId("gauge-percentage")).toHaveTextContent("72%");
    });

    it("renders 0% when percentage is 0", () => {
        render(<CircularGauge percentage={0} />);
        expect(screen.getByTestId("gauge-percentage")).toHaveTextContent("0%");
    });

    it("renders 100% when fully covered", () => {
        render(<CircularGauge percentage={100} />);
        expect(screen.getByTestId("gauge-percentage")).toHaveTextContent("100%");
    });

    it("renders an SVG arc element", () => {
        render(<CircularGauge percentage={50} />);
        expect(screen.getByTestId("gauge-arc")).toBeTruthy();
    });
});

describe("StatsGrid", () => {
    it("shows correct count for each badge type", () => {
        render(
            <StatsGrid grounded={10} partial={5} needsReview={3} noNotes={2} />
        );
        const counts = screen.getAllByTestId("stat-count");
        const values = counts.map((el) => el.textContent);
        expect(values).toContain("10");
        expect(values).toContain("5");
        expect(values).toContain("3");
        expect(values).toContain("2");
    });

    it("renders all four stat cards", () => {
        render(
            <StatsGrid grounded={1} partial={2} needsReview={3} noNotes={4} />
        );
        expect(screen.getByTestId("stats-grid")).toBeTruthy();
        const cards = screen.getAllByTestId("stat-count");
        expect(cards).toHaveLength(4);
    });

    it("shows zero counts correctly", () => {
        render(
            <StatsGrid grounded={0} partial={0} needsReview={0} noNotes={0} />
        );
        const counts = screen.getAllByTestId("stat-count");
        counts.forEach((el) => expect(el.textContent).toBe("0"));
    });
});
