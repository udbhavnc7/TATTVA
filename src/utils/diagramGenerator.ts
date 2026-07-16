/**
 * Takes generated notes text and returns a Mermaid code block.
 * Calls the backend /api/generate-diagram endpoint.
 */
export async function generateMermaidDiagram(notesText: string): Promise<string> {
  try {
    const response = await fetch('/api/generate-diagram', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ notesText }),
    });

    if (!response.ok) {
      throw new Error('Failed to generate diagram');
    }

    const data = await response.json();
    return data.diagramCode;
  } catch (error) {
    console.error('Error in generateMermaidDiagram:', error);
    // Fallback standard Mermaid code if generation fails
    return `graph TD
    A[Start Process] --> B[Execute Algorithms]
    B --> C{Decision Path}
    C -->|Success| D[Final Output]
    C -->|Failure| E[Review Logs]`;
  }
}
