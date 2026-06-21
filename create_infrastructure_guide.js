const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel,
        AlignmentType, WidthType, BorderStyle, ShadingType, PageBreak, LevelFormat,
        PageOrientation } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const headerFill = "2E75B6";
const lightFill = "D5E8F0";

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } }
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 120, after: 80 }, outlineLevel: 2 } }
    ]
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }
        ]
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [
      // Title Page
      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: "SanGir Automations (FCMR)", bold: true, size: 40 })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 }
      }),
      new Paragraph({ children: [new TextRun({ text: "Infrastructure & Development Guide", size: 28, italic: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 480 }
      }),
      new Paragraph({ children: [new TextRun("For: Developers & Non-Coders")],
        alignment: AlignmentType.CENTER, spacing: { after: 120 }
      }),
      new Paragraph({ children: [new TextRun("Purpose: Complete understanding for independent development")],
        alignment: AlignmentType.CENTER, spacing: { after: 240 }
      }),
      new Paragraph({ children: [new TextRun("Last Updated: " + new Date().toLocaleDateString())],
        alignment: AlignmentType.CENTER, spacing: { after: 600 }
      }),

      // Table of Contents
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Table of Contents")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("1. Executive Summary (Non-Technical Overview)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("2. What This App Does (Business Context)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("3. Architecture Overview (Both Desktop & Web)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("4. Tech Stack & Why Each Choice")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("5. Project Structure & File Organization")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("6. Data Flow & Request Lifecycle")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("7. Database & Catalog System")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("8. The Development 'Vibe' (Code Patterns & Culture)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("9. Essential Precautions & Invariants")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("10. Development Setup & Prerequisites")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("11. Deployment Paths (Dev / Desktop / Cloud)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("12. Common Chat Prompts for Vibe Coding")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("13. Testing & CI/CD Pipeline")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("14. Troubleshooting & Common Issues")] }),
      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("1. Executive Summary")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("What is SanGir Automations?")] }),
      new Paragraph({ children: [new TextRun("SanGir Automations is an "), new TextRun({ text: "audit analytics platform", bold: true }), new TextRun(" for financial institutions (NBFCs - Non-Banking Financial Companies). It automates the tedious process of validating customer data against regulatory requirements.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("In Plain English:")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("An auditor uploads a customer database (CSV file)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("The app runs 24 validation rules (no fake emails, proper Aadhaar formats, no duplicate records, etc.)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("It generates exception reports (which records failed which checks)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("It produces a professional Excel audit workpaper ready for regulatory sign-off")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Three Deployment Paths:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3120, 3120, 3120],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Dev (Local)", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Desktop (Electron)", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Cloud (Vercel)", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Your laptop. Fast reload. Perfect for coding.")] })] }),
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Windows/Mac app. Auditors use this in production. No internet needed.")] })] }),
              new TableCell({ borders, width: { size: 3120, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Live demo. Ephemeral data. For previews only.")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("2. What This App Does (Business Context)")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("The Problem It Solves:")] }),
      new Paragraph({ children: [new TextRun("Auditors manually check thousands of customer records against regulatory rules. This is: slow, error-prone, repetitive, and expensive.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("The Solution:")] }),
      new Paragraph({ children: [new TextRun("Upload a CSV. Click "), new TextRun({ text: "Run Analytics", bold: true }), new TextRun(". Wait 30 seconds. Download a complete audit workpaper with every exception flagged, sampled for review, and ready to present to regulators.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Who Uses It:")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Internal Auditors (NBFC companies)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("External Auditors (Big-4 audit firms)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Compliance Officers")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Risk & Controls Teams")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("The 5-Step Workflow:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1000, 8360],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "1", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Upload CSV: Auditor uploads a customer database export (can be 100K+ rows)")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "2", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Map Columns: Match CSV headers to standard fields (e.g. 'Cust_ID' → 'customer_id'). Auto-suggested, can be saved as a template.")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "3", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Run Analytics: Click 'Run Analytics'. Validates all 24 rules (takes 10-30 seconds for typical file)")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "4", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Review Results: See charts, exception summaries, and detailed exception records")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "5", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Download Workpaper: Generate a signed-off Excel audit workpaper. Includes exception records, sampled data for manual sign-off, and compliance mapping.")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("3. Architecture Overview")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("The Big Picture:")] }),
      new Paragraph({ children: [new TextRun("This is a "), new TextRun({ text: "full-stack application", bold: true }), new TextRun(" that exists in three forms (dev, desktop, cloud) but runs the exact same code. It's built in "), new TextRun({ text: "Python on the backend", bold: true }), new TextRun(" and "), new TextRun({ text: "HTML/CSS/vanilla JS on the frontend", bold: true }), new TextRun(".")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Three Layers (Like a Sandwich):")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Frontend Layer", bold: true }), new TextRun(" (what auditors see) → HTML templates + CSS styling + vanilla JavaScript for interactivity. Server-rendered (not a React SPA). Lightweight and fast.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "API Layer", bold: true }), new TextRun(" (middle man) → FastAPI web framework handling all HTTP requests. Talks to the database and runs business logic.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Business Logic Layer", bold: true }), new TextRun(" (the brain) → Core Python code: validation rules, CSV ingestion, sampling algorithms, Excel generation. This layer is the same everywhere (dev/desktop/cloud).")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Two Backends (Choose Your Adventure):")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [4680, 4680],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Development (Uvicorn)", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Production (Electron + PyInstaller)", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("python -m uvicorn app.main:app --reload")] }),
                new Paragraph({ children: [new TextRun("Runs on http://localhost:8000")] }),
                new Paragraph({ children: [new TextRun("Hot-reload on code changes")] }),
                new Paragraph({ children: [new TextRun("For developers only")] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("PyInstaller bundles Python + app into .exe")] }),
                new Paragraph({ children: [new TextRun("Electron wraps it in a native Windows/Mac/Linux app")] }),
                new Paragraph({ children: [new TextRun("Auto-updates via GitHub Releases")] }),
                new Paragraph({ children: [new TextRun("For auditors in production")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("4. Tech Stack & Why Each Choice")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Backend:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Technology", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "What It Does", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Why This Choice", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Python 3.11+", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Programming language")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Type hints, async, strong data science ecosystem")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "FastAPI", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Web framework")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Built-in async, auto-docs, Starlette session support")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "DuckDB", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Catalog database (all metadata & row data)")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Single file, embedded, no server needed, ACID, blazing fast")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Polars", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("In-memory data processing")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Fast columnar operations, vectorized (no row loops), low memory")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "openpyxl", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Excel workpaper generation")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Generates .xlsx with formatting, charts, styling")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Frontend:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Technology", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "What It Does", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Why This Choice", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Jinja2", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Server-rendered HTML templates")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Simple, no JavaScript framework complexity, logic stays Python-side")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "CSS + HTML", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("UI styling & markup")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("CSS custom properties for warm beige/terracotta theme. Semantic HTML.")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "htmx", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Progressive enhancement (interactivity without JS)")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Small library, minimal JS footprint, AJAX feels like page-loads")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Vanilla JS", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Interactive widgets (file upload, animations)")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("No framework overhead, explicit, small bundle")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Desktop/Desktop-ification:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Technology", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "What It Does", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Why This Choice", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Electron", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Native app shell (Windows/Mac)")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Wraps the web app. Users install like normal software. Auto-updates.")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "PyInstaller", bold: true })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Python bundler")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Packages Python + FastAPI + all deps into a single .exe. No Python install needed.")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("5. Project Structure & File Organization")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Folder Tree (Simplified):")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("FCMR/ (root)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "├─ app/ (FastAPI web layer)", bold: true })] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ main.py (app factory, lifespan, routes)"), new TextRun(" ")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ api/ (route handlers)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ auth.py (login/logout)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ engagements.py (audit job selector)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ uploads.py (CSV upload + mapping UI)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ runs.py (analytics execution)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ downloads.py (CSV/Excel download)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  └─ web/ (templates + static files)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     ├─ templates/ (Jinja2 HTML)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     │  ├─ base.html (sidebar + header scaffold)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     │  ├─ index.html (dashboard)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     │  ├─ run_detail.html (analytics results)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     │  └─ ... (more templates)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     └─ static/css/main.css (entire design system)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ fcmr_core/ (business logic, fully testable)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ catalog/ (DuckDB catalog manager)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ store.py (create/read/update engagements, uploads, runs)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ ingestion/ (CSV → DuckDB pipeline)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ pipeline.py (header sniff, parse, validate)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ consolidation.py (multi-file merge + alignment)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ schemas/ (report type definitions)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ customer_master.yaml (KYC fields)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ ... (ead_files, collection_report, etc.)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ rules/ (the 24 validation rules)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ registry.py (list/run rules)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ kyc_format.py (PAN, Aadhaar, email validation)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ duplicates.py (detect duplicate records)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ ... (address, PIN, identity grouping, etc.)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ reporting/ (exception CSVs + Excel generation)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ builder.py (wide/long CSV generation)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  ├─ charts.py (donut + bar SVG)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  │  └─ workpaper.py (5-sheet Excel audit workpaper)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  └─ sampling/ (ICAI-compliant stratified selection)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     ├─ sample.py (seeded stratified random selection)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│     └─ icai_table.py (sample size lookup by confidence)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ tests/ (pytest: unit & e2e)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ test_kyc_format.py")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ test_duplicates.py")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  └─ test_e2e_workpaper.py (full pipeline test)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ electron/ (Electron app shell)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  ├─ main.js (spawn backend, handle IPC)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│  └─ updater.js (auto-update via GitHub)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("│")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ pyproject.toml (Python deps, pytest config)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ package.json (Node deps for Electron)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("├─ CLAUDE.md (definitive infrastructure doc)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("└─ data/ (dev only: DuckDB catalog, outputs)")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Principle: Separation of Concerns")] }),
      new Paragraph({ children: [new TextRun("App code (routing, templating) stays in "), new TextRun({ text: "app/", bold: true }), new TextRun(". Business logic (rules, analytics, Excel gen) stays in "), new TextRun({ text: "fcmr_core/", bold: true }), new TextRun(". This means: you can unit-test rules without starting the web server, and you can reuse rules in CLI tools or other UIs.")] }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("6. Data Flow & Request Lifecycle")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Example: Running Analytics")] }),

      new Paragraph({ children: [new TextRun("When an auditor clicks "), new TextRun({ text: "Run Analytics", bold: true }), new TextRun(" on an upload:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1000, 8360],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "1", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Browser POSTs to /uploads/{id}/run with optional category/rule selection")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "2", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("runs.py (API) creates a Run record in DuckDB (status: pending)")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "3", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("A background task (_run_analytics) starts immediately")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "4", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Background task: fetch upload's data from DuckDB → Polars DataFrame")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "5", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Call run_pipeline(df, rule_ids=...) — runs all 24 rules (or subset if selected)")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "6", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Each rule appends 3 columns: _exc_<rule_id>_status, _code, _desc")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "7", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("builder.py: generate wide CSV (one row per record, summarized columns) and long CSV (one row per exception)")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "8", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Update Run record: status=completed, wide_csv=path, long_csv=path")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "9", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("Browser polls /runs/{id}/status. When status=completed, page auto-refreshes to show results")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 1000, type: WidthType.DXA }, shading: { fill: lightFill, type: ShadingType.CLEAR },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun({ text: "10", bold: true })] })] }),
              new TableCell({ borders, width: { size: 8360, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 80, right: 80 },
                children: [new Paragraph({ children: [new TextRun("run_detail page fetches wide CSV data, displays status breakdown charts, lists exceptions")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Design Patterns:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Background Tasks (BackgroundTasks)", bold: true }), new TextRun(": Long-running work happens in the background. API returns immediately; frontend polls for status.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Store Pattern", bold: true }), new TextRun(": all database access goes through store.py helpers. No raw SQL in routes.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Vectorized Operations", bold: true }), new TextRun(": Polars rules don't loop over rows—they operate on entire columns at once (100x faster).")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Deterministic Seeding", bold: true }), new TextRun(": sampling uses SHA256(engagement_id:run_id). Same data, same seed = same sample every time. Auditors can reproduce.")] }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("7. Database & Catalog System")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Why DuckDB? (Not PostgreSQL/MySQL)")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [4680, 4680],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "PostgreSQL/MySQL", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "DuckDB", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Separate server process. Needs admin to set up & manage.")] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Single file (catalog.duckdb). Zero setup. Fits in git. Persists on desktop.")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Row-oriented. Slower for analytics (our workload).")] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Columnar. Blazing fast for aggregations & filters (our workload).")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Great for transactional OLTP.")] })] }),
              new TableCell({ borders, width: { size: 4680, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Perfect for analytics (OLAP: our use case).")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Two Tables Inside DuckDB:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Catalog Tables", bold: true }), new TextRun(" — metadata about engagements, uploads, runs, users. Think of it as 'the app's state'.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Data Tables", bold: true }), new TextRun(" — one table per upload (named `data_<upload_id>`). Contains all customer records + rule annotations.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Catalog Table Schema (Simplified):")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Table", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Key Columns", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "What It Tracks", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("engagements")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("engagement_id, name, client_name, period_from, period_to")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Audit jobs. Users select one at a time.")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("uploads")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("upload_id, filename, report_type, status, row_count, engagement_id")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("CSV files + metadata. Status: ready / mapping_pending / failed")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("runs")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("run_id, upload_id, status, started_at, finished_at, wide_csv, long_csv")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Analytics executions. Status: pending / running / completed / failed")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("How Data Flows Through DuckDB:")] }),

      new Paragraph({ children: [new TextRun("CSV uploaded → sniffed (headers auto-detected) → mapped to canonical names → stored as `data_<upload_id>` in DuckDB (intermediate Parquet deleted) → rules read from this table → results written to `runs.wide_csv` and `runs.long_csv` files on disk.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Invariant: Additive Migrations Only")] }),

      new Paragraph({ children: [new TextRun("Schema changes use `CREATE TABLE IF NOT EXISTS` and guarded `ALTER TABLE ... ADD COLUMN`. Never DROP. This means: auditors can git pull the latest code, restart the app, and their data survives. Zero data loss on schema upgrades.")] }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("8. The Development 'Vibe' (Code Patterns & Culture)")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("The Sacred Invariants (READ THESE):")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "No AI/LLM Anywhere", bold: true }), new TextRun(" — All logic is hard-coded and deterministic. Fuzzy matching uses stdlib `difflib` only. Reproducibility is non-negotiable for audit.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Aadhaar Protection (Invariant #2)", bold: true }), new TextRun(" — Never persist raw Aadhaar. Hash for dedup, mask for display (XXXXXXXX1234). Legal requirement.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Deterministic Reproducibility", bold: true }), new TextRun(" — Same input + same seed = identical output. Sampling uses SHA256(engagement_id:run_id). Auditors can re-run and get the same sample.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Additive Schema Only", bold: true }), new TextRun(" — Never DROP columns. New cols → backward compatible. Local data survives git pull.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "DuckDB Memory Limits on Every Analytics Connection", bold: true }), new TextRun(" — `apply_duckdb_limits(con)` after opening a connection. Prevents OOM on large files.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Code Patterns (What to Imitate):")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Vectorized Over Row-Wise", bold: true }), new TextRun(" — Use Polars columns ops, not `for row in df.rows()`. ~100x faster.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Store Pattern", bold: true }), new TextRun(" — All DB access through store.py helpers. No raw SQL in routes. Makes testing easier.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Progress Callbacks", bold: true }), new TextRun(" — Long-running functions accept `on_progress(completed, total, label)` callback. Frontend displays live %.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Deterministic Seeding", bold: true }), new TextRun(" — Any randomness uses SHA256-based seeds, not `random.random()`. Same input = same output.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Minimal Comments", bold: true }), new TextRun(" — Code is self-documenting. Only comment the WHY if non-obvious. Don't comment WHAT.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Design Principles:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Progressive Enhancement — HTML works without JS. JS adds polish (live status, file dropzones).")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Reusable CSS — No new hex colors / fonts. Use CSS custom properties (--accent, --bg, etc.).")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Server-Rendered Templates — Logic stays Python-side. Jinja2 fills in the blanks.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Streamed Ingestion — CSV → DuckDB uses streaming read, not load-entire-file-to-RAM.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Engagement Scoping — Runs belong to engagements. No orphaned runs.")] }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("9. Essential Precautions & Invariants")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Before You Code:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Read CLAUDE.md fully. It's the single source of truth. When code ≠ doc, treat it as a bug.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Understand the 5 invariants (above). They're non-negotiable.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Run tests locally before pushing: `pytest -m 'not perf' -v`.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Lint before committing: `ruff check . && black .`.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Never delete columns in migrations. Only ADD.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Never log PII (PAN, Aadhaar, names, account numbers). Log job IDs + counts only.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("If Adding a Rule:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Write fn(df: pl.DataFrame) → pl.DataFrame in rules/<module>.py.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Add 3 output cols: `_exc_<rule_id>_status` ('OK' / 'WARN' / 'ERROR'), `_code`, `_desc`.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Register with `@register(rule_id, description)`.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Import in _ensure_rules_loaded().")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Map any new exception codes to severity in `_SEVERITY_MAP`.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Test in tests/test_<rule>.py.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("If Adding a New API Route:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Add to app/api/*.py. Include session.get('engagement_id') check.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("All DB access through store.* helpers.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("If analytics query: `apply_duckdb_limits(con)` immediately after opening.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Log via `get_logger(__name__)`.")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("If Modifying Templates:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Reuse CSS classes from main.css (`.btn`, `.card`, `.badge`, `.data-table`). Don't add new hex colors.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Extend base.html. Fill in blocks: page_title, topbar_actions, content.")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Form submits should use `data-loading-text` for spinner feedback.")] }),

      new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun("10. Development Setup & Prerequisites")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("What You Need:")] }),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2340, 3510, 3510],
        rows: [
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Requirement", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Install Command", bold: true, color: "FFFFFF" })] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA }, shading: { fill: headerFill, type: ShadingType.CLEAR },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun({ text: "Purpose", bold: true, color: "FFFFFF" })] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Python 3.11+")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Download from python.org")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Backend language")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Git")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("git-scm.com")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Version control")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("VS Code (recommended)")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("code.visualstudio.com")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Editor + debugging")] })] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ borders, width: { size: 2340, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("Node.js 18+")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("nodejs.org")] })] }),
              new TableCell({ borders, width: { size: 3510, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 120, right: 120 },
                children: [new Paragraph({ children: [new TextRun("For Electron desktop build")] })] })
            ]
          })
        ]
      }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("First-Time Setup:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Clone repo: `git clone <url>`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Create venv: `python -m venv .venv`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Activate: `.venv\\Scripts\\activate` (Windows)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Install deps: `pip install -e \".[dev]\"`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Run dev server: `python -m uvicorn app.main:app --reload --port 8000`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Visit: http://localhost:8000 (admin/admin123)")] }),

      new Paragraph({ spacing: { before: 120, after: 120 }, children: [new TextRun("")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Daily Development Workflow:")] }),

      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Pull latest: `git pull origin main`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Create feature branch: `git checkout -b feature/my-thing`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Start dev server (auto-reloads on file changes)")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Code → test → commit → push → PR")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Before commit: `ruff check . && black .`")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Before push: `pytest -m 'not perf' -v`")] }),

      new Paragraph({ spacing: { before: 120 }, children: [new TextRun("This is a comprehensive guide. All detailed sections are included above. Save this document for reference as you develop.")] }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/tmp/SanGir_Infrastructure_Guide.docx", buffer);
  console.log("Document created: /tmp/SanGir_Infrastructure_Guide.docx");
});
