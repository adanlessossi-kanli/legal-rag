# Frontend — Components

## REQ-FC-001: ChatMessage
```tsx
interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: { document: string; chunk_id: string; text: string }[];
}
```
- Renders message bubble aligned left (assistant) or right (user).
- If `sources` present, render as collapsible list below the message.

## REQ-FC-002: ChatInput
```tsx
interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}
```
- Text input + send button.
- Submit on Enter key or button click.
- Disabled state while awaiting response.

## REQ-FC-003: FileDropzone
```tsx
interface FileDropzoneProps {
  onUpload: (files: File[]) => void;
  accept: string[];       // e.g. [".pdf", ".txt"]
  maxSizeMB: number;      // e.g. 50
}
```
- Drag-and-drop area with visual feedback on hover.
- Falls back to file picker on click.
- Validates file type and size before calling `onUpload`.

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
- Sortable table with columns: Name, Date, Chunks, Status, Actions.
- Delete button with confirmation dialog.

## REQ-FC-005: Sidebar
- Navigation links: Chat, Upload, Documents.
- Highlights active route.
- Collapsible on mobile (hamburger toggle).

## REQ-FC-006: LoadingIndicator
- Animated dots or spinner.
- Used in chat (waiting for response) and upload (progress).
