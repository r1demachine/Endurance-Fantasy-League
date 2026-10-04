"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearAuth } from "@/lib/auth";
import { authApi } from "@/lib/auth";
import { getCachedUser, subscribeUser, refreshUser, clearUserCache } from "@/lib/apiCache";
import type { ReactNode } from "react";
import { Star, Sticker, DreamBubble } from "@/components/DreamBits";
import ConnectSources from "@/components/ConnectSources";
import SocialHub from "@/components/SocialHub";


type Tone = "default" | "yellow" | "orange" | "indigo" | "red";

function SectionTitle({ children, tone = "default" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    default: "bg-[#f4f4f0] text-[#111]",
    yellow: "bg-[#ffd500] text-[#111]",
    orange: "bg-[#ff4b26] text-white",
    indigo: "bg-[#5866f2] text-white",
    red: "bg-[#ff4b26] text-white",
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

export default function Profile() {
  const [userData, setUserData] = useState<any>(null);
  const router = useRouter();
  const [syncing, setSyncing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) setUserData(cached);
    const unsub = subscribeUser(setUserData);
    refreshUser();
    return unsub;
  }, []);



  const handleReset = async () => {
    if (!confirm("Удалить все тренировки и обнулить XP? Это действие нельзя отменить.")) return;
    setResetting(true);
    setMessage(null);
    try {
      await authApi.delete(`/api/reset`);;
      clearUserCache(); // сбрасываем и кэш, иначе вернётся старый XP
      setMessage({ type: "success", text: "🗑 Data cleared." });
    } catch {
      setMessage({ type: "error", text: "❌ Reset error." });
    } finally {
      setResetting(false);
    }
    
  };

  const handleLogout = () => {
    clearAuth();
    clearUserCache();
    router.push("/");
  };

  const seasonStats = userData?.season_stats ?? {
    season_start: "01.09.2026",
    total_km: 0,
    total_hours: 0,
    total_elevation: 0,
    total_workouts: 0,
    total_xp: 0,
  };



  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 sm:px-4 md:px-6 pb-2 sm:pb-4 md:pb-6 text-[#111] relative overflow-hidden flex flex-col">
      <Star className="absolute w-6 h-6 text-white/80 top-[6%] right-[5%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-[#ffd500] top-[20%] left-[6%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-white/70 bottom-[12%] right-[9%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-white/80 bottom-[6%] left-[4%] animate-pulse" />

      <div className="relative max-w-[1400px] w-full mx-auto border-2 border-t-0 border-black bg-[#f4f4f0] flex-1 flex flex-col breathe-table">
        {/* Заголовок + стикер */}
        <div className="relative grid md:grid-cols-[1fr_auto] border-b-2 border-black">
          <Sticker className="top-2 right-6 bg-[#f6b8d0] text-black rotate-[-4deg]">athlete file 📁</Sticker>
          <div className="p-5 md:p-8 flex flex-col gap-3 md:border-r-2 border-black">
            <Label className="text-[#666]">Endurance cabinet</Label>
            <h1 className="font-display uppercase leading-[0.9] text-4xl md:text-6xl lg:text-7xl">
              Profile<span className="text-[#ff4b26]">.</span>
            </h1>
          </div>
          <Link
            href="/dashboard"
            className="bg-[#5866f2] text-white px-5 py-4 flex items-center justify-between gap-4 text-[11px] font-bold tracking-widest uppercase hover:bg-black transition-colors"
          >
            <span>Back to<br />dashboard</span>
            <span>←</span>
          </Link>
        </div>

        {/* Сообщения */}
        {message && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className={`border-b-2 border-black px-5 py-4 text-sm font-bold ${
              message.type === "success" ? "bg-[#ffd500]/40" :
              message.type === "error" ? "bg-[#ff4b26]/20 text-[#ff4b26]" :
              "bg-[#5866f2]/15 text-[#5866f2]"
            }`}
          >
            {message.text}
          </motion.div>
        )}

        {/* Карточка атлета: BRUT-квадрат + Dream-пузыри сна */}
        <div className="relative grid md:grid-cols-[200px_1fr] border-b-2 border-black">
          <div className="relative hidden md:flex items-center justify-center border-r-2 border-black bg-[#171a38] text-white p-6 overflow-hidden">
            <span className="font-display text-6xl lowercase z-10">
              {userData ? userData.user.name.charAt(0) : "—"}
            </span>
            <DreamBubble emoji="😴" className="w-10 h-10 text-xl right-3 top-3" delay={0.3} />
            <DreamBubble emoji="⚡" className="w-8 h-8 text-base left-3 bottom-4" delay={0.9} />
          </div>
          <div>
            <SectionTitle>Athlete</SectionTitle>
            <div className="p-5 md:p-6 flex items-center gap-4">
              <div className="md:hidden w-14 h-14 bg-[#171a38] text-white flex items-center justify-center font-display text-3xl lowercase shrink-0">
                {userData ? userData.user.name.charAt(0) : "—"}
              </div>
              <div className="min-w-0">
                <h2 className="font-display uppercase text-2xl md:text-4xl tracking-tight truncate">
                  {userData ? userData.user.name : "athlete"}
                </h2>
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  <span className="px-3 py-1 bg-[#171a38] text-white text-[10px] font-bold tracking-widest uppercase">
                    LVL {userData ? userData.user.level : 1}
                  </span>
                  <span className="px-3 py-1 bg-[#ff4b26] text-white text-[10px] font-bold tracking-widest uppercase">
                    {Math.round(userData ? userData.user.total_xp : 0)} XP
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Статистика сезона */}
        <div className="border-b-2 border-black">
          <SectionTitle>Season Stats</SectionTitle>
          <div className="p-4 md:p-6">
            <Label className="text-[#666] mb-4 block">Since {seasonStats.season_start}</Label>
            <div className="flex justify-center">
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 -ml-[2px] -mt-[2px] w-full md:w-auto">
                {[
                  { label: "Distance", value: `${seasonStats.total_km}`, unit: "km" },
                  { label: "Time", value: `${seasonStats.total_hours}`, unit: "h" },
                  { label: "Climb", value: `${seasonStats.total_elevation}`, unit: "m" },
                  { label: "Workouts", value: `${seasonStats.total_workouts}`, unit: "" },
                  { label: "XP", value: `${Math.round(seasonStats.total_xp)}`, unit: "" },
                ].map((s) => (
                  <div key={s.label} className="p-3 md:p-4 text-center border-l-2 border-t-2 border-black">
                    <p className="font-display text-xl md:text-3xl">
                      {s.value}
                      <span className="text-xs text-[#666] ml-0.5">{s.unit}</span>
                    </p>
                    <Label className="text-[#666] mt-1">{s.label}</Label>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Социалка */}
        <SocialHub />

        {/* Источники данных */}
        {/* Intervals.icu key */}
        <div className="border-b-2 border-black">
          <div className="grid md:grid-cols-[200px_1fr]">
            <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#5866f2] text-white">
              <div>
                <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Connect</p>
                <div className="h-0.5 bg-black mt-3 mb-4"></div>
                <p className="block text-white/80 text-[10px] font-bold tracking-widest uppercase">Strava · Garmin · Intervals</p>              </div>
              <span className="font-display text-4xl mt-auto">↓</span>
            </div>
            <div>
              <div className="md:hidden">
                <div className="px-4 py-3 border-b-2 border-black bg-[#5866f2] text-white font-display uppercase text-xl md:text-2xl tracking-tight">
                  Connect
                </div>
              </div>
              <div className="p-5 md:p-6">
                <ConnectSources
                  hasKey={userData?.user?.has_intervals_key ?? false}
                  athleteId={userData?.user?.intervals_id ?? null}
                  onMessage={setMessage}
                />
              </div>
            </div>
          </div>
        </div>

        

        {/* Опасная зона */}
        <div className="grid md:grid-cols-[200px_1fr]">
          <div className="hidden md:flex items-center justify-center border-r-2 border-black bg-[#ff4b26] p-5">
            <span className="font-display text-4xl text-white">!</span>
          </div>
          <div>
            <SectionTitle tone="red">Danger zone</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="text-sm text-[#666] mb-4 max-w-lg">
                Полностью удаляет все синхронизированные тренировки и сбрасывает прогресс до 1 уровня. Это действие нельзя отменить.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={handleReset}
                  disabled={resetting || !userData}
                  className="px-5 py-3 bg-[#171a38] text-white text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-[#ff4b26] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {resetting ? "Clearing..." : "Clear all data"}
                </button>
                <button
                  onClick={handleLogout}
                  className="px-5 py-3 bg-[#ff4b26] text-white text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-black transition-colors"
                >
                  Logout →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}