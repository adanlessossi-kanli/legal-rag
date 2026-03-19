# Frontend — Pages

## Routes

| Route          | Page         | Description                        |
|---------------|--------------|------------------------------------|
| `/`           | Chat         | Main chat interface (default page) |
| `/upload`     | Upload       | Document upload with drag-and-drop |
| `/documents`  | Documents    | List uploaded/ingested documents   |

## REQ-FP-001: Chat Page (`/`)
- Display a scrollable message list (user + assistant messages).
- Input bar at the bottom with send button.
- Each assistant message must render cited sources as clickable chips below the answer.
- Show a loading indicator while waiting for the backend response.
- Session-scoped: conversation resets on page refresh.

### Behavior
- On send: POST to `/api/chat` with `{ question, history }`.
- Render streamed or complete response.
- If backend returns an error, show inline error message.

## REQ-FP-002: Upload Page (`/upload`)
- Drag-and-drop zone + file picker button.
- Accept `.pdf` and `.txt` files only.
- Show upload progress per file.
- On success: display confirmation with document name.
- On failure: display error message.

### Behavior
- On drop/select: POST multipart to `/api/upload`.
- Validate file type client-side before sending.

## REQ-FP-003: Documents Page (`/documents`)
- Table listing all ingested documents: name, upload date, chunk count, status.
- Status values: `processing`, `ready`, `error`.
- Delete button per document (calls DELETE `/api/documents/{id}`).

## Layout
- Shared sidebar navigation with links to all three pages.
- Responsive: sidebar collapses to hamburger on mobile.
- Dark/light mode via Tailwind `dark:` classes.
