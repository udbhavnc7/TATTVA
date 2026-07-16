import { redirect } from "next/navigation";

/**
 * Root route — redirect to the Syllabus Coverage screen,
 * which is the primary entry point of the Tattva Exam Engine.
 */
export default function RootPage() {
    redirect("/coverage");
}
