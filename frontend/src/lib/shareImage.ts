export type ShareKind = "activity" | "day" | "week" | "season";
export type ShareTextTheme = "light" | "dark";

export type ShareImageInput = {
  kind: ShareKind;
  xp: number;
  title?: string;
  date?: string;
  weekStart?: string;
  sport?: string;
  durationMinutes?: number;
  distanceKm?: number | null;
  tss?: number | null;
  goalPercent?: number | null;
  trainingDays?: number | null;
  leagueRank?: number | null;
  workoutCount?: number | null;
  totalKm?: number | null;
  totalHours?: number | null;
  totalElevation?: number | null;
  totalWorkouts?: number | null;
  bestWeekXp?: number | null;
  longestStreakDays?: number | null;
  achievementsCount?: number | null;
  bestLeagueRank?: number | null;
  duelWins?: number | null;
  duelDraws?: number | null;
  duelLosses?: number | null;
  userName?: string;
};

export type ShareImageOptions = {
  square?: boolean;
  textTheme?: ShareTextTheme;
  includeName?: boolean;
  includeLeagueRank?: boolean;
};

export type ShareTextLayout = {
  width: number;
  height: number;
  titleY: number;
  xpY: number;
  linesStartY: number;
  lineHeight: number;
  footerY: number;
  marginX: number;
  titleSize: number;
  xpSize: number;
  bodySize: number;
};

