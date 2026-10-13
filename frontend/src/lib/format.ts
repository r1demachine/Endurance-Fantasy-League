/**
 * Formats a Monday-based calendar week for Russian-language UI.
 * Examples:
 *   12 октября – 18 октября 2026
 *   28 декабря 2026 – 3 января 2027
 */
function asLocalDate(value: string | Date): Date | null {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null;
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]) - 1;
    const day = Number(match[3]);
    const parsed = new Date(year, month, day);
    if (parsed.getFullYear() !== year || parsed.getMonth() !== month || parsed.getDate() !== day) {
      return null;
    }
    return parsed;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? null
    : new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

function formatDayMonth(date: Date): string {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
  }).formatToParts(date);
  const day = parts.find((part) => part.type === "day")?.value ?? String(date.getDate());
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  return month ? `${day} ${month}` : day;
}

export function formatWeekRange(weekStart: string | Date | null | undefined): string {
  if (!weekStart) return "Неделя неизвестна";
  const start = asLocalDate(weekStart);
  if (!start) return "Неделя неизвестна";

  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
  const startDayMonth = formatDayMonth(start);
  const endDayMonth = formatDayMonth(end);

  if (start.getFullYear() !== end.getFullYear()) {
    return `${startDayMonth} ${start.getFullYear()} – ${endDayMonth} ${end.getFullYear()}`;
  }
  return `${startDayMonth} – ${endDayMonth} ${end.getFullYear()}`;
}
