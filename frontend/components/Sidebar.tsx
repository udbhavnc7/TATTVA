"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
    { href: "/coverage", label: "Syllabus Coverage" },
    { href: "/notes", label: "Grounded Notes" },
    { href: "/pyq", label: "PYQ Exam Paper" },
    { href: "/flashcards", label: "Spaced Repetition" },
    { href: "/chat", label: "Socratic Q&A" },
    { href: "/formulas", label: "Formula Sheet" },
];

export default function Sidebar() {
    const pathname = usePathname();

    const isActive = (href: string) =>
        pathname === href || pathname.startsWith(href + "/");

    return (
        <aside className="w-56 min-h-screen bg-[#111111] border-r border-[#1a1a1a] flex flex-col pt-6">
            {/* Logo */}
            <div className="px-4 mb-8">
                <span className="text-xl font-bold text-[#C9A84C]">Tattva</span>
            </div>

            {/* Navigation */}
            <nav className="flex flex-col gap-1">
                {NAV_LINKS.map(({ href, label }) => (
                    <Link
                        key={href}
                        href={href}
                        className={[
                            "min-h-[44px] min-w-[44px] flex items-center px-4",
                            isActive(href)
                                ? "border-l-2 border-[#C9A84C] text-[#C9A84C]"
                                : "text-gray-400 hover:text-white transition-colors",
                        ].join(" ")}
                    >
                        {label}
                    </Link>
                ))}
            </nav>
        </aside>
    );
}
