const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "legal-rag-access-token";
const REFRESH_KEY = "legal-rag-refresh-token";
const USER_KEY = "legal-rag-user";

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user?: User;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveAuth(data: AuthResponse) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(REFRESH_KEY, data.refresh_token);
  if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

async function authRequest(path: string, body: object): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(data.detail || "Request failed");
  }
  const data: AuthResponse = await res.json();
  saveAuth(data);
  return data;
}

export async function login(email: string, password: string): Promise<User> {
  const data = await authRequest("/api/auth/login", { email, password });
  return data.user!;
}

export async function register(email: string, password: string, name: string): Promise<User> {
  const data = await authRequest("/api/auth/register", { email, password, name });
  return data.user!;
}

export async function refreshToken(): Promise<boolean> {
  const token = localStorage.getItem(REFRESH_KEY);
  if (!token) return false;
  try {
    await authRequest("/api/auth/refresh", { refresh_token: token });
    return true;
  } catch {
    clearAuth();
    return false;
  }
}

export async function logout(): Promise<void> {
  const token = getAccessToken();
  if (token) {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  clearAuth();
}
