"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import FeedbackButton from "@/components/FeedbackButton";
import type { Source } from "@/lib/api";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  messageId?: string;
  conversationId?: string | null;
}

function UserAvatar() {
  return (
    <div className="flex-shrink-0 h-8 w-8 rounded-full bg-accent flex items-center justify-center">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div className="flex-shrink-0 h-8 w-8 rounded-full bg-surface border-2 border-accent-muted flex items-center justify-center">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    </div>
  );
}

function SourceIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0 mt-0.5">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

export default function ChatMessage({ role, content, sources, messageId, conversationId }: ChatMessageProps) {
  const t = useTranslations("chat");
  const [showSources, setShowSources] = useState(false);
  const isUser = role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {isUser ? <UserAvatar /> : <AssistantAvatar />}
      <div className={`max-w-[75%] min-w-0`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-accent text-white rounded-tr-md"
              : "bg-surface border border-border shadow-sm rounded-tl-md"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 prose-p:leading-relaxed">
              <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
            </div>
          )}
        </div>

        {sources && sources.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setShowSources(!showSources)}
              className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
              aria-expanded={showSources}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
                <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
              </svg>
              {showSources ? t("hideSources") : t("sourceCount", { count: sources.length })}
              <svg
                width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                className={`transition-transform duration-200 ${showSources ? "rotate-180" : ""}`}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {showSources && (
              <div className="mt-2 space-y-1.5">
                {sources.map((s) => (
                  <div
                    key={s.chunk_id}
                    className="flex gap-2 text-xs p-2.5 rounded-lg bg-surface-hover border border-border"
                  >
                    <SourceIcon />
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">{s.document}</span>
                      <p className="text-muted mt-0.5 break-words">{s.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {!isUser && messageId && (
          <FeedbackButton conversationId={conversationId || null} messageId={messageId} />
        )}
      </div>
    </div>
  );
}
