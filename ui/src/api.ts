// API client. The JWT is stored in localStorage and attached to every request.

import type { ChatCard, PlaceDetail } from "./types";

export type SSEHandler = (event: string, data: string) => void;

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem("va-token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function streamPost(url: string, body: unknown, onEvent: SSEHandler): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    onEvent("error", (await resp.text().catch(() => "")) || `HTTP ${resp.status}`);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r\n\r\n|\n\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split(/\r\n|\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent(event, data);
    }
  }
}

export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

// --- auth ---
export async function authRequest(mode: "login" | "register", email: string, password: string, home_city?: string) {
  const resp = await fetch(`/api/auth/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, home_city }),
  });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(json.detail || "Authentication failed");
  return json as { token: string; email: string };
}

export async function getProfile(): Promise<{ email?: string; home_city?: string }> {
  const resp = await fetch("/api/auth/me", { headers: authHeaders() });
  return resp.ok ? resp.json() : {};
}

export async function setHomeCity(home_city: string): Promise<void> {
  await fetch("/api/auth/me", { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ home_city }) });
}

// --- plans ---
export async function listPlans(): Promise<any[]> {
  const resp = await fetch("/api/plans", { headers: authHeaders() });
  return resp.ok ? resp.json() : [];
}

export async function loadPlan(id: string): Promise<any> {
  const resp = await fetch(`/api/plans/${id}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// --- chat threads ---
export async function createThread(plan_id: string): Promise<{ id: string }> {
  return postJSON("/api/chat/threads", { plan_id });
}
export async function listThreads(plan_id: string): Promise<any[]> {
  const resp = await fetch(`/api/chat/threads?plan_id=${encodeURIComponent(plan_id)}`, { headers: authHeaders() });
  return resp.ok ? resp.json() : [];
}
export async function getThread(id: string): Promise<{ id: string; title: string | null; messages: { role: string; text: string; cards?: ChatCard[] }[] }> {
  const resp = await fetch(`/api/chat/threads/${id}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
export async function postMessage(threadId: string, question: string): Promise<{ answer: string; plan?: any; title?: string | null; cards?: ChatCard[] | null }> {
  return postJSON(`/api/chat/threads/${threadId}/message`, { question });
}
export async function placeDetail(thread_id: string, name: string, city?: string | null): Promise<PlaceDetail> {
  return postJSON("/api/plan/place_detail", { thread_id, name, city });
}
export async function deleteThread(id: string): Promise<void> {
  await fetch(`/api/chat/threads/${id}`, { method: "DELETE", headers: authHeaders() });
}

export async function getPreferences(): Promise<string[]> {
  const resp = await fetch("/api/preferences", { headers: authHeaders() });
  if (!resp.ok) return [];
  return (await resp.json()).items ?? [];
}

export async function forgetPreferences(): Promise<void> {
  await fetch("/api/preferences", { method: "DELETE", headers: authHeaders() });
}