const numeric = (value: number | null | undefined, digits = 1): string =>
  Number(value ?? 0).toLocaleString("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });

const shortDate = (value?: string): string => {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  return `${match[3]}.${match[2]}.${match[1]}`;
};

/** Pure text formatter shared with tests. No names or league rank are included by default. */
export function formatShareLines(
  data: ShareImageInput,
  options: Pick<ShareImageOptions, "includeName" | "includeLeagueRank"> = {},
): string[] {
  const lines: string[] = [];
  if (data.kind === "activity") {
    const details = [
      data.sport?.trim(),
      data.durationMinutes != null ? `${numeric(data.durationMinutes, 0)} мин` : undefined,
      data.tss != null ? `TSS ${numeric(data.tss)}` : undefined,
    ].filter((value): value is string => Boolean(value));
    if (details.length) lines.push(details.join(" · "));
    if (data.distanceKm != null) lines.push(`Дистанция: ${numeric(data.distanceKm, 2)} км`);
    if (data.date) lines.push(shortDate(data.date));
  } else if (data.kind === "day") {
    if (data.date) lines.push(shortDate(data.date));
    lines.push(`Тренировок: ${numeric(data.workoutCount, 0)}`);
  } else if (data.kind === "week") {
    lines.push(`Всего за неделю: +${Math.round(data.xp)} XP`);
    if (data.goalPercent != null) lines.push(`Цель: ${numeric(data.goalPercent)}%`);
    if (data.trainingDays != null) lines.push(`Дней с тренировками: ${numeric(data.trainingDays, 0)}`);
    if (options.includeLeagueRank && data.leagueRank != null) {
      lines.push(`Место в лиге: #${numeric(data.leagueRank, 0)}`);
    }
    if (data.weekStart) lines.push(`Неделя с ${shortDate(data.weekStart)}`);
  } else {
    lines.push(`Дистанция: ${numeric(data.totalKm)} км`);
    lines.push(`Время: ${numeric(data.totalHours)} ч · набор: ${numeric(data.totalElevation, 0)} м`);
    lines.push(`Тренировок: ${numeric(data.totalWorkouts, 0)}`);
    if (data.bestWeekXp != null) lines.push(`Лучшая неделя: +${Math.round(data.bestWeekXp)} XP`);
    if (data.longestStreakDays != null) lines.push(`Серия тренировок: ${numeric(data.longestStreakDays, 0)} дн.`);
    if (data.achievementsCount != null) lines.push(`Достижений: ${numeric(data.achievementsCount, 0)}`);
    if (data.bestLeagueRank != null) lines.push(`Лучшее место в лиге: #${numeric(data.bestLeagueRank, 0)}`);
    if (data.duelWins != null || data.duelDraws != null || data.duelLosses != null) {
      lines.push(`Дуэли: ${numeric(data.duelWins, 0)}–${numeric(data.duelDraws, 0)}–${numeric(data.duelLosses, 0)}`);
    }
  }
  if (options.includeName && data.userName?.trim()) lines.push(data.userName.trim());
  return lines;
}

export function calculateShareLayout(square = false): ShareTextLayout {
  const width = 1080;
  const height = square ? 1080 : 1920;
  return {
    width,
    height,
    titleY: square ? 152 : 294,
    xpY: square ? 378 : 690,
    linesStartY: square ? 500 : 850,
    lineHeight: square ? 42 : 52,
    footerY: height - (square ? 74 : 92),
    marginX: 112,
    titleSize: square ? 40 : 48,
    xpSize: square ? 138 : 172,
    bodySize: square ? 31 : 37,
  };
}

function resolveLocalFontFamily(): string {
  // The body uses next/font's self-hosted Inter asset. Do not use .font-display here:
  // that typeface is imported from Google Fonts and may trigger a cross-origin request.
  const family = window.getComputedStyle(document.body).fontFamily || "sans-serif";
  return family.split(",")[0].trim() || "sans-serif";
}

function wrapMeasuredText(
  ctx: CanvasRenderingContext2D,
  value: string,
  maxWidth: number,
): string[] {
  const words = value.split(/\s+/).filter(Boolean);
  const wrapped: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (current && ctx.measureText(candidate).width > maxWidth) {
      wrapped.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) wrapped.push(current);
  return wrapped;
}

function shortenToFit(ctx: CanvasRenderingContext2D, value: string, maxWidth: number): string {
  if (ctx.measureText(value).width <= maxWidth) return value;
  let result = value;
  while (result.length > 3 && ctx.measureText(`${result.slice(0, -1)}…`).width > maxWidth) {
    result = result.slice(0, -1);
  }
  return `${result.slice(0, -1)}…`;
}

/**
 * Render a text-only transparent PNG locally. No images, stylesheets, or other remote
 * assets are fetched or painted into the canvas.
 */
export async function renderShareImage(
  data: ShareImageInput,
  options: ShareImageOptions = {},
): Promise<Blob> {
  if (typeof document === "undefined") {
    throw new Error("PNG можно создать только в браузере.");
  }

  const layout = calculateShareLayout(Boolean(options.square));
  const canvas = document.createElement("canvas");
  canvas.width = layout.width;
  canvas.height = layout.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Браузер не смог создать canvas.");

  const fontFamily = resolveLocalFontFamily();
  await Promise.all([
    document.fonts.load(`700 ${layout.titleSize}px ${fontFamily}`),
    document.fonts.load(`800 ${layout.xpSize}px ${fontFamily}`),
    document.fonts.load(`600 ${layout.bodySize}px ${fontFamily}`),
  ]);
  await document.fonts.ready;

  ctx.clearRect(0, 0, layout.width, layout.height);
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  const isLightText = options.textTheme !== "dark";
  const textColor = isLightText ? "#ffffff" : "#171717";
  const shadowColor = isLightText ? "rgba(0,0,0,0.72)" : "rgba(255,255,255,0.68)";
  const title = (data.title || ({
    activity: "ТРЕНИРОВКА",
    day: "ИТОГИ ДНЯ",
    week: "ИТОГИ НЕДЕЛИ",
    season: "ИТОГИ СЕЗОНА",
  } as const)[data.kind]).toLocaleUpperCase("ru-RU");

  ctx.fillStyle = textColor;
  ctx.shadowColor = shadowColor;
  ctx.shadowBlur = 20;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 4;

  ctx.font = `700 ${layout.titleSize}px ${fontFamily}`;
  ctx.fillText(shortenToFit(ctx, title, layout.width - layout.marginX * 2), layout.width / 2, layout.titleY);

  ctx.font = `800 ${layout.xpSize}px ${fontFamily}`;
  ctx.fillText(`+${Math.round(Number(data.xp) || 0)} XP`, layout.width / 2, layout.xpY);

  const lines = formatShareLines(data, options);
  let bodySize = layout.bodySize;
  let lineHeight = layout.lineHeight;
  let wrapped: string[] = [];
  const maxWidth = layout.width - layout.marginX * 2;
  const footerSafetyGap = options.square ? 128 : 148;
  const availableHeight = Math.max(lineHeight, layout.footerY - layout.linesStartY - footerSafetyGap);
  for (let attempt = 0; attempt < 5; attempt += 1) {
    ctx.font = `600 ${bodySize}px ${fontFamily}`;
    wrapped = lines.flatMap((line) => wrapMeasuredText(ctx, line, maxWidth));
    if (wrapped.length * lineHeight <= availableHeight) break;
    bodySize = Math.max(23, bodySize - 2);
    lineHeight = Math.max(32, lineHeight - 2);
  }

  ctx.font = `600 ${bodySize}px ${fontFamily}`;
  const blockHeight = wrapped.length * lineHeight;
  let y = layout.linesStartY + Math.max(0, (availableHeight - blockHeight) / 2);
  for (const line of wrapped) {
    ctx.fillText(line, layout.width / 2, y);
    y += lineHeight;
  }

  ctx.shadowBlur = 12;
  ctx.shadowOffsetY = 2;
  ctx.font = `800 ${options.square ? 52 : 62}px ${fontFamily}`;
  const brand = "fantasy";
  const dot = ".";
  const brandWidth = ctx.measureText(brand).width;
  const dotWidth = ctx.measureText(dot).width;
  const brandX = (layout.width - brandWidth - dotWidth) / 2;
  ctx.textAlign = "left";
  ctx.fillStyle = textColor;
  ctx.fillText(brand, brandX, layout.footerY);
  ctx.fillStyle = "#ff4b26";
  ctx.fillText(dot, brandX + brandWidth, layout.footerY);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Не удалось собрать PNG. Попробуй другой браузер."));
    }, "image/png");
  });
}
