const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const dashboard = read("src/app/dashboard/page.tsx");
const trainingPage = read("src/app/training/page.tsx");
const header = read("src/components/Header.tsx");
const trainingSections = read("src/components/dashboard/DashboardTrainingSections.tsx");
const yearChart = read("src/components/dashboard/YearWeeksChart.tsx");
const questsBoard = read("src/components/dashboard/QuestsBoard.tsx");
const weekBlock = read("src/components/dashboard/WeekBlock.tsx");
const workoutsList = read("src/components/dashboard/WorkoutsList.tsx");

test("dashboard blocks appear in the requested order and duel fetching is removed", () => {
  const positions = [
    dashboard.indexOf("<SectionTitle>Level</SectionTitle>"),
    dashboard.indexOf("<YearWeeksChart"),
    dashboard.indexOf("<WeekBlock"),
    dashboard.indexOf("<EventsFeed"),
    dashboard.indexOf("<QuestsBoard"),
  ];
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual(positions, [...positions].sort((a, b) => a - b));
  assert.doesNotMatch(dashboard, /\/api\/duels|DuelSummary|Ближайшая дуэль/);
});

test("the calendar-year chart and weekly summary use the same selectedWeekStart state", () => {
  assert.match(dashboard, /selectedWeekStart=\{selectedWeekStart \|\| weekData\?\.week_start \|\| ""\}/);
  assert.match(dashboard, /onWeekChange=\{setSelectedWeekStart\}/);
  assert.match(dashboard, /selectedWeekStart=\{selectedWeekStart \|\| weekData\?\.week_start \|\| ""\}[\s\S]*?<WeekBlock/);
  assert.match(yearChart, /authApi\.get\("\/api\/season\/weeks", \{[\s\S]*params: year === null \? \{\} : \{ year \}/);
  assert.match(yearChart, /setYear\(Number\(response\.data\.year\)\)/);
  assert.match(yearChart, /onClick=\{\(\) => onWeekChange\(week\.week_start\)\}/);
  assert.match(yearChart, /aria-label=\{label\}/);
  assert.match(yearChart, /week\.is_future \? "opacity-30"/);
  assert.match(yearChart, /repeating-linear-gradient/);
  assert.match(yearChart, /#38bdf8/);
  assert.match(yearChart, /aria-label="Легенда графика"/);
});

test("XP Dynamics is available on /training under the Graphs tab, not on dashboard", () => {
  assert.doesNotMatch(dashboard, /XpDynamics|XP Dynamics/);
  assert.match(header, /href: "\/training", label: "Тренировки"/);
  assert.match(trainingPage, /<DashboardTrainingSections/);
  assert.match(trainingSections, /role="tab"\s+aria-selected=\{activeTab === "graphs"\}/);
  const graphsPanel = trainingSections.slice(trainingSections.indexOf('{activeTab === "graphs"'));
  assert.match(graphsPanel, /<XpDynamics/);
  assert.match(graphsPanel, /<SeasonWeeksChart/);
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
  assert.match(questsBoard, /Загружаем достижения/);
});

test("all week selectors and workout list use the single Russian week formatter", () => {
  assert.match(weekBlock, /formatWeekRange\(selectedWeekStart\)/);
  assert.match(weekBlock, /formatWeekRange\(option\.week_start\)/);
  assert.match(trainingSections, /formatWeekRange\(option\.week_start\)/);
  assert.match(workoutsList, /formatWeekRange\(selectedWeekStart\)/);
});
