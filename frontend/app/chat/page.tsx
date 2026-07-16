/**
 * Socratic Q&A / Chat screen
 *
 * Lets students ask questions and receive answers grounded exclusively
 * in their uploaded lecture material. Answers are never fabricated from
 * LLM training data.
 */
export default function ChatPage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            {/* Persistent disclaimer — always visible without scrolling (Req 16.5) */}
            <div className="w-full max-w-2xl rounded-md border border-[#C9A84C] bg-surface px-4 py-3 text-sm text-[#C9A84C] mb-6">
                ⚠ Answers are sourced only from your uploaded lecture material.
                Tattva will not answer from general knowledge.
            </div>

            <h1 className="text-3xl font-bold text-foreground">
                Socratic Q&amp;A
            </h1>
            <p className="mt-2 text-muted-foreground">
                Ask questions about your subject — all answers are grounded in your
                PDFs.
            </p>
        </main>
    );
}
