# Frontend — Pages

## Routes

All pages live under the `[locale]` dynamic segment. The default locale (`en`) uses clean URLs via `localePrefix: "as-needed"`.

| Route                      | Page         | Auth     | Description                        |
|---------------------------|--------------|----------|-------------------------------------|
| `/[locale]`               | Chat         | Required | Main chat interface (default page)  |
| `/[locale]/upload`        | Upload       | Required | Document upload with drag-and-drop  |
| `/[locale]/documents`     | Documents    | Required | List uploaded/ingested documents    |
| `/[locale]/login`         | Login        | Public   | Email + password sign-in            |
| `/[locale]/register`      | Register     | Public   | Account creation form               |

### URL examples

| English (default) | French | German | Italian |
|-------------------|--------|--------|---------|
| `/`               | `/fr`  | `/de`  | `/it`   |
| `/login`          | `/fr/login` | `/de/login` | `/it/login` |
| `/upload`         | `/fr/upload` | `/de/upload` | `/it/upload` |
| `/documents`      | `/fr/documents` | `/de/documents` | `/it/documents` |

## REQ-FP-001: Chat Page (`/[locale]`)
- Display a scrollable message list (user + assistant messages).
- Input bar at the bottom with send button.
- Each assistant message renders cited sources as collapsible, grouped cards (grouped by document, see REQ-FC-001).
- Clicking a source entry opens the `SourceViewer` modal at the relevant page.
- Show a loading indicator while waiting for the backend response.
- Agent status indicator during streaming (Researching → Writing → Summarizing).
- Document scope selector to filter retrieval by specific documents.
- Conversation persistence: loads existing conversation from URL param `?c=<id>`, auto-creates new conversation on first message.
- Deep link support: URL hash `#source=<doc_id>&page=<page>` auto-opens `SourceViewer` on page load.
- Empty state with illustration, description, and example query chips.
- "New Chat" button clears conversation and resets URL.
- Export button for conversation download.
- Disclaimer footer about AI-generated answers.
- All labels translated via `useTranslations("chat")`.

### Behavior
- On send: stream via SSE to `/api/chat?stream=true` with `{ question, conversation_id, document_ids }`.
- On conversation load: GET `/api/conversations/{id}`.
- If backend returns an error, show inline error message.

## REQ-FP-002: Upload Page (`/[locale]/upload`)
- Drag-and-drop zone + file picker button.
- Accept `.pdf`, `.txt`, `.docx`, and `.pptx` files (max 50MB).
- Show animated spinner during upload.
- On success: display confirmation card with document name, then navigate to `/documents` via client-side routing after 500ms delay.
- On failure (all uploads in batch failed): stay on upload page and display error alerts. No navigation.
- **Cleanup**: clear `results` and `errors` state on component unmount. Clear navigation timer on unmount to prevent `router.push` on unmounted component.
- All labels translated via `useTranslations("upload")`.

### Behavior
- On drop/select: POST multipart to `/api/upload` (one request per file, via `Promise.allSettled`).
- Validate file type and size client-side before sending.
- After at least one successful upload: 500ms delay → `router.push("/documents")`.
- Documents page picks up the new document via its initial fetch + WebSocket for status updates.

## REQ-FP-003: Documents Page (`/[locale]/documents`)
- Table listing all ingested documents: name, date, chunk count, status.
- Status values: `processing`, `ready`, `error` (pill-shaped badges).
- Delete button per document with confirm/cancel inline actions.
- Optimistic UI: removes document from list immediately, reverts on error.
- Locale-aware date formatting via `useFormatter().dateTime()`.
- Pluralized document count subtitle via ICU message format.
- Illustrated empty state when no documents exist.
- **Search**: text input with debounced filename search.
- **Filters**: status filter (`All`, `Ready`, `Processing`, `Error`), file type filter (`All`, `PDF`, `DOCX`, `TXT`, `PPTX`).
- **Sorting**: by date, name, or chunk count with toggle direction.
- **Pagination**: prev/next buttons with page counter.
- **WebSocket**: listens for ingestion status events to update document status in real-time (no polling).
- All labels translated via `useTranslations("documents")`.

### Behavior
- On mount: GET `/api/documents` with search/filter/sort/page params.
- On delete: DELETE `/api/documents/{id}`.
- WebSocket (`connectIngestionWs`) updates document status in-place.

## REQ-FP-004: Login Page (`/[locale]/login`)
- Email + password form with translated labels and placeholders.
- Error alert on failed login.
- Link to register page.
- Language switcher fixed in top-right corner.
- Rendered without sidebar (public route).
- All labels translated via `useTranslations("auth.login")`.

### Behavior
- On submit: POST to `/api/auth/login`.
- On success: redirect to `/`.
- If already authenticated: redirect to `/`.

## REQ-FP-005: Register Page (`/[locale]/register`)
- Name + email + password form with translated labels, placeholders, and validation hints.
- Error alert on failed registration.
- Link to login page.
- Language switcher fixed in top-right corner.
- Rendered without sidebar (public route).
- All labels translated via `useTranslations("auth.register")`.

### Behavior
- On submit: POST to `/api/auth/register`.
- On success: redirect to `/`.
- If already authenticated: redirect to `/`.

## Layout

- **Root layout** (`app/layout.tsx`) — Font loading, global CSS only.
- **Locale layout** (`app/[locale]/layout.tsx`) — `NextIntlClientProvider`, `AuthGuard`, `ErrorBoundary`. Generates per-locale metadata.
- **AuthGuard** — Redirects unauthenticated users to `/login`, renders Sidebar for protected routes.
- **Sidebar** — Shared navigation with links to Chat, Upload, Documents. Language switcher and user info at bottom. Collapses to hamburger on mobile.
- Responsive: sidebar collapses on mobile with backdrop blur overlay.
- Dark/light mode via CSS custom properties.
