# Frontend — State & API Client

## State Management
Use React `useState`/`useReducer` — no external state library for v1.

### Chat State
```tsx
interface ChatState {
  messages: Message[];
  conversationId: string | null;
  isLoading: boolean;
  error: string | null;
}
```
- Managed in Chat page via `useReducer`.
- Actions: `LOAD`, `ADD_USER_MESSAGE`, `START_ASSISTANT`, `APPEND_TOKEN`, `SET_SOURCES`, `SET_CONVERSATION_ID`, `FINISH_ASSISTANT`, `SET_ERROR`, `CLEAR`.
- Error messages use `useTranslations("chat")` for translated fallbacks.

### Documents State
- Fetched on mount via `GET /api/documents`.
- Optimistic delete: removes from list immediately, reverts on error.
- Error messages use `useTranslations("documents")` for translated fallbacks.

## API Client (`lib/api.ts`)

```tsx
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function chat(question: string, history: Message[]): Promise<ChatResponse>;
async function uploadDocument(file: File): Promise<UploadResponse>;
async function getDocuments(): Promise<Document[]>;
async function deleteDocument(id: string): Promise<void>;
```

### Error Handling
- All API functions throw on non-2xx responses.
- Error shape: `{ detail: string }` (matches FastAPI default).
- UI catches and displays via `error` state.

## Environment Variables
| Variable               | Description              | Default                  |
|-----------------------|--------------------------|--------------------------|
| `NEXT_PUBLIC_API_URL` | Backend base URL         | `http://localhost:8000`  |
