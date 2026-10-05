"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { authApi } from "@/lib/auth";
import { refreshUser } from "@/lib/apiCache";

export type ConnectMessage = { type: "success" | "error" | "info"; text: string };

interface Source {
  id: "intervals" | "garmin" | "strava";
  name: string;
  desc: string;
  emoji: string;
  available: boolean;
}

const SOURCES: Source[] = [
  { id: "intervals", name: "Intervals.icu", desc: "Strava, Garmin, Wahoo aggregator", emoji: "🔌", available: true },
  { id: "garmin", name: "Garmin", desc: "Через мост Intervals.icu — отдельный ключ не нужен", emoji: "⌚", available: false },
  { id: "strava", name: "Strava", desc: "Direct Strava link", emoji: "🚴", available: false },
];

export default function ConnectSources({
  hasKey,
  athleteId,
  onMessage,
}: {
  hasKey: boolean;
  athleteId: string | null;
  onMessage: (m: ConnectMessage) => void;
}) {
  const [expanded, setExpanded] = useState<Source["id"] | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [athleteInput, setAthleteInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const isOpen = expanded === "intervals";

  const openForm = () => {
    setAthleteInput(athleteId || "");
    setApiKey("");
    setExpanded("intervals");
  };

  const toggleRow = (s: Source) => {
    if (s.id === "garmin") {
      onMessage({
        type: "info",
        text: hasKey
          ? "⌚ Garmin уже течёт через мост Intervals.icu — данные обновляются с каждой синхронизацией."
          : "⌚ Garmin подключается через мост Intervals.icu: агрегатор сам тянет твои данные из Garmin. Подключи Intervals — и Garmin заработает автоматически!",
      });
      return;
    }
    if (!s.available) {
      onMessage({ type: "info", text: `🚧 ${s.name} sync is under development — coming soon.` });
      return;
    }
    if (isOpen) setExpanded(null);
    else openForm();
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.post("/api/intervals/connect", {
        api_key: apiKey.trim(),
        athlete_id: athleteInput.trim(),
      });
      onMessage({ type: "success", text: `✅ ${res.data.message}` });
      setExpanded(null); // сворачиваем секцию после успеха
      setApiKey("");
      await refreshUser(true);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      onMessage({ type: "error", text: `❌ ${typeof detail === "string" ? detail : err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await authApi.post("/api/sync");
      onMessage({
        type: "success",
        text: `✅ Sync done: ${res.data.synced_count} workouts · +${Math.round(res.data.new_xp)} XP`,
      });
      await refreshUser(true);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      onMessage({ type: "error", text: `❌ ${typeof detail === "string" ? detail : "Sync error"}` });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="border-2 border-black bg-white">
      {SOURCES.map((s, idx) => (
        <div key={s.id} className={idx > 0 ? "border-t-2 border-black" : ""}>
          {/* ── Строка источника ── */}
          <button
            type="button"
            onClick={() => toggleRow(s)}
            className="w-full grid grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-3 text-left hover:bg-black/5 transition-colors"
          >
            <span className="w-12 h-12 md:w-14 md:h-14 border-2 border-black flex items-center justify-center text-xl md:text-2xl bg-[#f4f4f0] shrink-0">
              {s.emoji}
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-2 flex-wrap">
                <span className="font-bold uppercase tracking-wide text-sm md:text-base">{s.name}</span>
                {s.id === "intervals" && hasKey ? (
                  <span className="px-2 py-0.5 bg-[#5866f2] text-white text-[9px] font-bold tracking-widest uppercase">
                    Connected
                  </span>
                ) : s.id === "garmin" && hasKey ? (
                  <span className="px-2 py-0.5 bg-[#16a34a] text-white text-[9px] font-bold tracking-widest uppercase">
                    via Intervals
                  </span>
                ) : s.id === "garmin" ? (
                  <span className="px-2 py-0.5 border border-black/30 text-[#666] text-[9px] font-bold tracking-widest uppercase">
                    bridge
                  </span>
                ) : s.available ? (
                  <span className="px-2 py-0.5 border border-black/30 text-[#666] text-[9px] font-bold tracking-widest uppercase">
                    Available
                  </span>
                ) : (
                  <span className="px-2 py-0.5 border border-black/30 text-[#666] text-[9px] font-bold tracking-widest uppercase">
                    Soon
                  </span>
                )}
              </span>
              <span className="block text-[10px] text-[#666] truncate mt-0.5">{s.desc}</span>
            </span>
            <span className="font-display text-xl shrink-0">
              {s.id === "intervals" ? (isOpen ? "▲" : "▼") : "→"}
            </span>
          </button>

          {/* ── Garmin: плашка «подключено через мост Intervals» ── */}
          <AnimatePresence initial={false}>
            {s.id === "garmin" && hasKey && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4">
                  <div className="border-2 border-[#16a34a] bg-[#16a34a]/10 px-4 py-3 flex items-center gap-3">
                    <span className="text-xl shrink-0">⌚</span>
                    <div className="min-w-0">
                      <p className="text-[9px] font-bold tracking-widest uppercase text-[#16a34a]">
                        Connected via bridge
                      </p>
                      <p className="text-sm font-bold uppercase truncate">
                        Garmin → Intervals.icu → Fantasy League
                      </p>
                      <p className="text-[10px] text-[#666] mt-0.5">
                        Отдельный ключ не нужен — агрегатор сам тянет твои данные из Garmin.
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Подключено: статус + 2 кнопки (когда секция свёрнута) ── */}
          <AnimatePresence initial={false}>
            {s.id === "intervals" && hasKey && !isOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4">
                  <div className="border-2 border-[#5866f2] bg-[#5866f2]/10 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[9px] font-bold tracking-widest uppercase text-[#5866f2]">Connected</p>
                      <p className="font-bold uppercase truncate">athlete: {athleteId || "—"}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={handleSync}
                        disabled={syncing}
                        className="px-4 py-2 bg-[#ff4b26] text-white text-[10px] font-bold tracking-widest uppercase hover:bg-black transition-colors disabled:opacity-50"
                      >
                        {syncing ? "Syncing..." : "Sync data ⚡"}
                      </button>
                      <button
                        type="button"
                        onClick={openForm}
                        className="px-4 py-2 bg-white border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-[#ffd500] transition-colors"
                      >
                        Update key 🔑
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Раскрытая секция: форма ключа ── */}
          <AnimatePresence initial={false}>
            {isOpen && s.id === "intervals" && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <form onSubmit={handleConnect} className="mx-4 mb-4 px-4 py-4 border-2 border-dashed border-black/30 bg-[#f4f4f0] space-y-3">
                  <div>
                    <label className="block text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">
                      Intervals.icu API key
                    </label>
                    <input
                      type="password"
                      required
                      minLength={5}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="paste your API key"
                      className="w-full px-4 py-3 bg-white border-2 border-black font-mono text-sm focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
                    />
                  </div>
                  <div>
                    <label className="block text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">
                      Athlete ID
                    </label>
                    <input
                      type="text"
                      required
                      minLength={2}
                      value={athleteInput}
                      onChange={(e) => setAthleteInput(e.target.value)}
                      placeholder="i337ххх"
                      className="w-full px-4 py-3 bg-white border-2 border-black font-mono text-sm focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
                    />
                  </div>
                  <ol className="text-xs text-[#666] space-y-1 list-decimal list-inside">
                    <li>
                      Open{" "}
                      <a href="https://intervals.icu" target="_blank" rel="noopener" className="text-[#5866f2] font-bold underline">
                        intervals.icu
                      </a>
                    </li>
                    <li>
                      Go to <b>Settings → API</b>
                    </li>
                    <li>Copy API key and athlete ID (looks like iXXXXX)</li>
                  </ol>
                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={loading}
                      className="flex-1 px-4 py-3 bg-[#ff4b26] text-white text-[10px] font-bold tracking-widest uppercase hover:bg-black transition-colors disabled:opacity-50"
                    >
                      {loading ? "Connecting..." : hasKey ? "Save new key →" : "Connect →"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setExpanded(null)}
                      className="px-4 py-3 border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}
    </div>
  );
}