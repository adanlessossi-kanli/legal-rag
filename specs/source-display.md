# Source Display — Specification

## Problem

Sources currently show only the document name and a truncated text excerpt. Users cannot navigate to the original document location. There is no way to verify the source in context — the user must manually find the passage in the original file. Multiple sources from the same document appear as flat, ungrouped cards with no relevance indication. PPTX files are not supported. After uploading a document, the user has no feedback that the documents list has changed without manually navigating away and back.

## Goals

1. Clicking a source link opens the original PDF (or document) with the relevant page highlighted.
2. Chunk metadata carries enough information (page range, character offsets) to locate the source precisely.
3. The frontend renders an in-app PDF viewer at the correct page when a source is clicked.
4. Sources are grouped by document, deduplicated, scored by relevance, and navigable.
5. Support PPTX file uploads with slide-level text extraction and page metadata.
6. After a successful upload, navigate the user to the documents page (client-side, no full reload) so they see the new document immediately.

---

## Backend Changes

### REQ-SD-001: Enrich Chunk Metadata with Page Range + Offsets

The loader already stores `page` in `DocumentPage.metadata`. The chunker must propagate this and add character offsets so the frontend can highlight the exact passage.

**Chunker changes** (`app/rag/chunker.py`):

- Continue using `langchain_text_splitters.RecursiveCharacterTextSplitter` (already in use).
- Use `splitter.create_documents([page.text], metadatas=[page.metadata])` instead of `splitter.split_text()`. This returns `Document` objects that carry the source metadata and allows langchain to track character positions natively, avoiding unreliable `str.find()` offset tracking.
- After splitting, compute `start_char` and `end_char` offsets relative to the source page text. Use the `loc` metadata that `create_documents` provides when available; fall back to a sliding-position search (tracking last found index to handle overlap duplicates) when it does not.
- A chunk can span two pages when the chunker joins all pages with `\n\n` before splitting. Track both `page_start` and `page_end` to handle cross-page chunks.
- The existing loader writes `metadata={"source": name, "page": i + 1}`. The **chunker** is responsible for renaming `page` → `page_start`, computing `page_end`, and copying `page_start` back as `page` for backward compatibility. The loader itself does not change.
- Each `Chunk.metadata` must include:

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | Original filename |
| `page` | `int` | Alias for `page_start` (backward compat) |
| `page_start` | `int` | 1-based start page number (or slide number for PPTX) |
| `page_end` | `int` | 1-based end page number (same as `page_start` for single-page chunks) |
| `doc_id` | `str` | Parent document ID |
| `start_char` | `int` | Start character offset within the start page |
| `end_char` | `int` | End character offset within the end page |

### REQ-SD-002: Enrich Source Schema

Update `Source` in `app/models/schemas.py`:

```python
class Source(BaseModel):
    document: str
    doc_id: str
    chunk_id: str
    text: str
    page: int | None = None
    page_end: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    relevance: float | None = None
```

All existing code that constructs `Source` objects must populate `doc_id`, `page`, and `relevance` from chunk metadata / retrieval scores. The `page_end`, `start_char`, `end_char` fields are optional for backward compatibility with chunks indexed before this change.

### REQ-SD-003: Source Deduplication + Merging

When multiple chunks originate from the same page of the same document, merge them into a single `Source` entry before returning to the client.

Add a utility function in `app/rag/sources.py`:

- Group retrieved chunks by `(doc_id, page_start)`.
- For chunks on the same page: merge into one `Source` with the union character range (`min(start_char)` → `max(end_char)`) and concatenated text (joined by `…` separator, capped at `SOURCE_TEXT_MAX_LENGTH`).
- Keep the highest `relevance` score from the merged chunks.
- Preserve original ordering (highest relevance first).

Call this function in the orchestrator before returning sources to the chat endpoint.

### REQ-SD-004: Enrich Source Construction with Relevance + Full Metadata

The retrieval pipeline already computes cosine similarity scores per chunk. Update **all** source construction paths to include `doc_id`, `page`, `page_end`, `start_char`, `end_char`, and `relevance` (from `chunk["score"]`).

Files that construct or pass through `Source` objects:

