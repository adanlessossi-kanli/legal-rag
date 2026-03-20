"use client";

import { useReducer, useRef, useEffect, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import AgentIndicator from "@/components/AgentIndicator";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import LoadingIndicator from "@/components/LoadingIndicator";
import { chatStream, getConversation, getDocuments, type Message, type Source, type Document } from "@/lib/api";

interface ChatState {
  messages: Message[];
  conversationId: string | null;
  isLoading: boolean;
  error: string | null;
  activeAgent: string | null;
}

type Action =
  | { type: "LOAD"; messages: Message[]; conversationId: string }
  | { type: "ADD_USER_MESSAGE"; id: string; content: string }
  | { type: "START_ASSISTANT"; id: string }
  | { type: "APPEND_TOKEN"; id: string; token: string }
  | { type: "SET_SOURCES"; id: string; sources: Source[] }
  | { type: "SET_CONVERSATION_ID"; conversationId: string }
  | { type: "FINISH_ASSISTANT" }
  | { type: "SET_ERROR"; error: string }
  | { type: "SET_AGENT"; agent: string | null }
  | { type: "CLEAR" };

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "LOAD":
      return { ...state, messages: action.messages, conversationId: action.conversationId, error: null, activeAgent: null };
    case "ADD_USER_MESSAGE":
      return { ...state, messages: [...state.messages, { id: action.id, role: "user", content: action.content }], error: null };
    case "START_ASSISTANT":
      return { ...state, messages: [...state.messages, { id: action.id, role: "assistant", content: "" }], isLoading: true };
    case "APPEND_TOKEN":
      return { ...state, messages: state.messages.map((m) => m.id === action.id ? { ...m, content: m.content + action.token } : m) };
    case "SET_SOURCES":
      return { ...state, messages: state.messages.map((m) => m.id === action.id ? { ...m, sources: action.sources } : m) };
    case "SET_CONVERSATION_ID":
      return { ...state, conversationId: action.conversationId };
    case "FINISH_ASSISTANT":
      return { ...state, isLoading: false, activeAgent: null };
    case "SET_ERROR":
      return { ...state, error: action.error, isLoading: false, activeAgent: null };
    case "SET_AGENT":
      return { ...state, activeAgent: action.agent };
    case "CLEAR":
      return { messages: [], conversationId: null, isLoading: false, error: null, activeAgent: null };
  }
}

