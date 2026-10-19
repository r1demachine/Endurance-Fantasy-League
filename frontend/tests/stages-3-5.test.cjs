const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const activity = read("src/components/ActivityCard.tsx");
const tooltip = read("src/components/XpTooltip.tsx");
const floatingTooltip = read("src/components/ui/FloatingTooltip.tsx");
const rating = read("src/components/compete/RatingPanel.tsx");
const weekly = read("src/components/compete/WeeklyLeaguePanel.tsx");
const compete = read("src/app/compete/page.tsx");
const profile = read("src/app/profile/page.tsx");

test("activity XP breakdown loads lazily, caches success, and supports retry", () => {
  assert.match(activity, /authApi\.get\(\`\/api\/activities\/\$\{act\.id\}\/xp\`\)/);
  assert.match(activity, /if \(breakdown \|\| loading\) return/);
  assert.match(activity, /if \(next && !breakdown && !loading\) void loadBreakdown\(\)/);
  assert.match(activity, /<ErrorState message=\{error\} onRetry=\{\(\) => void loadBreakdown\(\)\}/);
  for (const label of ["За нагрузку этой тренировки", "Достижения за эту тренировку", "Итого"]) {
    assert.ok(activity.includes(label), `missing breakdown row: ${label}`);
  }
  for (const obsoleteLabel of ["Регулярность (за день)", "Quality (за неделю)", "Квесты дня"]) {
    assert.ok(!activity.includes(obsoleteLabel), `obsolete breakdown label: ${obsoleteLabel}`);
  }
  assert.ok(activity.includes("activityAwardsTotal"));
  assert.ok(activity.includes("for_this_activity_xp"));
  assert.doesNotMatch(activity, /Общие бонусы дня|Общие бонусы недели|related\?\.general/);
  assert.match(activity, /Потолок — 300 TSS в день/);
  assert.match(activity, /распределяется между тренировками пропорционально их TSS/);
});

test("XP tooltip supports accessible explanatory text as well as chart mode", () => {
  assert.match(tooltip, /content\?: ReactNode/);
  assert.match(tooltip, /<FloatingTooltip/);
  assert.match(floatingTooltip, /role="tooltip"/);
  assert.match(activity, /<XpTooltip label=/);
});

test("weekly league is its own container before the Global/Friends rating", () => {
  assert.match(compete, /<WeeklyLeaguePanel\s*\/>[\s\S]*?<RatingPanel\s*\/>/);
  assert.match(rating, /label: "Общий"/);
  assert.match(rating, /label: "Друзья"/);
  assert.doesNotMatch(rating, /label: "Weekly"|scope === "weekly"|entry\.division|entry\.score/);
  assert.match(rating, /params: \{ scope: requestedScope, limit: 10 \}/);
  assert.match(rating, /"Рейтинг пока пуст\."/);
  assert.match(rating, /<Skeleton label="Загружаем рейтинг"/);
  assert.match(rating, /<ErrorState message=\{errors\[scope\]/);
  assert.match(weekly, /scope: "weekly", limit: 10/);
  assert.match(weekly, /entry\.division/);
  assert.match(weekly, /entry\.score/);
  assert.doesNotMatch(weekly, /Лига формируется/);
  assert.match(weekly, /board\?\.beta/);
  assert.match(weekly, /Ты первый, позови друзей/);
  assert.match(weekly, /Ты — место \{yourRank\}/);
  assert.match(weekly, /<Skeleton label="Загружаем Weekly League"/);
  assert.match(weekly, /<ErrorState message=\{error\} onRetry=\{\(\) => void loadWeekly\(\)\}/);
});

test("profile stats are URL-driven and the unwanted min-height gaps are removed", () => {
  assert.match(profile, /authApi\.get\("\/api\/profile\/stats", \{ params: \{ range: statsRange \} \}\)/);
  assert.match(profile, /value: "season", label: "Сезон"/);
  assert.match(profile, /value: "year", label: "Год"/);
  assert.match(profile, /value: "week", label: "Неделя"/);
  assert.match(profile, /params\.set\("range", nextRange\)/);
  assert.match(profile, /formatWeekRange\(statsData\.start_date\)/);
  assert.match(profile, /Сезон с /);
  assert.match(profile, /<Skeleton label="Загружаем статистику"/);
  assert.match(profile, /<ErrorState message=\{statsError\} onRetry=\{\(\) => void loadStats\(\)\}/);
  assert.doesNotMatch(profile, /min-h-\[300px\]|min-h-\[220px\]/);
});
