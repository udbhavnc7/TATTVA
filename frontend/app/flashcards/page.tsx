/**
 * Spaced Repetition / Flashcards screen
 *
 * Surfaces AI-generated flashcards scheduled via the SM-2 spaced repetition
 * algorithm to maximise long-term retention.
 */
export default function FlashcardsPage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            <h1 className="text-3xl font-bold text-foreground">
                Spaced Repetition
            </h1>
            <p className="mt-2 text-muted-foreground">
                Review flashcards scheduled by the SM-2 algorithm to maximise
                retention.
            </p>
        </main>
    );
}
