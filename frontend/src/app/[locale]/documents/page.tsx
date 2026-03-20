"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import DocumentTable from "@/components/DocumentTable";
import { getDocuments, deleteDocument, connectIngestionWs, type Document, type IngestionEvent } from "@/lib/api";

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const wsCleanup = useRef<(() => void) | null>(null);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await getDocuments(page, pageSize);
      setDocuments(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    } finally {
      setLoading(false);
    }
  }, [page, t]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  // WebSocket for real-time ingestion status updates
  useEffect(() => {
    const cleanup = connectIngestionWs((event: IngestionEvent) => {
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === event.doc_id
            ? { ...d, status: event.status as Document["status"], chunk_count: event.chunk_count }
            : d
        )
      );
    });
    wsCleanup.current = cleanup;
    return () => { wsCleanup.current?.(); };
  }, []);

  const handleDelete = async (id: string) => {
    const prev = documents;
    setDocuments((docs) => docs.filter((d) => d.id !== id));
    setError(null);
    try {
      await deleteDocument(id);
      setTotal((t) => t - 1);
    } catch (err) {
      setDocuments(prev);
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      <div className="mb-6 pb-3 border-b border-border">
        <h1 className="text-lg font-semibold text-foreground">{t("title")}</h1>
        <p className="text-xs text-muted mt-0.5">
          {loading ? t("loading") : t("documentCount", { count: total })}
        </p>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-danger bg-danger-light border border-danger/20 rounded-lg px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <svg className="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
            <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
        </div>
      ) : (
        <>
          <DocumentTable documents={documents} onDelete={handleDelete} />
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-xs rounded-lg border border-border text-muted hover:bg-surface-hover disabled:opacity-30"
              >
                ←
              </button>
              <span className="text-xs text-muted">{page} / {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 text-xs rounded-lg border border-border text-muted hover:bg-surface-hover disabled:opacity-30"
              >
                →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
