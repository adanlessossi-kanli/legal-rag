"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import DocumentTable from "@/components/DocumentTable";
import { searchDocuments, deleteDocument, connectIngestionWs, type Document, type IngestionEvent } from "@/lib/api";

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const wsCleanup = useRef<(() => void) | null>(null);

  // Search & filter state
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [fileType, setFileType] = useState("");
  const [sortBy, setSortBy] = useState("uploaded_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await searchDocuments({
        page,
        pageSize,
        search: search || undefined,
        status: statusFilter || undefined,
        fileType: fileType || undefined,
        sortBy,
        sortOrder,
      });
      setDocuments(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, fileType, sortBy, sortOrder, t]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

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

  const handleSearchChange = (value: string) => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => {
      setSearch(value);
      setPage(1);
    }, 300);
  };

  const toggleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
    setPage(1);
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

      {/* Search & Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-[200px]">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder={t("searchPlaceholder") || "Search documents..."}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border bg-surface text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border bg-surface text-foreground"
        >
          <option value="">{t("allStatuses") || "All statuses"}</option>
          <option value="ready">{t("statusReady") || "Ready"}</option>
          <option value="processing">{t("statusProcessing") || "Processing"}</option>
          <option value="error">{t("statusError") || "Error"}</option>
        </select>
        <select
          value={fileType}
          onChange={(e) => { setFileType(e.target.value); setPage(1); }}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border bg-surface text-foreground"
        >
          <option value="">{t("allTypes") || "All types"}</option>
          <option value="pdf">PDF</option>
          <option value="docx">DOCX</option>
          <option value="txt">TXT</option>
        </select>
        <div className="flex items-center gap-1">
          {["uploaded_at", "name", "chunk_count"].map((field) => (
            <button
              key={field}
              onClick={() => toggleSort(field)}
              className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                sortBy === field
                  ? "border-accent text-accent bg-accent-light"
                  : "border-border text-muted hover:bg-surface-hover"
              }`}
            >
              {field === "uploaded_at" ? (t("sortDate") || "Date") : field === "name" ? (t("sortName") || "Name") : (t("sortChunks") || "Chunks")}
              {sortBy === field && (sortOrder === "asc" ? " ↑" : " ↓")}
            </button>
          ))}
        </div>
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
