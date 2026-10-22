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
  assert.match(today, /h-\[58px\]/);
  assert.match(checkins, /h-\[58px\]/);
  assert.match(dashboard, /aria-label="Показатели спортсмена"/);
  assert.match(dashboard, /formatStreak\(Number\(todayData\.streak\)/);
  assert.match(dashboard, /formatSecondsLeftToday\(Number\(todayData\.seconds_left_today\)/);
  assert.match(dashboard, /grid min-w-0 grid-cols-2 gap-1 border-b-2 border-black bg-\[#f4f4f0\] p-1 sm:grid-cols-4 xl:flex xl:flex-nowrap/);
  assert.match(dashboard, /xl:grid-cols-2 xl:items-stretch/);
});


test("dashboard hides requested helper copy and shows equal-height compact cards", () => {
  assert.doesNotMatch(today, /Твой план и прогресс/);
  assert.doesNotMatch(today, /Задачи и достижения выбранной календарной недели/);
  assert.doesNotMatch(checkins, /Ответы видны только тебе и не влияют на XP, достижения или рейтинги/);
  assert.doesNotMatch(checkins, /Сегодня заполнено\. Неизвестные показатели остались пустыми\./);
  assert.doesNotMatch(checkins, /className="mt-2 text-xs leading-relaxed text-\[#666\]">\{importedSleepText\(sleep\)\}<\/p>/);
  assert.match(checkins, /const visibleActivities = activities\.slice\(0, 3\)/);
  assert.doesNotMatch(checkins, /visibleActivityCount|nextActivityOffset|loadMoreActivities|Показать более ранние тренировки|Загрузить предыдущие тренировки/);
  assert.match(today, /className="flex h-full min-w-0 flex-col bg-white"/);
  assert.match(checkins, /className="flex h-full min-w-0 flex-col border-b-2 border-black bg-\[#f4f4f0\]"/);
  assert.match(dashboard, /className="h-full min-w-0 xl:border-r-2 xl:border-black"/);
  assert.match(dashboard, /className="h-full min-w-0">/);
});

test("deload eligibility explanation appears only after clicking an unavailable deload action", () => {
  const weekBlock = read("src/components/dashboard/WeekBlock.tsx");
  assert.match(weekBlock, /const \[deloadReasonShownForWeek, setDeloadReasonShownForWeek\] = useState<string \| null>\(null\)/);
  assert.match(weekBlock, /onClick=\{handleEnableDeload\}/);
  assert.match(weekBlock, /deloadReasonShownForWeek === selectedWeekStart && weekData\.is_current_week && !weekData\.can_set_deload/);
  assert.match(weekBlock, /Не менее 2 из предыдущих 3 недель должны достигать 75% baseline\./);
  assert.doesNotMatch(weekBlock, /\{!weekData\.can_set_deload && weekData\.deload_block_reason &&/);
  assert.match(weekBlock, /flex flex-wrap items-center gap-2/);
});
