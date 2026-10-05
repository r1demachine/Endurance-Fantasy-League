import { authApi, getToken, isAuthenticated } from "@/lib/auth";

export interface Notif {
  id: number;
  type: string;
  text: string;
  read: boolean;
  created_at: string | null;
}

let items: Notif[] = [];
let unread = 0;

let es: EventSource | null = null;
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
  emit(); // квадратик гаснет сразу
  try { await authApi.post("/api/notifications/read"); } catch {}
  loadNotifications();
}

/** SSE-поток. Перезапускается, если сменился юзер (токен). */
export function startNotificationStream() {
  const token = getToken();
  if (!isAuthenticated() || !token) {
    stopNotificationStream();
    return;
  }
  if (es && streamToken === token) return; // уже течёт для этого юзера

  // сменился юзер — убиваем старый стрим с чужим токеном
  if (es) { es.close(); es = null; }
  streamToken = token;

  const base = authApi.defaults.baseURL || "http://localhost:8000";
  es = new EventSource(`${base}/api/notifications/stream?token=${token}`);
  es.onmessage = () => loadNotifications();

  // страховка: поллинг раз в 15 сек, если SSE отвалится
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadNotifications, 15000);

  loadNotifications();
}

export function stopNotificationStream() {
  if (es) { es.close(); es = null; }
  streamToken = null;
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}