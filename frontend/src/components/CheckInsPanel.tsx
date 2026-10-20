"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authApi } from "@/lib/auth";
import { Modal } from "@/components/Modal";

type MorningAnswers = {
  readiness: number | null;
  fatigue: number | null;
  soreness: number | null;
  wellbeing: number | null;
};
type MorningCheckIn = MorningAnswers & {
  id: number;
  local_date: string;
  status: "pending" | "completed" | "skipped";
  prompted_at: string;
  skip_warning_at: string | null;
};
type Activity = {
  id: number;
  name?: string;
  sport?: string;
  distance_km?: number;
  moving_time_min?: number;
  date?: string;
  checkin: ActivityCheckIn | null;
};
type ActivityCheckIn = {
  activity_id: number;
  rpe: number;
  load_expectation: "easier" | "as_expected" | "harder" | null;
  discomfort: "none" | "mild" | "significant" | null;
  updated_at?: string | null;
};
type ActivityAnswers = {
  rpe: string;
  expectation: string;
  discomfort: string;
};
type SleepData = { source: string; sleep_secs: number | null; sleep_score: number | null } | null;

const emptyAnswers: MorningAnswers = {
  readiness: null,
  fatigue: null,
  soreness: null,
  wellbeing: null,
};

function ScaleButtons({
  title,
  lowLabel,
  highLabel,
  value,
  onChange,
}: {
  title: string;
  lowLabel: string;
  highLabel: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <fieldset className="border-t border-black/15 py-3">
      <legend className="text-sm font-bold">{title}</legend>
      <div className="mt-2 grid grid-cols-5 gap-2">
        {[1, 2, 3, 4, 5].map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            onClick={() => onChange(option)}
            className={"min-h-10 border-2 border-black font-display text-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] motion-reduce:transition-none " +
              (value === option ? "bg-[#ffd500]" : "bg-white hover:bg-black/5")}
          >
            {option}
          </button>
        ))}
      </div>
      <div className="mt-1 flex items-start justify-between gap-3 text-[10px] text-[#666]">
        <span>{lowLabel}</span>
        <span className="text-right">{highLabel}</span>
      </div>
      <button
        type="button"
        onClick={() => onChange(null)}
        className="mt-1 text-[10px] font-bold underline decoration-dotted underline-offset-2 text-[#666] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5866f2]"
      >
        Не указывать
      </button>
    </fieldset>
  );
}

function importedSleepText(sleep: SleepData): string {
  if (!sleep) return "Автоматические данные сна из Intervals.icu за этот день недоступны. Пропуск данных не заменяется нулём.";
  const bits: string[] = [];
  if (typeof sleep.sleep_secs === "number") {
    const hours = Math.floor(sleep.sleep_secs / 3600);
    const minutes = Math.floor((sleep.sleep_secs % 3600) / 60);
    bits.push("сон " + hours + " ч " + minutes + " мин");
  }
  if (typeof sleep.sleep_score === "number") bits.push("Sleep Score " + Math.round(sleep.sleep_score));
  return bits.length > 0
    ? "Автоматически из " + sleep.source + ": " + bits.join(" · ") + "."
    : "Запись сна из Intervals.icu есть, но в ней нет длительности или Sleep Score.";
}

