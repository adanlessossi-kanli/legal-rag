"use client";

import { useState } from "react";
import { useTranslations, useFormatter } from "next-intl";
import type { Document } from "@/lib/api";

interface DocumentTableProps {
  documents: Document[];
  onDelete: (id: string) => void;
}

const STATUS_CONFIG: Record<string, { bg: string; dot: string }> = {
  ready: { bg: "bg-success-light text-success", dot: "bg-success" },
  processing: { bg: "bg-warning-light text-warning", dot: "bg-warning" },
  error: { bg: "bg-danger-light text-danger", dot: "bg-danger" },
};

function EmptyDocuments() {
  const t = useTranslations("documents.empty");
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" className="mb-4 opacity-60">
        <rect x="18" y="10" width="44" height="56" rx="4" fill="var(--surface)" stroke="var(--border)" strokeWidth="1.5" />
        <line x1="28" y1="26" x2="52" y2="26" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <line x1="28" y1="34" x2="48" y2="34" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <line x1="28" y1="42" x2="44" y2="42" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
        <circle cx="60" cy="56" r="14" fill="var(--accent-light)" stroke="var(--accent-muted)" strokeWidth="1.5" />
        <line x1="54" y1="56" x2="66" y2="56" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
        <line x1="60" y1="50" x2="60" y2="62" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <p className="text-sm font-medium text-foreground">{t("title")}</p>
      <p className="text-xs text-muted mt-1">{t("description")}</p>
    </div>
  );
}

export default function DocumentTable({ documents, onDelete }: DocumentTableProps) {
  const t = useTranslations("documents");
  const format = useFormatter();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (documents.length === 0) return <EmptyDocuments />;

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted uppercase tracking-wider">
            <th className="py-3 px-4 font-medium">{t("columns.document")}</th>
            <th className="py-3 px-4 font-medium">{t("columns.date")}</th>
            <th className="py-3 px-4 font-medium">{t("columns.chunks")}</th>
            <th className="py-3 px-4 font-medium">{t("columns.status")}</th>
            <th className="py-3 px-4 font-medium text-right">{t("columns.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const status = STATUS_CONFIG[doc.status] || STATUS_CONFIG.ready;
            return (
              <tr key={doc.id} className="border-b border-border last:border-0 hover:bg-surface-hover transition-colors">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2.5">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span className="font-medium text-foreground truncate max-w-[200px]">{doc.name}</span>
                  </div>
                </td>
                <td className="py-3 px-4 text-muted">{format.dateTime(new Date(doc.uploaded_at), { dateStyle: "medium" })}</td>
                <td className="py-3 px-4 text-muted">{doc.chunk_count}</td>
                <td className="py-3 px-4">
                  <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${status.bg}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
                    {doc.status}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  {confirmId === doc.id ? (
                    <span className="inline-flex items-center gap-2">
                      <button
                        onClick={() => { onDelete(doc.id); setConfirmId(null); }}
                        className="text-xs font-medium text-danger hover:underline"
                      >
                        {t("confirm")}
                      </button>
                      <button
                        onClick={() => setConfirmId(null)}
                        className="text-xs text-muted hover:text-foreground"
                      >
                        {t("cancel")}
                      </button>
                    </span>
                  ) : (
                    <button
                      onClick={() => setConfirmId(doc.id)}
                      className="p-1.5 rounded-lg text-muted hover:text-danger hover:bg-danger-light transition-colors"
                      aria-label={t("deleteLabel", { name: doc.name })}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                      </svg>
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
