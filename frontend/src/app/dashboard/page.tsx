"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { sectionItemVariants, sectionStaggerVariants, useTransitionDirection } from "@/components/PageTransition";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearUserCache, getCachedUser, subscribeUser, refreshUser } from "@/lib/apiCache";
import { authApi, isAuthenticated, logout } from "@/lib/auth";
import { Star, Sticker } from "@/components/DreamBits";
import { Modal, PauseDialog } from "@/components/Modal";
import ActivityUpload from "@/components/ActivityUpload";
import { getApiErrorMessage, parsePauseDate, parsePauseWeeks } from "@/components/dialog-utils";
import { ErrorState, Label, Skeleton } from "@/components/ui";
import WeekBlock from "@/components/dashboard/WeekBlock";
import QuestsBoard from "@/components/dashboard/QuestsBoard";
import YearWeeksChart from "@/components/dashboard/YearWeeksChart";
import WeekCalendar from "@/components/dashboard/WeekCalendar";
import TodayCard from "@/components/dashboard/TodayCard";
import ProfileSettingsModal, { type SettingsTab } from "@/components/ProfileSettingsModal";
import { useSeason } from "@/lib/seasons";
import { PreviousWeekRecapBanner } from "@/components/dashboard/RecapCards";
import CheckInsPanel from "@/components/CheckInsPanel";

