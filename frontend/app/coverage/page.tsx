/**
 * Syllabus Coverage screen
 *
 * Displays the subject/module/topic taxonomy and tracks which topics
 * are covered by the student's uploaded lecture PDFs.
 */
export default function CoveragePage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            <h1 className="text-3xl font-bold text-foreground">
                Syllabus Coverage
            </h1>
            <p className="mt-2 text-muted-foreground">
                Track how much of the syllabus your uploaded PDFs cover.
            </p>
        </main>
    );
}
