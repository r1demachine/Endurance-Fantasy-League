const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const dashboard = read("src/app/dashboard/page.tsx");
const header = read("src/components/Header.tsx");
const yearChart = read("src/components/dashboard/YearWeeksChart.tsx");
const questsBoard = read("src/components/dashboard/QuestsBoard.tsx");
const weekBlock = read("src/components/dashboard/WeekBlock.tsx");
const workoutsSection = read("src/components/dashboard/DashboardWorkoutsSection.tsx");
const workoutsList = read("src/components/dashboard/WorkoutsList.tsx");

test("dashboard blocks appear in order and duel fetching is removed", () => {
  const positions = [
    dashboard.indexOf("<SectionTitle>Level</SectionTitle>"),
    dashboard.indexOf("<YearWeeksChart"),
    dashboard.indexOf("<WeekBlock"),
    dashboard.indexOf("<QuestsBoard"),
    dashboard.indexOf("<DashboardWorkoutsSection"),
  ];
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual(positions, [...positions].sort((a, b) => a - b));
  assert.doesNotMatch(dashboard, /EventsFeed|XP-событий недели/);
  assert.doesNotMatch(dashboard, /\/api\/duels|DuelSummary|Ближайшая дуэль/);
});

test("selected and current week frames have room and use full outlines", () => {
  assert.match(yearChart, /overflow-x-auto overscroll-x-contain px-1 pb-2 pt-2/);
  assert.match(yearChart, /selected && week\.is_current \? "ring-2 ring-\[#5866f2\] ring-offset-1 outline outline-2 outline-black outline-offset-2"/);
  assert.match(yearChart, /week\.is_current \? "ring-2 ring-black ring-offset-1"/);
  assert.match(yearChart, /onClick=\{\(\) => onWeekChange\(week\.week_start\)\}/);
  assert.match(yearChart, /aria-label=\{label\}/);
  assert.match(yearChart, /week\.is_future \? "opacity-30"/);
  assert.match(yearChart, /repeating-linear-gradient/);
});

test("workout list is beneath achievements on dashboard and the Training navigation tab is removed", () => {
  assert.match(dashboard, /<QuestsBoard[\s\S]*?<DashboardWorkoutsSection/);
  assert.match(dashboard, /selectedWeekStart=\{selectedWeekStart \|\| weekData\?\.week_start \|\| ""\}[\s\S]*?onWeekChange=\{setSelectedWeekStart\}/);
  assert.doesNotMatch(header, /href: "\/training"|label: "Тренировки"/);
  assert.match(workoutsSection, /<WorkoutsList/);
  assert.match(workoutsSection, /Выбрать неделю для списка тренировок/);
  assert.match(workoutsList, /onClick=\{onOpenSources\}/);
  assert.match(workoutsSection, /onOpenSources=\{onOpenSources\}/);
  assert.doesNotMatch(workoutsList, /\/profile\?settings=sources/);
  assert.doesNotMatch(workoutsList, /\/training/);
  assert.throws(() => fs.accessSync(path.join(__dirname, "..", "src/app/training/page.tsx")));
});

test("achievement cards render progress, sleep slots, unavailable reasons, and earned date", () => {
  assert.match(dashboard, /authApi\.get\("\/api\/quests"\)/);
  assert.match(dashboard, /loading=\{questsLoading\}/);
  assert.match(dashboard, /error=\{questsError\}/);
  assert.match(questsBoard, /role="progressbar"/);
  assert.match(questsBoard, /quest\.slug === "sleep_connected"/);
  assert.match(questsBoard, /\[0, 1, 2\]\.map/);
  assert.match(questsBoard, /quest\.progress_reason/);
  assert.match(questsBoard, /Получено \{quest\.earned_at\}/);
  assert.match(questsBoard, /<ErrorState message=\{error\} onRetry=\{onRetry\}/);
});

test("all week selectors and workout list use the single Russian week formatter", () => {
  assert.match(weekBlock, /formatWeekRange\(selectedWeekStart\)/);
  assert.match(weekBlock, /formatWeekRange\(option\.week_start\)/);
  assert.match(workoutsSection, /formatWeekRange\(week\.week_start\)/);
  assert.match(workoutsList, /formatWeekRange\(selectedWeekStart\)/);
});
