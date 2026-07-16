import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import Sidebar from "../Sidebar";

// Mock next/navigation
const mockUsePathname = vi.fn();

vi.mock("next/navigation", () => ({
    usePathname: () => mockUsePathname(),
}));

// Mock next/link to render a plain anchor so href and className are testable
vi.mock("next/link", () => ({
    default: ({
        href,
        className,
        children,
    }: {
        href: string;
        className?: string;
        children: React.ReactNode;
    }) => (
        <a href={href} className={className}>
            {children}
        </a>
    ),
}));

describe("Sidebar", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUsePathname.mockReturnValue("/");
    });

    it("renders all six nav links", () => {
        render(<Sidebar />);

        expect(screen.getByText("Syllabus Coverage")).toBeInTheDocument();
        expect(screen.getByText("Grounded Notes")).toBeInTheDocument();
        expect(screen.getByText("PYQ Exam Paper")).toBeInTheDocument();
        expect(screen.getByText("Spaced Repetition")).toBeInTheDocument();
        expect(screen.getByText("Socratic Q&A")).toBeInTheDocument();
        expect(screen.getByText("Formula Sheet")).toBeInTheDocument();
    });

    it("active link has gold indicator", () => {
        mockUsePathname.mockReturnValue("/coverage");
        render(<Sidebar />);

        const coverageLink = screen.getByText("Syllabus Coverage").closest("a");
        expect(coverageLink).not.toBeNull();
        expect(coverageLink!.className).toContain("border-[#C9A84C]");
    });

    it("inactive links do not have active class", () => {
        mockUsePathname.mockReturnValue("/coverage");
        render(<Sidebar />);

        const notesLink = screen.getByText("Grounded Notes").closest("a");
        expect(notesLink).not.toBeNull();
        expect(notesLink!.className).not.toContain("border-[#C9A84C]");
    });
});
