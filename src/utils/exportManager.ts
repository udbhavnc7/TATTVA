import { jsPDF } from 'jspdf';
import { Flashcard } from '../types';

/**
 * Escapes a cell value for CSV output according to RFC 4180 standard.
 * Encloses values containing quotes, commas, semicolons, or linebreaks in double-quotes,
 * and doubles any existing double-quotes.
 */
function escapeCSVField(field: string): string {
  if (!field) return '';
  const normalized = field.replace(/\r?\n/g, '\n');
  if (
    normalized.includes('"') ||
    normalized.includes(',') ||
    normalized.includes(';') ||
    normalized.includes('\n')
  ) {
    return `"${normalized.replace(/"/g, '""')}"`;
  }
  return normalized;
}

/**
 * Formats and triggers the download of flashcards in an Anki-compatible CSV structure.
 */
export function exportFlashcardsToAnkiCSV(flashcards: Flashcard[], deckName: string): void {
  if (!flashcards || flashcards.length === 0) {
    console.warn('No flashcards provided for export');
    return;
  }

  // Create the CSV file content
  // Column 1: Front (Question)
  // Column 2: Back (Answer)
  // Column 3: Tags (Deck Grouping)
  const header = 'Front,Back,Tags';
  const rows = flashcards.map(fc => {
    const front = escapeCSVField(fc.question);
    const back = escapeCSVField(fc.answer);
    const tag = escapeCSVField(deckName);
    return `${front},${back},${tag}`;
  });

  const csvContent = [header, ...rows].join('\n');
  
  // Add UTF-8 BOM to guarantee proper encoding representation when opened in Anki, Excel, or other systems
  const BOM = '\uFEFF';
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.href = url;
  const sanitizedDeckName = deckName.replace(/[^a-zA-Z0-9_-]/g, '_');
  link.download = `Anki_Flashcards_${sanitizedDeckName}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Formats and triggers the download of comprehensive study notes into standard Markdown format
 * with an elegant custom frontmatter block.
 */
export function exportNoteToMarkdown(topicName: string, depth: string, contentMd: string): void {
  if (!contentMd) {
    console.warn('No notes content provided for export');
    return;
  }

  const cleanTopic = topicName.trim();
  const readableDepth = depth === '2mark' ? '2-Mark Short' : depth === '6mark' ? '6-Mark Medium' : '10-Mark Detailed';

  // Build Frontmatter block
  const frontmatter = `---
title: "Study Notes: ${cleanTopic}"
depth: "${readableDepth}"
exported_at: "${new Date().toLocaleDateString()}"
app: "Tattva Syllabus Companion"
---

# ${cleanTopic} (${readableDepth} Study Notes)

`;

  const finalContent = frontmatter + contentMd;
  const blob = new Blob([finalContent], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  const sanitizedTopic = cleanTopic.replace(/[^a-zA-Z0-9_-]/g, '_');
  link.download = `Notes_${sanitizedTopic}_${depth}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Formats and triggers the download of the current study note as a professional formatted PDF using jsPDF.
 */
export function exportNoteToPDF(topicName: string, depth: string, contentMd: string): void {
  if (!contentMd) {
    console.warn('No notes content provided for export');
    return;
  }

  const doc = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4'
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginLeft = 20;
  const marginRight = 20;
  const marginTop = 25;
  const marginBottom = 20;
  const contentWidth = pageWidth - marginLeft - marginRight;

  let y = marginTop;
  let pageCount = 1;

  // Helper to add a new page with header
  const addNewPage = () => {
    doc.addPage();
    pageCount++;
    y = marginTop;
    drawPageHeaderFooter();
  };

  const drawPageHeaderFooter = () => {
    // Header
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139); // Slate-500
    doc.text('TATTVA SYLLABUS COMPANION', marginLeft, 12);
    doc.text('TOPIC STUDY NOTES', pageWidth - marginRight, 12, { align: 'right' });
    
    // Header line
    doc.setDrawColor(226, 232, 240); // Slate-200
    doc.setLineWidth(0.2);
    doc.line(marginLeft, 14, pageWidth - marginRight, 14);

    // Footer line
    doc.line(marginLeft, pageHeight - 14, pageWidth - marginRight, pageHeight - 14);

    // Footer
    doc.text(`Generated on ${new Date().toLocaleDateString()}`, marginLeft, pageHeight - 10);
    doc.text(`Page ${pageCount}`, pageWidth - marginRight, pageHeight - 10, { align: 'right' });
  };

  // Draw header/footer for the first page
  drawPageHeaderFooter();

  // Draw main title
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(22);
  doc.setTextColor(15, 23, 42); // Slate-900

  const readableDepth = depth === '2mark' ? '2-Mark Short' : depth === '6mark' ? '6-Mark Medium' : '10-Mark Detailed';
  
  const titleLines: string[] = doc.splitTextToSize(topicName, contentWidth);
  titleLines.forEach(line => {
    if (y > pageHeight - marginBottom) addNewPage();
    doc.text(line, marginLeft, y);
    y += 8;
  });

  y += 2;

  // Subtitle / metadata
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  doc.setTextColor(71, 85, 105); // Slate-600
  doc.text(`EXAM DEPTH: ${readableDepth.toUpperCase()}`, marginLeft, y);
  y += 6;
  doc.text(`EXPORTED AT: ${new Date().toLocaleDateString()}`, marginLeft, y);
  y += 12;

  // Draw separator line
  doc.setDrawColor(203, 213, 225); // Slate-300
  doc.setLineWidth(0.4);
  doc.line(marginLeft, y - 4, pageWidth - marginRight, y - 4);

  // Split markdown content by lines
  const lines = contentMd.split('\n');
  let inCodeBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    // Skip empty lines or collapse them slightly
    if (line === '') {
      y += 4;
      continue;
    }

    // Code block toggle
    if (line.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }

    // Set styling based on line type
    if (inCodeBlock) {
      doc.setFont('courier', 'normal');
      doc.setFontSize(9);
      doc.setTextColor(30, 41, 59); // Slate-800
      
      const wrappedLines: string[] = doc.splitTextToSize(line, contentWidth - 4);
      wrappedLines.forEach(wl => {
        if (y > pageHeight - marginBottom) addNewPage();
        // Draw light background block for code line
        doc.setFillColor(241, 245, 249); // Slate-100
        doc.rect(marginLeft, y - 3.5, contentWidth, 5, 'F');
        doc.text(wl, marginLeft + 2, y);
        y += 5;
      });
    } else if (line.startsWith('# ')) {
      const text = line.replace('# ', '').trim();
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(16);
      doc.setTextColor(15, 23, 42); // Slate-900
      y += 4; // Add margin before heading
      
      const wrappedLines: string[] = doc.splitTextToSize(text, contentWidth);
      wrappedLines.forEach(wl => {
        if (y > pageHeight - marginBottom) addNewPage();
        doc.text(wl, marginLeft, y);
        y += 7;
      });
      y += 2;
    } else if (line.startsWith('## ')) {
      const text = line.replace('## ', '').trim();
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(13);
      doc.setTextColor(15, 23, 42); // Slate-900
      y += 3;
      
      const wrappedLines: string[] = doc.splitTextToSize(text, contentWidth);
      wrappedLines.forEach(wl => {
        if (y > pageHeight - marginBottom) addNewPage();
        doc.text(wl, marginLeft, y);
        y += 6;
      });
      y += 1.5;
    } else if (line.startsWith('### ')) {
      const text = line.replace('### ', '').trim();
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(11);
      doc.setTextColor(15, 23, 42); // Slate-900
      y += 2;
      
      const wrappedLines: string[] = doc.splitTextToSize(text, contentWidth);
      wrappedLines.forEach(wl => {
        if (y > pageHeight - marginBottom) addNewPage();
        doc.text(wl, marginLeft, y);
        y += 5.5;
      });
      y += 1;
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      const text = line.substring(2).trim();
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9.5);
      doc.setTextColor(51, 65, 85); // Slate-700
      
      const indent = 5;
      const wrappedLines: string[] = doc.splitTextToSize(text, contentWidth - indent);
      wrappedLines.forEach((wl, idx) => {
        if (y > pageHeight - marginBottom) addNewPage();
        if (idx === 0) {
          // Draw bullet point
          doc.setFont('helvetica', 'bold');
          doc.text('•', marginLeft + 1, y);
          doc.setFont('helvetica', 'normal');
        }
        doc.text(wl, marginLeft + indent, y);
        y += 5;
      });
    } else {
      // Normal paragraph
      const cleanLine = line.replace(/\*\*/g, '');
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9.5);
      doc.setTextColor(51, 65, 85); // Slate-700

      const wrappedLines: string[] = doc.splitTextToSize(cleanLine, contentWidth);
      wrappedLines.forEach(wl => {
        if (y > pageHeight - marginBottom) addNewPage();
        doc.text(wl, marginLeft, y);
        y += 5;
      });
    }
  }

  // Trigger download
  const sanitizedTopic = topicName.trim().replace(/[^a-zA-Z0-9_-]/g, '_');
  doc.save(`Study_Notes_${sanitizedTopic}_${depth}.pdf`);
}

/**
 * Formats and triggers the download of a formula sheet in standard Markdown format with metadata frontmatter.
 */
export function exportFormulaSheetToMarkdown(subjectCode: string, subjectName: string, contentMd: string): void {
  if (!contentMd) {
    console.warn('No formula sheet content provided for export');
    return;
  }

  const cleanCode = subjectCode.trim();
  const cleanName = subjectName.trim();

  // Build Frontmatter block
  const frontmatter = `---
title: "Equation & Algorithm Sheet: ${cleanCode} - ${cleanName}"
subject_code: "${cleanCode}"
subject_name: "${cleanName}"
exported_at: "${new Date().toLocaleDateString()}"
app: "Tattva Syllabus Companion"
---

# ${cleanCode} — ${cleanName} (Equation & Algorithm Sheet)

`;

  const finalContent = frontmatter + contentMd;
  const blob = new Blob([finalContent], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  const sanitizedCode = cleanCode.replace(/[^a-zA-Z0-9_-]/g, '_');
  link.download = `Formula_Sheet_${sanitizedCode}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

