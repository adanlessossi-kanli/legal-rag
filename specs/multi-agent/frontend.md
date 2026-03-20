# Multi-Agent RAG — Frontend Changes

## REQ-FE-001: Scope

Frontend changes are additive. The API contract (request/response shapes) does not change. The only addition is a new SSE event type `agent_status` that enables a real-time agent activity indicator. Old frontends that don't handle this event continue to work (unknown SSE event types are ignored by the existing parser).

## REQ-FE-002: New SSE Event — `agent_status`

### Event Shape

```
data: {"type": "agent_status", "agent": "researcher", "status": "working"}
```

| Field    | Type   | Values                                      |
|---------|--------|---------------------------------------------|
| `type`   | string | Always `"agent_status"`                     |
| `agent`  | string | `"researcher"`, `"writer"`, `"summarizer"` |
| `status` | string | `"working"`, `"done"`                       |

### Full SSE Sequence (streaming query)

```
data: {"type": "agent_status", "agent": "researcher", "status": "working"}
data: {"type": "sources", "sources": [...]}
data: {"type": "agent_status", "agent": "writer", "status": "working"}
data: {"type": "conversation_id", "conversation_id": "abc123"}
data: {"type": "token", "token": "According"}
data: {"type": "token", "token": " to"}
...
data: {"type": "agent_status", "agent": "done", "status": "done"}
data: {"type": "done"}
```

### Backward Compatibility

The `agent_status` event is inserted between existing events. Existing event types (`sources`, `token`, `conversation_id`, `done`) remain in the same relative order. A frontend that doesn't handle `agent_status` simply skips it.

## REQ-FE-003: Modified Files

### `src/lib/api.ts`

Add optional `onAgentStatus` callback to `chatStream`:

```typescript
export async function chatStream(
  question: string,
  conversationId: string | null,
  onToken: (token: string) => void,
  onSources: (sources: Source[]) => void,
  onConversationId: (id: string) => void,
  signal?: AbortSignal,
  documentIds?: string[],
  onAgentStatus?: (agent: string, status: string) => void,  // NEW — optional
): Promise<void> {
  // ... existing code ...

  // In the SSE parsing loop, add one branch:
  else if (data.type === "agent_status" && onAgentStatus) {
    onAgentStatus(data.agent, data.status);
  }
}
```

The callback is optional — callers that don't pass it get the same behavior as before.

### `src/app/[locale]/page.tsx`

Add `activeAgent` to chat state:

```typescript
interface ChatState {
  messages: Message[];
  conversationId: string | null;
  isLoading: boolean;
  error: string | null;
  activeAgent: string | null;  // NEW
}

// New action type
| { type: "SET_AGENT"; agent: string | null }

// Reducer cases
case "SET_AGENT":
  return { ...state, activeAgent: action.agent };
case "FINISH_ASSISTANT":
  return { ...state, isLoading: false, activeAgent: null };  // clear agent on finish
case "CLEAR":
  return { messages: [], conversationId: null, isLoading: false, error: null, activeAgent: null };
case "SET_ERROR":
  return { ...state, error: action.error, isLoading: false, activeAgent: null };  // clear agent on error
```

Wire the callback in `handleSend`:

```typescript
await chatStream(
  question,
  state.conversationId,
  (token) => dispatch({ type: "APPEND_TOKEN", id: assistantMsgId, token }),
  (sources) => dispatch({ type: "SET_SOURCES", id: assistantMsgId, sources }),
  (id) => { ... },
  controller.signal,
  selectedDocIds,
  (agent, status) => dispatch({
    type: "SET_AGENT",
    agent: status === "done" ? null : agent,
  }),
);
```

Render the indicator above the loading dots:

```tsx
{state.isLoading && state.activeAgent && (
  <AgentIndicator agent={state.activeAgent} />
)}
{state.isLoading && state.messages[state.messages.length - 1]?.content === "" && (
  <LoadingIndicator />
)}
```

