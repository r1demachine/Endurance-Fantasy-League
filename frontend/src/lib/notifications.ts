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
let started = false;

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

/** SSE-поток: живые обновления без перезагрузки страницы. */
export function startNotificationStream() {
  if (started || !isAuthenticated()) return;
  started = true;

  const base = authApi.defaults.baseURL || "http://localhost:8000";
  const es = new EventSource(`${base}/api/notifications/stream?token=${getToken()}`);
  es.onmessage = () => loadNotifications();
  loadNotifications();
}