"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCachedUser, subscribeUser, refreshUser } from "@/lib/apiCache";
import { authApi, isAuthenticated } from "@/lib/auth";
import { Star, Sticker } from "@/components/DreamBits";
import { Modal, PauseDialog } from "@/components/Modal";
import ActivityUpload from "@/components/ActivityUpload";
import { getApiErrorMessage, parsePauseDate, parsePauseWeeks } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Label, SectionTitle, Skeleton } from "@/components/ui";
import WeekBlock from "@/components/dashboard/WeekBlock";
import EventsFeed from "@/components/dashboard/EventsFeed";
import QuestsBoard from "@/components/dashboard/QuestsBoard";

type DuelSummary = {
  id: number;
  week_start: string | null;
  status: string;
  other: { username: string; display_name: string } | null;
  my_xp: number | null;
  other_xp: number | null;
};

export default function Dashboard() {
  const router = useRouter();
  const [userData, setUserData] = useState<any>(null);
  const [weekData, setWeekData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [weekOptions, setWeekOptions] = useState<{ week_start: string; label: string }[]>([]);
  const [selectedWeekStart, setSelectedWeekStart] = useState("");
  const [quests, setQuests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAuthed, setIsAuthed] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [weekLoading, setWeekLoading] = useState(true);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseNow, setPauseNow] = useState(0);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [pauseError, setPauseError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [syncError, setSyncError] = useState("");
  const [nextDuel, setNextDuel] = useState<DuelSummary | null>(null);
  const [duelLoading, setDuelLoading] = useState(true);
  const [duelError, setDuelError] = useState("");

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) {
      setUserData(cached);
      setWeekData(cached.week || null);
      setEvents(cached.recent_events || []);
      setQuests(cached.quests || []);
    }
    const unsubscribe = subscribeUser((user) => {
      setUserData(user);
      setQuests(user?.quests || []);
    });
    void refreshUser();
    setIsAuthed(isAuthenticated());
    setLoading(false);
    return unsubscribe;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setWeekLoading(true);
    setDashboardError("");
    authApi.get("/api/weekly-summary", {
      params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
      signal: controller.signal,
    }).then((response) => {
      const result = response.data;
      setWeekData(result.week || null);
      setEvents(result.events || []);
      setWeekOptions(result.week_options || []);
      if (!selectedWeekStart && result.week?.week_start) {
        setSelectedWeekStart(result.week.week_start);
      }
    }).catch((error: unknown) => {
      const name = (error as { name?: string }).name;
      if (name !== "CanceledError" && name !== "AbortError") {
        setDashboardError(getApiErrorMessage(error, "Не удалось загрузить данные недели."));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setWeekLoading(false);
    });
    return () => controller.abort();
  }, [selectedWeekStart]);

  const loadNextDuel = useCallback(async () => {
    setDuelLoading(true);
    setDuelError("");
    try {
      const response = await authApi.get("/api/duels");
      const items = Array.isArray(response.data.items) ? response.data.items as DuelSummary[] : [];
      const candidates = items.filter((duel) => duel.status === "active" || duel.status === "pending");
      candidates.sort((a, b) => {
        const priority = (status: string) => status === "active" ? 0 : 1;
        return priority(a.status) - priority(b.status);
      });
      setNextDuel(candidates[0] ?? null);
    } catch (error: unknown) {
      setDuelError(getApiErrorMessage(error, "Не удалось загрузить ближайшую дуэль."));
    } finally {
      setDuelLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthed) {
      setDuelLoading(false);
      return;
    }
    void loadNextDuel();
  }, [isAuthed, loadNextDuel]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2]">
        <p className="animate-pulse font-display text-2xl uppercase text-white">Dreaming...</p>
      </div>
    );
  }

  const isEmpty = !userData || !userData.user;
  const data = userData ?? {
    user: { name: "athlete", level: 1, total_xp: 0, xp_to_next_level: 100 },
    recent_activities: [],
  };
  const stats = data.stats ?? { day_streak: 0, week_streak: 0, week_hours: 0, week_goal_hours: 10 };
  const goalHours = Math.max(1, Number(stats.week_goal_hours) || 10);
  const xpProgress = isEmpty ? 0 : Number(data.user.total_xp || 0) % 100;
  const weekOptionIndex = weekOptions.findIndex((option) =>
    option.week_start === (selectedWeekStart || weekData?.week_start)
  );
  const canGoPrevious = weekOptionIndex >= 0 && weekOptionIndex < weekOptions.length - 1;
  const canGoNext = weekOptionIndex > 0;

  const navigateWeek = (direction: "previous" | "next") => {
    const index = weekOptions.findIndex((option) =>
      option.week_start === (selectedWeekStart || weekData?.week_start)
    );
    const target = weekOptions[index + (direction === "previous" ? 1 : -1)];
    if (target) setSelectedWeekStart(target.week_start);
  };

  const openPause = () => {
    setPauseNow(Date.now());
    setPauseError("");
    setPauseDialogOpen(true);
  };

  const handlePauseSubmit = async (weeks: number) => {
    const validWeeks = parsePauseWeeks(weeks);
    if (validWeeks === null) {
      setPauseError("Выбери целое число недель от 0 до 8.");
      return;
    }
    const pauseEnd = parsePauseDate(typeof userData?.user?.paused_until === "string" ? userData.user.paused_until : null);
    const currentlyPaused = Boolean(pauseEnd && pauseEnd.getTime() > Date.now());
    if (validWeeks === 0 && !currentlyPaused) {
      setPauseError("Сейчас активной паузы нет.");
      return;
    }

    setPauseBusy(true);
    setPauseError("");
    try {
      await authApi.post("/api/pause", { weeks: validWeeks });
      await refreshUser(true);
      setWeekData((previous: any) => previous ? { ...previous, paused: validWeeks > 0 } : previous);
      setPauseDialogOpen(false);
    } catch (error: unknown) {
      setPauseError(getApiErrorMessage(error, "Не удалось обновить паузу. Проверь соединение и попробуй ещё раз."));
    } finally {
      setPauseBusy(false);
    }
  };

  const handleSync = async () => {
    setSyncMessage("");
    setSyncError("");
    if (!isAuthed) {
      router.push("/login");
      return;
    }
    if (!data.user?.has_intervals_key) {
      router.push("/training?tab=sources");
      return;
    }

    const now = new Date();
    const since = `${now.getFullYear()}-01-01`;
    setSyncing(true);
    try {
      const response = await authApi.post("/api/sync", null, { params: { since } });
      setSyncMessage(`Синхронизация завершена: новых ${response.data.synced_count ?? 0}, обновлено ${response.data.updated_count ?? 0}, +${Math.round(Number(response.data.new_xp) || 0)} XP.`);
      await refreshUser(true);
    } catch (error: unknown) {
      setSyncError(getApiErrorMessage(error, "Не удалось синхронизировать данные."));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <Star className="absolute left-[3%] top-[6%] h-6 w-6 animate-pulse text-white/80" />
      <Star className="absolute right-[6%] top-[16%] h-4 w-4 animate-pulse text-white/70" />
      <Star className="absolute bottom-[10%] left-[8%] h-5 w-5 animate-pulse text-[#ffd500]" />
      <Star className="absolute bottom-[5%] right-[4%] h-7 w-7 animate-pulse text-white/80" />

      <div className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        {(!isAuthed || isEmpty) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="relative space-y-4 border-b-2 border-black bg-white p-6 text-center md:p-10"
          >
            <Sticker className="left-6 top-3 rotate-[3deg] bg-[#ffd500] text-black">zzz…</Sticker>
            {isAuthed ? (
              <>
                <p className="font-display text-4xl uppercase md:text-6xl">Добро пожаловать.</p>
                <Label className="text-[#666]">Уровень 1 · 0 XP · 0 тренировок</Label>
                <p className="mx-auto max-w-md text-sm text-[#666]">Синхронизируй первую тренировку — и прогресс появится здесь.</p>
                <Link href="/training?tab=sources" className="inline-block bg-[#ff4b26] px-6 py-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-[#5866f2]">Подключить источник →</Link>
              </>
            ) : (
              <>
                <p className="font-display text-4xl uppercase md:text-6xl">Твоя следующая глава.</p>
                <Label className="text-[#666]">Войди, чтобы видеть свой прогресс</Label>
                <p className="mx-auto max-w-md text-sm text-[#666]">Войди или зарегистрируйся, чтобы отслеживать уровень, тренировки, квесты и дуэли.</p>
                <Link href="/login" className="inline-block bg-[#ff4b26] px-6 py-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-[#5866f2]">Войти →</Link>
              </>
            )}
          </motion.div>
        )}

        <header className="relative grid border-b-2 border-black md:grid-cols-[1fr_auto]">
          <Sticker className="right-4 top-2 rotate-[-4deg] bg-[#f6b8d0] text-black md:right-10">don't stop fighting</Sticker>
          <div className="flex flex-col gap-3 p-5 md:border-r-2 md:border-black md:p-8">
            <Label className="text-[#666]">ТВОЙ ПРОГРЕСС · SEASON 001</Label>
            <h1 className="font-display text-4xl uppercase leading-[0.9] md:text-6xl lg:text-7xl">
              Привет, <span className="text-[#ff4b26]">{data.user.name}</span>.
            </h1>
          </div>
          <Link href="/profile" className="flex items-center justify-between gap-4 bg-[#5866f2] px-5 py-4 text-[11px] font-bold uppercase tracking-widest text-white transition-colors hover:bg-black">
            <span>Профиль<br />атлета</span><span>→</span>
          </Link>
        </header>

        {dashboardError && <ErrorState message={dashboardError} onRetry={() => window.location.reload()} />}

        <section className="grid border-b-2 border-black md:grid-cols-3">
          <div className="md:border-r-2 md:border-black">
            <SectionTitle>Level</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">{data.user.level}</p>
              <div className="mt-4 h-3 w-full border border-black/20 bg-black/10">
                <div className="h-full bg-[#ffd500] transition-all" style={{ width: `${xpProgress}%` }} />
              </div>
              <Label className="mt-3 text-[#666]">{isEmpty ? "100 XP до следующего" : `${Math.round(Number(data.user.xp_to_next_level) || 0)} XP до следующего уровня`}</Label>
            </div>
          </div>
          <div className="border-t-2 border-black md:border-r-2 md:border-t-0">
            <SectionTitle tone="yellow">Streak</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl text-[#ff4b26] md:text-7xl">{stats.day_streak}</p>
              <Label className="mt-2 text-[#666]">Дней подряд</Label>
              <div className="mt-4 border-t border-black/20 pt-3"><Label className="text-[#666]">{stats.week_streak} недель подряд</Label></div>
            </div>
          </div>
          <div className="border-t-2 border-black md:border-t-0">
            <SectionTitle>Week goal</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">{stats.week_hours}<span className="text-xl text-[#666] md:text-2xl"> / {stats.week_goal_hours}h</span></p>
              <div className="mt-4 h-3 w-full border border-black/20 bg-black/10">
                <div className="h-full bg-[#5866f2] transition-all" style={{ width: `${Math.min(100, (Number(stats.week_hours) || 0) / goalHours * 100)}%` }} />
              </div>
              <Label className="mt-3 text-[#666]">{Math.min(100, Math.round((Number(stats.week_hours) || 0) / goalHours * 100))}% цели</Label>
            </div>
          </div>
        </section>

        {isAuthed && !isEmpty && (
          <>
            {weekLoading ? (
              <section className="border-b-2 border-black bg-white p-5 md:p-6"><Skeleton label="Загружаем недельную сводку" rows={4} /></section>
            ) : (
              <WeekBlock
                weekData={weekData}
                weekOptions={weekOptions}
                selectedWeekStart={selectedWeekStart || weekData?.week_start || ""}
                onWeekChange={setSelectedWeekStart}
                onPreviousWeek={() => navigateWeek("previous")}
                onNextWeek={() => navigateWeek("next")}
                canGoPrevious={canGoPrevious}
                canGoNext={canGoNext}
                onPauseClick={openPause}
              />
            )}

            <EventsFeed events={events} />
            <QuestsBoard quests={quests} />

            <section className="border-b-2 border-black bg-white">
              <SectionTitle tone="indigo">Ближайшая дуэль</SectionTitle>
              <div className="p-4 md:p-6">
                {duelLoading ? (
                  <Skeleton label="Загружаем дуэль" rows={2} />
                ) : duelError ? (
                  <ErrorState message={duelError} onRetry={() => void loadNextDuel()} />
                ) : nextDuel ? (
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-display text-2xl uppercase">vs {nextDuel.other?.display_name ?? "Соперник"}</p>
                      <Label className="mt-1 text-[#666]">{nextDuel.status === "active" ? "Идёт сейчас" : "Ожидает ответа"} · неделя {nextDuel.week_start || "—"}</Label>
                    </div>
                    {nextDuel.status === "active" && <p className="font-display text-2xl">{nextDuel.my_xp ?? 0} : {nextDuel.other_xp ?? 0} XP</p>}
                    <Link href="/compete?tab=duels" className="border-2 border-black bg-[#ffd500] px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-black hover:text-white">Открыть дуэль →</Link>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <EmptyState>Пока нет ближайших дуэлей. Вызови друга и проверь прогресс недели.</EmptyState>
                    <Link href="/compete?tab=duels" className="border-2 border-black px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-[#ffd500]">Дуэли →</Link>
                  </div>
                )}
              </div>
            </section>
          </>
        )}

        <section className="border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
          <h2 className="font-display text-xl uppercase">Быстрые действия</h2>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <button type="button" onClick={() => void handleSync()} disabled={syncing} className="border-2 border-black bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-black disabled:opacity-50">
              {syncing ? "Синхронизация…" : "Синхронизировать"}
            </button>
            <button type="button" onClick={() => setUploadOpen(true)} className="border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-bold uppercase tracking-widest transition-colors hover:bg-black hover:text-white">Загрузить тренировку</button>
            <button type="button" onClick={openPause} disabled={!isAuthed} className="border-2 border-black bg-white px-4 py-3 text-xs font-bold uppercase tracking-widest transition-colors hover:bg-[#ff4b26] hover:text-white disabled:opacity-50">Пауза</button>
          </div>
          {syncMessage && <p role="status" className="mt-3 border-2 border-[#16803c] bg-white px-3 py-2 text-sm font-bold text-[#16803c]">{syncMessage}</p>}
          {syncError && <ErrorState message={syncError} onRetry={() => void handleSync()} />}
        </section>
      </div>

      <AnimatePresence>
        {pauseDialogOpen && (
          <PauseDialog
            onClose={() => setPauseDialogOpen(false)}
            onSubmit={handlePauseSubmit}
            busy={pauseBusy}
            error={pauseError}
            now={pauseNow}
            pauseSetAt={userData?.user?.pause_set_at ?? null}
            pausedUntil={userData?.user?.paused_until ?? null}
          />
        )}
        {uploadOpen && (
          <Modal title="Загрузить тренировку" onClose={() => setUploadOpen(false)}>
            <ActivityUpload />
          </Modal>
        )}
      </AnimatePresence>
    </main>
  );
}
