# Frontend — Components

All components use `useTranslations` from `next-intl` for user-visible text. Navigation uses localized `Link`, `useRouter`, and `usePathname` from `@/i18n/navigation`.

## REQ-FC-001: ChatMessage
```tsx
interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: { document: string; chunk_id: string; text: string }[];
}
```
- Renders message bubble aligned left (assistant) or right (user).
- Assistant messages render markdown via `react-markdown` + `remark-gfm`.
- If `sources` present, render as collapsible list with ICU-pluralized toggle label.
- Namespace: `chat` (`hideSources`, `sourceCount`).

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
  accept: string[];       // e.g. [".pdf", ".txt", ".docx"]
  maxSizeMB: number;      // e.g. 50
}
```
- Drag-and-drop area with visual feedback on hover.
- Falls back to file picker on click.
- Validates file type and size before calling `onUpload`.
- Uses `t.rich()` for inline rich text in dropzone label.
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
