const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const activity = read("src/components/ActivityCard.tsx");
const tooltip = read("src/components/XpTooltip.tsx");
const rating = read("src/components/compete/RatingPanel.tsx");
const profile = read("src/app/profile/page.tsx");

test("activity XP breakdown loads lazily, caches success, and supports retry", () => {
  assert.match(activity, /authApi\.get\(\`\/api\/activities\/\$\{act\.id\}\/xp\`\)/);
  assert.match(activity, /if \(breakdown \|\| loading\) return/);
  assert.match(activity, /if \(next && !breakdown && !loading\) void loadBreakdown\(\)/);
  assert.match(activity, /<ErrorState message=\{error\} onRetry=\{\(\) => void loadBreakdown\(\)\}/);
  for (const label of ["За нагрузку этой тренировки", "Регулярность (за день)", "Quality (за неделю)", "Квесты дня", "Итого"]) {
    assert.ok(activity.includes(label), `missing breakdown row: ${label}`);
  }
  assert.match(activity, /Потолок 300 TSS в день/);
  assert.match(activity, /распределяемых между тренировками пропорционально их TSS/);
});

test("XP tooltip supports accessible explanatory text as well as chart mode", () => {
  assert.match(tooltip, /content\?: string/);
  assert.match(tooltip, /role="tooltip"/);
  assert.match(activity, /<XpTooltip label=/);
});

test("weekly league is separate, grouped by division, and limited to ten entries", () => {
  assert.match(rating, /label: "Global"/);
  assert.match(rating, /label: "Друзья"/);
  assert.match(rating, /label: "Weekly"/);
  assert.match(rating, /scope === "weekly" && \(index === 0 \|\| entries\[index - 1\]\?\.division !== entry\.division\)/);
  assert.match(rating, /const params = \{ scope: requestedScope, limit: 10 \}/);
  assert.match(rating, /Лига формируется/);
  assert.match(rating, /Ты — место \{yourRank\}/);
  assert.match(rating, /<Skeleton label="Загружаем рейтинг"/);
  assert.match(rating, /<ErrorState message=\{errors\[scope\]/);
});

test("profile stats are URL-driven and use the stats API for all three ranges", () => {
  assert.match(profile, /authApi\.get\("\/api\/profile\/stats", \{ params: \{ range: statsRange \} \}\)/);
  assert.match(profile, /value: "season", label: "Сезон"/);
  assert.match(profile, /value: "year", label: "Год"/);
  assert.match(profile, /value: "week", label: "Неделя"/);
  assert.match(profile, /params\.set\("range", nextRange\)/);
  assert.match(profile, /formatWeekRange\(statsData\.start_date\)/);
  assert.match(profile, /Сезон с /);
  assert.match(profile, /<Skeleton label="Загружаем статистику"/);
  assert.match(profile, /<ErrorState message=\{statsError\} onRetry=\{\(\) => void loadStats\(\)\}/);
});
