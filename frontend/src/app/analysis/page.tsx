"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import AuthGuard from "@/components/AuthGuard";
import { authApi } from "@/lib/auth";
import { sectionItemVariants, sectionStaggerVariants, useTransitionDirection } from "@/components/PageTransition";

type DailyStats = {
  mean: number | null;
  days_with_data: number;
  samples: number;
};

type TrendMetric = {
  key: string;
  label: string;
  source: string;
  unit: string;
  status: "ready" | "insufficient_data" | string;
  trend: "upward" | "downward" | "stable" | "insufficient_data" | string;
  current: DailyStats;
  previous: DailyStats;
  change: number | null;
  minimum_days_required_per_period: number;
};

type TrendsResponse = {
  status: "ready" | "insufficient_data" | string;
  timezone: string;
  period: { start: string; end: string; days: number };
  comparison_windows: {
    current: { start: string; end: string; days: number };
    previous: { start: string; end: string; days: number };
  };
  observations: TrendMetric[];
  training_load_relationship: {
    status: string;
    paired_days?: number;
    median_daily_tss?: number | null;
    lower_or_equal_load?: { days: number; mean_daily_rpe: number | null };
    above_median_load?: { days: number; mean_daily_rpe: number | null };
    rpe_difference_high_minus_low?: number | null;
    reason?: string;
    limitations?: string[];
  };
  coverage: {
    morning_checkins?: {
      period_days?: number;
      completed_days?: number;
      skipped_days?: number;
      pending_days?: number;
      days_without_completed_checkin?: number;
      no_record_days?: number;
    };
    sleep?: {
      days_with_wellness_record?: number;
      days_with_quality_value?: number;
      days_with_duration_value?: number;
    };
    activities?: {
      activities_in_period?: number;
      activities_with_measured_tss?: number;
      activities_with_estimated_tss?: number;
      activities_without_tss?: number;
      activities_with_rpe?: number;
      activities_without_rpe?: number;
      days_with_activities?: number;
    };
  };
  data_gaps: string[];
  methodology: string[];
  disclaimer: string;
};

type Interpretation = {
  headline: string;
  summary: string;
  positive_signals: string[];
  caution_signals: string[];
  practical_next_steps: string[];
  data_limitations: string[];
};

type InterpretationResponse = {
  status: string;
  provider?: string;
  model?: string;
  generated_at?: string;
  period?: { start: string; end: string; days: number };
  analysis?: Interpretation | null;
  data_gaps?: string[];
  data_quality?: { data_gaps?: string[] };
  message?: string;
  disclaimer?: string;
};

