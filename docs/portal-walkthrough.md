# PDF-QA Validation Portal Walkthrough

This document outlines the final system implementation, code layout, and validation testing for the PDF-QA Validation Portal.

---

## 1. Accomplished Work & Changes

### Backend Component
- **FastAPI Core (`backend/main.py`)**: Wired all routing endpoints, set up CORS middleware, and mounted a `/uploads` static file server.
- **SQLite DB Layer (`backend/database.py` & `backend/models.py`)**: Defined schemas for `documents`, `sections`, `footnotes`, and `annotations`. Created the SQLite `fts5` virtual table and insert/update/delete triggers to automatically synchronize sections text indices.
- **Enriched JSON Traverser (`backend/services/json_parser.py`)**: Flattened the Pakistan Income Tax Ordinance JSON hierarchy (Chapters/Schedules → Parts → Divisions → Sections) into database-ready records.
- **PDF Page Count Helper (`backend/services/pdf_service.py`)**: Used `pypdf` to get total pages for database stats.
- **REST Endpoints**:
  - `/documents` (upload, listing, deleting document metadata with calculated stats).
  - `/documents/.../sections` (TOC sidebar listing, detailed section HTML retriever, and `by-page` page-level mapping).
  - `/sections/.../annotations` (Inline highlight annotations CRUD).
  - `/footnotes` (Validation status updater).
  - `/documents/.../export` (Compiles QA report, streaming it as a downloadable CSV or JSON file).

### Frontend Component
- **Stores (Zustand)**: `documentStore.js` (document fetching, sections, and search), `reviewStore.js` (annotations CRUD, pagination, and view comparison mode toggles), and `uiStore.js` (dark/light mode triggers, sidebar state, resizable split panel ratio, and PDF zoom levels).
- **Core Workspace Panels**:
  - `PdfPanel.jsx` / `usePdfRenderer.js`: Standard client-side canvas-level rendering hook using PDF.js.
  - `HtmlPanel.jsx` / `useTextSelection.js`: Standard selection hook capturing DOM offsets, combined with automatic highlight injection via `<mark>` elements on load.
  - `FootnotePanel.jsx`: Visualizes markers and pages with status triggers.
- **Page Layout**:
  - `DashboardPage.jsx`: Main interface with stats counters, document cards, circular SVG progress meters, and CSV/JSON downloads.
  - `UploadPage.jsx`: Form dropzones providing local JSON validation (FileReader based) and metadata parsing before server ingestion.
  - `ReviewPage.jsx` / `SplitPane.jsx`: Resizable workspace pane binding PDF and HTML outputs side-by-side, supporting keyboard page navigation and view comparisons.

---

## 2. Seeding sample legal documents
We created a custom seeding script: `backend/seed.py`. Running it copied the original Income Tax Ordinance 2001 PDF and its enriched JSON, parsed all 368 sections and 1,323 footnotes, and initialized the SQLite database files.

---

## 3. Visual Verification

The browser subagent verified the dashboard, loaded the Pakistan Income Tax Ordinance 2001 workspace, toggled layouts, checked navigation, and confirmed highlights.

### PDF & HTML Side-by-Side Verification
Here is the screenshot showing the Pakistan Income Tax Ordinance loaded in the portal with the PDF on the left and HTML on the right:

![PDF Loaded Successfully](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/pdf_loaded_success_1782245088551.png)

### Web Portal Session Recording
Here is the full interaction video demonstrating the portal loading and page navigation:

![QA Portal Interaction Video](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/qa_portal_verification_1782244859259.webp)

### Review Toolbar Layout Fix
We resolved a visual layout discrepancy where the review toolbar at the bottom of the HTML pane wrapped awkwardly on smaller screen widths. We redesigned the toolbar to use a compact row layout:
- Styled the review status as a clean, nowrap metadata badge.
- Shortened button text ("Approve Section" → "Approve", "Flag Issues" → "Flag") and styled them with `white-space: nowrap`.
- Replaced text-based Previous/Next navigation links with compact icon buttons.

Here is the screenshot showing the fixed, compact review toolbar aligned correctly in the workspace:

![Fixed Review Toolbar Layout](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/toolbar_verification_1782245538085.png)

