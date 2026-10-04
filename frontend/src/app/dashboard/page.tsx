"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import axios from "axios";
import { getCachedUser, subscribeUser, refreshUser } from "@/lib/apiCache";
import { authApi, isAuthenticated } from "@/lib/auth";
import type { ReactNode } from "react";
import ActivityCard from "@/components/ActivityCard";
import { Star, Sticker, DreamDecor } from "@/components/DreamBits";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Tone = "default" | "yellow" | "orange" | "indigo";

function SectionTitle({ children, tone = "default" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    default: "bg-[#f4f4f0] text-[#111]",
    yellow: "bg-[#ffd500] text-[#111]",
    orange: "bg-[#ff4b26] text-white",
    indigo: "bg-[#5866f2] text-white",
  };
  return (
    <div className={`px-4 py-3 border-b-2 border-black font-display uppercase text-xl md:text-2xl tracking-tight ${tones[tone]}`}>
      {children}
    </div>
  );
}

function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`text-[9px] md:text-[10px] font-bold tracking-widest uppercase ${className}`}>
      {children}
    </p>
  );
}

function XpTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-[#c7d2fe] text-[#111] border-2 border-black p-3 shadow-[4px_4px_0_#000] text-sm min-w-[200px]">
      <p className="font-display uppercase text-base mb-1">{d.name}</p>
      <p className="text-[9px] font-bold tracking-widest uppercase text-[#4b5563] mb-2">
        {d.date} · {d.sport} · {d.distance} km
      </p>
      <div className="flex justify-between gap-4"><span className="text-[#4b5563] font-bold uppercase text-[10px]">Base XP</span><span className="font-display">{d.base_xp}</span></div>
      <div className="flex justify-between gap-4"><span className="text-[#4b5563] font-bold uppercase text-[10px]">Intensity</span><span className="font-display text-[#ff4b26]">{d.intensity_category} ×{Number(d.intensityMult).toFixed(2)}</span></div>
      <div className="flex justify-between gap-4"><span className="text-[#4b5563] font-bold uppercase text-[10px]">Sleep</span><span className="font-display">×{Number(d.sleepMult).toFixed(2)}</span></div>
      <div className="flex justify-between gap-4"><span className="text-[#4b5563] font-bold uppercase text-[10px]">Streak</span><span className="font-display text-[#16a34a]">×{Number(d.streakMult ?? 1).toFixed(2)}</span></div>
      <div className="flex justify-between gap-4 mt-1 pt-1 border-t border-black/20"><span className="font-bold uppercase text-[10px]">Total</span><span className="font-display text-[#171a38]">+{d.xp} XP</span></div>
    </div>
  );
}

function useIsTouch() {
  const [touch, setTouch] = useState(false);

  useEffect(() => {
    setTouch(
      typeof window !== "undefined" &&
        (
          window.matchMedia?.("(pointer: coarse)").matches ||
          window.matchMedia?.("(hover: none)").matches ||
          "ontouchstart" in window
        )
    );
  }, []);

  return touch;
}
 