const DAY_OPTIONS = [
  { value: 14, label: "14 дней" },
  { value: 28, label: "28 дней" },
  { value: 56, label: "56 дней" },
  { value: 90, label: "90 дней" },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isDailyStats(value: unknown): value is DailyStats {
  return isRecord(value)
    && (value.mean === null || (typeof value.mean === "number" && Number.isFinite(value.mean)))
    && typeof value.days_with_data === "number"
    && Number.isInteger(value.days_with_data)
    && value.days_with_data >= 0
    && typeof value.samples === "number"
    && Number.isInteger(value.samples)
    && value.samples >= 0;
}

function isTrendMetric(value: unknown): value is TrendMetric {
  return isRecord(value)
    && typeof value.key === "string"
    && typeof value.label === "string"
    && typeof value.source === "string"
    && typeof value.unit === "string"
    && typeof value.status === "string"
    && typeof value.trend === "string"
    && isDailyStats(value.current)
    && isDailyStats(value.previous)
    && (value.change === null || (typeof value.change === "number" && Number.isFinite(value.change)))
    && typeof value.minimum_days_required_per_period === "number";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isTrendResponse(value: unknown): value is TrendsResponse {
  if (!isRecord(value)) return false;
  const period = value.period;
  const windows = value.comparison_windows;
  const current = isRecord(windows) ? windows.current : null;
  const previous = isRecord(windows) ? windows.previous : null;
  const observations = value.observations;
  return typeof value.status === "string"
    && isRecord(period)
    && typeof period.start === "string"
    && typeof period.end === "string"
    && typeof period.days === "number"
    && isRecord(current)
    && typeof current.start === "string"
    && typeof current.end === "string"
    && isRecord(previous)
    && typeof previous.start === "string"
    && typeof previous.end === "string"
    && Array.isArray(observations)
    && observations.every(isTrendMetric)
    && isRecord(value.coverage)
    && isRecord(value.training_load_relationship)
    && isStringArray(value.data_gaps)
    && isStringArray(value.methodology)
    && typeof value.disclaimer === "string";
}

function isInterpretation(value: unknown): value is Interpretation {
  if (!isRecord(value)) return false;
  const stringFields = ["headline", "summary"];
  const listFields = ["positive_signals", "caution_signals", "practical_next_steps", "data_limitations"];
  return stringFields.every((field) => typeof value[field] === "string")
    && listFields.every((field) => Array.isArray(value[field])
      && (value[field] as unknown[]).every((entry) => typeof entry === "string"));
}

function errorMessage(error: unknown, fallback: string): string {
  if (!isRecord(error)) return fallback;
  const response = isRecord(error.response) ? error.response : null;
  const status = response && typeof response.status === "number" ? response.status : null;
  if (status === 429) return "Слишком много запросов. Подожди немного и повтори.";
  if (status === 502) return "AI-сервис временно недоступен или вернул некорректный ответ. Тенденции не изменены — попробуй ещё раз.";
  if (status === 503) return "AI-анализ пока не настроен на сервере. Обычные расчёты тенденций доступны.";
  if (status === 401) return "Сессия истекла. Войди снова.";
  if (status !== null && status >= 500) return "Сервер временно недоступен. Попробуй ещё раз позже.";
  return fallback;
}

function formatMean(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—";
}

function formatDelta(value: number | null, unit: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Нет достаточных данных для сравнения";
  const sign = value > 0 ? "+" : "";
  return sign + value.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " " + unit;
}

function trendLabel(metric: TrendMetric): string {
  if (metric.status !== "ready") return "Недостаточно данных";
  if (metric.trend === "upward") return "Среднее выросло";
  if (metric.trend === "downward") return "Среднее снизилось";
  if (metric.trend === "stable") return "Без заметного изменения";
  return "Нет надёжного сравнения";
}

function periodText(start?: string, end?: string): string {
  if (!start || !end) return "период не указан";
  return start === end ? start : start + " — " + end;
}

function StringList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (!items.length) return <p className="text-sm text-[#666]">{emptyText}</p>;
  return (
    <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
      {items.map((item, index) => <li key={index}>{item}</li>)}
    </ul>
  );
}

function MetricCard({ metric }: { metric: TrendMetric }) {
  return (
    <article className="min-w-0 border-2 border-black bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-lg uppercase leading-tight">{metric.label}</h3>
        <span className={"shrink-0 border border-black px-2 py-1 text-[9px] font-bold uppercase tracking-wide " + (
          metric.status === "ready" ? "bg-[#ffd500] text-[#111]" : "bg-[#eeeeea] text-[#555]"
        )}>
          {metric.status === "ready" ? "Есть данные" : "Мало данных"}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#666]">{metric.source}</p>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="border-t border-black/15 pt-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#666]">Последние 7 дней</p>
          <p className="mt-1 font-display text-2xl">{formatMean(metric.current?.mean)}</p>
          <p className="mt-1 text-[10px] text-[#666]">{metric.current?.days_with_data ?? 0} дн. · {metric.current?.samples ?? 0} знач.</p>
        </div>
        <div className="border-t border-black/15 pt-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#666]">Предыдущие 7 дней</p>
          <p className="mt-1 font-display text-2xl">{formatMean(metric.previous?.mean)}</p>
          <p className="mt-1 text-[10px] text-[#666]">{metric.previous?.days_with_data ?? 0} дн. · {metric.previous?.samples ?? 0} знач.</p>
        </div>
      </div>
      <div className="mt-3 border-t-2 border-black pt-3">
        <p className="text-xs font-bold">{trendLabel(metric)}</p>
        <p className="mt-1 text-xs text-[#555]">{formatDelta(metric.change, metric.unit)}</p>
        {metric.status !== "ready" && (
          <p className="mt-2 text-[10px] leading-relaxed text-[#777]">
            Нужно минимум {metric.minimum_days_required_per_period || 3} дня с данными в каждом окне. Пропуски не считаются нулём.
          </p>
        )}
      </div>
    </article>
  );
}

function AnalysisContent() {
  const transitionDirection = useTransitionDirection();
  const [days, setDays] = useState(28);
  const [refreshKey, setRefreshKey] = useState(0);
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [trendsLoading, setTrendsLoading] = useState(true);
  const [trendsError, setTrendsError] = useState("");
  const [interpretation, setInterpretation] = useState<InterpretationResponse | null>(null);
  const [interpretationLoading, setInterpretationLoading] = useState(false);
  const [interpretationError, setInterpretationError] = useState("");
  const [showMethodology, setShowMethodology] = useState(false);
  const [showCoverage, setShowCoverage] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setTrendsLoading(true);
    setTrendsError("");
    setTrends(null);
    setInterpretation(null);
    setInterpretationError("");

    authApi.get("/api/personal-analysis/trends", {
      params: { days },
      signal: controller.signal,
    }).then((response) => {
      if (!isTrendResponse(response.data)) {
        setTrendsError("Сервер вернул данные неожиданного формата. Попробуй обновить страницу.");
        return;
      }
      setTrends(response.data);
    }).catch((error: unknown) => {
      if (controller.signal.aborted || (isRecord(error) && error.name === "CanceledError")) return;
      setTrendsError(errorMessage(error, "Не удалось загрузить персональные тенденции."));
    }).finally(() => {
      if (!controller.signal.aborted) setTrendsLoading(false);
    });

    return () => controller.abort();
  }, [days, refreshKey]);

  const runInterpretation = useCallback(async () => {
    if (interpretationLoading || !trends || trends.status !== "ready") return;
    setInterpretationLoading(true);
    setInterpretation(null);
    setInterpretationError("");
    try {
      const response = await authApi.post("/api/personal-analysis/interpretation", null, { params: { days } });
      const payload = response.data as unknown;
      if (!isRecord(payload) || typeof payload.status !== "string") {
        setInterpretationError("AI-сервис вернул данные неожиданного формата. Попробуй ещё раз.");
        return;
      }
      if (payload.status === "insufficient_data") {
        setInterpretation({
          status: "insufficient_data",
          message: typeof payload.message === "string" ? payload.message : "Недостаточно данных для интерпретации.",
          data_gaps: Array.isArray(payload.data_gaps) ? payload.data_gaps.filter((item): item is string => typeof item === "string") : [],
          disclaimer: typeof payload.disclaimer === "string" ? payload.disclaimer : undefined,
        });
        return;
      }
      if (payload.status !== "ready" || !isInterpretation(payload.analysis)) {
        setInterpretationError("AI-сервис не вернул полный анализ. Тенденции сохранены; повтори запрос позже.");
        return;
      }
      setInterpretation({
        status: "ready",
        provider: typeof payload.provider === "string" ? payload.provider : undefined,
        model: typeof payload.model === "string" ? payload.model : undefined,
        generated_at: typeof payload.generated_at === "string" ? payload.generated_at : undefined,
        period: isRecord(payload.period) ? {
          start: String(payload.period.start ?? ""),
          end: String(payload.period.end ?? ""),
          days: Number(payload.period.days ?? days),
        } : undefined,
        analysis: payload.analysis,
        data_quality: isRecord(payload.data_quality) ? {
          data_gaps: Array.isArray(payload.data_quality.data_gaps)
            ? payload.data_quality.data_gaps.filter((item): item is string => typeof item === "string")
            : [],
        } : undefined,
        disclaimer: typeof payload.disclaimer === "string" ? payload.disclaimer : undefined,
      });
    } catch (error: unknown) {
      setInterpretationError(errorMessage(error, "Не удалось получить AI-интерпретацию. Попробуй ещё раз."));
    } finally {
      setInterpretationLoading(false);
    }
  }, [days, interpretationLoading, trends]);

  const handleDaysChange = (value: string) => {
    const nextDays = Number(value);
    if (!DAY_OPTIONS.some((option) => option.value === nextDays)) return;
    setDays(nextDays);
    setInterpretation(null);
    setInterpretationError("");
  };

  const coverage = trends?.coverage;
  const relationship = trends?.training_load_relationship;

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <div aria-hidden="true" className="pointer-events-none absolute left-[8%] top-[12%] h-3 w-3 animate-pulse rounded-full bg-[#ffd500]" />
      <div aria-hidden="true" className="pointer-events-none absolute right-[10%] top-[26%] h-2 w-2 rounded-full bg-white/80" />
      <div className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        <header className="border-b-2 border-black bg-[#5866f2] px-5 py-6 text-white md:px-8 md:py-8">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-white/80">Личные данные · приватная аналитика</p>
          <h1 className="mt-2 font-display text-4xl uppercase leading-none md:text-6xl">Анализ.</h1>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-white/90">
            Сопоставление самочувствия, сна и субъективной нагрузки по сохранённым данным EFL. Это тренировочная аналитика, не медицинская оценка.
          </p>
        </header>

        <section className="flex flex-col gap-4 border-b-2 border-black bg-white p-4 md:flex-row md:items-end md:justify-between md:px-6">
          <div>
            <label htmlFor="analysis-days" className="block text-[10px] font-black uppercase tracking-widest text-[#555]">Период данных</label>
            <select id="analysis-days" value={days} onChange={(event) => handleDaysChange(event.target.value)}
              className="mt-2 min-h-11 w-full border-2 border-black bg-white px-3 py-2 text-sm font-bold md:w-48">
              {DAY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            {trends?.period && <p className="mt-2 text-xs text-[#666]">{periodText(trends.period.start, trends.period.end)} · {trends.timezone || "UTC"}</p>}
          </div>
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={trendsLoading}
            className="min-h-11 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-black uppercase tracking-wide hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50">
            {trendsLoading ? "Обновляем…" : "Обновить тенденции"}
          </button>
        </section>

        <motion.div variants={sectionStaggerVariants} initial="initial" animate="animate" className="space-y-5 p-4 md:p-6">
          <motion.section variants={sectionItemVariants} custom={transitionDirection} aria-labelledby="trends-heading">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-[#666]">Сравнение окон</p>
                <h2 id="trends-heading" className="font-display text-2xl uppercase md:text-3xl">Динамика показателей</h2>
              </div>
              {trends?.comparison_windows && (
                <p className="text-right text-[10px] leading-relaxed text-[#666]">
                  Сейчас: {periodText(trends.comparison_windows.current.start, trends.comparison_windows.current.end)}<br />
                  До этого: {periodText(trends.comparison_windows.previous.start, trends.comparison_windows.previous.end)}
                </p>
              )}
            </div>

            {trendsLoading && (
              <div role="status" className="border-2 border-black bg-white p-6">
                <p className="animate-pulse font-display text-xl uppercase">Считаем тенденции…</p>
                <p className="mt-2 text-sm text-[#666]">Пропущенные значения не заменяются нулями.</p>
              </div>
            )}
            {!trendsLoading && trendsError && (
              <div role="alert" className="border-2 border-[#ff4b26] bg-white p-5">
                <h3 className="font-display text-xl uppercase">Не удалось загрузить анализ</h3>
                <p className="mt-2 text-sm leading-relaxed text-[#555]">{trendsError}</p>
                <button type="button" onClick={() => setRefreshKey((key) => key + 1)} className="mt-4 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-black uppercase">Повторить загрузку</button>
              </div>
            )}
            {!trendsLoading && !trendsError && trends && trends.observations.length === 0 && (
              <div className="border-2 border-black bg-white p-5">
                <h3 className="font-display text-xl uppercase">Пока нет тенденций</h3>
                <p className="mt-2 text-sm text-[#555]">Данные за выбранный период пока не позволяют построить показатели. Заполняй утренние и послетренировочные чек-ины и синхронизируй тренировки.</p>
              </div>
            )}
            {!trendsLoading && !trendsError && trends && trends.observations.length > 0 && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {trends.observations.map((metric) => <MetricCard key={metric.key} metric={metric} />)}
              </div>
            )}
          </motion.section>

          {!trendsLoading && !trendsError && trends && (
            <>
              <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-2 border-black bg-white">
                <div className="border-b-2 border-black bg-[#ffd500] p-4">
                  <p className="text-[10px] font-black uppercase tracking-widest">Нагрузка и восприятие</p>
                  <h2 className="mt-1 font-display text-2xl uppercase">TSS ↔ RPE</h2>
                </div>
                <div className="p-4 md:p-5">
                  {relationship?.status === "ready" ? (
                    <>
                      <p className="text-sm leading-relaxed">{typeof relationship.rpe_difference_high_minus_low === "number"
                        ? "Разница среднего RPE между днями с нагрузкой выше и не выше медианы: " + formatDelta(relationship.rpe_difference_high_minus_low, "пункта RPE") + "."
                        : "Сравнение доступно."}</p>
                      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                        <div className="border-2 border-black p-3"><p className="text-[10px] font-bold uppercase text-[#666]">Парных дней</p><p className="mt-1 font-display text-2xl">{relationship.paired_days ?? "—"}</p></div>
                        <div className="border-2 border-black p-3"><p className="text-[10px] font-bold uppercase text-[#666]">TSS не выше медианы</p><p className="mt-1 font-display text-2xl">{formatMean(relationship.lower_or_equal_load?.mean_daily_rpe)} <span className="text-xs">RPE</span></p></div>
                        <div className="border-2 border-black p-3"><p className="text-[10px] font-bold uppercase text-[#666]">TSS выше медианы</p><p className="mt-1 font-display text-2xl">{formatMean(relationship.above_median_load?.mean_daily_rpe)} <span className="text-xs">RPE</span></p></div>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm leading-relaxed text-[#555]">
                      Недостаточно парных дней для сравнения нагрузки и RPE. Нужно не менее 8 дней с измеренным полным TSS и RPE, включая минимум 3 дня в каждой группе. Оценочный TSS не смешивается с измеренным.
                    </p>
                  )}
                  <p className="mt-3 text-xs leading-relaxed text-[#666]">Это описательная связь, а не доказательство причинности. Полнота последней синхронизации отдельно не проверяется.</p>
                </div>
              </motion.section>

              <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-2 border-black bg-white">
                <div className="flex items-start justify-between gap-3 border-b-2 border-black p-4">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-[#666]">Покрытие данных</p>
                    <h2 className="mt-1 font-display text-xl uppercase">Что учтено</h2>
                  </div>
                  <button type="button" onClick={() => setShowCoverage((shown) => !shown)} aria-expanded={showCoverage}
                    className="border-2 border-black px-3 py-2 text-[10px] font-black uppercase hover:bg-[#ffd500]">
                    {showCoverage ? "Свернуть" : "Подробнее"}
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
                  <div className="border border-black/20 p-3"><p className="text-[10px] font-bold uppercase text-[#666]">Утренние чек-ины</p><p className="mt-1 font-display text-2xl">{coverage?.morning_checkins?.completed_days ?? 0}/{coverage?.morning_checkins?.period_days ?? days}</p><p className="text-xs text-[#666]">заполнено дней</p></div>
                  <div className="border border-black/20 p-3"><p className="text-[10px] font-bold uppercase text-[#666]">Качество сна</p><p className="mt-1 font-display text-2xl">{coverage?.sleep?.days_with_quality_value ?? 0}/{days}</p><p className="text-xs text-[#666]">дней со значением</p></div>
                  <div className="border border-black/20 p-3"><p className="text-[10px] font-bold uppercase text-[#666]">Тренировки</p><p className="mt-1 font-display text-2xl">{coverage?.activities?.activities_in_period ?? 0}</p><p className="text-xs text-[#666]">сохранено в EFL</p></div>
                </div>
                {showCoverage && (
                  <div className="space-y-4 border-t border-black/15 p-4 text-sm">
                    <div><h3 className="mb-2 font-bold">Утренние отметки</h3><p>Пропущено: {coverage?.morning_checkins?.skipped_days ?? 0}; незавершено: {coverage?.morning_checkins?.pending_days ?? 0}; нет записи о статусе: {coverage?.morning_checkins?.no_record_days ?? 0}.</p></div>
                    <div><h3 className="mb-2 font-bold">Сон</h3><p>Записи Wellness: {coverage?.sleep?.days_with_wellness_record ?? 0}; продолжительность: {coverage?.sleep?.days_with_duration_value ?? 0} дней.</p></div>
                    <div><h3 className="mb-2 font-bold">Тренировки</h3><p>Измеренный TSS: {coverage?.activities?.activities_with_measured_tss ?? 0}; оценочный TSS: {coverage?.activities?.activities_with_estimated_tss ?? 0}; без пригодного TSS: {coverage?.activities?.activities_without_tss ?? 0}; с RPE: {coverage?.activities?.activities_with_rpe ?? 0}.</p></div>
                  </div>
                )}
                <div className="border-t-2 border-black bg-[#f4f4f0] p-4">
                  <h3 className="font-bold">Пропуски и ограничения</h3>
                  <StringList items={trends.data_gaps} emptyText="Явные пробелы в данных не отмечены." />
                </div>
              </motion.section>

              <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-2 border-black bg-white">
                <div className="border-b-2 border-black bg-[#5866f2] p-4 text-white md:p-5">
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/80">Интерпретация по запросу</p>
                  <h2 className="mt-1 font-display text-2xl uppercase md:text-3xl">Что это может означать?</h2>
                  <p className="mt-2 text-sm leading-relaxed text-white/90">AI объяснит только наблюдения по имеющимся данным. Это не диагноз и не персональное назначение тренировочного плана.</p>
                </div>
                <div className="p-4 md:p-5">
                  <button type="button" onClick={() => void runInterpretation()} disabled={interpretationLoading || trends.status !== "ready"}
                    className="min-h-12 w-full border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-black uppercase tracking-wide hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto">
                    {interpretationLoading ? "Готовим интерпретацию…" : interpretation ? "Сгенерировать заново" : "Получить AI-интерпретацию"}
                  </button>
                  <p className="mt-2 text-[11px] leading-relaxed text-[#666]">Запрос выполняется только по кнопке. При повторе может расходоваться дополнительный лимит AI-сервиса.</p>
                  {trends.status !== "ready" && <p className="mt-3 text-sm text-[#666]">Сначала нужны пригодные сравнения в обеих неделях. Сейчас AI-запрос отключён.</p>}
                  {interpretationLoading && <p role="status" className="mt-4 border-l-4 border-[#5866f2] bg-[#5866f2]/5 px-3 py-3 text-sm">Запрашиваем интерпретацию. Повторный запрос не нужен — подожди ответа.</p>}
                  {interpretationError && (
                    <div role="alert" className="mt-4 border-2 border-[#ff4b26] p-4">
                      <p className="text-sm leading-relaxed">{interpretationError}</p>
                      <button type="button" onClick={() => void runInterpretation()} disabled={interpretationLoading || trends.status !== "ready"} className="mt-3 border-2 border-black bg-white px-3 py-2 text-xs font-bold uppercase hover:bg-[#ffd500] disabled:opacity-50">Повторить AI-запрос</button>
                    </div>
                  )}
                  {interpretation?.status === "insufficient_data" && (
                    <div role="status" className="mt-4 border-2 border-black bg-[#f4f4f0] p-4">
                      <h3 className="font-display text-xl uppercase">Мало данных</h3>
                      <p className="mt-2 text-sm">{interpretation.message}</p>
                      <StringList items={interpretation.data_gaps ?? []} emptyText="Сервер не вернул дополнительные пояснения." />
                    </div>
                  )}
                  {interpretation?.status === "ready" && interpretation.analysis && (
                    <div className="mt-5 space-y-4">
                      <article className="border-2 border-black bg-[#f4f4f0] p-4 md:p-5">
                        <p className="text-[10px] font-black uppercase tracking-widest text-[#666]">Итог</p>
                        <h3 className="mt-1 font-display text-2xl uppercase">{interpretation.analysis.headline}</h3>
                        <p className="mt-3 text-sm leading-relaxed">{interpretation.analysis.summary}</p>
                        {interpretation.generated_at && <p className="mt-3 text-[10px] text-[#666]">Создано: {new Date(interpretation.generated_at).toLocaleString("ru-RU")}</p>}
                      </article>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <article className="border-2 border-black bg-white p-4"><h3 className="mb-3 font-display text-lg uppercase">Положительные сигналы</h3><StringList items={interpretation.analysis.positive_signals} emptyText="Не выделены." /></article>
                        <article className="border-2 border-black bg-white p-4"><h3 className="mb-3 font-display text-lg uppercase">На что обратить внимание</h3><StringList items={interpretation.analysis.caution_signals} emptyText="Не выделены." /></article>
                        <article className="border-2 border-black bg-white p-4"><h3 className="mb-3 font-display text-lg uppercase">Следующие шаги</h3><StringList items={interpretation.analysis.practical_next_steps} emptyText="Нет рекомендаций." /></article>
                        <article className="border-2 border-black bg-white p-4"><h3 className="mb-3 font-display text-lg uppercase">Ограничения</h3><StringList items={interpretation.analysis.data_limitations} emptyText="Не выделены." /></article>
                      </div>
                      {(interpretation.data_quality?.data_gaps?.length || interpretation.disclaimer) && (
                        <div className="border-l-4 border-[#5866f2] bg-white p-4">
                          <h3 className="font-bold">Качество данных</h3>
                          <StringList items={interpretation.data_quality?.data_gaps ?? []} emptyText="Сервер не отметил дополнительные пробелы." />
                          {interpretation.disclaimer && <p className="mt-3 text-xs leading-relaxed text-[#666]">{interpretation.disclaimer}</p>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </motion.section>

              <motion.section variants={sectionItemVariants} custom={transitionDirection} className="border-2 border-black bg-white">
                <button type="button" onClick={() => setShowMethodology((shown) => !shown)} aria-expanded={showMethodology}
                  className="flex w-full items-center justify-between gap-3 p-4 text-left hover:bg-black/5">
                  <span><span className="block text-[10px] font-black uppercase tracking-widest text-[#666]">Как рассчитывается</span><span className="mt-1 block font-display text-lg uppercase">Методология и ограничения</span></span>
                  <span aria-hidden="true" className="font-display text-2xl">{showMethodology ? "−" : "+"}</span>
                </button>
                {showMethodology && <div className="space-y-3 border-t border-black/15 p-4"><StringList items={trends.methodology ?? []} emptyText="Дополнительная методология не передана." />{trends.disclaimer && <p className="border-t border-black/15 pt-3 text-xs leading-relaxed text-[#666]">{trends.disclaimer}</p>}</div>}
              </motion.section>
            </>
          )}
        </motion.div>
      </div>
    </main>
  );
}

export default function PersonalAnalysisPage() {
  return (
    <AuthGuard>
      <AnalysisContent />
    </AuthGuard>
  );
}