- `app/agents/orchestrator.py` — assembles sources from retrieval results; include `chunk["score"]` as `relevance`.
- `app/agents/librarian.py` — the `search` tool returns chunks with metadata; pass all fields through.
- `app/rag/pipeline.py` — the `query` / `query_stream` functions build `Source` lists; propagate new fields.
- `app/api/chat.py` — serializes `Source` objects to the response / SSE stream; no filtering of new fields.

### REQ-SD-005: Document File Serving Endpoint

Add `GET /api/documents/{doc_id}/file` to serve the original uploaded file.

- Auth: requires valid JWT or signed URL (see REQ-SD-005a); user must own the document or belong to the document's org.
- Returns the file with correct `Content-Type`:
  - `.pdf` → `application/pdf`
  - `.txt` → `text/plain`
  - `.docx` → `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - `.pptx` → `application/vnd.openxmlformats-officedocument.presentationml.presentation`
- Sets `Content-Disposition: inline; filename="<original_name>"` so the browser can render PDFs natively.
- Resolves the file path from the `uploads/` directory using the `doc_id` prefix pattern (`{doc_id}_{sanitized_name}`).
- Must prevent path traversal — validate that the resolved path is within `UPLOAD_DIR`.
- If the document record exists in MongoDB but the file is missing from disk (manual deletion, disk failure), return `404` with body `{"detail": "File no longer available on disk"}`. The frontend must handle this and show a user-facing message (see REQ-SD-010).

```
GET /api/documents/{doc_id}/file
Authorization: Bearer <token>  OR  ?sig=<token>&exp=<timestamp>

→ 200 (binary file with Content-Type)
→ 404 if document not found OR file missing from disk
→ 403 if user doesn't own the document
```

#### REQ-SD-005a: Signed URL Authentication

The PDF viewer loads files via `<iframe>` / `react-pdf` which cannot set `Authorization` headers. Instead of passing the raw JWT as a query parameter (which leaks into browser history and server logs), use a short-lived signed URL:

- Add `GET /api/documents/{doc_id}/file-token` — returns a signed token (HMAC-SHA256 of `doc_id + user_id + expiry`, using `JWT_SECRET` as the key) with a 5-minute TTL.
- The `file-token` endpoint **must validate document existence and user ownership before generating the token**. Return `404` / `403` at token generation time, not only at file-serve time. This prevents users from generating tokens for documents they cannot access.
- The file endpoint accepts `?sig=<signed_token>&exp=<timestamp>` and validates the signature + expiry instead of a Bearer token.
- The frontend calls `file-token` first, then constructs the file URL with the signature.

```
GET /api/documents/{doc_id}/file-token
Authorization: Bearer <token>

→ 200 { "url": "/api/documents/{doc_id}/file?sig=...&exp=..." }
→ 404 if document not found
→ 403 if user doesn't own the document
```

#### REQ-SD-005b: Range Request Support

Large PDFs should not require a full download before rendering the first page.

- The file endpoint must support HTTP `Range` headers (`Accept-Ranges: bytes`).
- Return `206 Partial Content` with `Content-Range` when a `Range` header is present.
- Use FastAPI's `FileResponse` or stream the file manually with range parsing.
- This allows `react-pdf` to load pages on demand.

#### REQ-SD-005c: Caching Headers

- Set `Cache-Control: private, max-age=3600, immutable` on file responses (documents don't change after upload unless re-versioned).
- Set `ETag` based on the document's `content_hash` (already stored in metadata).
- Support `If-None-Match` → return `304 Not Modified` when the hash matches.

### REQ-SD-006: PPTX File Support

Add PPTX as a supported upload and ingestion format.

#### REQ-SD-006a: PPTX Loader (`app/rag/loader.py`)

Add a `_load_pptx` function alongside the existing `_load_pdf`, `_load_txt`, `_load_docx` loaders.

- Use `python-pptx` library to extract text from PowerPoint files.
- Iterate over each slide. For each slide, concatenate all text from shapes that have a `text_frame` (text boxes, titles, content placeholders, table cells).
- Each slide becomes one `DocumentPage` with:
  - `text`: all extracted text from the slide, joined by `\n`.
  - `metadata`: `{"source": filename, "page": slide_number}` where `slide_number` is 1-based.
- Skip slides that produce empty text after stripping whitespace.
- **Edge case — all slides empty**: If every slide is skipped (0 pages returned), the ingestion pipeline will produce 0 chunks. The document will be saved with `chunk_count: 0` and `status: "ready"`. This is acceptable and consistent with how an empty TXT file behaves. The chat will return a "no context found" response when querying against it.
- Extract text from:
  - Shape text frames (titles, subtitles, body text, text boxes).
  - Table cells (`shape.has_table` → iterate rows/cells).
  - Grouped shapes (recurse into `shape.shapes` for group shapes).
- Do NOT extract: images, charts, SmartArt diagrams, speaker notes. This is a deliberate scope cut. Speaker notes are a future enhancement candidate — legal presentations often contain detailed notes that may be valuable for retrieval.

```python
def _load_pptx(path: Path, name: str) -> list[DocumentPage]:
    from pptx import Presentation
    prs = Presentation(str(path))
    pages = []
    for i, slide in enumerate(prs.slides):
        texts = _extract_slide_texts(slide.shapes)
        text = "\n".join(t for t in texts if t.strip())
        if text.strip():
            pages.append(DocumentPage(text=text, metadata={"source": name, "page": i + 1}))
    logger.info("Loaded PPTX %s: %d slides", name, len(pages))
    return pages


