"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import FeedbackButton from "@/components/FeedbackButton";
import type { Source } from "@/lib/api";

const SourceViewer = dynamic(() => import("@/components/SourceViewer"), { ssr: false });

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

function RelevanceBadge({ relevance }: { relevance?: number }) {
  if (relevance == null) return null;
  const pct = Math.round(relevance * 100);
  const color = relevance >= 0.9 ? "text-success" : relevance >= 0.8 ? "text-warning" : "text-muted";
  return <span className={`text-[10px] font-medium ${color}`}>{pct}%</span>;
}

function isPptx(name: string) {
  return name.toLowerCase().endsWith(".pptx");
}

function sourcePageLabel(source: Source) {
  if (isPptx(source.document)) return `Slide ${source.page ?? "?"}`;
  return `Page ${source.page ?? "?"}`;
}

export default function ChatMessage({ role, content, sources, messageId, conversationId }: ChatMessageProps) {
  const t = useTranslations("chat");
  const [showSources, setShowSources] = useState(false);
  const [viewerSource, setViewerSource] = useState<Source | null>(null);
  const isUser = role === "user";

  const grouped = useMemo(() => {
    if (!sources?.length) return [];
    const map = new Map<string, Source[]>();
    const order: string[] = [];
    for (const s of sources) {
      const key = s.doc_id || s.document;
      if (!map.has(key)) { map.set(key, []); order.push(key); }
      map.get(key)!.push(s);
    }
    return order.map((key) => ({ docName: map.get(key)![0].document, sources: map.get(key)! }));
  }, [sources]);

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

        {grouped.length > 0 && (
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
              {showSources ? t("hideSources") : t("sourceCount", { count: sources!.length })}
              <svg
                width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                className={`transition-transform duration-200 ${showSources ? "rotate-180" : ""}`}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {grouped.map((group) => (
                  <div key={group.docName} className="rounded-lg border border-border bg-surface-hover p-2">
                    <div className="flex items-center gap-1.5 text-xs font-medium text-foreground mb-1.5">
                      <SourceIcon />
                      <span className="truncate">{group.docName}</span>
                      <span className="text-muted">({group.sources.length})</span>
                    </div>
                    <div className="space-y-1">
                      {group.sources.map((s) => (
                        <button
                          key={s.chunk_id}
                          onClick={() => setViewerSource(s)}
                          className="w-full text-left flex items-start gap-2 text-xs p-2 rounded-md hover:bg-accent-light transition-colors cursor-pointer group"
                          title={t("viewSource")}
                        >
                          <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5">
                            <span className="text-accent font-medium">{sourcePageLabel(s)}</span>
                            <RelevanceBadge relevance={s.relevance} />
                          </div>
                          <p className="text-muted min-w-0 break-words flex-1">{s.text}</p>
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted">
                            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                        </button>
                      ))}
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

      {viewerSource && (
        <SourceViewer source={viewerSource} open={true} onClose={() => setViewerSource(null)} />
      )}
    </div>
  );
}
