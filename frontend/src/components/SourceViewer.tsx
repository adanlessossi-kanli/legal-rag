"use client";

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { getDocumentFileUrl, type Source } from "@/lib/api";

interface SourceViewerProps {
  source: Source;
  open: boolean;
  onClose: () => void;
}

function isPdf(name: string) {
  return name.toLowerCase().endsWith(".pdf");
}

function isPptx(name: string) {
  return name.toLowerCase().endsWith(".pptx");
}

function pageLabel(source: Source, t: ReturnType<typeof useTranslations>) {
  if (isPptx(source.document)) return t("slide", { page: source.page ?? 1 });
  if (source.page && source.page_end && source.page_end > source.page)
    return t("pageRange", { start: source.page, end: source.page_end });
  return t("page", { page: source.page ?? 1 });
}

export default function SourceViewer({ source, open, onClose }: SourceViewerProps) {
  const t = useTranslations("chat");
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchUrl = useCallback(async () => {
    if (!source.doc_id) return;
    setLoading(true);
    setError(null);
    try {
      const url = await getDocumentFileUrl(source.doc_id);
      setFileUrl(url);
    } catch (e) {
      setError(e instanceof Error && e.message.includes("no longer available")
        ? t("fileUnavailable")
        : t("fileUnavailable"));
    } finally {
      setLoading(false);
    }
  }, [source.doc_id, t]);

  useEffect(() => {
    if (open && isPdf(source.document) && source.doc_id) {
      fetchUrl();
    }
    return () => { setFileUrl(null); setError(null); };
  }, [open, source.document, source.doc_id, fetchUrl]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    window.location.hash = `source=${source.doc_id}&page=${source.page ?? 1}`;
    return () => { if (window.location.hash.includes("source=")) window.location.hash = ""; };
  }, [open, source.doc_id, source.page]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t("sourceViewerTitle", { document: source.document })}
    >
      <div
        className="bg-surface border border-border rounded-2xl shadow-md w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden md:mx-4 mx-0 md:rounded-2xl rounded-none md:max-h-[90vh] max-h-full md:w-auto w-full md:h-auto h-full"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground truncate">
              {t("sourceViewerTitle", { document: source.document })}
            </h2>
            <p className="text-xs text-muted">{pageLabel(source, t)}</p>
          </div>
          <button
            onClick={onClose}
            className="text-muted hover:text-foreground transition-colors p-1"
            aria-label={t("closeViewer")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center py-16">
              <svg className="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
              <span className="ml-2 text-sm text-muted">{t("loadingViewer")}</span>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" className="mb-3">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <p className="text-sm text-muted">{error}</p>
            </div>
          )}

          {!loading && !error && isPdf(source.document) && fileUrl && (
            <iframe
              src={`${fileUrl}#page=${source.page ?? 1}`}
              className="w-full h-[70vh] rounded-lg border border-border"
              title={source.document}
            />
          )}

          {!loading && !error && !isPdf(source.document) && (
            <div className="space-y-3">
              <div className="inline-flex items-center gap-1.5 text-xs text-muted bg-surface-hover rounded-md px-2 py-1">
                {pageLabel(source, t)}
              </div>
              <pre className="text-sm text-foreground bg-surface-hover border border-border rounded-lg p-4 whitespace-pre-wrap break-words leading-relaxed">
                {source.text}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
