"use client";

import { useState } from "react";
import { useRouter, Link } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import { register } from "@/lib/auth";
import LanguageSwitcher from "@/components/LanguageSwitcher";

export default function RegisterPage() {
  const t = useTranslations("auth.register");
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, password, name);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="fixed top-4 right-4 w-32">
        <LanguageSwitcher />
      </div>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-accent mb-3">
            <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
              <path d="M9 8h8a2 2 0 012 2v1h-2v-1H11v12h6v-1h2v1a2 2 0 01-2 2H9a2 2 0 01-2-2V10a2 2 0 012-2z" fill="white" />
              <path d="M15 13h8a1 1 0 011 1v8a1 1 0 01-1 1h-8a1 1 0 01-1-1v-8a1 1 0 011-1z" fill="white" fillOpacity="0.7" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted mt-1">{t("subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="text-sm text-danger bg-danger-light border border-danger/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="name" className="block text-sm font-medium text-foreground mb-1">{t("nameLabel")}</label>
            <input
              id="name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              placeholder={t("namePlaceholder")}
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-foreground mb-1">{t("emailLabel")}</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              placeholder={t("emailPlaceholder")}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1">{t("passwordLabel")}</label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              placeholder={t("passwordPlaceholder")}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent text-white py-2.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-colors"
          >
            {loading ? t("submitting") : t("submit")}
          </button>
        </form>

        <p className="text-center text-sm text-muted mt-6">
          {t("hasAccount")}{" "}
          <Link href="/login" className="text-accent hover:underline">{t("signInLink")}</Link>
        </p>
      </div>
    </div>
  );
}
