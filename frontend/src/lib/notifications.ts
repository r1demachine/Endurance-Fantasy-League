"use client";

import { authApi, getToken, isAuthenticated } from "@/lib/auth";

export interface Notif {
  id: number;
  type: string;
  text: string;
  link: string | null;
  read: boolean;
  created_at: string | null;
}

let items: Notif[] = [];
let unread = 0;
let streamController: AbortController | null = null;
let streamToken: string | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function subscribeNotifications(cb: () => void) {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}
export function getNotifItems() { return items; }
export function getUnread() { return unread; }

export async function loadNotifications() {
  if (!isAuthenticated()) return;
  try {
    const r = await authApi.get("/api/notifications");
    items = r.data.items;
    unread = r.data.unread;
    emit();
  } catch {}
}

export async function markAllRead() {
  unread = 0;
  emit();
  try { await authApi.post("/api/notifications/read"); } catch {}
  loadNotifications();
}

function waitForRetry(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
  });
}

async function consumeNotificationStream(base: string, token: string, signal: AbortSignal) {
  let retryMs = 1000;

  while (!signal.aborted && getToken() === token) {
    try {
      const response = await fetch(`${base}/api/notifications/stream`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
        },
        cache: "no-store",
        signal,
      });

      if (response.status === 401 || response.status === 403) {
        stopNotificationStream();
        await loadNotifications();
        return;
      }
      if (!response.ok || !response.body) {
        throw new Error(`Notification stream failed: HTTP ${response.status}`);
      }

      retryMs = 1000;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!signal.aborted && getToken() === token) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        while (true) {
          const match = buffer.match(/\r?\n\r?\n/);
          if (!match || match.index === undefined) break;

          const block = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          const data = block
            .split(/\r?\n/)
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("\n");

          if (data) {
            try {
              const payload = JSON.parse(data);
              if (payload?.error === "unauthorized") {
                stopNotificationStream();
                return;
              }
            } catch {
              // Ignore malformed SSE payloads; the next event can still be valid.
            }
            await loadNotifications();
          }
        }
      }

      if (signal.aborted || getToken() !== token) return;
      throw new Error("Notification stream closed");
    } catch {
      if (signal.aborted || getToken() !== token) return;
    }

    await waitForRetry(retryMs, signal);
    retryMs = Math.min(retryMs * 2, 15000);
  }
}

/** Authenticated SSE; the JWT is sent in a header and never placed in the URL. */
export function startNotificationStream() {
  const token = getToken();
  if (!isAuthenticated() || !token) {
    stopNotificationStream();
    return;
  }
  if (streamController && streamToken === token) return;

  stopNotificationStream();
  streamToken = token;
  const controller = new AbortController();
  streamController = controller;

  const base = (authApi.defaults.baseURL || "http://localhost:8000").replace(/\/+$/, "");
  void consumeNotificationStream(base, token, controller.signal).finally(() => {
    if (streamController === controller) {
      streamController = null;
      streamToken = null;
    }
  });

  // Polling is a fallback if the streaming connection is unavailable.
  pollTimer = setInterval(loadNotifications, 15000);
  loadNotifications();
}

export function stopNotificationStream() {
  if (streamController) {
    streamController.abort();
    streamController = null;
  }
  streamToken = null;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
