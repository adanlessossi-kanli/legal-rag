# Frontend — Components

All components use `useTranslations` from `next-intl` for user-visible text. Navigation uses localized `Link`, `useRouter`, and `usePathname` from `@/i18n/navigation`.

## REQ-FC-001: ChatMessage
```tsx
interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  messageId?: string;
  conversationId?: string | null;
}

interface Source {
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
- Renders message bubble aligned left (assistant) or right (user).
- Assistant messages render markdown via `react-markdown` + `remark-gfm`.
- If `sources` present:
  - Group sources by `doc_id` under a document header showing name and passage count.
  - Each source entry within a group shows page/slide label, relevance badge, and text excerpt.
  - Page label: "Page N" for PDF/TXT/DOCX, "Slide N" for PPTX (detected from `source.document` extension).
  - Relevance badge: percentage (e.g., "92%"), color-coded green ≥ 0.9, yellow ≥ 0.8, gray below. Hidden when `relevance` is absent.
  - Each entry is clickable — opens `SourceViewer` modal with the source.
  - Visual affordance: hover state with `bg-accent-light`, cursor pointer, external-link icon.
  - Collapsible with ICU-pluralized toggle label.
- Feedback button for assistant messages (when `messageId` is present).
- Namespace: `chat` (`hideSources`, `sourceCount`, `viewSource`, `relevance`, `sourcesFromDocument`, `page`, `slide`).

## REQ-FC-002: ChatInput
```tsx
interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}
```
- Auto-resizing textarea + send button.
- Submit on Enter key or button click.
- Disabled state while awaiting response.
- Namespace: `chat` (`inputPlaceholder`, `sendLabel`, `inputLabel`).

## REQ-FC-003: FileDropzone
```tsx
interface FileDropzoneProps {
  onUpload: (files: File[]) => void;
  accept: string[];       // [".pdf", ".txt", ".docx", ".pptx"]
  maxSizeMB: number;      // 50
}
```
- Drag-and-drop area with visual feedback on hover.
- Falls back to file picker on click.
- Validates file type and size before calling `onUpload`.
- Uses `t.rich()` for inline rich text in dropzone label.
- Hint text renders `accept.join(", ")` — automatically includes `.pptx`.
- Namespace: `upload.dropzone` (`label`, `text`, `hint`, `unsupportedType`, `tooLarge`).

## REQ-FC-004: DocumentTable
```tsx
interface Document {
  id: string;
  name: string;
  uploaded_at: string;
  chunk_count: number;
  status: "processing" | "ready" | "error";
}
interface DocumentTableProps {
  documents: Document[];
  onDelete: (id: string) => void;
}
```
- Table with translated column headers: Document, Date, Chunks, Status, Actions.
- Locale-aware date formatting via `useFormatter().dateTime()`.
- Delete button with inline confirm/cancel actions.
- Illustrated empty state when no documents.
- Namespace: `documents` (`columns.*`, `empty.*`, `confirm`, `cancel`, `deleteLabel`).

## REQ-FC-005: Sidebar
- Navigation links: New Chat, Upload, Documents (translated labels).
- Highlights active route.
- Recent conversations list (auto-fetched, scrollable).
- Language switcher (LanguageSwitcher component) in bottom section.
- User name/email display + logout button.
- Collapsible on mobile (hamburger toggle with backdrop blur overlay).
- Namespace: `common` (`appName`, `appTagline`, `nav.*`, `recent`, `signOut`, `openNav`, `closeNav`, `closeNavOverlay`).

## REQ-FC-006: LanguageSwitcher
```tsx
// No props — reads locale from context
```
- Dropdown `<select>` with locale options: English, Français, Deutsch, Italiano.
- On change: calls `router.replace(pathname, { locale })` to switch locale.
- Placed in Sidebar (authenticated pages) and fixed top-right on Login/Register (public pages).
- Labels are hardcoded (language-neutral, not translated).

## REQ-FC-007: LoadingIndicator
- Animated typing dots inside a styled bubble.
- Used in chat while waiting for assistant response.
- No translatable text.

## REQ-FC-008: ErrorBoundary
- Class component wrapping a functional `ErrorFallback` for hook access.
- Displays error illustration, translated message, and refresh button.
- Namespace: `errors` (`somethingWentWrong`, `refreshHint`, `refreshPage`).

## REQ-FC-009: AuthGuard
- Client-side auth check on route change.
- Redirects unauthenticated users to `/login` (localized).
- Redirects authenticated users away from public routes to `/`.
- Renders Sidebar + main content wrapper for protected routes.
- No translatable text.

## REQ-FC-010: AgentIndicator
```tsx
interface AgentIndicatorProps {
  agent: string;   // "researcher" | "writer" | "summarizer" | "planner"
}
```
- Shows active agent name with animated ping dot and SVG icon.
- Displayed during streaming chat while agents are working.
- Namespace: `chat` (agent name labels).

## REQ-FC-011: SourceViewer
```tsx
interface SourceViewerProps {
  source: Source;
  open: boolean;
  onClose: () => void;
}
```
- Modal/overlay that opens when a source link is clicked.
- **Viewer mode** determined by file extension of `source.document`:
  - `.pdf` → PDF viewer mode (react-pdf).
  - `.txt`, `.docx`, `.pptx` → Text-excerpt mode (styled code block with page/slide label).
- **PDF viewer mode**:
  - Opens to the specific `page` from source metadata.
  - Highlights source text passage via `start_char` / `end_char` (best-effort, custom text renderer).
  - Page thumbnail sidebar (scrollable, clickable, current page highlighted).
  - Prev/Next navigation (arrow buttons + keyboard left/right). Page counter: "Page N of M".
  - Text search input in toolbar — highlights matches across PDF, navigate with up/down arrows.
- **Text-excerpt mode**: styled code block with "Page N" (TXT/DOCX) or "Slide N" (PPTX) label.
- **Signed URL expiry**: if a request returns 401/403 (expired signature), silently re-fetches a new signed URL and retries. Shows error only if retry also fails.
- **File missing from disk**: if file endpoint returns 404, shows "This document is no longer available for preview" message.
- Close on Escape key, backdrop click, or close button.
- Accessible: focus trap, `aria-modal`, `role="dialog"`.
- **Mobile** (< 768px): full-screen overlay, touch-friendly controls, swipe to change pages.
- **Lazy-loaded**: imported via `next/dynamic` with `ssr: false`. Loading spinner shown while chunk loads.
- **Deep link**: updates URL hash to `#source=<doc_id>&page=<page>` on open, clears on close. Auto-opens on page load if hash is present.
- Dependencies: `react-pdf`, `pdfjs-dist` (not in main bundle).
- Namespace: `chat` (`sourceViewerTitle`, `page`, `slide`, `pageRange`, `closeViewer`, `searchInDocument`, `pageOf`, `loadingViewer`, `previousPage`, `nextPage`, `fileUnavailable`).

## REQ-FC-012: FeedbackButton
```tsx
interface FeedbackButtonProps {
  conversationId: string | null;
  messageId: string;
}
```
- Thumbs up/down buttons for assistant message feedback.
- Submits rating via `POST /api/feedback`.
- Namespace: `chat` (feedback labels).

## REQ-FC-013: ExportButton
```tsx
interface ExportButtonProps {
  conversationId: string | null;
}
```
- Downloads conversation as markdown or JSON.
- Namespace: `chat` (export labels).
