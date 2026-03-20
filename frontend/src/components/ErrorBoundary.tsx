"use client";

import React, { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslations } from "next-intl";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

function ErrorFallback() {
  const t = useTranslations("errors");
  return (
    <div className="flex items-center justify-center min-h-[60vh] p-6">
      <div className="text-center">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="mx-auto mb-4 opacity-60">
          <circle cx="32" cy="32" r="28" fill="var(--danger-light)" stroke="var(--danger)" strokeWidth="1.5" opacity="0.5" />
          <path d="M32 20v14" stroke="var(--danger)" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="32" cy="42" r="2" fill="var(--danger)" />
        </svg>
        <p className="text-base font-medium text-foreground">{t("somethingWentWrong")}</p>
        <p className="mt-1 text-sm text-muted">{t("refreshHint")}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors"
        >
          {t("refreshPage")}
        </button>
      </div>
    </div>
  );
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return <ErrorFallback />;
    }
    return this.props.children;
  }
}