def _extract_slide_texts(shapes) -> list[str]:
    """Recursively extract text from shapes, including grouped shapes and tables."""
    texts = []
    for shape in shapes:
        if shape.has_text_frame:
            texts.append(shape.text_frame.text)
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    texts.append(cell.text)
        if hasattr(shape, "shapes"):  # GroupShape
            texts.extend(_extract_slide_texts(shape.shapes))
    return texts
```

Register `.pptx` in the `load_document` dispatcher:

```python
if ext == ".pptx":
    return _load_pptx(path, name)
```

#### REQ-SD-006b: Backend Upload Validation

Update `app/api/upload.py`:

- Add `.pptx` to `ALLOWED_EXTENSIONS`: `{".pdf", ".txt", ".docx", ".pptx"}`.
- No other changes needed — the existing upload flow (read bytes, hash, save to disk, enqueue) is format-agnostic.

#### REQ-SD-006c: Document Filter Options

Update `app/api/documents.py`:

- Extend the `file_type` query parameter validation pattern to include `pptx`: `^(pdf|txt|docx|pptx)$`.

Both the backend validation regex and the frontend filter dropdown must be updated together (see REQ-SD-013).

#### REQ-SD-006d: Dependency

Add `python-pptx` to `requirements.txt`:

```
python-pptx==1.0.2
```

---

## Frontend Changes

### REQ-SD-007: Update Source TypeScript Interface

In `lib/api.ts`:

```typescript
export interface Source {
  document: string;
  doc_id: string;
  chunk_id: string;
  text: string;
  page?: number;
  page_end?: number;
  start_char?: number;
  end_char?: number;
  relevance?: number;
}
```

### REQ-SD-008: Add Signed File URL Helper

In `lib/api.ts`, add:

```typescript
export async function getDocumentFileUrl(docId: string): Promise<string> {
  const { url } = await request<{ url: string }>(`/api/documents/${docId}/file-token`);
  return `${API_BASE}${url}`;
}
```

### REQ-SD-009: PDF Viewer Modal Component

Create `components/SourceViewer.tsx`:

- A modal/overlay that opens when a source link is clicked.
- **Viewer mode** is determined by the file extension of `source.document`:
  - `.pdf` → **PDF viewer mode** (react-pdf).
  - `.txt`, `.docx`, `.pptx` → **Text-excerpt mode** (styled code block with page/slide label).
- For PDF viewer mode:
  - Open to the specific `page` from the source metadata.
  - Highlight the source text passage on the page if `start_char` / `end_char` are available (best-effort text highlight via `react-pdf`'s custom text renderer).
  - **Page thumbnail sidebar**: render a scrollable column of page thumbnails on the left side of the viewer. Clicking a thumbnail navigates to that page. Highlight the current page thumbnail.
  - **Prev/Next navigation**: arrow buttons and keyboard left/right to navigate pages. Display current page number and total pages.
  - **Text search**: a search input in the viewer toolbar that highlights matching terms across the PDF using `react-pdf`'s text layer. Navigate between matches with up/down arrows.
- For text-excerpt mode: display the source text excerpt in a styled code block. Label as "Page N" for TXT/DOCX or "Slide N" for PPTX.
- **Signed URL expiry handling**: if a range request or page load returns 401/403 (expired signature), silently re-fetch a new signed URL via `getDocumentFileUrl()` and retry the request. Do not show an error to the user unless the retry also fails.
- **File missing from disk**: if the file endpoint returns 404 with `"File no longer available on disk"`, show a user-facing message: "This document is no longer available for preview" with a close button. Do not show a generic error.
- Close on Escape key, backdrop click, or close button.
- Accessible: focus trap, `aria-modal`, `role="dialog"`.
- **Mobile**: on viewports < 768px, render as a full-screen overlay instead of a centered modal. Use touch-friendly controls (larger buttons, swipe to change pages).

**Props**:
```typescript
interface SourceViewerProps {
  source: Source;
  open: boolean;
  onClose: () => void;
}
```

**Dependencies**: `react-pdf` (add to `package.json`). Uses `pdfjs-dist` worker for rendering.

#### REQ-SD-009a: Lazy Loading

`react-pdf` and `pdfjs-dist` are large dependencies (~500KB). Do not include them in the main bundle.

- Use `next/dynamic` with `ssr: false` to dynamically import `SourceViewer` only when the user clicks a source card.
- Show a loading spinner in the modal while the viewer chunk loads.

### REQ-SD-010: Source Grouping by Document

When multiple sources come from the same document, group them under a single document header instead of rendering flat cards.

Update `components/ChatMessage.tsx`:

- Group `sources` by `doc_id`.
- Render each group as:
  ```
  📄 contract.pdf
    ├─ Page 3 (92% match)  — "The total liability shall not exceed..."
    └─ Page 7 (85% match)  — "Indemnification obligations include..."
  ```
  For PPTX sources, label as "Slide N" instead of "Page N".
- Each page/slide entry is individually clickable (opens `SourceViewer` at that page).
- The document header shows the document name and the number of source passages.

### REQ-SD-011: Make Source Cards Clickable in ChatMessage

Update `components/ChatMessage.tsx`:

- Each source entry (within a document group) becomes a clickable button.
- On click: open the `SourceViewer` modal. The viewer determines its mode (PDF viewer vs text-excerpt) from the file extension (see REQ-SD-009).
- Visual affordance: add a hover state with `bg-accent-light`, cursor pointer, and a small external-link icon.
- Display relevance as a percentage badge (e.g., `92%`) if `relevance` is present. Color-code: green ≥ 0.9, yellow ≥ 0.8, gray below.

### REQ-SD-012: PPTX Support in Frontend

Update all frontend locations that reference allowed file types:

- `app/[locale]/upload/page.tsx` — change `accept` prop to `[".pdf", ".txt", ".docx", ".pptx"]`.
- `components/FileDropzone.tsx` — no code changes needed (it reads `accept` from props). The `hint` text will automatically include `.pptx` since it renders `accept.join(", ")`.
- `app/[locale]/documents/page.tsx` — add `pptx` option to the file type filter dropdown:
  ```tsx
  <option value="pptx">PPTX</option>
  ```

### REQ-SD-013: Post-Upload Navigation to Documents Page

After a successful upload, navigate the user to the documents page using client-side routing (no full page reload) so they immediately see the new document in the list.

Update `app/[locale]/upload/page.tsx`:

- Import `useRouter` from `@/i18n/navigation`.
- After all files in a batch have been uploaded (i.e., after `Promise.allSettled` resolves and at least one upload succeeded):
  - Wait a short delay (500ms) so the user can see the success confirmation.
  - Call `router.push("/documents")` to navigate client-side.
- If all uploads in the batch failed, stay on the upload page and show errors (no navigation).
- **Cleanup on unmount**: clear `results` and `errors` state when the component unmounts (via `useEffect` cleanup or by resetting state on mount). This prevents stale success cards from appearing if the user navigates back to `/upload` via the sidebar — Next.js may reuse the component instance depending on its caching behavior.
- **In-flight uploads**: if the user navigates away manually (e.g., clicks sidebar) while uploads are in progress, the `Promise.allSettled` will still resolve in the background. This is acceptable — the upload completes server-side regardless. The navigation timer should be cleared on unmount to avoid calling `router.push` on an unmounted component.

**Flow**:
```
User drops file → Upload starts → Spinner shown
  → Upload succeeds → Success card shown briefly (500ms)
  → router.push("/documents") → Documents page renders (SPA navigation)
  → New document visible with "processing" pill
  → WebSocket event arrives → Status updates to "ready" in-place
