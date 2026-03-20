"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslations } from "next-intl";

interface FileDropzoneProps {
  onUpload: (files: File[]) => void;
  accept: string[];
  maxSizeMB: number;
}

function UploadCloudIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" className="mb-3">
      <path d="M14 36c-4.42 0-8-3.58-8-8 0-3.7 2.52-6.82 5.94-7.72A12 12 0 0135.64 22 8 8 0 0136 38h-2" stroke="var(--accent-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M24 24v16" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <polyline points="18,30 24,24 30,30" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function FileDropzone({ onUpload, accept, maxSizeMB }: FileDropzoneProps) {
  const t = useTranslations("upload.dropzone");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = useCallback(
    (files: File[]): File[] => {
      const maxBytes = maxSizeMB * 1024 * 1024;
      const valid: File[] = [];
      for (const f of files) {
        const ext = "." + f.name.split(".").pop()?.toLowerCase();
        if (!accept.includes(ext)) {
          setError(t("unsupportedType", { ext }));
          return [];
        }
        if (f.size > maxBytes) {
          setError(t("tooLarge", { name: f.name, maxSize: maxSizeMB }));
          return [];
        }
        valid.push(f);
      }
      return valid;
    },
    [accept, maxSizeMB, t]
  );

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    setError(null);
    const valid = validate(Array.from(files));
    if (valid.length) onUpload(valid);
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-200 ${
          dragging
            ? "border-accent bg-accent-light scale-[1.01]"
            : "border-border hover:border-accent-muted hover:bg-surface-hover"
        }`}
        role="button"
        aria-label={t("label")}
      >
        <UploadCloudIcon />
        <p className="text-sm font-medium text-foreground">
          {t.rich("text", { browse: (chunks) => <span className="text-accent">{chunks}</span> })}
        </p>
        <p className="mt-1.5 text-xs text-muted">
          {t("hint", { types: accept.join(", "), maxSize: maxSizeMB })}
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept.join(",")}
        multiple
        onChange={(e) => handleFiles(e.target.files)}
        className="hidden"
        aria-hidden="true"
      />
      {error && (
        <div className="mt-3 flex items-center gap-2 text-sm text-danger bg-danger-light border border-danger/20 rounded-lg px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}
