import { getAccessToken, refreshToken, clearAuth } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Source {
  document: string;
  chunk_id: string;
  text: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  conversation_id?: string;
  no_context?: boolean;
}

export interface Document {
  id: string;
  name: string;
  uploaded_at: string;
  chunk_count: number;
  status: "processing" | "ready" | "error";
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface UploadResponse {
  id: string;
  name: string;
  chunk_count: number;
  status: string;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: { role: "user" | "assistant"; content: string; sources?: Source[]; created_at: string }[];
}

export interface OrgSummary {
  id: string;
  name: string;
  member_count: number;
}

export interface OrgMember {
  user_id: string;
  email: string;
  name: string;
  role: "admin" | "member";
}

export interface OrgDetail {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
  members: OrgMember[];
}

export interface IngestionEvent {
  type: "ingestion_status";
  doc_id: string;
  status: "ready" | "error";
  name: string;
  chunk_count: number;
  error: string | null;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

async function request<T>(path: string, options?: RequestInit, retry = true): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  });

  if (res.status === 401 && retry) {
    const refreshed = await refreshToken();
    if (refreshed) return request<T>(path, options, false);
    clearAuth();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Request failed");
  }
  return res.json();
}

export async function chat(
  question: string,
  conversationId?: string | null,
  signal?: AbortSignal,
  documentIds?: string[],
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      conversation_id: conversationId || undefined,
      document_ids: documentIds?.length ? documentIds : undefined,
    }),
    signal,
  });
}

export async function chatStream(
  question: string,
  conversationId: string | null,
  onToken: (token: string) => void,
  onSources: (sources: Source[]) => void,
  onConversationId: (id: string) => void,
  signal?: AbortSignal,
  documentIds?: string[],
  onAgentStatus?: (agent: string, status: string) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat?stream=true`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      question,
      conversation_id: conversationId || undefined,
      document_ids: documentIds?.length ? documentIds : undefined,
    }),
    signal,
  });

  if (res.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) return chatStream(question, conversationId, onToken, onSources, onConversationId, signal, documentIds);
    clearAuth();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "sources") onSources(data.sources);
        else if (data.type === "token") onToken(data.token);
        else if (data.type === "conversation_id") onConversationId(data.conversation_id);
        else if (data.type === "agent_status" && onAgentStatus) onAgentStatus(data.agent, data.status);
      } catch { /* ignore malformed SSE data */ }
    }
  }
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/upload", { method: "POST", body: form });
}

export async function getDocuments(page = 1, pageSize = 20): Promise<PaginatedResponse<Document>> {
  return request<PaginatedResponse<Document>>(`/api/documents?page=${page}&page_size=${pageSize}`);
}

export async function getDocumentStatus(id: string): Promise<Document> {
  return request<Document>(`/api/documents/${id}/status`);
}

export async function deleteDocument(id: string): Promise<void> {
  await request(`/api/documents/${id}`, { method: "DELETE" });
}

export async function getConversations(page = 1, pageSize = 20): Promise<PaginatedResponse<Conversation>> {
  return request<PaginatedResponse<Conversation>>(`/api/conversations?page=${page}&page_size=${pageSize}`);
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${id}`);
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`/api/conversations/${id}`, { method: "DELETE" });
}

// --- Organizations ---

export async function createOrg(name: string): Promise<OrgDetail> {
  return request<OrgDetail>("/api/organizations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function getOrgs(): Promise<OrgSummary[]> {
  return request<OrgSummary[]>("/api/organizations");
}

export async function getOrg(id: string): Promise<OrgDetail> {
  return request<OrgDetail>(`/api/organizations/${id}`);
}

export async function inviteMember(orgId: string, email: string, role: "admin" | "member" = "member"): Promise<OrgMember> {
  return request<OrgMember>(`/api/organizations/${orgId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  await request(`/api/organizations/${orgId}/members/${userId}`, { method: "DELETE" });
}

// --- WebSocket ingestion notifications ---

export function connectIngestionWs(onEvent: (event: IngestionEvent) => void): (() => void) | null {
  const token = getAccessToken();
  if (!token) return null;

  const wsBase = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/api/ws/ingestion?token=${token}`);

  ws.onmessage = (e) => {
    try {
      const event: IngestionEvent = JSON.parse(e.data);
      onEvent(event);
    } catch { /* ignore parse errors */ }
  };

  ws.onerror = () => ws.close();

  return () => ws.close();
}
