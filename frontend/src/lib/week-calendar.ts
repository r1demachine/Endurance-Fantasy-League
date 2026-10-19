/** Calendar-specific formatting kept pure so it can be tested without rendering React. */
export function formatSleepDuration(seconds: number): string {
  const totalMinutes = Math.max(0, Math.floor((Number(seconds) || 0) / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours}ч ${String(minutes).padStart(2, "0")}м`;
}

export function formatActivityDuration(minutes: number): string {
  const safeMinutes = Math.max(0, Math.floor(Number(minutes) || 0));
  if (safeMinutes < 60) return `${safeMinutes} мин`;
  const hours = Math.floor(safeMinutes / 60);
  const rest = safeMinutes % 60;
  return rest ? `${hours}ч ${rest}м` : `${hours}ч`;
}

export function getCalendarWeekDates(weekStart: string): string[] {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(weekStart);
  if (!match) return [];
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const base = new Date(Date.UTC(year, month - 1, day));
  if (
    base.getUTCFullYear() !== year ||
    base.getUTCMonth() !== month - 1 ||
    base.getUTCDate() !== day
  ) {
    return [];
  }

  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(Date.UTC(year, month - 1, day + index));
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
  });
}