```

### REQ-SD-014: Deep Link / Shareable Source URL

Encode the source location in the URL hash so users can share a link to a specific source view.

- When the `SourceViewer` opens, update the URL hash to `#source=<doc_id>&page=<page>`.
- On page load, if the hash contains `#source=...`, auto-open the `SourceViewer` with the specified document and page.
- When the viewer closes, clear the hash.
- This works within the existing chat page URL (`/?c=<conversation_id>#source=<doc_id>&page=3`).

### REQ-SD-015: i18n Keys

Add to all locale files (`messages/en.json`, `fr.json`, `de.json`, `it.json`):

**`chat` namespace:**

| Key | EN | Description |
|-----|-----|-------------|
| `chat.viewSource` | `"View source"` | Tooltip on source card |
| `chat.sourceViewerTitle` | `"Source: {document}"` | Modal title |
| `chat.page` | `"Page {page}"` | Page label in viewer |
| `chat.slide` | `"Slide {page}"` | Slide label for PPTX sources |
| `chat.pageRange` | `"Pages {start}–{end}"` | Page range label for cross-page chunks |
| `chat.closeViewer` | `"Close"` | Close button label |
| `chat.relevance` | `"{score}% match"` | Relevance badge label |
| `chat.sourcesFromDocument` | `"{count} sources from {document}"` | Document group header |
| `chat.searchInDocument` | `"Search in document…"` | Search input placeholder |
| `chat.pageOf` | `"Page {current} of {total}"` | Page counter in viewer |
| `chat.loadingViewer` | `"Loading document…"` | Spinner text while viewer loads |
| `chat.previousPage` | `"Previous page"` | Prev button aria-label |
| `chat.nextPage` | `"Next page"` | Next button aria-label |
| `chat.fileUnavailable` | `"This document is no longer available for preview"` | Shown when file is missing from disk |

