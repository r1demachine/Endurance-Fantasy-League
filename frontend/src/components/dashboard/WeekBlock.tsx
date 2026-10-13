import { formatWeekRange } from "@/lib/format";

export default function WeekBlock({
  weekData, weekOptions, selectedWeekStart, onWeekChange, onPreviousWeek, onNextWeek,
  canGoPrevious, canGoNext, onPauseClick, onDeloadAction, deloadBusy, deloadError,
}: {
  weekData: any;
  weekOptions: { week_start: string; label: string }[];
  selectedWeekStart: string;
  onWeekChange: (value: string) => void;
  onPreviousWeek: () => void;
  onNextWeek: () => void;
  canGoPrevious: boolean;
  canGoNext: boolean;
  onPauseClick: () => void;
  onDeloadAction: (enable: boolean) => void;
  deloadBusy: boolean;
  deloadError: string;
}) {
  if (!weekData) return null;
  const pct = Math.min(Math.max(weekData.completion_ratio || 0, 0), 150);
  const isReady = weekData.state === "ready";
  const isInProgress = weekData.state === "in_progress";

  return (
    <div className="border-b-2 border-black bg-white p-4 md:p-6">
      <div className="flex flex-col gap-3 mb-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 className="font-display uppercase text-xl md:text-2xl">Твоя неделя</h3>
            <p className="mt-1 text-xs text-[#666]">{formatWeekRange(selectedWeekStart)}</p>
          </div>
          <div className="flex items-center gap-2">
            {isInProgress && <span className="px-2 py-1 bg-[#ffd500] text-[10px] font-bold tracking-widest uppercase">В процессе</span>}
            {weekData.is_deload && (
              <span className={`px-2 py-1 text-white text-[10px] font-bold tracking-widest uppercase ${weekData.deload_source === "manual" ? "bg-[#a855f7]" : "bg-[#0ea5e9]"}`}>
                Deload · {weekData.deload_source === "manual" ? "вручную" : "авто"}
              </span>
            )}
            {weekData.paused && <span className="px-2 py-1 bg-[#666] text-white text-[10px] font-bold tracking-widest uppercase">Пауза</span>}
            {weekData.state === "no_data" && <span className="px-2 py-1 bg-[#666] text-white text-[10px] font-bold tracking-widest uppercase">{weekData.target_load > 0 ? "Стартовая норма" : "Нет данных"}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" aria-label="Предыдущая неделя" disabled={!canGoPrevious} onClick={onPreviousWeek} className="w-9 h-9 border-2 border-black font-bold disabled:opacity-30 hover:bg-[#ffd500] transition-colors">←</button>
          <select value={selectedWeekStart} onChange={(e) => onWeekChange(e.target.value)} aria-label="Выбрать неделю" className="min-w-0 flex-1 max-w-[300px] border-2 border-black bg-white px-3 py-2 text-sm font-bold">
            {weekOptions.map((option) => <option key={option.week_start} value={option.week_start}>{formatWeekRange(option.week_start)}</option>)}
          </select>
          <button type="button" aria-label="Следующая неделя" disabled={!canGoNext} onClick={onNextWeek} className="w-9 h-9 border-2 border-black font-bold disabled:opacity-30 hover:bg-[#ffd500] transition-colors">→</button>
        </div>
      </div>

      {/* Кольцо цели */}
      <div className="flex items-center gap-6 mb-6">
        <div className="relative w-24 h-24 shrink-0">
          <svg className="w-full h-full transform -rotate-90">
            <circle cx="48" cy="48" r="40" stroke="#e5e7eb" strokeWidth="8" fill="none" />
            <circle
              cx="48" cy="48" r="40"
              stroke={pct >= 100 ? "#16a34a" : "#ff4b26"}
              strokeWidth="8"
              fill="none"
              strokeDasharray={`${Math.min(pct, 100) * 2.51} 251`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-display text-xl">{Math.round(pct)}%</span>
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mb-1">
            Цель нагрузки
          </p>
          <p className="font-display text-2xl mb-1">
            {weekData.actual_load} / {weekData.target_load} TSS
          </p>
          <p className="text-[10px] text-[#666]">
            {weekData.training_days} тренировочных дней
          </p>
          <p className="text-[10px] text-[#666] mt-1">
            Дивизион:{" "}
            <span className="font-bold text-[#171a38]">{weekData.division ?? "Provisional"}</span>
            {weekData.division_source && (
              <span className="text-[#999]"> · {weekData.division_source}</span>
            )}
          </p>
        </div>
      </div>

      {weekData.is_current_week && (
        <div className="mb-4 border-2 border-black/15 bg-[#f4f4f0] p-3">
          {weekData.is_deload ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Разгрузочная неделя активна</p>
                <p className="mt-1 text-sm">{weekData.deload_source === "manual" ? "Установлена вручную. Goal XP ограничен значением 85%." : "Назначена автоматически по нагрузке прошлых недель."}</p>
              </div>
              {weekData.deload_source === "manual" && (
                <button type="button" disabled={!weekData.can_set_deload || deloadBusy} onClick={() => onDeloadAction(false)} className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-[#ff4b26] hover:text-white disabled:cursor-not-allowed disabled:opacity-40">
                  {deloadBusy ? "Сохраняем…" : "Снять Deload"}
                </button>
              )}
            </div>
          ) : (
            <button type="button" disabled={!weekData.can_set_deload || deloadBusy} onClick={() => onDeloadAction(true)} className="border-2 border-black bg-[#ffd500] px-3 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-40">
              {deloadBusy ? "Сохраняем…" : "Поставить разгрузочную неделю"}
            </button>
          )}
          {!weekData.can_set_deload && weekData.deload_block_reason && (
            <p className="mt-2 text-xs text-[#666]">{weekData.deload_block_reason}</p>
          )}
          {weekData.deload_suggestion && !weekData.is_deload && (
            <div className="mt-3 border-l-4 border-[#5866f2] bg-white p-3">
              <p className="text-sm font-bold">Похоже, это разгрузочная неделя. Поставить Deload?</p>
              <p className="mt-1 text-xs text-[#666]">Предложение необязательное. Если ничего не делать, в конце недели система проверит условия автоматического Deload.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={!weekData.can_set_deload || deloadBusy} onClick={() => onDeloadAction(true)} className="border-2 border-black bg-[#5866f2] px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-40">Поставить</button>
                <button type="button" disabled={deloadBusy} onClick={() => onDeloadAction(false)} className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-[#e9e9e2] disabled:opacity-40">Не сейчас</button>
              </div>
            </div>
          )}
          {deloadError && <p role="alert" className="mt-2 text-xs font-bold text-[#b91c1c]">{deloadError}</p>}
        </div>
      )}

      {weekData.state === "no_data" && weekData.target_load > 0 && (
        <p className="text-[10px] text-[#666] mb-4">
          История ещё не накоплена — цель равна стартовой норме (3 тренировки × 45 мин).
          Синхронизируй тренировки, и цель станет персональной.
        </p>
      )}

      <div className="mb-4">
        <button
          type="button"
          onClick={onPauseClick}
          className="px-3 py-2 border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-[#ffd500] transition-colors"
        >
          ⏸ Пауза (болезнь / отпуск)
        </button>
      </div>

      <div className="flex items-center justify-between gap-3 border-y-2 border-black/10 py-3 mb-4">
        <span className="text-[10px] font-bold tracking-widest uppercase text-[#666]">Итого XP за неделю</span>
        <span className="font-display text-2xl text-[#ff4b26]">+{Math.round(Number(weekData.total_xp) || 0)}</span>
      </div>

      {/* Разбивка XP */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { label: "Нагрузка", value: weekData.effort_xp, color: "text-[#ff4b26]" },
          { label: "Цель", value: weekData.goal_xp, color: "text-[#16a34a]" },
          { label: "Регулярность", value: weekData.consistency_xp, color: "text-[#5866f2]" },
          { label: "Качество", value: weekData.quality_xp, color: "text-[#ffd500]" },
          { label: "Восстановление", value: weekData.recovery_xp, color: "text-[#0ea5e9]" },
          { label: "Квесты и бонусы", value: weekData.quest_xp, color: "text-[#a855f7]" },
        ].map((item) => (
          <div key={item.label} className="border border-black/10 p-2">
            <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">
              {item.label}
            </p>
            <p className={`font-display text-lg ${item.color}`}>+{item.value}</p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[#666]">
        «Квесты и бонусы» включают награды за недельные достижения, +12 XP за каждую не ручную тренировку от 45 минут и +6 XP за каждую ночь со сном от 6 часов или sleep score от 60.
      </p>

      {isReady && (
        <div className="mt-4 pt-4 border-t border-black/10 flex items-center justify-between">
          <span className="text-[10px] font-bold tracking-widest uppercase text-[#666]">
            League Score
          </span>
          <span className="font-display text-xl text-[#171a38]">
            {weekData.league_score}
          </span>
        </div>
      )}
    </div>
  );
}
