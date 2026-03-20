"use client";

import { useTranslations } from "next-intl";

interface AgentIndicatorProps {
  agent: string;
}

function AgentIcon({ agent }: { agent: string }) {
  const icons: Record<string, JSX.Element> = {
    researcher: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
    writer: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
      </svg>
    ),
    summarizer: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
  };
  return icons[agent] || null;
}

export default function AgentIndicator({ agent }: AgentIndicatorProps) {
  const t = useTranslations("chat");

  let label: string;
  try {
    label = t(`agents.${agent}`);
  } catch {
    label = agent;
  }

  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface-hover border border-border text-xs text-muted ml-11 motion-reduce:animate-none"
      role="status"
      aria-live="polite"
    >
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75 motion-reduce:hidden" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
      </span>
      <AgentIcon agent={agent} />
      {label}...
    </div>
  );
}