**`upload` namespace:**

| Key | EN | Description |
|-----|-----|-------------|
| `upload.redirecting` | `"Redirecting to documents…"` | Shown briefly before navigation |

**`documents` namespace:**

| Key | EN | Description |
|-----|-----|-------------|
| `documents.typePptx` | `"PPTX"` | File type filter label |

---

## Data Flow

### Source Viewer Flow

```
User clicks source entry (e.g., "Page 3" under contract.pdf)
  → Dynamic import loads SourceViewer chunk (first time only)
  → URL hash updates to #source=doc_abc123&page=3
  → Frontend calls GET /api/documents/doc_abc123/file-token
    → Backend validates doc exists + user owns it → returns signed URL
  → SourceViewer opens (modal on desktop, full-screen on mobile)
  → react-pdf fetches PDF via signed URL (Range requests for large files)
  → Browser caches the file (ETag / Cache-Control)
  → PDF renders at page 3
  → Text layer highlights characters start_char→end_char (best-effort)
  → User can navigate pages, search text, view thumbnails
  → If signed URL expires (>5min idle): viewer silently re-fetches token
  → On close: hash cleared, modal unmounted
```

### Upload → Documents Navigation Flow

```
User uploads file on /upload page
  → POST /api/upload → 200 { id, name, status: "processing" }
  → Success card rendered
  → 500ms delay
  → router.push("/documents") (client-side, no reload)
  → Upload page unmounts → cleanup clears timer + resets state
  → Documents page mounts, calls GET /api/documents
  → New document appears with "processing" status pill
  → WebSocket (already connected) receives ingestion_status event
  → Document status updates to "ready" in-place via setDocuments()
```

---

## Migration / Backward Compatibility

