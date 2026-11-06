// Thin API client for the FastAPI backend.
// Empty = same origin; Next.js rewrites /api/* to the FastAPI server (see next.config.ts).
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export type Source = {
  index: number;
  id: string;
  source: string;
  page: number | null;
  section: string;
  text: string;
  score: number;
  scores: Record<string, number>;
};

export type ChatDone = {
  type: "done";
  answer: string;
  cited: number[];
  refused: boolean;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  timings_ms: Record<string, number>;
  message_id?: number;
};

export type ChatEvent =
  | { type: "sources"; sources: Source[]; rewritten_query: string; conversation_id: number }
  | { type: "token"; text: string }
  | ChatDone
  | { type: "error"; message: string };

export type User = { id: number; email: string; name: string; role: "user" | "admin" };

export type PublicConfig = {
  product_name: string;
  tagline: string;
  language: "ar" | "en";
  sample_questions: string[];
  disclaimer: string;
  metadata_filters: string[];
  allow_anonymous_chat: boolean;
};

const TOKEN_KEY = "rag_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* not json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

/** POST /api/chat and parse the Server-Sent Events stream. */
export async function streamChat(
  body: { question: string; conversation_id?: number | null; filters?: Record<string, string> | null },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal
) {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
    }
  }
}
