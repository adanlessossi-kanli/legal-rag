"use client";

import { useState, useRef, useEffect } from "react";
import { useTranslations } from "next-intl";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const t = useTranslations("chat");
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="relative bg-surface border border-border rounded-2xl shadow-md transition-shadow focus-within:shadow-lg focus-within:border-accent/50">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
          }
        }}
        disabled={disabled}
        placeholder={t("inputPlaceholder")}
        rows={1}
        className="w-full resize-none bg-transparent pl-4 pr-14 py-3.5 text-sm text-foreground placeholder:text-muted focus:outline-none disabled:opacity-50"
        aria-label={t("inputLabel")}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        className="absolute right-2.5 bottom-2.5 p-2 rounded-xl bg-accent text-white hover:bg-accent-hover disabled:opacity-30 disabled:hover:bg-accent transition-all duration-150"
        aria-label={t("sendLabel")}
      >
        <SendIcon />
      </button>
    </div>
  );
}
