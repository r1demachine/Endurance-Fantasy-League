"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCachedUser, refreshUser, subscribeUser } from "@/lib/apiCache";
import { authApi, isAuthenticated } from "@/lib/auth";
import { ErrorState, Skeleton } from "@/components/ui";
import { getApiErrorMessage } from "@/components/dialog-utils";
import DashboardTrainingSections from "@/components/dashboard/DashboardTrainingSections";

export default function TrainingPage() {
  const router = useRouter();
  const [userData, setUserData] = useState<any>(null);
  const [isAuthed, setIsAuthed] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [weekData, setWeekData] = useState<any>(null);
  const [weekOptions, setWeekOptions] = useState<{ week_start: string; label: string }[]>([]);
  const [weekActivities, setWeekActivities] = useState<any[]>([]);
  const [selectedWeekStart, setSelectedWeekStart] = useState("");
  const [weekLoading, setWeekLoading] = useState(true);
  const [weekError, setWeekError] = useState("");

  useEffect(() => {
    const queryTab = new URLSearchParams(window.location.search).get("tab");
    if (queryTab === "sources") {
      router.replace("/profile?settings=sources");
      return;
    }

    const authenticated = isAuthenticated();
    setIsAuthed(authenticated);
    setAuthReady(true);
    if (!authenticated) {
      router.replace("/login");
      return;
    }

    const cached = getCachedUser();
    if (cached) setUserData(cached);
    const unsubscribe = subscribeUser(setUserData);
    let active = true;
    void refreshUser(true).then((updated) => {
      if (active && updated) setUserData(updated);
    }).catch(() => {
      // The weekly request below shows its own retryable error.
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [router]);

  const loadWeek = useCallback(async (signal?: AbortSignal) => {
    setWeekLoading(true);
    setWeekError("");
    try {
      const response = await authApi.get("/api/weekly-summary", {
        params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
        ...(signal ? { signal } : {}),
      });
      if (signal?.aborted) return;
      const result = response.data;
      setWeekData(result.week || null);
      setWeekOptions(Array.isArray(result.week_options) ? result.week_options : []);
      setWeekActivities(Array.isArray(result.activities) ? result.activities : []);
      if (!selectedWeekStart && result.week?.week_start) {
        setSelectedWeekStart(result.week.week_start);
      }
    } catch (requestError: unknown) {
      if (!signal?.aborted) {
        setWeekError(getApiErrorMessage(requestError, "Не удалось загрузить тренировки. Попробуй ещё раз."));
      }
    } finally {
      if (!signal?.aborted) setWeekLoading(false);
    }
  }, [selectedWeekStart]);

  useEffect(() => {
    if (!isAuthed) return;
    const controller = new AbortController();
    void loadWeek(controller.signal);
    return () => controller.abort();
  }, [isAuthed, loadWeek]);

  if (!authReady || !isAuthed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2]">
        <p className="animate-pulse font-display text-2xl uppercase text-white">Загружаем тренировки…</p>
      </div>
    );
  }

  return (
    <main className="relative flex min-h-screen flex-col bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <div className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-black bg-[#171a38] px-4 py-5 text-white sm:px-6 md:px-8">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/65">Endurance Fantasy League</p>
            <h1 className="mt-1 font-display text-3xl uppercase leading-none sm:text-4xl">Тренировки<span className="text-[#ff4b26]">.</span></h1>
            <p className="mt-2 text-xs text-white/70">Тренировки по неделям, XP Dynamics и сезонная нагрузка.</p>
          </div>
          <Link href="/dashboard" className="border-2 border-white/80 bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest transition-colors hover:bg-white hover:text-[#171a38]">
            ← На главную
          </Link>
        </header>

        {weekError && <ErrorState message={weekError} onRetry={() => void loadWeek()} />}

        {!userData ? (
          <div className="p-5 md:p-8"><Skeleton label="Загружаем данные атлета" rows={4} /></div>
        ) : (
          <DashboardTrainingSections
            userData={userData}
            weekLoading={weekLoading}
            weekActivities={weekActivities}
            weekOptions={weekOptions}
            weekData={weekData}
            selectedWeekStart={selectedWeekStart}
            onWeekChange={setSelectedWeekStart}
          />
        )}
      </div>
    </main>
  );
}