function DocumentScopeSelector({ documents, selected, onChange }: {
  documents: Document[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const t = useTranslations("chat");
  const [open, setOpen] = useState(false);
  const ready = documents.filter((d) => d.status === "ready");

  if (ready.length === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-accent transition-colors px-2.5 py-1.5 rounded-lg hover:bg-accent-light border border-border"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        {selected.length === 0 ? t("allDocuments") : t("scopedDocuments", { count: selected.length })}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-surface border border-border rounded-xl shadow-md z-10 py-1 max-h-48 overflow-y-auto">
          <button
            onClick={() => { onChange([]); setOpen(false); }}
            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-surface-hover transition-colors ${selected.length === 0 ? "text-accent font-medium" : "text-muted"}`}
          >
            {t("allDocuments")}
          </button>
          {ready.map((doc) => {
            const isSelected = selected.includes(doc.id);
            return (
              <button
                key={doc.id}
                onClick={() => {
                  onChange(isSelected ? selected.filter((id) => id !== doc.id) : [...selected, doc.id]);
                }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-surface-hover transition-colors truncate ${isSelected ? "text-accent font-medium" : "text-muted"}`}
              >
                {isSelected ? "✓ " : ""}{doc.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  const t = useTranslations("chat");
  const exampleQueries = [
    t("exampleQueries.termination"),
    t("exampleQueries.liability"),
    t("exampleQueries.payment"),
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
      <svg width="120" height="120" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className="mb-6 opacity-80">
        <rect x="25" y="20" width="50" height="65" rx="4" fill="var(--accent-light)" stroke="var(--accent-muted)" strokeWidth="1.5" />
        <rect x="30" y="15" width="50" height="65" rx="4" fill="var(--surface)" stroke="var(--border)" strokeWidth="1.5" />
        <line x1="38" y1="32" x2="72" y2="32" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <line x1="38" y1="40" x2="68" y2="40" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <line x1="38" y1="48" x2="65" y2="48" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <line x1="38" y1="56" x2="60" y2="56" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <rect x="60" y="55" width="40" height="30" rx="8" fill="var(--accent)" />
        <path d="M70 85l-5 10 10-5z" fill="var(--accent)" />
        <circle cx="72" cy="70" r="2.5" fill="white" />
        <circle cx="80" cy="70" r="2.5" fill="white" />
        <circle cx="88" cy="70" r="2.5" fill="white" />
        <path d="M95 25l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" fill="var(--accent-muted)" />
        <path d="M15 50l1.5 4 4 1.5-4 1.5-1.5 4-1.5-4-4-1.5 4-1.5z" fill="var(--accent-muted)" opacity="0.6" />
      </svg>
      <h2 className="text-lg font-semibold text-foreground mb-2">{t("emptyState.title")}</h2>
      <p className="text-sm text-muted max-w-md leading-relaxed">{t("emptyState.description")}</p>
      <div className="flex flex-wrap justify-center gap-2 mt-5">
        {exampleQueries.map((q) => (
          <span key={q} className="text-xs px-3 py-1.5 rounded-full bg-surface border border-border text-muted">
            {q}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const t = useTranslations("chat");
  const searchParams = useSearchParams();
  const router = useRouter();
  const conversationParam = searchParams.get("c");

  const [state, dispatch] = useReducer(reducer, { messages: [], conversationId: null, isLoading: false, error: null, activeAgent: null });
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getDocuments(1, 100).then((res) => setDocuments(res.items)).catch(() => {});
  }, []);

  useEffect(() => {
    if (conversationParam) {
      getConversation(conversationParam)
        .then((convo) => {
          const msgs: Message[] = convo.messages.map((m, i) => ({
            id: `loaded-${i}`,
            role: m.role,
            content: m.content,
            sources: m.sources,
          }));
          dispatch({ type: "LOAD", messages: msgs, conversationId: convo.id });
        })
        .catch(() => {
          dispatch({ type: "SET_ERROR", error: t("failedToLoad") });
        });
    } else {
      dispatch({ type: "CLEAR" });
    }
  }, [conversationParam, t]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.messages]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const handleSend = useCallback(async (question: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    dispatch({ type: "ADD_USER_MESSAGE", id: userMsgId, content: question });
    dispatch({ type: "START_ASSISTANT", id: assistantMsgId });

    try {
      await chatStream(
        question,
        state.conversationId,
        (token) => dispatch({ type: "APPEND_TOKEN", id: assistantMsgId, token }),
        (sources) => dispatch({ type: "SET_SOURCES", id: assistantMsgId, sources }),
        (id) => {
          dispatch({ type: "SET_CONVERSATION_ID", conversationId: id });
          if (!state.conversationId) router.replace(`/?c=${id}`, { scroll: false });
        },
        controller.signal,
        selectedDocIds,
        (agent, status) => dispatch({
          type: "SET_AGENT",
          agent: status === "done" ? null : agent,
        }),
      );
      dispatch({ type: "FINISH_ASSISTANT" });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : t("somethingWentWrong") });
    }
  }, [state.conversationId, router, t, selectedDocIds]);

  const handleClear = useCallback(() => {
    dispatch({ type: "CLEAR" });
    setSelectedDocIds([]);
    router.push("/");
  }, [router]);

  const hasMessages = state.messages.length > 0;

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t("title")}</h1>
          <p className="text-xs text-muted">{t("subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <DocumentScopeSelector documents={documents} selected={selectedDocIds} onChange={setSelectedDocIds} />
          {hasMessages && (
            <button
              onClick={handleClear}
              className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-accent transition-colors px-2.5 py-1.5 rounded-lg hover:bg-accent-light"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              {t("newChat")}
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {hasMessages ? (
          <div className="space-y-4 pb-4">
            {state.messages.map((msg) => (
              <ChatMessage key={msg.id} role={msg.role} content={msg.content} sources={msg.sources} />
            ))}
            {state.isLoading && state.activeAgent && <AgentIndicator agent={state.activeAgent} />}
            {state.isLoading && state.messages[state.messages.length - 1]?.content === "" && <LoadingIndicator />}
            {state.error && (
              <div className="flex items-center gap-2 text-sm text-danger bg-danger-light border border-danger/20 rounded-lg px-3 py-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                {state.error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        ) : (
          <EmptyState />
        )}
      </div>

      <div className="pt-3">
        <ChatInput onSend={handleSend} disabled={state.isLoading} />
        <p className="text-[10px] text-muted text-center mt-2">{t("disclaimer")}</p>
      </div>
    </div>
  );
}
