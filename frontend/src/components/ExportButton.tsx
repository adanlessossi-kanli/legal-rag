"use client";

import { useState } from "react";
import { exportConversation } from "@/lib/api";

interface ExportButtonProps {
  conversationId: string | null;
}

export default function ExportButton({ conversationId }: ExportButtonProps) {
  const [exporting, setExporting] = useState(false);

  if (!conversationId) return null;

  const handleExport = async (format: "markdown" | "json") => {
    setExporting(true);
    try {
      const blob = await exportConversation(conversationId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `conversation.${format === "markdown" ? "md" : "json"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silently fail
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="relative group">
      <button
        disabled={exporting}
        className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-accent transition-colors px-2.5 py-1.5 rounded-lg hover:bg-accent-light"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        {exporting ? "..." : "Export"}
      </button>
      <div className="absolute right-0 top-full mt-1 hidden group-hover:block bg-surface border border-border rounded-lg shadow-md z-10 py-1 min-w-[100px]">
        <button
          onClick={() => handleExport("markdown")}
          className="w-full text-left px-3 py-1.5 text-xs text-muted hover:bg-surface-hover transition-colors"
        >
          Markdown
        </button>
        <button
          onClick={() => handleExport("json")}
          className="w-full text-left px-3 py-1.5 text-xs text-muted hover:bg-surface-hover transition-colors"
        >
          JSON
        </button>
      </div>
    </div>
  );
}
