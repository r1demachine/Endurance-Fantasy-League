"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { authApi, logout } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { ErrorState, Skeleton } from "@/components/ui";
import { formatWeekRange } from "@/lib/format";
import { clearUserCache, getCachedUser, refreshUser, subscribeUser } from "@/lib/apiCache";
import ProfileSettingsModal, { type SettingsTab } from "@/components/ProfileSettingsModal";
import SocialHub from "@/components/SocialHub";
import { sectionItemVariants, sectionStaggerVariants, useTransitionDirection } from "@/components/PageTransition";

type ProfileData = {
  user?: {
    name?: string;
    username?: string;
    level?: number;
    total_xp?: number;
    avatar_url?: string | null;
  };
  season_stats?: {
    season_start?: string;
    total_km?: number;
    total_hours?: number;
    total_elevation?: number;
    total_workouts?: number;
    total_xp?: number;
  };
  week?: {
    is_deload?: boolean;
    deload_source?: "auto" | "manual" | null;
    actual_load?: number;
    target_load?: number;
  };
  recent_events?: { id: number | string; type: string; title?: string; amount?: number; date?: string }[];
};

type StatsRange = "season" | "year" | "week";
type StatsData = { range: StatsRange; start_date: string; end_date: string; distance_km: number; hours: number; elevation: number; workouts: number; xp: number };
const STATS_RANGES: { value: StatsRange; label: string }[] = [
  { value: "season", label: "Сезон" }, { value: "year", label: "Год" }, { value: "week", label: "Неделя" },
];
function isStatsRange(value: string | null): value is StatsRange {
  return value === "season" || value === "year" || value === "week";
}

const SETTINGS_TABS: SettingsTab[] = ["account", "appearance", "sources", "training", "privacy", "danger"];

function isSettingsTab(value: string | null): value is SettingsTab {
  return value !== null && SETTINGS_TABS.includes(value as SettingsTab);
}

