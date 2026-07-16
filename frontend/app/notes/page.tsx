/**
 * Grounded Notes screen
 *
 * Displays AI-generated study notes (2-mark, 6-mark, 10-mark depth)
 * sourced exclusively from the student's uploaded lecture PDFs.
 */
export default function NotesPage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            <h1 className="text-3xl font-bold text-foreground">
                Grounded Notes
            </h1>
            <p className="mt-2 text-muted-foreground">
                AI-generated notes grounded in your uploaded PDFs — 2-mark, 6-mark, and
                10-mark depth levels.
            </p>
        </main>
    );
}