export default function Dashboard() {
  const router = useRouter();
  const season = useSeason();
  const transitionDirection = useTransitionDirection();
  const [userData, setUserData] = useState<any>(null);
  const [weekData, setWeekData] = useState<any>(null);
  const [weekOptions, setWeekOptions] = useState<{ week_start: string; label: string }[]>([]);
  const [todayData, setTodayData] = useState<any>(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [todayError, setTodayError] = useState("");
  const [selectedWeekStart, setSelectedWeekStart] = useState("");
  const [deepLinkActivityId, setDeepLinkActivityId] = useState<number | null>(null);
  const [quests, setQuests] = useState<any[]>([]);
  const [questsLoading, setQuestsLoading] = useState(true);
  const [questsError, setQuestsError] = useState("");
  const [loading, setLoading] = useState(true);
  const [isAuthed, setIsAuthed] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [weekLoading, setWeekLoading] = useState(true);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseNow, setPauseNow] = useState(0);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [pauseError, setPauseError] = useState("");
  const [deloadBusy, setDeloadBusy] = useState(false);
  const [deloadError, setDeloadError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [syncError, setSyncError] = useState("");
  const [newlySyncedActivityIds, setNewlySyncedActivityIds] = useState<number[]>([]);
  const [restDayBusy, setRestDayBusy] = useState(false);
  const [restDayMessage, setRestDayMessage] = useState("");
  const [restDayError, setRestDayError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const activityIdValue = params.get("activity_id");
    const activityId = Number(activityIdValue);
    if (activityIdValue && Number.isSafeInteger(activityId) && activityId > 0) {
      setDeepLinkActivityId(activityId);
    }
    const weekStart = params.get("week_start");
    if (weekStart && /^\d{4}-\d{2}-\d{2}$/.test(weekStart)) {
      setSelectedWeekStart(weekStart);
    }
  }, []);

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) {
      setUserData(cached);
      setWeekData(cached.week || null);
    }
    const unsubscribe = subscribeUser((user) => {
      setUserData(user);
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
      setWeekData(result.week ? { ...result.week, days: Array.isArray(result.days) ? result.days : [], week_bonuses: Array.isArray(result.week_bonuses) ? result.week_bonuses : [], is_current_week: Boolean(result.is_current_week), streak_rest_day: result.streak_rest_day } : null);
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

  const loadQuests = useCallback(async (weekStart = selectedWeekStart) => {
    setQuestsLoading(true);
    setQuests([]);
    setQuestsError("");
    try {
      const response = await authApi.get("/api/quests", {
        params: weekStart ? { week_start: weekStart } : {},
      });
      setQuests(Array.isArray(response.data) ? response.data : []);
    } catch (error: unknown) {
      setQuests([]);
      setQuestsError(getApiErrorMessage(error, "Не удалось загрузить достижения."));
    } finally {
      setQuestsLoading(false);
    }
  }, [selectedWeekStart]);

  const loadToday = useCallback(async () => {
    setTodayLoading(true);
    setTodayError("");
    try {
      const response = await authApi.get("/api/today");
      setTodayData(response.data);
    } catch (error: unknown) {
      setTodayError(getApiErrorMessage(error, "Не удалось загрузить данные за сегодня."));
    } finally {
      setTodayLoading(false);
    }
  }, []);

  const refreshDashboardAfterDataChange = useCallback(async () => {
    setWeekLoading(true);
    setDashboardError("");
    try {
      const response = await authApi.get("/api/weekly-summary", {
        params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
      });
      const result = response.data;
      setWeekData(result.week ? { ...result.week, days: Array.isArray(result.days) ? result.days : [], week_bonuses: Array.isArray(result.week_bonuses) ? result.week_bonuses : [], is_current_week: Boolean(result.is_current_week), streak_rest_day: result.streak_rest_day } : null);
      setWeekOptions(Array.isArray(result.week_options) ? result.week_options : []);
      if (!selectedWeekStart && result.week?.week_start) {
        setSelectedWeekStart(result.week.week_start);
      }
    } catch (error: unknown) {
      setDashboardError(getApiErrorMessage(error, "Не удалось обновить данные после изменения тренировок."));
    } finally {
      setWeekLoading(false);
    }
    await loadQuests();
    await loadToday();
  }, [selectedWeekStart, loadQuests, loadToday]);

  useEffect(() => {
    if (!isAuthed) {
      setQuestsLoading(false);
      setTodayLoading(false);
      return;
    }
    void loadQuests();
    void loadToday();
  }, [isAuthed, loadQuests, loadToday]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center ">
        <p className="animate-pulse font-display text-2xl uppercase text-white">Dreaming...</p>
      </div>
    );
  }

  const isEmpty = !userData || !userData.user;
  const data = userData ?? {
    user: { name: "athlete", level: 1, total_xp: 0, xp_to_next_level: 100 },
    recent_activities: [],
  };
  const currentLevelXp = isEmpty ? 0 : Math.floor(Number(data.user.total_xp || 0) % 100);
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

  const openSourceSettings = () => {
    if (!isAuthed) {
      router.push("/login");
      return;
    }
    setSettingsTab("sources");
  };

  const handleSettingsLogout = async () => {
    await logout();
    clearUserCache();
    setSettingsTab(null);
    router.push("/");
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
      await refreshDashboardAfterDataChange();
      setPauseDialogOpen(false);
    } catch (error: unknown) {
      setPauseError(getApiErrorMessage(error, "Не удалось обновить паузу. Проверь соединение и попробуй ещё раз."));
    } finally {
      setPauseBusy(false);
    }
  };

  const handleDeloadAction = async (enable: boolean) => {
    setDeloadBusy(true);
    setDeloadError("");
    try {
      await authApi.post("/api/deload", { enable });
      await refreshUser(true);
      await refreshDashboardAfterDataChange();
    } catch (error: unknown) {
      setDeloadError(getApiErrorMessage(error, "Не удалось обновить Deload. Проверь условия недели и попробуй ещё раз."));
      try {
        const response = await authApi.get("/api/weekly-summary", {
          params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
        });
        setWeekData(response.data.week ? { ...response.data.week, days: Array.isArray(response.data.days) ? response.data.days : [], week_bonuses: Array.isArray(response.data.week_bonuses) ? response.data.week_bonuses : [], is_current_week: Boolean(response.data.is_current_week), streak_rest_day: response.data.streak_rest_day } : null);
      } catch {
        // Keep the latest usable week snapshot if the refresh also fails.
      }
    } finally {
      setDeloadBusy(false);
    }
  };

  const handleUseRestDay = async () => {
    setRestDayBusy(true);
    setRestDayMessage("");
    setRestDayError("");
    try {
      const response = await authApi.post("/api/streak/rest-day");
      setRestDayMessage(String(response.data?.message || "День отдыха использован. Серия сохранена."));
      await refreshUser(true);
      await refreshDashboardAfterDataChange();
    } catch (error: unknown) {
      setRestDayError(getApiErrorMessage(error, "Не удалось сохранить день отдыха."));
      try {
        const response = await authApi.get("/api/weekly-summary", {
          params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
        });
        setWeekData(response.data.week ? { ...response.data.week, days: Array.isArray(response.data.days) ? response.data.days : [], week_bonuses: Array.isArray(response.data.week_bonuses) ? response.data.week_bonuses : [], is_current_week: Boolean(response.data.is_current_week), streak_rest_day: response.data.streak_rest_day } : null);
      } catch {
        // Keep the latest usable calendar if a status refresh also fails.
      }
    } finally {
      setRestDayBusy(false);
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
      setSettingsTab("sources");
      return;
    }

    const sinceDate = new Date();
    sinceDate.setHours(12, 0, 0, 0);
    sinceDate.setDate(sinceDate.getDate() - 13);
    const since = `${sinceDate.getFullYear()}-${String(sinceDate.getMonth() + 1).padStart(2, "0")}-${String(sinceDate.getDate()).padStart(2, "0")}`;
    setSyncing(true);
    setNewlySyncedActivityIds([]);
    try {
      const knownActivityIds = new Set<number>();
      try {
        const before = await authApi.get("/api/check-ins/history/activities", { params: { offset: 0, limit: 20 } });
        const rows = Array.isArray(before.data?.activities) ? before.data.activities : [];
        for (const row of rows) {
          const id = Number(row?.id);
          if (Number.isSafeInteger(id) && id > 0) knownActivityIds.add(id);
        }
      } catch {
        // Sync must remain available even if the optional pre-sync history check fails.
      }

      const response = await authApi.post("/api/sync", null, { params: { since } });
      try {
        const after = await authApi.get("/api/check-ins/history/activities", { params: { offset: 0, limit: 20 } });
        const rows = Array.isArray(after.data?.activities) ? after.data.activities : [];
        const newIds = rows
          .map((row: { id?: number | string }) => Number(row?.id))
          .filter((id: number) => Number.isSafeInteger(id) && id > 0 && !knownActivityIds.has(id));
        setNewlySyncedActivityIds(newIds);
      } catch {
        // The sync succeeds even if the optional follow-up check-in list refresh fails.
      }
      setSyncMessage(`Синхронизация завершена: новых ${response.data.synced_count ?? 0}, обновлено ${response.data.updated_count ?? 0}, +${Math.round(Number(response.data.new_xp) || 0)} XP.`);
      await refreshUser(true);
      await refreshDashboardAfterDataChange();
    } catch (error: unknown) {
      setSyncError(getApiErrorMessage(error, "Не удалось синхронизировать данные."));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <Star className="absolute left-[3%] top-[6%] h-6 w-6 animate-pulse text-white/80" />
      <Star className="absolute right-[6%] top-[16%] h-4 w-4 animate-pulse text-white/70" />
      <Star className="absolute bottom-[10%] left-[8%] h-5 w-5 animate-pulse text-[#ffd500]" />
      <Star className="absolute bottom-[5%] right-[4%] h-7 w-7 animate-pulse text-white/80" />

      <motion.div variants={sectionStaggerVariants} className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        {(!isAuthed || isEmpty) && (
          <motion.div
            variants={sectionItemVariants} custom={transitionDirection}
            className="relative space-y-4 border-b-2 border-black bg-white p-6 text-center md:p-10"
          >
            <Sticker className="left-6 top-3 rotate-[3deg] bg-[#ffd500] text-black">zzz…</Sticker>
            {isAuthed ? (
              <>
                <p className="font-display text-4xl uppercase md:text-6xl">Добро пожаловать.</p>
                <Label className="text-[#666]">Уровень 1 · 0 XP · 0 тренировок</Label>
                <p className="mx-auto max-w-md text-sm text-[#666]">Синхронизируй первую тренировку — и прогресс появится здесь.</p>
                <button
                  type="button"
                  onClick={openSourceSettings}
                  className="inline-block bg-[#ff4b26] px-6 py-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:bg-[#5866f2]"
                >
                  Подключить источник →
                </button>
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

        <motion.header variants={sectionItemVariants} custom={transitionDirection} className="relative grid border-b-2 border-black md:grid-cols-[1fr_auto]">
          <Sticker className="right-4 top-2 rotate-[-4deg] bg-[#f6b8d0] text-black md:right-10">не останавливайся на достигнутом</Sticker>
          <div className="flex flex-col gap-3 p-5 md:border-r-2 md:border-black md:p-8">
            <Label className="text-[#666]">ТВОЙ ПРОГРЕСС · SEASON {String(season.num).padStart(3, "0")}</Label>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <h1 className="font-display text-4xl uppercase leading-[0.9] md:text-6xl lg:text-7xl">
                Привет, <span className="text-[#ff4b26]">{data.user.name}</span>.
              </h1>
              {isAuthed && !isEmpty && (
                <span data-tour="dashboard-level" className="inline-flex shrink-0 items-center border-2 border-black bg-[#ffd500] px-3 py-2 font-display text-sm uppercase md:text-base">
                  Ур. {data.user.level} · {currentLevelXp}/100 XP
                </span>
              )}
            </div>
          </div>
          <Link href="/profile" className="flex items-center justify-between gap-4 bg-[#5866f2] px-5 py-4 text-[11px] font-bold uppercase tracking-widest text-white transition-colors hover:bg-black">
            <span>Профиль<br />атлета</span><span>→</span>
          </Link>
        </motion.header>

        {isAuthed && !isEmpty && <motion.div variants={sectionItemVariants} custom={transitionDirection}><PreviousWeekRecapBanner userName={typeof data.user?.name === "string" ? data.user.name : undefined} /></motion.div>}

        {dashboardError && <motion.div variants={sectionItemVariants} custom={transitionDirection}><ErrorState message={dashboardError} onRetry={() => window.location.reload()} /></motion.div>}

        {isAuthed && !isEmpty && (
          <motion.section
            variants={sectionItemVariants}
            custom={transitionDirection}
            aria-label="Сегодня и чек-ины"
            className="grid min-w-0 border-b-2 border-black bg-white xl:grid-cols-2 xl:items-start"
          >
            <div className="min-w-0 xl:border-r-2 xl:border-black">
              <TodayCard
                data={todayData}
                loading={todayLoading}
                error={todayError}
                onRetry={() => void loadToday()}
                onOpenSources={openSourceSettings}
                level={Number(data.user?.level) || 1}
                totalXp={Number(data.user?.total_xp) || 0}
              />
            </div>
            <div className="min-w-0">
              <CheckInsPanel key={Array.isArray(data.recent_activities) ? data.recent_activities.map((activity: { id: number }) => activity.id).join(",") : "none"}
                autoPromptActivityIds={newlySyncedActivityIds}
              />
            </div>
          </motion.section>
        )}

        {isAuthed && !isEmpty && (
          <>
            <motion.div data-tour="dashboard-year-chart" variants={sectionItemVariants} custom={transitionDirection}>
            <YearWeeksChart
              selectedWeekStart={selectedWeekStart || weekData?.week_start || ""}
              onWeekChange={setSelectedWeekStart}
            />
            </motion.div>

            <motion.div data-tour="dashboard-week-summary" variants={sectionItemVariants} custom={transitionDirection}>
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
                onDeloadAction={handleDeloadAction}
                deloadBusy={deloadBusy}
                deloadError={deloadError}
                userName={typeof data.user?.name === "string" ? data.user.name : undefined}
              />
            )}
            </motion.div>

            <motion.div data-tour="dashboard-achievements" variants={sectionItemVariants} custom={transitionDirection}>
            <QuestsBoard
              quests={quests}
              loading={questsLoading}
              error={questsError}
              onRetry={() => void loadQuests()}
            />
            </motion.div>
            <motion.div data-tour="dashboard-workouts" variants={sectionItemVariants} custom={transitionDirection}>
            <WeekCalendar
              weekLoading={weekLoading}
              weekData={weekData}
              weekOptions={weekOptions}
              selectedWeekStart={selectedWeekStart || weekData?.week_start || ""}
              onWeekChange={setSelectedWeekStart}
              onOpenSources={openSourceSettings}
              initialActivityId={deepLinkActivityId}
              userName={typeof data.user?.name === "string" ? data.user.name : undefined}
              restDayState={weekData?.streak_rest_day}
              restDayBusy={restDayBusy}
              restDayMessage={restDayMessage}
              restDayError={restDayError}
              onUseRestDay={() => void handleUseRestDay()}
            />
            </motion.div>
          </>
        )}

        <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
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
        </motion.section>
      </motion.div>

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
            <ActivityUpload onUploaded={refreshDashboardAfterDataChange} />
          </Modal>
        )}
      </AnimatePresence>

      {settingsTab && (
        <ProfileSettingsModal
          tab={settingsTab}
          userData={userData ?? data}
          onClose={() => { setSettingsTab(null); void loadToday(); }}
          onTabChange={setSettingsTab}
          onLogout={handleSettingsLogout}
          onActivityUploaded={refreshDashboardAfterDataChange}
        />
      )}
    </main>
  );
}
