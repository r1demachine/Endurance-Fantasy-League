export type LifetimeAchievementSummaryItem = {
  slug: string;
  kind?: "weekly" | "lifetime";
  status: "earned" | "open" | "unavailable" | string;
};

export function getLifetimeAchievementModel(quests: LifetimeAchievementSummaryItem[]) {
  const all = quests.filter((quest) => quest.kind !== "weekly");
  const available = all.filter((quest) => quest.status !== "unavailable");
  const earned = available.filter((quest) => quest.status === "earned");
  const unearned = all.filter((quest) => quest.status !== "earned");
  const availableCount = available.length;
  const earnedCount = earned.length;

  return {
    all,
    earned,
    unearned,
    availableCount,
    earnedCount,
    allAvailableEarned: availableCount > 0 && earnedCount === availableCount,
  };
}
