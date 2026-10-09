"use client";

/* Общий тултип XP-графика: до 4 карточек тренировок за день.
   Используется в дашборде и в публичном профиле. */

export default function XpTooltip({
  active,
  payload,
  chartData,
}: {
  active?: boolean;
  payload?: any[];
  chartData: any[];
}) {
  if (!active || !payload?.length) return null;

  const current = payload[0]?.payload;
  if (!current) return null;

  const activities = chartData
    .filter((item) => item.date === current.date)
    .slice(0, 4);

  if (!activities.length) return null;

  const renderCard = (d: any) => {
    const multiplier = Number(d.intensityMult ?? 1);
    // Категория приходит с бэкенда (v5.0): LOW | MEDIUM | HIGH | UNKNOWN.
    // НЕ выводить из множителя: множитель — это ×0.5–×1.5, а не IF 0–1.
    const category = String(d.intensity_category ?? "UNKNOWN").toUpperCase();

    const CAT_COLOR: Record<string, string> = {
      HIGH: "text-[#ff4b26]",
      MEDIUM: "text-[#5866f2]",
      LOW: "text-[#16a34a]",
      UNKNOWN: "text-[#999]",
    };
    const multiplierColor = CAT_COLOR[category] ?? "text-[#111]";
    const multiplierLabel = category;

    return (
      <div
        key={`${d.date}-${d.name}-${d.sport}-${d.xp}`}
        className="w-full min-w-0 bg-[#c7d2fe] text-[#111] border-2 border-black p-3 shadow-[4px_4px_0_#000] text-sm"
      >
        <p className="font-display uppercase text-base mb-1 truncate">
          {d.name}
        </p>

        <p className="text-[9px] font-bold tracking-widest uppercase text-[#4b5563] mb-2 truncate">
          {d.date} · {d.sport} · {d.distance} km
        </p>

        {d.base_xp == null ? (
          <>
            <div className="flex items-center justify-between gap-4">
              <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">Load XP</span>
              <span className="flex-1 text-right font-display">+{d.xp}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">Source</span>
              <span className="flex-1 text-right font-display">{d.tss_estimated ? "EST" : "TSS"}</span>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-between gap-4">
            <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">Base XP</span>
            <span className="flex-1 text-right font-display">{d.base_xp}</span>
          </div>
        )}

        {/* Intensity */}
        <div className="flex items-center justify-between gap-4">
          <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">
            Intens
          </span>

          <span
            className={`flex-1 text-right font-display ${multiplierColor}`}
          >
            {multiplierLabel} ×{multiplier.toFixed(2)}
          </span>
        </div>

        {d.base_xp == null && (
          <div className="flex items-center justify-between gap-4">
            <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">
              Sleep
            </span>

            <span className="flex-1 text-right font-display">
              ×{Number(d.sleepMult ?? 1).toFixed(2)}
            </span>
          </div>
        )}

        {d.base_xp == null && (
          <div className="flex items-center justify-between gap-4">
            <span className="shrink-0 text-[#4b5563] font-bold uppercase text-[10px]">
              Streak
            </span>

            <span className="flex-1 text-right font-display text-[#16a34a]">
              ×{Number(d.streakMult ?? 1).toFixed(2)}
            </span>
          </div>
        )}

        {/* Total */}
        <div className="flex items-center justify-between gap-4 mt-1 pt-1 border-t border-black/20">
          <span className="shrink-0 font-bold uppercase text-[10px]">
            Total
          </span>

          <span className="flex-1 text-right font-display text-[#171a38]">
            +{d.xp} XP
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full max-w-[900px] px-2 pointer-events-none">
      {activities.length === 1 && (
        <div className="w-full flex justify-center">
          <div className="w-full max-w-[440px]">
            {renderCard(activities[0])}
          </div>
        </div>
      )}
      {activities.length === 2 && (
        <div className="grid grid-cols-2 gap-2 w-full">
          {activities.map(renderCard)}
        </div>
      )}

      {activities.length === 3 && (
        <div className="grid grid-cols-2 gap-2 w-full">
          <div className="col-span-2 flex justify-center min-w-0">
            <div className="w-1/2 min-w-0">
              {renderCard(activities[0])}
            </div>
          </div>

          {renderCard(activities[1])}
          {renderCard(activities[2])}
        </div>
      )}

      {activities.length === 4 && (
        <div className="grid grid-cols-2 gap-2 w-full">
          {activities.map(renderCard)}
        </div>
      )}
    </div>
  );
}
