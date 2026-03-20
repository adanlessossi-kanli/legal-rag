"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { getUser, logout } from "@/lib/auth";
import { getConversations, type Conversation } from "@/lib/api";
import LanguageSwitcher from "@/components/LanguageSwitcher";

function LogoIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d="M9 8h8a2 2 0 012 2v1h-2v-1H11v12h6v-1h2v1a2 2 0 01-2 2H9a2 2 0 01-2-2V10a2 2 0 012-2z" fill="white" />
      <path d="M15 13h8a1 1 0 011 1v8a1 1 0 01-1 1h-8a1 1 0 01-1-1v-8a1 1 0 011-1z" fill="white" fillOpacity="0.7" />
      <path d="M16 16h6M16 19h4" stroke="var(--accent)" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function ChatIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? "var(--accent)" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    </svg>
  );
}

function UploadIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? "var(--accent)" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function DocumentIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? "var(--accent)" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="3" y1="5" x2="17" y2="5" />
      <line x1="3" y1="10" x2="17" y2="10" />
      <line x1="3" y1="15" x2="17" y2="15" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="5" y1="5" x2="15" y2="15" />
      <line x1="15" y1="5" x2="5" y2="15" />
    </svg>
  );
}

export default function Sidebar() {
  const t = useTranslations("common");
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const user = getUser();

  const NAV_ITEMS = [
    { href: "/" as const, label: t("nav.newChat"), Icon: ChatIcon },
    { href: "/upload" as const, label: t("nav.upload"), Icon: UploadIcon },
    { href: "/documents" as const, label: t("nav.documents"), Icon: DocumentIcon },
  ];

  useEffect(() => {
    getConversations(1, 15).then((res) => setConversations(res.items)).catch(() => {});
  }, [pathname]);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="fixed top-4 left-4 z-50 md:hidden p-2 rounded-lg bg-surface border border-border shadow-sm transition-colors hover:bg-surface-hover"
        aria-label={open ? t("closeNav") : t("openNav")}
        aria-expanded={open}
      >
        {open ? <CloseIcon /> : <MenuIcon />}
      </button>

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-surface border-r border-border flex flex-col transform transition-transform duration-200 ease-out md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
          <LogoIcon />
          <div>
            <div className="text-sm font-semibold tracking-tight text-foreground">{t("appName")}</div>
            <div className="text-[11px] text-muted">{t("appTagline")}</div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex flex-col gap-0.5 px-3 py-4" aria-label="Main navigation">
          {NAV_ITEMS.map(({ href, label, Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 ${
                  active
                    ? "bg-accent-light text-accent font-medium shadow-sm"
                    : "text-muted hover:bg-surface-hover hover:text-foreground"
                }`}
                aria-current={active ? "page" : undefined}
              >
                <Icon active={active} />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Recent Conversations */}
        <div className="flex-1 overflow-y-auto px-3 pb-2">
          {conversations.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-muted px-3 mb-1">{t("recent")}</div>
              <div className="space-y-0.5">
                {conversations.slice(0, 15).map((c) => (
                  <Link
                    key={c.id}
                    href={`/?c=${c.id}`}
                    onClick={() => setOpen(false)}
                    className="block px-3 py-1.5 rounded-lg text-xs text-muted hover:bg-surface-hover hover:text-foreground truncate transition-colors"
                    title={c.title}
                  >
                    {c.title}
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Language Switcher & User */}
        <div className="mt-auto px-5 py-4 border-t border-border space-y-3">
          <LanguageSwitcher />
          {user && (
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-xs font-medium text-foreground truncate">{user.name}</div>
                <div className="text-[10px] text-muted truncate">{user.email}</div>
              </div>
              <button
                onClick={handleLogout}
                className="p-1.5 rounded-lg text-muted hover:text-danger hover:bg-danger-light transition-colors flex-shrink-0"
                aria-label={t("signOut")}
                title={t("signOut")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm md:hidden transition-opacity"
          onClick={() => setOpen(false)}
          aria-label={t("closeNavOverlay")}
          role="button"
          tabIndex={-1}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        />
      )}
    </>
  );
}