export default function CheckInsPanel() {
  const [morning, setMorning] = useState<MorningCheckIn | null>(null);
  const [sleep, setSleep] = useState<SleepData>(null);
  const [morningOpen, setMorningOpen] = useState(false);
  const [stage, setStage] = useState<"form" | "warning">("form");
  const [answers, setAnswers] = useState<MorningAnswers>(emptyAnswers);
  const [morningBusy, setMorningBusy] = useState(false);
  const [morningError, setMorningError] = useState("");
  const [activities, setActivities] = useState<Activity[]>([]);
  const [nextActivityOffset, setNextActivityOffset] = useState<number | null>(null);
  const [visibleActivityCount, setVisibleActivityCount] = useState(5);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [activitiesError, setActivitiesError] = useState("");
  const [editingActivityId, setEditingActivityId] = useState<number | null>(null);
  const [activityAnswers, setActivityAnswers] = useState<ActivityAnswers>({
    rpe: "",
    expectation: "",
    discomfort: "",
  });
  const [activityBusy, setActivityBusy] = useState(false);
  const [activityError, setActivityError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const [serverOffsetMs, setServerOffsetMs] = useState(0);

  const loadMorning = useCallback(async () => {
    setMorningError("");
    try {
      const response = await authApi.post("/api/check-ins/morning/prompt");
      const serverNow = Date.parse(String(response.data?.server_now ?? ""));
      if (Number.isFinite(serverNow)) setServerOffsetMs(serverNow - Date.now());
      const value = response.data?.checkin as MorningCheckIn;
      setMorning(value);
      setSleep((response.data?.sleep ?? null) as SleepData);
      setAnswers({
        readiness: value.readiness ?? null,
        fatigue: value.fatigue ?? null,
        soreness: value.soreness ?? null,
        wellbeing: value.wellbeing ?? null,
      });
      if (value.status === "pending") {
        setStage(value.skip_warning_at ? "warning" : "form");
        setMorningOpen(true);
      } else {
        setMorningOpen(false);
      }
    } catch {
      setMorningError("Не удалось загрузить состояние чек-ина. Проверь соединение и повтори запрос.");
    }
  }, []);

  useEffect(() => {
    void loadMorning();
  }, [loadMorning]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  const loadActivities = useCallback(async (offset = 0) => {
    setActivitiesLoading(true);
    setActivitiesError("");
    try {
      const response = await authApi.get("/api/check-ins/history/activities", {
        params: { offset, limit: 20 },
      });
      const rows = Array.isArray(response.data?.activities) ? response.data.activities as Activity[] : [];
      setActivities(rows);
      setNextActivityOffset(
        response.data?.next_offset === null || response.data?.next_offset === undefined
          ? null
          : Number(response.data.next_offset),
      );
      setVisibleActivityCount(5);
    } catch {
      setActivitiesError("Не удалось загрузить историю тренировок и чек-инов.");
    } finally {
      setActivitiesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadActivities();
  }, [loadActivities]);

  const promptedAt = morning?.prompted_at ? Date.parse(morning.prompted_at) : NaN;
  const effectiveNow = now + serverOffsetMs;
  const skipRemaining = Number.isFinite(promptedAt)
    ? Math.max(0, Math.ceil((promptedAt + 15000 - effectiveNow) / 1000))
    : 15;
  const warningAt = morning?.skip_warning_at ? Date.parse(morning.skip_warning_at) : NaN;
  const warningRemaining = Number.isFinite(warningAt)
    ? Math.max(0, Math.ceil((warningAt + 5000 - effectiveNow) / 1000))
    : 5;

  const updateAnswer = (key: keyof MorningAnswers, value: number | null) => {
    setAnswers((current) => ({ ...current, [key]: value }));
  };

  const openMorningForm = () => {
    setAnswers({
      readiness: morning?.readiness ?? null,
      fatigue: morning?.fatigue ?? null,
      soreness: morning?.soreness ?? null,
      wellbeing: morning?.wellbeing ?? null,
    });
    setStage("form");
    setMorningError("");
    setMorningOpen(true);
  };

  const closeMorning = () => {
    if (stage === "warning" && morning?.status === "pending" && morning.skip_warning_at) {
      void authApi.post("/api/check-ins/morning/skip-warning/cancel")
        .then((response) => {
          const serverNow = Date.parse(String(response.data?.server_now ?? ""));
          if (Number.isFinite(serverNow)) setServerOffsetMs(serverNow - Date.now());
          setMorning(response.data?.checkin ?? morning);
        })
        .catch(() => setMorningError("Не удалось отменить пропуск. Повтори запрос перед подтверждением."));
      setStage("form");
    }
    setMorningOpen(false);
  };

  const saveMorning = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (Object.values(answers).every((value) => value === null)) {
      setMorningError("Укажи хотя бы один известный показатель. Неизвестные значения можно оставить пустыми.");
      return;
    }
    setMorningBusy(true);
    setMorningError("");
    try {
      const response = await authApi.post("/api/check-ins/morning", answers);
      const serverNow = Date.parse(String(response.data?.server_now ?? ""));
      if (Number.isFinite(serverNow)) setServerOffsetMs(serverNow - Date.now());
      setMorning(response.data?.checkin ?? null);
      setSleep((response.data?.sleep ?? null) as SleepData);
      setMorningOpen(false);
    } catch {
      setMorningError("Не удалось сохранить чек-ин. Ответы не отмечены как сохранённые; попробуй ещё раз.");
    } finally {
      setMorningBusy(false);
    }
  };

  const beginSkip = async () => {
    setMorningBusy(true);
    setMorningError("");
    try {
      const response = await authApi.post("/api/check-ins/morning/skip-warning");
      const serverNow = Date.parse(String(response.data?.server_now ?? ""));
      if (Number.isFinite(serverNow)) setServerOffsetMs(serverNow - Date.now());
      const value = response.data?.checkin as MorningCheckIn;
      setMorning(value);
      setStage("warning");
    } catch {
      setMorningError("Пропуск пока недоступен. Дождись окончания таймера и повтори.");
    } finally {
      setMorningBusy(false);
    }
  };

  const confirmSkip = async () => {
    setMorningBusy(true);
    setMorningError("");
    try {
      const response = await authApi.post("/api/check-ins/morning/skip");
      const serverNow = Date.parse(String(response.data?.server_now ?? ""));
      if (Number.isFinite(serverNow)) setServerOffsetMs(serverNow - Date.now());
      setMorning(response.data?.checkin ?? null);
      setMorningOpen(false);
      setStage("form");
    } catch {
      setMorningError("Подтверждение ещё недоступно. Прочитай предупреждение до конца и повтори.");
    } finally {
      setMorningBusy(false);
    }
  };

  const startActivityEdit = (activity: Activity) => {
    const existing = activity.checkin;
    setEditingActivityId(activity.id);
    setActivityAnswers({
      rpe: existing ? String(existing.rpe) : "",
      expectation: existing?.load_expectation ?? "",
      discomfort: existing?.discomfort ?? "",
    });
    setActivityError("");
  };

  const saveActivity = async (event: FormEvent<HTMLFormElement>, activityId: number) => {
    event.preventDefault();
    if (!activityAnswers.rpe) {
      setActivityError("Оцени тяжесть тренировки по шкале RPE от 1 до 10.");
      return;
    }
    setActivityBusy(true);
    setActivityError("");
    try {
      const response = await authApi.post("/api/check-ins/activities/" + activityId, {
        rpe: Number(activityAnswers.rpe),
        load_expectation: activityAnswers.expectation || null,
        discomfort: activityAnswers.discomfort || null,
      });
      const saved = response.data?.checkin as ActivityCheckIn;
      setActivities((current) => current.map((activity) => activity.id === activityId ? { ...activity, checkin: saved } : activity));
      setEditingActivityId(null);
    } catch {
      setActivityError("Не удалось сохранить чек-ин тренировки. Проверь соединение и повтори.");
    } finally {
      setActivityBusy(false);
    }
  };

  const visibleActivities = activities.slice(0, visibleActivityCount);

  const loadMoreActivities = async () => {
    if (visibleActivityCount < activities.length) {
      setVisibleActivityCount(Math.min(activities.length, visibleActivityCount + 15));
      return;
    }
    if (nextActivityOffset === null || activitiesLoading) return;
    const offset = nextActivityOffset;
    setActivitiesLoading(true);
    setActivitiesError("");
    try {
      const response = await authApi.get("/api/check-ins/history/activities", {
        params: { offset, limit: 20 },
      });
      const rows = Array.isArray(response.data?.activities) ? response.data.activities as Activity[] : [];
      const currentIds = new Set(activities.map((activity) => activity.id));
      const fresh = rows.filter((activity) => !currentIds.has(activity.id));
      setActivities((current) => [...current, ...fresh]);
      setVisibleActivityCount((current) => current + fresh.length);
      setNextActivityOffset(
        response.data?.next_offset === null || response.data?.next_offset === undefined
          ? null
          : Number(response.data.next_offset),
      );
    } catch {
      setActivitiesError("Не удалось загрузить предыдущие тренировки. Попробуй ещё раз.");
    } finally {
      setActivitiesLoading(false);
    }
  };

  return (
    <section className="border-b-2 border-black bg-[#f4f4f0]" aria-labelledby="check-ins-title">
      <header className="border-b-2 border-black bg-[#5866f2] p-4 text-white md:p-5">
        <p className="text-[10px] font-black uppercase tracking-widest text-white/80">Самочувствие · приватные данные</p>
        <h2 id="check-ins-title" className="mt-1 font-display text-2xl uppercase md:text-3xl">Чек-ины</h2>
        <p className="mt-1 text-xs leading-relaxed text-white/90">Ответы видны только тебе и не влияют на XP, достижения или рейтинги.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2">
        <div className="border-b-2 border-black bg-white p-4 md:border-b-0 md:border-r-2 md:p-5">
          <h3 className="font-display text-xl uppercase">Утро</h3>
          {morning?.status === "completed" ? (
            <p className="mt-2 text-sm font-bold">Сегодня заполнено. Неизвестные показатели остались пустыми.</p>
          ) : morning?.status === "skipped" ? (
            <p className="mt-2 text-sm text-[#555]">Сегодня пропущено. Ответы не записывались, оценка самочувствия не подставлялась.</p>
          ) : (
            <p className="mt-2 text-sm text-[#555]">Короткая отметка готовности, усталости, мышечной болезненности и общего самочувствия.</p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-[#666]">{importedSleepText(sleep)}</p>
          {morningError && !morningOpen && <p role="alert" className="mt-2 text-xs font-bold text-[#b42318]">{morningError}</p>}
          {morningError && !morningOpen && (
            <button type="button" onClick={() => void loadMorning()} className="mt-2 border-2 border-black bg-white px-3 py-2 text-xs font-bold uppercase">Повторить запрос</button>
          )}
          <button
            type="button"
            onClick={openMorningForm}
            className="mt-4 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-black uppercase tracking-widest transition-colors hover:bg-black hover:text-white motion-reduce:transition-none"
          >
            {morning?.status === "completed" ? "Изменить чек-ин" : morning?.status === "skipped" ? "Заполнить сейчас" : "Заполнить чек-ин"}
          </button>
        </div>

        <div className="min-w-0 bg-white p-4 md:p-5">
          <h3 className="font-display text-xl uppercase">После тренировки</h3>
          <p className="mt-2 text-sm text-[#555]">Оцени субъективную тяжесть каждого занятия после его появления в EFL. Пропущенную запись можно добавить позже.</p>
          {activitiesError && <p role="alert" className="mt-2 text-xs font-bold text-[#b42318]">{activitiesError}</p>}
          {activitiesLoading && activities.length === 0 ? (
            <p role="status" className="mt-3 border-t border-black/15 pt-3 text-xs text-[#666]">Загружаем историю тренировок…</p>
          ) : visibleActivities.length === 0 ? (
            <p className="mt-3 border-t border-black/15 pt-3 text-xs text-[#666]">Тренировок пока нет. После синхронизации они появятся здесь.</p>
          ) : (
            <ul className="mt-3 divide-y divide-black/15 border-t border-black/15">
              {visibleActivities.map((activity) => {
                const existing = activity.checkin;
                const editing = editingActivityId === activity.id;
                return (
                  <li key={activity.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-bold">{activity.name || "Тренировка"}</p>
                        <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-[#666]">
                          {[activity.date, activity.sport, typeof activity.moving_time_min === "number" ? activity.moving_time_min + " мин" : null].filter(Boolean).join(" · ")}
                        </p>
                        {existing && <p className="mt-1 text-xs text-[#16803c]">RPE {existing.rpe}/10 · {existing.load_expectation === "harder" ? "тяжелее ожиданий" : existing.load_expectation === "easier" ? "легче ожиданий" : existing.load_expectation === "as_expected" ? "как ожидалось" : "без сравнения с ожиданиями"}</p>}
                      </div>
                      <button
                        type="button"
                        onClick={() => editing ? setEditingActivityId(null) : startActivityEdit(activity)}
                        className="shrink-0 border-2 border-black bg-white px-3 py-2 text-[10px] font-black uppercase transition-colors hover:bg-[#ffd500] motion-reduce:transition-none"
                      >
                        {editing ? "Закрыть" : existing ? "Изменить" : "Оценить"}
                      </button>
                    </div>
                    {editing && (
                      <form onSubmit={(event) => void saveActivity(event, activity.id)} className="mt-3 border-t border-black/15 pt-3">
                        <label className="block text-xs font-bold" htmlFor={"rpe-" + activity.id}>Тяжесть занятия · RPE</label>
                        <select
                          id={"rpe-" + activity.id}
                          value={activityAnswers.rpe}
                          onChange={(event) => setActivityAnswers((current) => ({ ...current, rpe: event.target.value }))}
                          required
                          className="mt-1 w-full border-2 border-black bg-white px-3 py-2 text-sm"
                        >
                          <option value="">Выбери RPE от 1 до 10</option>
                          {Array.from({ length: 10 }, (_, index) => index + 1).map((value) => (
                            <option key={value} value={String(value)}>{value} {value === 1 ? "· очень легко" : value === 10 ? "· максимально тяжело" : ""}</option>
                          ))}
                        </select>
                        <label className="mt-3 block text-xs font-bold" htmlFor={"expectation-" + activity.id}>Нагрузка относительно ожиданий</label>
                        <select
                          id={"expectation-" + activity.id}
                          value={activityAnswers.expectation}
                          onChange={(event) => setActivityAnswers((current) => ({ ...current, expectation: event.target.value }))}
                          className="mt-1 w-full border-2 border-black bg-white px-3 py-2 text-sm"
                        >
                          <option value="">Не указывать</option>
                          <option value="easier">Легче ожиданий</option>
                          <option value="as_expected">Как ожидалось</option>
                          <option value="harder">Тяжелее ожиданий</option>
                        </select>
                        <label className="mt-3 block text-xs font-bold" htmlFor={"discomfort-" + activity.id}>Заметный дискомфорт</label>
                        <select
                          id={"discomfort-" + activity.id}
                          value={activityAnswers.discomfort}
                          onChange={(event) => setActivityAnswers((current) => ({ ...current, discomfort: event.target.value }))}
                          className="mt-1 w-full border-2 border-black bg-white px-3 py-2 text-sm"
                        >
                          <option value="">Не указывать</option>
                          <option value="none">Нет</option>
                          <option value="mild">Небольшой</option>
                          <option value="significant">Выраженный</option>
                        </select>
                        {activityError && <p role="alert" className="mt-2 text-xs font-bold text-[#b42318]">{activityError}</p>}
                        <button type="submit" disabled={activityBusy} className="mt-3 w-full border-2 border-black bg-[#ffd500] px-3 py-3 text-xs font-black uppercase disabled:opacity-50">
                          {activityBusy ? "Сохраняем…" : "Сохранить чек-ин"}
                        </button>
                      </form>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {(visibleActivityCount < activities.length || nextActivityOffset !== null) && (
            <button
              type="button"
              onClick={() => void loadMoreActivities()}
              disabled={activitiesLoading}
              className="mt-3 w-full border-2 border-black bg-[#ffd500] px-3 py-3 text-xs font-black uppercase tracking-wide disabled:opacity-50 motion-reduce:transition-none"
            >
              {activitiesLoading
                ? "Загружаем…"
                : visibleActivityCount < activities.length
                  ? "Показать более ранние тренировки"
                  : "Загрузить предыдущие тренировки"}
            </button>
          )}
        </div>
      </div>

      {morningOpen && (
        <Modal title={stage === "warning" ? "Перед пропуском" : "Утренний чек-ин"} onClose={closeMorning} portalToBody>
          {stage === "form" ? (
            <form onSubmit={(event) => void saveMorning(event)} className="max-h-[78vh] overflow-y-auto p-4 sm:p-5">
              <p className="text-sm text-[#555]">Оцени только то, что действительно знаешь. Неизвестные показатели можно не указывать.</p>
              <ScaleButtons title="Готовность к тренировке" lowLabel="1 · совсем не готов" highLabel="5 · полностью готов" value={answers.readiness} onChange={(value) => updateAnswer("readiness", value)} />
              <ScaleButtons title="Усталость" lowLabel="1 · нет усталости" highLabel="5 · очень сильная" value={answers.fatigue} onChange={(value) => updateAnswer("fatigue", value)} />
              <ScaleButtons title="Мышечная болезненность" lowLabel="1 · отсутствует" highLabel="5 · очень сильная" value={answers.soreness} onChange={(value) => updateAnswer("soreness", value)} />
              <ScaleButtons title="Общее самочувствие" lowLabel="1 · очень плохое" highLabel="5 · отличное" value={answers.wellbeing} onChange={(value) => updateAnswer("wellbeing", value)} />
              <p className="mt-3 border-t border-black/15 pt-3 text-xs leading-relaxed text-[#666]">{importedSleepText(sleep)}</p>
              {morningError && <p role="alert" className="mt-3 text-sm font-bold text-[#b42318]">{morningError}</p>}
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <button type="submit" disabled={morningBusy || Object.values(answers).every((value) => value === null)} className="min-h-11 flex-1 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-black uppercase tracking-wide disabled:opacity-50">
                  {morningBusy ? "Сохраняем…" : "Сохранить чек-ин"}
                </button>
                <button type="button" onClick={() => void beginSkip()} disabled={morningBusy || skipRemaining > 0 || morning?.status !== "pending"} className="min-h-11 border-2 border-black bg-white px-4 py-3 text-xs font-black uppercase tracking-wide disabled:opacity-50">
                  {skipRemaining > 0 ? "Пропуск через " + skipRemaining + " с" : "Пропустить"}
                </button>
              </div>
              {skipRemaining > 0 && <p aria-live="polite" className="mt-2 text-[10px] text-[#666]">Кнопка пропуска станет доступна через {skipRemaining} секунд. Заполнить чек-ин можно сразу.</p>}
            </form>
          ) : (
            <div className="p-4 sm:p-5">
              <h3 className="font-display text-xl uppercase">Без записи анализ будет менее полным</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#555]">Если пропустить чек-ин, за этот локальный день не будет субъективных оценок самочувствия. Это не считается плохим самочувствием и не подставляется вместо неизвестных значений.</p>
              <p aria-live="polite" className="mt-3 border-t border-black/15 pt-3 text-xs font-bold text-[#666]">
                {warningRemaining > 0 ? "Подтверждение пропуска доступно через " + warningRemaining + " с." : "Теперь можно подтвердить пропуск или вернуться к заполнению."}
              </p>
              {morningError && <p role="alert" className="mt-3 text-sm font-bold text-[#b42318]">{morningError}</p>}
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <button type="button" onClick={closeMorning} disabled={morningBusy} className="min-h-11 flex-1 border-2 border-black bg-white px-4 py-3 text-xs font-black uppercase">
                  Вернуться к заполнению
                </button>
                <button type="button" onClick={() => void confirmSkip()} disabled={morningBusy || warningRemaining > 0} className="min-h-11 flex-1 border-2 border-black bg-[#ff4b26] px-4 py-3 text-xs font-black uppercase text-white disabled:opacity-50">
                  {morningBusy ? "Сохраняем…" : warningRemaining > 0 ? "Подтвердить через " + warningRemaining + " с" : "Подтвердить пропуск"}
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </section>
  );
}