function ProfileContent() {
  const [userData, setUserData] = useState<ProfileData | null>(null);
  const [statsData, setStatsData] = useState<StatsData | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState("");
  const router = useRouter();
  const transitionDirection = useTransitionDirection();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const queryTab = searchParams.get("settings");
  const settingsTab = isSettingsTab(queryTab) ? queryTab : null;
  const queryRange = searchParams.get("range");
  const statsRange: StatsRange = isStatsRange(queryRange) ? queryRange : "season";
  const pendingSettingsUrlRef = useRef<string | null>(null);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError("");
    try {
      const response = await authApi.get("/api/profile/stats", { params: { range: statsRange } });
      setStatsData(response.data as StatsData);
    } catch (requestError: unknown) {
      setStatsError(getApiErrorMessage(requestError, "Не удалось загрузить статистику. Попробуй ещё раз."));
    } finally {
      setStatsLoading(false);
    }
  }, [statsRange]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (!isStatsRange(queryRange)) {
      const params = new URLSearchParams(queryString);
      params.set("range", "season");
      router.replace(pathname + "?" + params.toString(), { scroll: false });
    }
  }, [pathname, queryRange, queryString, router]);

  const changeStatsRange = (nextRange: StatsRange) => {
    const params = new URLSearchParams(queryString);
    params.set("range", nextRange);
    router.replace(pathname + "?" + params.toString(), { scroll: false });
  };

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) setUserData(cached);
    const unsubscribe = subscribeUser(setUserData);
    void refreshUser(true);

    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    // Release the duplicate-click guard after Next reflects the URL update.
    pendingSettingsUrlRef.current = null;
  }, [pathname, queryString]);

  const updateSettingsUrl = (tab: SettingsTab | null, historyMode: "push" | "replace" = "replace") => {
    const nextParams = new URLSearchParams(queryString);
    if (tab) nextParams.set("settings", tab);
    else nextParams.delete("settings");

    const nextQuery = nextParams.toString();
    if (nextQuery === queryString || pendingSettingsUrlRef.current === nextQuery) return;

    pendingSettingsUrlRef.current = nextQuery;
    const target = pathname + (nextQuery ? "?" + nextQuery : "");
    if (historyMode === "push") router.push(target, { scroll: false });
    else router.replace(target, { scroll: false });
  };

  const openSettings = () => updateSettingsUrl("account", "push");
  const closeSettings = () => updateSettingsUrl(null, "replace");
  const selectSettingsTab = (tab: SettingsTab) => updateSettingsUrl(tab, "replace");

  const handleLogout = async () => {
    await logout();
    clearUserCache();
    router.push("/");
  };

  const user = userData?.user;
  const achievements = (userData?.recent_events ?? [])
    .filter((event) => event.type === "achievement")
    .slice(0, 3);

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <div aria-hidden="true" className="pointer-events-none absolute left-[8%] top-[12%] h-3 w-3 animate-pulse rounded-full bg-[#ffd500]" />
      <div aria-hidden="true" className="pointer-events-none absolute right-[10%] top-[26%] h-2 w-2 rounded-full bg-white/80" />
      <div aria-hidden="true" className="pointer-events-none absolute bottom-[18%] right-[15%] h-4 w-4 animate-pulse rounded-full bg-white/70" />

      <motion.div variants={sectionStaggerVariants} className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        <motion.header data-tour="profile-header" variants={sectionItemVariants} custom={transitionDirection} className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-black bg-[#171a38] px-4 py-5 text-white sm:px-6 md:px-8">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/65">Endurance Fantasy League</p>
            <h1 className="mt-1 font-display text-3xl uppercase leading-none sm:text-4xl">Профиль<span className="text-[#ff4b26]">.</span></h1>
          </div>
          <button
            type="button"
            onClick={openSettings}
            aria-label="Открыть настройки профиля"
            title="Настройки"
            className="flex min-h-12 items-center gap-3 border-2 border-white/80 bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-white hover:text-[#171a38]"
          >
            <span aria-hidden="true" className="text-xl leading-none">⚙️</span>
            <span className="hidden sm:inline">Настройки</span>
          </button>
        </motion.header>

        <motion.section variants={sectionItemVariants} custom={transitionDirection} className="grid gap-0 border-b-2 border-black md:grid-cols-[minmax(0,1fr)_250px]">
          <div className="flex min-w-0 items-center gap-4 p-5 sm:p-7 md:p-8">
            <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden border-2 border-black bg-[#ffd500] font-display text-4xl uppercase text-[#171a38] sm:h-24 sm:w-24 sm:text-5xl">
              {user?.avatar_url ? (
                <Image src={user.avatar_url} alt="" width={96} height={96} className="h-full w-full object-cover" unoptimized />
              ) : (
                (user?.name || "A").trim().slice(0, 1).toUpperCase()
              )}
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#666]">Athlete profile</p>
              <h2 className="mt-1 truncate font-display text-2xl uppercase leading-tight sm:text-4xl">{user?.name || "Атлет"}</h2>
              {user?.username && <p className="mt-1 truncate text-sm text-[#666]">@{user.username}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="border-2 border-black bg-[#171a38] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-white">
                  Уровень {user?.level ?? 1}
                </span>
                <span className="border-2 border-black bg-[#ff4b26] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-white">
                  {Math.round(user?.total_xp ?? 0)} XP
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-col justify-center gap-3 border-t-2 border-black bg-[#e9e9e2] p-5 md:border-l-2 md:border-t-0 md:p-6">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Публичный профиль</p>
            {user?.username ? (
              <Link
                href={"/u/" + encodeURIComponent(user.username)}
                className="break-all text-sm font-bold underline decoration-2 underline-offset-4 hover:text-[#5866f2]"
              >
                Мой публичный профиль ↗
              </Link>
            ) : (
              <span className="text-sm text-[#666]">Профиль загружается…</span>
            )}
          </div>
        </motion.section>

        {userData?.week?.is_deload && (
          <motion.section variants={sectionItemVariants} custom={transitionDirection} className={`border-b-2 border-black px-4 py-4 sm:px-6 ${userData.week.deload_source === "manual" ? "bg-[#f3e8ff]" : "bg-[#e0f2fe]"}`}>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Текущая неделя · Deload</p>
            <p className="mt-1 font-display text-xl uppercase">
              Разгрузочная неделя {userData.week.deload_source === "manual" ? "· установлена вручную" : "· назначена автоматически"}
            </p>
            <p className="mt-1 text-xs text-[#555]">
              Нагрузка: {Math.round(Number(userData.week.actual_load) || 0)} / {Math.round(Number(userData.week.target_load) || 0)} TSS.
              {userData.week.deload_source === "manual" ? " Goal XP ограничен значением 85%." : ""}
            </p>
          </motion.section>
        )}

        <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-b-2 border-black">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b-2 border-black px-4 py-3 sm:px-6">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Athlete Stats</p>
              <h3 className="font-display text-xl uppercase sm:text-2xl">Статистика</h3>
              <p className="mt-1 text-xs text-[#666]">
                {statsData ? statsRange === "season" ? "Сезон с " + new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(new Date(statsData.start_date + "T12:00:00")) : statsRange === "year" ? new Date(statsData.start_date + "T12:00:00").getFullYear() + " год" : formatWeekRange(statsData.start_date) : "Выбери период"}
              </p>
            </div>
            <div role="group" aria-label="Период статистики" className="flex border-2 border-black">
              {STATS_RANGES.map((range) => (
                <button key={range.value} type="button" aria-pressed={statsRange === range.value} onClick={() => changeStatsRange(range.value)} className={`min-h-10 border-r-2 border-black px-3 text-[10px] font-bold uppercase tracking-wide last:border-r-0 sm:px-4 ${statsRange === range.value ? "bg-[#ffd500]" : "bg-white hover:bg-black/5"}`}>
                  {range.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            {statsLoading ? (
              <div className="p-4 sm:p-6"><Skeleton label="Загружаем статистику" rows={3} /></div>
            ) : statsError ? (
              <div className="p-4 sm:p-6"><ErrorState message={statsError} onRetry={() => void loadStats()} /></div>
            ) : statsData ? (
              <div className="grid grid-cols-2 divide-x-2 divide-y-2 divide-black sm:grid-cols-3 sm:divide-y-0 lg:grid-cols-5">
                {[
                  { label: "Дистанция", value: String(statsData.distance_km ?? 0), unit: "км" },
                  { label: "Время", value: String(statsData.hours ?? 0), unit: "ч" },
                  { label: "Набор", value: String(statsData.elevation ?? 0), unit: "м" },
                  { label: "Тренировки", value: String(statsData.workouts ?? 0), unit: "" },
                  { label: "XP за период", value: String(Math.round(statsData.xp ?? 0)), unit: "" },
                ].map((item) => (
                  <div key={item.label} className="min-w-0 px-3 py-4 text-center sm:p-4">
                    <p className="font-display text-2xl sm:text-3xl">{item.value}<span className="ml-1 text-xs text-[#666]">{item.unit}</span></p>
                    <p className="mt-1 text-[9px] font-bold uppercase tracking-widest text-[#666] sm:text-[10px]">{item.label}</p>
                  </div>
                ))}
              </div>
            ) : <div className="p-6 text-sm text-[#666]">Статистика пока недоступна.</div>}
          </div>
        </motion.section>

        <motion.section variants={sectionItemVariants} custom={transitionDirection}>
          <div className="border-b-2 border-black px-4 py-3 sm:px-6">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Milestones</p>
            <h3 className="font-display text-xl uppercase sm:text-2xl">Достижения</h3>
          </div>
          {achievements.length > 0 ? (
            <div className="grid gap-0 sm:grid-cols-3 sm:divide-x-2 sm:divide-black">
              {achievements.map((achievement) => (
                <div key={achievement.id} className="flex min-w-0 items-start gap-3 border-b-2 border-black p-4 last:border-b-0 sm:border-b-0">
                  <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center border-2 border-black bg-[#ffd500] text-xl">🏅</span>
                  <div className="min-w-0">
                    <p className="break-words text-sm font-bold">{achievement.title || "Достижение"}</p>
                    {achievement.date && <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-[#666]">{achievement.date}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-3 p-4 sm:p-5">
              <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center border-2 border-black bg-white text-xl">☆</span>
              <p className="text-sm text-[#666]">Здесь появятся выполненные достижения и значимые спортивные вехи.</p>
            </div>
          )}
        </motion.section>

        <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-t-2 border-black bg-white">
          <div className="border-b-2 border-black px-4 py-3 sm:px-6">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Community</p>
            <h3 className="font-display text-xl uppercase sm:text-2xl">Друзья и клубы</h3>
          </div>
          <SocialHub />
        </motion.section>
      </motion.div>

      {settingsTab && (
        <ProfileSettingsModal
          tab={settingsTab}
          userData={userData}
          onClose={closeSettings}
          onTabChange={selectSettingsTab}
          onLogout={handleLogout}
        />
      )}
    </main>
  );
}

export default function Profile() {
  return (
    <Suspense fallback={<div className="min-h-screen " />}>
      <ProfileContent />
    </Suspense>
  );
}
