"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import FileDropzone from "@/components/FileDropzone";
import { uploadDocument, type UploadResponse } from "@/lib/api";

export default function UploadPage() {
  const t = useTranslations("upload");
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResponse[]>([]);
  const [errors, setErrors] = useState<string[]>([]);

  const handleUpload = async (files: File[]) => {
    setUploading(true);
    setErrors([]);
    const settled = await Promise.allSettled(files.map(uploadDocument));
    for (const result of settled) {
      if (result.status === "fulfilled") {
        setResults((prev) => [...prev, result.value]);
      } else {
        setErrors((prev) => [...prev, result.reason?.message || t("failed")]);
      }
    }
    setUploading(false);
  };

  return (
    <div className="max-w-2xl">
      <div className="mb-6 pb-3 border-b border-border">
        <h1 className="text-lg font-semibold text-foreground">{t("title")}</h1>
        <p className="text-xs text-muted mt-0.5">{t("subtitle")}</p>
      </div>

      <FileDropzone onUpload={handleUpload} accept={[".pdf", ".txt", ".docx"]} maxSizeMB={50} />

      {uploading && (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted">
          <svg className="animate-spin h-4 w-4 text-accent" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
            <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
          {t("processing")}
        </div>
      )}

      {errors.map((e, i) => (
        <div key={i} className="mt-3 flex items-center gap-2 text-sm text-danger bg-danger-light border border-danger/20 rounded-lg px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          {e}
        </div>
      ))}

      {results.length > 0 && (
        <div className="mt-5 space-y-2">
          {results.map((r) => (
            <div key={r.id} className="flex items-center gap-3 rounded-xl border border-success/30 bg-success-light p-3 text-sm">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <div>
                <span className="font-medium text-foreground">{r.name}</span>
                <span className="text-muted ml-2">— {r.status === "processing" ? t("status.processing") : t("status.chunks", { count: r.chunk_count })}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