### Search Navigation Sync Fix
We resolved an issue where clicking on search results from the Sidebar Search panel caused the Parsed HTML pane to jump, but left the PDF original view stuck on the previous page.
- We updated [Sidebar.jsx](file:///Users/muhammad.husnain/Downloads/code/AG/PDF-QA-Portal/frontend/src/components/layout/Sidebar.jsx#L35-L40)'s `handleSectionClick` action to dynamically retrieve `sec.start_page` from the fetched section document if the `startPage` argument is not explicitly provided (which is the case for search results, as the search index endpoint only provides metadata snippets).
- The click action now correctly triggers the `setCurrentPage` state event and synchronizes the PDF canvas and parsed HTML panes simultaneously.

### PDF Zoom Horizontal Scroll Fix
We resolved an layout scrollbug where zooming in on the PDF canvas caused the left side to get clipped and prevented horizontal scrolling.
- **Cause**: The `.pdf-scroll-container` utilized flex layout with horizontal centering (`display: flex; justify-content: center`). In browser layout engines, when a flex item overflows a centered container, it overflows equally on both sides. The left-side overflow falls behind the scroll start line (`scrollLeft = 0`) and becomes unreachable via scrolling.
- **Fix**: Updated [index.css](file:///Users/muhammad.husnain/Downloads/code/AG/PDF-QA-Portal/frontend/src/index.css#L406-L425) to use block layout (`display: block`) for the overflow scroll container, and centered the canvas wrapper utilizing margin-auto (`margin: 0 auto; width: max-content`). When the canvas is smaller than the pane, it centers. When zoomed, it expands block-wise to the right, letting the browser trigger scrollbars for complete horizontal pan visibility.

Here is the screenshot showing the zoomed PDF view with active horizontal scrolling:

![Zoomed PDF with Horizontal Scroll](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/pdf_scrolled_175_1782286332974.png)

### Dockerized Application Verification
We successfully built the Docker images and launched the application stack locally via Docker Compose. The browser subagent navigated to `http://localhost:5173/` and verified that the containerized frontend can connect to the containerized backend, query the SQLite database, and load the workspace successfully.

Here is the screenshot of the side-by-side view running in Docker:

![Docker Side-by-Side View](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/review_side_by_side_1782297606503.png)

Here is the screen recording of the browser verification flow:

![Docker Verification Session](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/docker_verification_1782297563342.webp)

### Footnote Selection, Status & Reporting Updates
We resolved issues around footnotes interaction and added a complete validation framework for footnote texts:
1. **Interactive Text Selection & Annotation**: Enabled selecting text segments inside footnote cards to create popover annotations. These annotations are persisted to the database with a reference to the footnote (`footnote_id`).
2. **Footnote Text Highlighting**: Text annotations on footnotes dynamically compile into yellow inline highlight marks (`<mark>` tag wrappers) rendered directly in the React footnote text container.
3. **Approval and Flag Action Status Updates**: Fixed a Zustand store issue (`TypeError: docStore.setState is not a function`) by correctly invoking the store's hook method (`useDocumentStore.setState`). Status updates now work correctly for both single-section reviews and page-level grouped section reviews.

Here is the screenshot showing the verified, highlighted footnote annotation in the workspace:

![Footnote Annotation Verified](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/footnote_annotation_verified_1782305448796.png)

Here is the screen recording demonstrating footnote status toggles and text highlight annotation reporting:

![Footnote Verification Recording](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/footnote_fixes_verify_1782305145806.webp)

### Global Issues & Resolution Workflow
We added support for document-level mismatch auditing and status resolution tracking:
1. **Document-wide Issues tab**: The "Issues" tab in the left sidebar aggregates all reported annotations (at both the section body and footnote card levels) for the active document.
2. **Open / Resolved sub-tabs**: The list features two sub-tabs displaying **Open** issues (still active) and **Resolved** issues (marked as resolved).
3. **Resolving Issues (Checkboxes)**: Tapping the checkbox next to any issue card toggles its state between open and resolved. Resolving an issue dynamically shifts the card to the resolved list and removes the yellow highlight overlays from the main visual panes (HTML and footnote text) to reduce visual clutter.
4. **Redirection on Click**: Clicking any issue card in the global list triggers a redirect that jumps the PDF viewer and HTML panels directly to the corresponding section.

Here is the screenshot showing the global Issues tab with open annotations and status counts:

![Global Issues Workspace](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/reopened_issue_1782307889637.png)

Here is the screen recording demonstrating the global issues checklist, resolving a mismatch, and navigating back and forth:

![Global Issues Verification Recording](/Users/muhammad.husnain/.gemini/antigravity-ide/brain/35fd6d3e-3083-46fe-8f44-61249f3d5dd4/global_issues_verify_1782307113271.webp)

---


## 4. How to Run the Portal

### Option A: Running with Docker Compose (Recommended)
This method containerizes the entire stack, linking the frontend and backend services automatically. Ensure Docker Desktop is installed and running on your host machine.

From the project root directory, run:
```bash
# Build and start both services in the background
docker compose up -d --build
```
- **Dashboard**: Access the portal in your browser at `http://localhost:5173/`
- **Backend API Docs**: Access `http://localhost:8000/docs`
- **Persistence**: Database state (`backend/data/`) and uploaded documents (`backend/uploads/`) map dynamically to the host machine for safety.

To stop the containers:
```bash
docker compose down
```

---

### Option B: Running Locally (Manual setup)

#### Prerequisites
- Python 3.10+
- Node.js 18+

#### Step 1: Start Backend Server
Ensure you are in the project root directory, then run:
```bash
# Activate virtual environment
source backend/venv/bin/activate

# Run FastAPI uvicorn server
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

#### Step 2: Start Frontend Dev Server
In a separate terminal tab, run:
```bash
cd frontend
npm run dev -- --host 127.0.0.1
```
The Vite dev server will run at `http://127.0.0.1:5173/`. Open it in any browser to start validation!