## REQ-FE-004: New Component — `AgentIndicator`

### File

`src/components/AgentIndicator.tsx`

### Props

```typescript
interface AgentIndicatorProps {
  agent: string;  // "researcher" | "writer" | "summarizer"
}
```

### Behavior

- Renders only when `agent` is non-null (controlled by parent).
- Displays a translated label with a pulsing dot animation.
- Agent name is mapped to an icon and i18n key.
- Accessible: includes `role="status"` and `aria-live="polite"` for screen readers.

### Agent → Icon Mapping

| Agent        | Icon | Description        |
|-------------|------|--------------------|
| `researcher` | 🔍   | Magnifying glass   |
| `writer`     | ✍️   | Writing hand       |
| `summarizer` | 📝   | Memo/notepad       |

Icons are inline SVGs (consistent with existing components), not emoji. The emoji above is for illustration.

### Rendering

```tsx
export default function AgentIndicator({ agent }: AgentIndicatorProps) {
  const t = useTranslations("chat");
  const label = t(`agents.${agent}`);

  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl
                 bg-surface-hover border border-border text-xs text-muted
                 ml-11"  /* aligned with assistant message (avatar width + gap) */
      role="status"
      aria-live="polite"
    >
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
      </span>
      <AgentIcon agent={agent} />
      {label}...
    </div>
  );
}
```

### Styling

| Property        | Value                    |
|----------------|--------------------------|
| Background      | `var(--surface-hover)`   |
| Border          | `1px solid var(--border)` |
| Border radius   | `0.75rem`                |
| Padding         | `0.375rem 0.75rem`       |
| Font size       | `0.75rem` (12px)         |
| Text color      | `var(--muted)`           |
| Pulsing dot     | `var(--accent)`, Tailwind `animate-ping` |
| Width           | `fit-content`            |
| Left margin     | `2.75rem` (avatar 2rem + gap 0.75rem) |

## REQ-FE-005: i18n Additions

All four locale files get the same new keys under `chat.agents`:

### `messages/en.json`

```json
{
  "chat": {
    "agents": {
      "researcher": "Researching",
      "writer": "Writing",
      "summarizer": "Summarizing"
    }
  }
}
```

### `messages/fr.json`

```json
{
  "chat": {
    "agents": {
      "researcher": "Recherche en cours",
      "writer": "Rédaction en cours",
      "summarizer": "Résumé en cours"
    }
  }
}
```

### `messages/de.json`

```json
{
  "chat": {
    "agents": {
      "researcher": "Recherche läuft",
      "writer": "Schreibt",
      "summarizer": "Zusammenfassung"
    }
  }
}
```

### `messages/it.json`

```json
{
  "chat": {
    "agents": {
      "researcher": "Ricerca in corso",
      "writer": "Scrittura in corso",
      "summarizer": "Riepilogo in corso"
    }
  }
}
```

## REQ-FE-006: Accessibility

- `AgentIndicator` uses `role="status"` and `aria-live="polite"` so screen readers announce agent transitions without interrupting the user.
- The pulsing animation respects `prefers-reduced-motion` — when enabled, the ping animation is disabled and only the static dot is shown:
  ```css
  @media (prefers-reduced-motion: reduce) {
    .animate-ping { animation: none; }
  }
  ```
- Agent icons are decorative (not informational) — they have `aria-hidden="true"`.
- The translated label provides the semantic meaning.

## REQ-FE-007: Error States

| Scenario                        | Behavior                                          |
|--------------------------------|---------------------------------------------------|
| `agent_status` event malformed  | Ignored (no crash). Logged to console in dev mode. |
| Agent name not in i18n keys     | Falls back to raw agent name (e.g., "researcher"). |
| Status events stop mid-stream   | `activeAgent` cleared on `FINISH_ASSISTANT` or `SET_ERROR`. No stale indicator. |
| SSE connection drops             | Existing error handling applies. Agent indicator cleared via `SET_ERROR`. |
