import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: "Tattva — AI Exam Engine",
    description:
        "AI-powered exam preparation platform. Grounded notes, PYQ analysis, and spaced repetition — all sourced from your lecture PDFs.",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" className="dark">
            <body
                className={`${inter.className} min-h-screen bg-background text-foreground antialiased`}
            >
                <div className="flex min-h-screen bg-background">
                    <Sidebar />
                    <main className="flex-1 min-w-0">{children}</main>
                </div>
            </body>
        </html>
    );
}