export default function Dashboard() {
  const [userData, setUserData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [leaderboardTab, setLeaderboardTab] = useState<"global" | "friends">("global");
  const [inviteMessage, setInviteMessage] = useState("");
  const [globalBoard, setGlobalBoard] = useState<any[]>([]);
  const [friendsBoard, setFriendsBoard] = useState<any[]>([]);
  const [boardsLoaded, setBoardsLoaded] = useState(false);
  const isTouch = useIsTouch();
  const [touchTooltipActive, setTouchTooltipActive] = useState(false);

  const touchStartRef = useRef<{
    time: number;
    x: number;
    y: number;
  } | null>(null);

  const TOUCH_HOLD_MS = 250;

  const handleChartTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];

    touchStartRef.current = {
      time: Date.now(),
      x: touch.clientX,
      y: touch.clientY,
    };

    setTouchTooltipActive(false);
  };

  const handleChartTouchMove = (e: React.TouchEvent) => {
    if (!touchStartRef.current) return;

    const touch = e.touches[0];

    const elapsed = Date.now() - touchStartRef.current.time;
    const dx = Math.abs(touch.clientX - touchStartRef.current.x);
    const dy = Math.abs(touch.clientY - touchStartRef.current.y);

    // Не показываем карточку от обычного быстрого свайпа/тапа.
    if (
      elapsed >= TOUCH_HOLD_MS &&
      (dx > 4 || dy > 4)
    ) {
      setTouchTooltipActive(true);
    }
  };

  const handleChartTouchEnd = () => {
    touchStartRef.current = null;
    setTouchTooltipActive(false);
  };

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) { setUserData(cached); setLoading(false); } // мгновенно из кэша
    const unsub = subscribeUser(setUserData);               // живые обновления
    refreshUser();                                          // фон: прогрев
    setLoading(false);                                      // сразу снимаем лоадер — кэш уже подтянут выше
    return unsub;
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) return;
    (async () => {
      try {
        const [g, f] = await Promise.all([
          authApi.get("/api/leaderboard", { params: { scope: "global" } }),
          authApi.get("/api/leaderboard", { params: { scope: "friends" } }),
        ]);
        setGlobalBoard(g.data.entries || []);
        setFriendsBoard(f.data.entries || []);
      } catch {} finally {
        setBoardsLoaded(true);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] flex items-center justify-center">
        <p className="font-display uppercase text-2xl text-white animate-pulse">Dreaming...</p>
      </div>
    );
  }

  const isEmpty = !userData || !userData.user;
  const data = userData ?? {
    user: { name: "athlete", level: 1, total_xp: 0, xp_to_next_level: 100 },
    recent_activities: [],
  };
  const stats = data.stats ?? { day_streak: 0, week_streak: 0, week_hours: 0, week_goal_hours: 10 };

  const chartData = [...(data.recent_activities || [])]
    .slice()
    .reverse()
    .map((act: any) => ({
      date: act.date || "",
      xp: Math.round(Number(act.xp) || 0),
      name: act.name || "workout",
      sport: act.sport || "",
      distance: act.distance_km ?? 0,
      sleepMult: act.sleep_multiplier ?? 1,
      intensityMult: act.intensity_multiplier ?? 1,
      base_xp: act.base_xp ?? 0,
      intensity_category: act.intensity_category ?? "MEDIUM",
      streakMult: act.streak_multiplier ?? 1,
    }));

  const xpProgress = isEmpty ? 0 : (data.user.total_xp % 100);

  const handleInvite = async () => {
    try {
      await navigator.clipboard.writeText(window.location.origin);
      setInviteMessage("✅ Link copied — send it to your friends");
    } catch {
      setInviteMessage("Copy the link from the address bar");
    }
    setTimeout(() => setInviteMessage(""), 3000);
  };

  const rows = leaderboardTab === "global" ? globalBoard : friendsBoard;

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 sm:px-4 md:px-6 pb-2 sm:pb-4 md:pb-6 text-[#111] relative overflow-hidden flex flex-col">
      {/* ✦ сонный фон */}
      <Star className="absolute w-6 h-6 text-white/80 top-[6%] left-[3%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-white/70 top-[16%] right-[6%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-[#ffd500] bottom-[10%] left-[8%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-white/80 bottom-[5%] right-[4%] animate-pulse" />

      {/* 📰 жёсткая таблица поверх сна */}
      <div className="relative max-w-[1400px] w-full mx-auto border-2 border-t-0 border-black bg-[#f4f4f0] flex-1 flex flex-col breathe-table">        

        {/* Пустое состояние */}
        {isEmpty && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="relative border-b-2 border-black bg-white p-6 md:p-10 text-center space-y-4"
          >
            <Sticker className="-top-3 left-6 bg-[#ffd500] text-black rotate-[3deg]">zzz…</Sticker>
            <p className="font-display uppercase text-4xl md:text-6xl">Empty.</p>
            <Label className="text-[#666]">Level 1 · 0 XP · 0 workouts</Label>
            <p className="text-sm text-[#666] max-w-md mx-auto">
              Синхронизируй первую тренировку — и прогресс появится здесь.
            </p>
            <Link
              href="/profile"
              className="inline-block px-6 py-3 bg-[#ff4b26] text-white text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] transition-colors"
            >
              Sync →
            </Link>
          </motion.div>
        )}

        {/* Заголовок + стикер, вылезающий за рамку */}
        <div className="relative grid md:grid-cols-[1fr_auto] border-b-2 border-black">
          <Sticker className="top-2 right-4 md:right-10 bg-[#f6b8d0] text-black rotate-[-4deg]">don't stop fighting 🔥</Sticker>
          <div className="p-5 md:p-8 flex flex-col gap-3 md:border-r-2 border-black">
            <Label className="text-[#666]">Season 001 · Athlete: {data.user.name}</Label>
            <h1 className="font-display uppercase leading-[0.9] text-4xl md:text-6xl lg:text-7xl">
              Progress<span className="text-[#ff4b26]">.</span>
            </h1>
          </div>
          <Link
            href="/profile"
            className="bg-[#5866f2] text-white px-5 py-4 flex items-center justify-between gap-4 text-[11px] font-bold tracking-widest uppercase hover:bg-black transition-colors"
          >
            <span>Go to<br />profile</span>
            <span>→</span>
          </Link>
        </div>

        {/* Статистика */}
        
        <div className="grid md:grid-cols-3 border-b-2 border-black">
          <div className="md:border-r-2 border-black">
            <SectionTitle>Level</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">{data.user.level}</p>
              <div className="w-full bg-black/10 h-3 mt-4 border border-black/20">
                <div className="bg-[#ffd500] h-full transition-all" style={{ width: `${xpProgress}%` }}></div>
              </div>
              <Label className="text-[#666] mt-3">
                {isEmpty ? "100 XP to next" : `${Math.round(data.user.xp_to_next_level)} XP to next level`}
              </Label>
            </div>
          </div>

          <div className="md:border-r-2 border-black border-t-2 md:border-t-0">
            <SectionTitle tone="yellow">Streak</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl text-[#ff4b26]">{stats.day_streak}</p>
              <Label className="text-[#666] mt-2">Days in a row</Label>
              <div className="mt-4 pt-3 border-t border-black/20">
                <Label className="text-[#666]">{stats.week_streak} weeks streak</Label>
              </div>
            </div>
          </div>

          <div className="border-t-2 md:border-t-0 border-black">
            <SectionTitle>Week goal</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">
                {stats.week_hours}<span className="text-xl md:text-2xl text-[#666]"> / {stats.week_goal_hours}h</span>
              </p>
              <div className="w-full bg-black/10 h-3 mt-4 border border-black/20">
                <div
                  className="bg-[#5866f2] h-full transition-all"
                  style={{ width: `${Math.min(100, (stats.week_hours / stats.week_goal_hours) * 100)}%` }}
                ></div>
              </div>
              <Label className="text-[#666] mt-3">
                {Math.min(100, Math.round((stats.week_hours / stats.week_goal_hours) * 100))}% complete
              </Label>
            </div>
          </div>
        </div>

        {/* Рейтинг */}
        <div className="border-b-2 border-black">
          <div className="relative grid md:grid-cols-[200px_1fr]">
            <Sticker className="-top-3 right-4 bg-[#5866f2] text-white rotate-[3deg] z-30">who's here? 👀</Sticker>
            <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#5866f2] text-white">
              <div>
                <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Rating</p>
                <div className="h-0.5 bg-black mt-3 mb-4"></div>
                <Label className="block text-white/80">Global & Friends</Label>
              </div>
              <span className="font-display text-4xl mt-auto">↓</span>
            </div>
            <div>
              <div className="md:hidden">
                <SectionTitle tone="indigo">Rating</SectionTitle>
              </div>
              <div className="flex border-b-2 border-black">
                <button
                  onClick={() => setLeaderboardTab("global")}
                  className={`flex-1 px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase transition-colors ${
                    leaderboardTab === "global" ? "bg-[#5866f2] text-white" : "hover:bg-black/5"
                  }`}
                >
                  Global
                </button>
                <button
                  onClick={() => setLeaderboardTab("friends")}
                  className={`flex-1 px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase border-l-2 border-black transition-colors ${
                    leaderboardTab === "friends" ? "bg-[#5866f2] text-white" : "hover:bg-black/5"
                  }`}
                >
                  Friends
                </button>
              </div>

              <div>
                {!boardsLoaded ? (
                  <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
                    Loading rating...
                  </p>
                ) : rows.length === 0 ? (
                  <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
                    {leaderboardTab === "friends"
                      ? "No friends yet — find athletes in your profile 👥"
                      : "Be the first on the leaderboard! 🏆"}
                  </p>
                ) : (
                  rows.map((player, idx) => (
                    <div
                      key={player.id}
                      className={`flex justify-between items-center px-4 py-3 ${
                        idx > 0 ? "border-t border-black/20" : ""
                      } ${player.is_you ? "bg-[#5866f2]/15 border-l-4 border-l-[#5866f2]" : "hover:bg-black/5"} transition-colors`}
                    >
                      <div className="flex items-center gap-3 md:gap-4">
                        <span className={`font-display text-lg w-8 ${player.rank <= 3 ? "text-[#ff4b26]" : "text-[#999]"}`}>
                          {String(player.rank).padStart(2, "0")}
                        </span>
                        <div>
                          <p className={`font-bold uppercase tracking-wide text-sm ${player.is_you ? "text-[#5866f2]" : ""}`}>
                            {player.display_name} {player.is_you && "(YOU)"}
                          </p>
                          <Label className="text-[#666]">LVL {player.level}</Label>
                        </div>
                      </div>
                      <span className="font-display text-[#ff4b26]">
                        {Math.round(player.total_xp).toLocaleString()}
                      </span>
                    </div>
                  ))
                )}
              </div>

              {leaderboardTab === "friends" && (
                <div className="border-t-2 border-black">
                  <button
                    onClick={handleInvite}
                    className="w-full px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] hover:text-white transition-colors"
                  >
                    + Invite friends
                  </button>
                  {inviteMessage && (
                    <p className="text-[10px] font-bold text-[#5866f2] text-center py-2 bg-[#5866f2]/10">{inviteMessage}</p>
                  )}
                </div>
              )}

              <Label className="text-[#999] text-center py-3 border-t border-black/20">
                * Live rating · real athletes data
              </Label>
            </div>
          </div>
        </div>

        {/* График */}
        {chartData.length > 0 && (
          <div className="border-b-2 border-black">
            <div className="grid md:grid-cols-[200px_1fr]">
              <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#f4f4f0]">
                <div>
                  <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">XP Dynamics</p>
                  <div className="h-0.5 bg-black mt-3 mb-4"></div>
                  <Label className="text-[#666] block">Last {chartData.length} workouts</Label>
                </div>
                <span className="font-display text-4xl mt-auto">↓</span>
              </div>
              <div className="p-4 md:p-6 bg-white">
                <div className="md:hidden mb-4">
                  <SectionTitle>XP Dynamics</SectionTitle>
                </div>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={chartData}
                      margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                      onTouchStart={isTouch ? handleChartTouchStart : undefined}
                      onTouchMove={isTouch ? handleChartTouchMove : undefined}
                      onTouchEnd={isTouch ? handleChartTouchEnd : undefined}
                      onTouchCancel={isTouch ? handleChartTouchEnd : undefined}
                    >
                      <defs>
                        <linearGradient id="xpFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#ff4b26" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#ff4b26" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#00000015" />
                      <XAxis dataKey="date" tick={{ fill: "#666", fontSize: 10 }} axisLine={{ stroke: "#000" }} tickLine={false} />
                      <YAxis tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
                      <Tooltip
                        content={<XpTooltip />}
                        trigger="hover"
                        active={isTouch ? touchTooltipActive : undefined}
                        cursor={
                          isTouch
                            ? touchTooltipActive
                              ? { stroke: "#5866f2", strokeWidth: 1 }
                              : false
                            : { stroke: "#5866f2", strokeWidth: 1 }
                        }
                      />
                      <Area type="monotone" dataKey="xp" stroke="#ff4b26" strokeWidth={2.5} fill="url(#xpFill)"
                        activeDot={{ r: 5, fill: "#171a38", stroke: "#ffd500", strokeWidth: 2 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Тренировки */}
        <div className="border-b-2 border-black">
          <div className="grid md:grid-cols-[200px_1fr]">
            <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#ff4b26] text-white">
              <div>
                <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Workouts</p>
                <div className="h-0.5 bg-black mt-3 mb-4"></div>
                <Label className="block text-white/80">Hover / long press for details</Label>
              </div>
              <span className="font-display text-4xl mt-auto">↓</span>
            </div>
            <div className="p-4 md:p-6">
              <div className="md:hidden mb-4">
                <SectionTitle tone="orange">Workouts</SectionTitle>
              </div>
              {data.recent_activities.length === 0 ? (
                <p className="text-sm text-[#666]">
                  Пока пусто. Синхронизируй тренировки в{" "}
                  <Link href="/profile" className="text-[#5866f2] font-bold underline">профиле</Link>.
                </p>
              ) : (
                <div className="space-y-0">
                  {data.recent_activities.map((act: any, idx: number) => (
                    <div key={idx} className={idx > 0 ? "border-t-2 border-black" : ""}>
                      <ActivityCard act={act} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        
      </div>
    </main>
  );
}