"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { isAuthenticated } from "@/lib/auth";
import {
  getNotifItems,
  getUnread,
  markAllRead,
  startNotificationStream,
  subscribeNotifications,
  type Notif,
} from "@/lib/notifications";

function timeAgo(iso: string | null) {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

function iconFor(type: string) {
  if (type === "friend_request") return "👥";
  if (type === "friend_accepted") return "✅";
  return "🌙";
}

export default function NotificationBell({ variant }: { variant: "top" | "bottom" }) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [, force] = useState(0);

  useEffect(() => {
    setMounted(true);
  }, []);
  useEffect(() => subscribeNotifications(() => force((x) => x + 1)), []);
  useEffect(() => {
    if (mounted) startNotificationStream();
  }, [mounted]);

  if (!mounted || !isAuthenticated()) return null;

  const unread = getUnread();
  const items = getNotifItems();
  const hasUnread = unread > 0;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) markAllRead();
  };

  const wrap = variant === "top" ? "relative flex items-stretch" : "relative w-14 shrink-0 flex items-stretch";
  const btn =
    variant === "top"
      ? `relative px-4 md:px-5 border-l-2 border-black transition-colors flex items-center justify-center text-lg ${
          hasUnread ? "bg-[#ff4b26] text-white hover:bg-black" : "hover:bg-black hover:text-white"
        }`
      : `relative w-full flex items-center justify-center text-xl transition-colors ${
          hasUnread ? "bg-[#ff4b26] text-white active:bg-black" : "active:bg-black active:text-white"
        }`;
  const panelPos =
    variant === "top"
      ? "absolute right-0 top-[calc(100%+10px)] w-80 max-w-[calc(100vw-24px)]"
      : "absolute right-2 bottom-[calc(100%+10px)] w-[calc(100vw-16px)] max-w-sm";

  return (
    <div className={wrap}>
      <button type="button" onClick={toggle} className={btn} aria-label="Notifications">
        {hasUnread ? (
          <motion.span
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ repeat: Infinity, duration: 1.5, ease: "easeInOut" }}
            className="text-lg"
          >
            🔥
          </motion.span>
        ) : (
          <span className="text-lg">🔔</span>
        )}
        {hasUnread && (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 bg-[#ffd500] text-[#111] text-[10px] font-black border-2 border-black rounded-full flex items-center justify-center pointer-events-none z-20 shadow-[2px_2px_0_rgba(0,0,0,0.3)]">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[74]"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, y: variant === "top" ? -10 : 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: variant === "top" ? -10 : 10 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className={`z-[75] bg-[#f4f4f0] text-[#111] border-2 border-black shadow-[6px_6px_0_rgba(0,0,0,0.4)] flex flex-col max-h-[60vh] ${panelPos}`}
            >
              <div className="px-4 py-3 border-b-2 border-black bg-[#ffd500] font-display uppercase text-lg leading-none">
                Notifications
              </div>
              <div className="overflow-y-auto">
                {items.length === 0 && (
                  <p className="p-6 text-center text-[10px] font-bold tracking-widest uppercase text-[#666]">
                    Empty. Sweet dreams 🌙
                  </p>
                )}
                {items.map((n: Notif) => (
                  <div key={n.id} className="px-4 py-3 border-b border-black/15 flex gap-3 items-start bg-white">
                    <span className="text-lg shrink-0">{iconFor(n.type)}</span>
                    <div className="min-w-0">
                      <p className="text-sm font-bold leading-snug">{n.text}</p>
                      <p className="text-[9px] text-[#666] font-bold tracking-widest uppercase mt-1">
                        {timeAgo(n.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}