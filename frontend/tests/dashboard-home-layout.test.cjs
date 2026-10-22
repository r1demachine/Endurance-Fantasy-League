const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const dashboard = read("src/app/dashboard/page.tsx");
const today = read("src/components/dashboard/TodayCard.tsx");
const checkins = read("src/components/CheckInsPanel.tsx");
const quests = read("src/components/dashboard/QuestsBoard.tsx");
const profile = read("src/app/profile/page.tsx");

test("today and check-ins render inside one responsive two-column container", () => {
  assert.match(dashboard, /aria-label="Сегодня и чек-ины"/);
  assert.match(dashboard, /xl:grid-cols-2/);
  assert.match(dashboard, /<TodayCard[\s\S]*?level=\{Number\(data\.user\?\.level\)/);
  assert.match(dashboard, /<CheckInsPanel[\s\S]*?autoPromptActivityIds=\{newlySyncedActivityIds\}/);
  assert.match(today, /Уровень \{Math\.max\(1, number\(level\)\)\}/);
  assert.match(today, /Доступные задачи/);
});

test("newly synced workouts are queued for sequential post-workout check-in dialogs", () => {
  assert.match(dashboard, /knownActivityIds/);
  assert.match(dashboard, /setNewlySyncedActivityIds\(newIds\)/);
  assert.match(checkins, /const requestedIds = new Set\(autoPromptActivityIds \?\? \[\]\)/);
  assert.match(checkins, /setActivityQueue\(\(current\) =>/);
  assert.match(checkins, /<Modal title="Чек-ин после тренировки"/);
  assert.match(checkins, /setActivityQueue\(\(current\) => current\.filter\(\(id\) => id !== activityId\)\)/);
});

test("manual sync requests a rolling 14-day window including today", () => {
  assert.match(dashboard, /sinceDate\.setDate\(sinceDate\.getDate\(\) - 13\)/);
  assert.match(dashboard, /authApi\.post\("\/api\/sync", null, \{ params: \{ since \} \}\)/);
});

test("achievements use weekly and lifetime tabs with weekly selected by default", () => {
  assert.match(quests, /useState<"weekly" \| "lifetime">\("weekly"\)/);
  assert.match(quests, /role="tablist" aria-label="Категории достижений"/);
  assert.match(quests, /onClick=\{\(\) => setActiveTab\("weekly"\)\}/);
  assert.match(quests, /onClick=\{\(\) => setActiveTab\("lifetime"\)\}/);
  assert.match(quests, /activeTab === "weekly" && weeklyQuests\.length > 0/);
  assert.match(quests, /activeTab === "lifetime" && lifetimeQuests\.length > 0/);
});

test("season recap is on profile and week recap card is no longer rendered on dashboard", () => {
  assert.match(profile, /import \{ SeasonRecapCard \} from "@\/components\/dashboard\/RecapCards"/);
  assert.match(profile, /<SeasonRecapCard userName=/);
  assert.doesNotMatch(dashboard, /<WeekRecapCard/);
  assert.doesNotMatch(dashboard, /<SeasonRecapCard/);
});


test("TodayCard hides the XP breakdown and weekly goal, and groups three training alternatives", () => {
  assert.doesNotMatch(today, /title="Нагрузка"/);
  assert.doesNotMatch(today, /title="Дневной бонус"/);
  assert.doesNotMatch(today, /title="Хороший сон"/);
  assert.doesNotMatch(today, /title="Достижения сегодня"/);
  assert.match(today, /quest\.slug !== "goal_100"/);
  assert.match(today, /title="Ключевая тренировка"/);
  assert.match(today, /alternativeSlugs\.has\(quest\.slug\)/);
  assert.match(today, /trailing=\{alternativeDone \? "1\/1" : "0\/1"\}/);
  assert.match(today, /достаточно выполнить любую одну/);
});

test("top headers align on desktop, streak cards share a compact grid, and check-ins do not stretch into an empty panel", () => {
  assert.match(today, /xl:h-\[132px\]/);
  assert.match(checkins, /xl:h-\[132px\]/);
  assert.match(today, /grid min-w-0 grid-cols-2 gap-2 md:grid-cols-3/);
  assert.match(dashboard, /xl:grid-cols-2 xl:items-start/);
});
