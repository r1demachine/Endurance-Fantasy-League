export type TodayAchievement = {
  slug: string;
  title: string;
  reward: number;
  kind?: string;
  status?: string;
  earned_today?: boolean;
};

export type TodayWeeklyAchievement = {
  slug: string;
  title: string;
  reward: number;
  kind?: string;
  status: string;
  progress?: { current?: number; target?: number; unit?: string; season_active?: boolean } | null;
  actionable_today?: boolean;
  completed_today?: boolean;
  completed_before_today?: boolean;
};

export type TodayCardChecklistSource = {
  weekly_achievements?: TodayWeeklyAchievement[];
  achievements_today?: TodayAchievement[];
};

function parseLocalCalendarDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const parsed = new Date(year, month, day, 12);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month ||
    parsed.getDate() !== day
  ) {
    return null;
  }
  return parsed;
}

export function formatTodayDate(value: string): string {
  const date = parseLocalCalendarDate(value);
  if (!date) return "дата неизвестна";
  const weekday = new Intl.DateTimeFormat("ru-RU", { weekday: "short" }).format(date).replace(/\.$/, "");
  const day = String(date.getDate());
  const month = new Intl.DateTimeFormat("ru-RU", { month: "short" }).format(date).replace(/\.$/, "");
  return `${weekday}, ${day} ${month}`;
}

export function formatSecondsLeftToday(value: number): string {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  if (seconds === 0) return "День завершён";
  const totalMinutes = Math.ceil(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `Осталось ${minutes} м`;
  return `Осталось ${hours} ч ${minutes} м`;
}

export function formatStreak(value: number): string {
  const streak = Math.max(0, Math.floor(Number(value) || 0));
  const remainder100 = streak % 100;
  const remainder10 = streak % 10;
  let noun = "дней";
  if (remainder100 < 11 || remainder100 > 14) {
    if (remainder10 === 1) noun = "день";
    else if (remainder10 >= 2 && remainder10 <= 4) noun = "дня";
  }
  return `Серия ${streak} ${noun}`;
}

export function todayChecklistModel(source: TodayCardChecklistSource) {
  const weekly = Array.isArray(source.weekly_achievements) ? source.weekly_achievements : [];
  const receivedToday = Array.isArray(source.achievements_today) ? source.achievements_today : [];
  return {
    visibleWeekly: weekly.filter((quest) => quest.actionable_today || quest.completed_today),
    completedEarlier: weekly.filter((quest) => quest.completed_before_today),
    lifetimeReceivedToday: receivedToday.filter(
      (achievement) =>
        achievement.kind === "lifetime" &&
        achievement.status === "earned" &&
        achievement.earned_today === true,
    ),
  };
}

export function formatWeeklyProgress(quest: TodayWeeklyAchievement): string | null {
  const progress = quest.progress;
  if (!progress) return null;
  const current = Number(progress.current) || 0;
  const target = Number(progress.target) || 0;
  if (quest.slug === "goal_100") return `${Math.round(current)}% цели`;
  if (quest.slug === "qualifying_days_5") return `${current}/${target || 5} дней`;
  if (quest.slug === "good_sleep_5") return `${current}/${target || 5} ночей`;
  if (quest.slug === "long_workout_2h" || quest.slug === "long_workout_3h" || quest.slug === "high_intensity" || quest.slug === "trainer_week") {
    return current >= target && target > 0 ? "1/1" : "0/1";
  }
  if (target <= 0) return null;
  return `${current}/${target}${progress.unit ? ` ${progress.unit}` : ""}`;
}
