/**
 * Formula Sheet screen
 *
 * Displays all LaTeX formulas extracted from the student's uploaded PDFs,
 * organised by subject and module.
 */
export default function FormulasPage() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
            <h1 className="text-3xl font-bold text-foreground">
                Formula Sheet
            </h1>
            <p className="mt-2 text-muted-foreground">
                All formulas extracted from your PDFs, organised by subject and module.
            </p>
        </main>
    );
}
