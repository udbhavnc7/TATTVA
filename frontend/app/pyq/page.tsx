/**
 * PYQ Exam Paper screen
 *
 * Shows Previous Year Question frequency analysis and lets students
 * generate mock exam papers weighted by PYQ heat.
 */
export default function PYQPage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            <h1 className="text-3xl font-bold text-foreground">
                PYQ Exam Paper
            </h1>
            <p className="mt-2 text-muted-foreground">
                Analyze previous year question frequency and generate targeted mock
                papers.
            </p>
        </main>
    );
}
