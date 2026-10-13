"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/auth";
import { clearUserCache, getCachedUser, refreshUser, subscribeUser } from "@/lib/apiCache";
import ProfileSettingsModal, { type SettingsTab } from "@/components/ProfileSettingsModal";

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
  recent_events?: { id: number | string; type: string; title?: string; amount?: number; date?: string }[];
};

const SETTINGS_TABS: SettingsTab[] = ["account", "sources", "training", "privacy", "danger"];

function readSettingsTab(): SettingsTab | null {
  if (typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("settings");
  return SETTINGS_TABS.includes(value as SettingsTab) ? value as SettingsTab : null;
}

export default function Profile() {
  const [userData, setUserData] = useState<ProfileData | null>(null);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | null>(null);
  const router = useRouter();

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) setUserData(cached);
    const unsubscribe = subscribeUser(setUserData);
    void refreshUser(true);

    const syncSettingsFromUrl = () => setSettingsTab(readSettingsTab());
    syncSettingsFromUrl();
    window.addEventListener("popstate", syncSettingsFromUrl);
    return () => {
      unsubscribe();
      window.removeEventListener("popstate", syncSettingsFromUrl);
    };
  }, []);

  const updateSettingsUrl = (tab: SettingsTab | null, historyMode: "push" | "replace" = "replace") => {
    const url = new URL(window.location.href);
    if (tab) url.searchParams.set("settings", tab);
    else url.searchParams.delete("settings");
    const target = url.pathname + url.search + url.hash;
    if (historyMode === "push") window.history.pushState(window.history.state, "", target);
    else window.history.replaceState(window.history.state, "", target);
    setSettingsTab(tab);
  };

  const openSettings = () => updateSettingsUrl("account", "push");
  const closeSettings = () => updateSettingsUrl(null);
  const selectSettingsTab = (tab: SettingsTab) => updateSettingsUrl(tab);

  const handleLogout = async () => {
    await logout();
    clearUserCache();
    router.push("/");
  };

  const user = userData?.user;
  const season = userData?.season_stats;
  const achievements = (userData?.recent_events ?? [])
    .filter((event) => event.type === "achievement")
    .slice(0, 3);

  return (
    <main className="relative min-h-[calc(100dvh-72px)] overflow-hidden bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-3 pb-28 pt-4 text-[#111] sm:px-5 sm:pt-6 md:min-h-[calc(100dvh-88px)] md:px-8 md:pb-10">
      <div aria-hidden="true" className="pointer-events-none absolute left-[8%] top-[12%] h-3 w-3 animate-pulse rounded-full bg-[#ffd500]" />
      <div aria-hidden="true" className="pointer-events-none absolute right-[10%] top-[26%] h-2 w-2 rounded-full bg-white/80" />
      <div aria-hidden="true" className="pointer-events-none absolute bottom-[18%] right-[15%] h-4 w-4 animate-pulse rounded-full bg-white/70" />

      <div className="relative mx-auto w-full max-w-5xl border-2 border-black bg-[#f4f4f0] shadow-[8px_8px_0_rgba(0,0,0,0.3)]">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-black bg-[#171a38] px-4 py-5 text-white sm:px-6 md:px-8">
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
        </header>

        <section className="grid gap-0 border-b-2 border-black md:grid-cols-[minmax(0,1fr)_250px]">
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
        </section>

        <section className="border-b-2 border-black">
          <div className="flex items-end justify-between gap-3 border-b-2 border-black px-4 py-3 sm:px-6">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Season Stats</p>
              <h3 className="font-display text-xl uppercase sm:text-2xl">Статистика сезона</h3>
            </div>
            <span className="pb-1 text-right text-[10px] font-bold uppercase tracking-wide text-[#666]">
              С {season?.season_start ?? "текущего сезона"}
            </span>
          </div>
          <div className="grid grid-cols-2 divide-x-2 divide-y-2 divide-black sm:grid-cols-3 sm:divide-y-0 lg:grid-cols-5">
            {[
              { label: "Дистанция", value: String(season?.total_km ?? 0), unit: "км" },
              { label: "Время", value: String(season?.total_hours ?? 0), unit: "ч" },
              { label: "Набор", value: String(season?.total_elevation ?? 0), unit: "м" },
              { label: "Тренировки", value: String(season?.total_workouts ?? 0), unit: "" },
              { label: "XP за сезон", value: String(Math.round(season?.total_xp ?? 0)), unit: "" },
            ].map((item) => (
              <div key={item.label} className="min-w-0 px-3 py-4 text-center sm:p-4">
                <p className="font-display text-2xl sm:text-3xl">
                  {item.value}<span className="ml-1 text-xs text-[#666]">{item.unit}</span>
                </p>
                <p className="mt-1 text-[9px] font-bold uppercase tracking-widest text-[#666] sm:text-[10px]">{item.label}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
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
        </section>
      </div>

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
