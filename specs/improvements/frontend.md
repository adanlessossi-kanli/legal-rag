# Improvements — Frontend

## REQ-IF-001: React Error Boundary

A rendering error in any component currently crashes the entire app with a white screen.

### Requirements
- Add an `ErrorBoundary` component wrapping `{children}` in `layout.tsx`.
- On error, display a user-friendly fallback: "Something went wrong. Please refresh the page."
- Log the error to `console.error` for debugging.

### Component
```tsx
// components/ErrorBoundary.tsx
interface State { hasError: boolean }

class ErrorBoundary extends React.Component<{ children: ReactNode }, State> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info); }
  render() {
    if (this.state.hasError) return <fallback UI>;
    return this.props.children;
  }
}
```

### Integration
- Wrap `{children}` in `layout.tsx` with `<ErrorBoundary>`.

---

## REQ-IF-002: Stable Message Keys

Chat messages are keyed by array index (`key={i}`), which can cause rendering bugs if messages are reordered or removed.

### Requirements
- Assign a unique `id` (e.g. `crypto.randomUUID()`) to each message when created.
- Add `id: string` to the `Message` interface in `lib/api.ts`.
- Use `msg.id` as the React `key` in the message list.

### State Change
```tsx
// In reducer ADD_USER_MESSAGE action:
{ id: crypto.randomUUID(), role: "user", content: action.content }
```

---

## REQ-IF-003: AbortController for In-Flight Requests

If the user navigates away or the component unmounts while a chat request is pending, the fetch continues running and may update unmounted state.

### Requirements
- Create an `AbortController` before each chat API call.
- Pass `signal` to the `fetch` options in `lib/api.ts`.
- Abort the controller on component unmount (via `useEffect` cleanup) or when a new request is sent.
- Ignore `AbortError` in the catch handler (don't show it as a user-facing error).

### API Client Change
```tsx
export async function chat(
  question: string,
  history: { role: string; content: string }[],
  signal?: AbortSignal
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
    signal,
  });
}
```

---

## REQ-IF-004: Parallel File Uploads

The upload page processes files sequentially in a `for` loop. Uploading multiple files is unnecessarily slow.

### Requirements
- Use `Promise.allSettled()` to upload all selected files in parallel.
- For each settled promise:
  - `fulfilled` → add to results list.
  - `rejected` → add to an errors list.
- Display both successful uploads and individual file errors.

### Implementation
```tsx
const handleUpload = async (files: File[]) => {
  setUploading(true);
  setError(null);
  const settled = await Promise.allSettled(files.map(uploadDocument));
  for (const result of settled) {
    if (result.status === "fulfilled") {
      setResults((prev) => [...prev, result.value]);
    } else {
      setErrors((prev) => [...prev, result.reason?.message || "Upload failed"]);
    }
  }
  setUploading(false);
};
```