- Existing chunks in MongoDB lack `start_char`, `end_char`, `page_end`. The new fields are optional (`None`). The viewer gracefully degrades: opens the PDF at the correct page but without text highlighting.
- Existing chunks already have `page` and `doc_id` in their `metadata` dict — these just need to be surfaced into the `Source` schema. The chunker adds `page_start` and `page_end` as new fields; `page` remains unchanged.
- Existing chunks lack `relevance` in stored sources. The field is optional. The relevance badge is hidden when the value is absent.
- No database migration required. New chunks will automatically include the enriched metadata.
- Source deduplication/merging is applied at query time, not at storage time — no reindexing needed.
- PPTX support is additive — no existing data or behavior changes.

---

## Testing

### Backend

- **test_chunker.py** — Verify chunks include `page_start`, `page_end`, `start_char`, `end_char` in metadata. Verify `page` is preserved as alias for `page_start`. Verify offsets are correct for multi-page documents. Verify cross-page chunks have different `page_start` and `page_end`.
- **test_loader.py** — Add PPTX loading tests: single-slide, multi-slide, slides with tables, empty slides skipped, grouped shapes, all-slides-empty (returns empty list). Verify `DocumentPage.metadata` has correct `source` and `page` (slide number).
- **test_sources.py** — Verify deduplication: two chunks from the same `(doc_id, page)` merge into one `Source` with union character range. Verify ordering preserved. Verify highest relevance kept.
- **test_api.py** — Test `GET /api/documents/{doc_id}/file`: auth required, returns correct content-type (including PPTX), 404 for missing doc, 404 with specific message for doc-exists-but-file-missing-from-disk, 403 for unauthorized access, path traversal prevention, Range header support (206 response), ETag / If-None-Match (304 response).
- **test_api.py** — Test `GET /api/documents/{doc_id}/file-token`: returns signed URL, validates doc ownership before generating token (403 for unauthorized), URL expires after 5 minutes, invalid signature rejected, 404 for nonexistent doc.
- **test_upload.py** — Verify `.pptx` is accepted, other extensions still rejected.
- **test_chat.py** — Verify `Source` objects in chat response include `doc_id`, `page`, and `relevance`. Verify sources are deduplicated and grouped.

### Frontend

- **SourceViewer** — Renders modal, loads PDF at correct page, closes on Escape/backdrop. Page navigation (prev/next/thumbnail). Text search highlights matches. Full-screen on mobile. Lazy-loaded (not in main bundle). Text-excerpt mode for PPTX/DOCX/TXT with "Slide N" label for PPTX. Shows "file unavailable" message on 404. Silently refreshes signed URL on 401/403 expiry.
- **ChatMessage** — Sources grouped by document. Each entry clickable, opens viewer with correct props. Relevance badge displayed and color-coded. Deep link hash updated on open, cleared on close. PPTX sources labeled "Slide N".
- **Upload page** — After successful upload, navigates to `/documents` via client-side routing. No navigation on failure. PPTX files accepted in dropzone. State cleaned up on unmount. Navigation timer cleared on unmount.
- **Documents page** — File type filter includes PPTX option (synced with backend regex). WebSocket updates document status in-place after navigation from upload.

---

## API Summary

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/documents/{doc_id}/file` | Signed URL | Serve original uploaded file (supports Range) |
| `GET` | `/api/documents/{doc_id}/file-token` | Yes | Generate short-lived signed URL (validates ownership) |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_TOKEN_EXPIRY_SECONDS` | `300` | Signed file URL TTL (5 minutes) |

All other settings use existing configuration (`UPLOAD_DIR`, `JWT_SECRET`, `SOURCE_TEXT_MAX_LENGTH`).

---

## Dependencies

| Package | Version | Layer | Purpose |
|---------|---------|-------|---------|
| `python-pptx` | `1.0.2` | Backend | PPTX text extraction |
| `react-pdf` | latest | Frontend | In-browser PDF rendering |
| `pdfjs-dist` | (peer dep of react-pdf) | Frontend | PDF.js worker |

---

## Future Enhancements (Out of Scope)

- **PPTX speaker notes extraction** — Legal presentations often have detailed notes. Add an opt-in config flag to include notes as additional text per slide.
- **PPTX/DOCX inline viewer** — Convert to PDF server-side (via LibreOffice headless) for in-browser rendering with the same PDF viewer.
- **Image/chart OCR** — Extract text from embedded images and charts in PPTX/PDF via OCR.
