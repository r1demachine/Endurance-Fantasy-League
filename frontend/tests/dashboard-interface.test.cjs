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
const activityCard = read("src/components/ActivityCard.tsx");
const workoutsSection = read("src/components/dashboard/DashboardWorkoutsSection.tsx");
const workoutsList = read("src/components/dashboard/WorkoutsList.tsx");
const activityUpload = read("src/components/ActivityUpload.tsx");
const settingsModal = read("src/components/ProfileSettingsModal.tsx");

test("dashboard removes weekly XP events and puts workouts after the complete achievements list", () => {
  const positions = [
    dashboard.indexOf("<YearWeeksChart"),
    dashboard.indexOf("<WeekBlock"),
    dashboard.indexOf("<QuestsBoard"),
    dashboard.indexOf("<DashboardWorkoutsSection"),
  ];
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual(positions, [...positions].sort((a, b) => a - b));
  assert.doesNotMatch(dashboard, /EventsFeed|setEvents|recent_events/);
  assert.match(questsBoard, /useState\(true\)/);
  assert.match(questsBoard, /Показать все/);
  assert.match(questsBoard, /quest\.status === "earned"/);
  assert.match(questsBoard, /quest\.progress_reason/);
});

test("weekly and lifetime achievements are shown as separate sections with live progress", () => {
  assert.match(questsBoard, /quest.kind === "weekly"/);
  assert.match(questsBoard, /Недельные достижения/);
  assert.match(questsBoard, /formatWeekRange\(weekStart\)/);
  assert.match(questsBoard, /Разовые достижения/);
  assert.match(questsBoard, /progress.steps.map/);
  assert.match(questsBoard, /aria-valuenow=\{Math.min\(current, target\)\}/);
});

test("year chart and weekly summary share week state without clipped outlines", () => {
  assert.match(dashboard, /selectedWeekStart=\{selectedWeekStart \|\| weekData\?\.week_start \|\| ""\}/);
  assert.match(dashboard, /onWeekChange=\{setSelectedWeekStart\}/);
  assert.match(dashboard, /const loadQuests = useCallback\(async \(weekStart = selectedWeekStart\)/);
  assert.match(dashboard, /params: weekStart \? \{ week_start: weekStart \} : \{\}/);
  assert.match(yearChart, /overflow-x-auto overscroll-x-contain px-1 pb-2 pt-2/);
  assert.match(yearChart, /selected && week\.is_current \? "ring-2 ring-\[#5866f2\] ring-offset-1 outline outline-2 outline-black outline-offset-2"/);
  assert.match(yearChart, /week\.is_current \? "ring-2 ring-black ring-offset-1"/);
  assert.match(yearChart, /aria-label=\{label\}/);
  assert.match(yearChart, /repeating-linear-gradient/);
});

test("sources open through the existing portal settings modal on the current page", () => {
  assert.doesNotMatch(workoutsList, /\/profile\?settings=sources|href=.*settings=sources/);
  assert.match(workoutsList, /<button type="button" onClick=\{onOpenSources\}/);
  assert.match(workoutsSection, /onOpenSources: \(\) => void/);
  assert.match(workoutsSection, /onOpenSources=\{onOpenSources\}/);
  assert.match(dashboard, /onOpenSources=\{openSourceSettings\}/);
  assert.match(dashboard, /setSettingsTab\("sources"\)/);
  assert.match(dashboard, /<ProfileSettingsModal[\s\S]*?onActivityUploaded=\{refreshDashboardAfterDataChange\}/);
  assert.match(settingsModal, /<Modal title="Настройки"[^>]*variant="settings"/);
  assert.match(settingsModal, /<ActivityUpload onUploaded=\{onActivityUploaded\} \/>/);
  assert.match(activityUpload, /onUploaded\?: \(\) => void \| Promise<void>/);
  assert.match(activityUpload, /await onUploaded\(\)/);
  assert.doesNotMatch(header, /href: "\/training"/);
  assert.equal(fs.existsSync(path.join(__dirname, "..", "src/app/training/page.tsx")), false);
});

test("manual uploads and sync refresh current activities and achievements", () => {
  assert.match(dashboard, /const refreshDashboardAfterDataChange = useCallback/);
  assert.match(dashboard, /await loadQuests\(\)/);
  assert.match(dashboard, /await refreshDashboardAfterDataChange\(\)/);
  assert.match(weekBlock, /Квесты и бонусы/);
  assert.match(weekBlock, /«Нагрузка» — XP за нагрузку тренировок/);
  assert.match(weekBlock, /дневные бонусы \+20 XP/);
  assert.match(weekBlock, /максимум до 120%/);
  assert.match(dashboard, /<ActivityUpload onUploaded=\{refreshDashboardAfterDataChange\} \/>/);
  assert.match(dashboard, /setQuests\(\[\]\)/);
  assert.match(dashboard, /setQuestsError\(getApiErrorMessage/);
});

test("all visible week selectors use the shared Russian week formatter", () => {
  assert.match(weekBlock, /formatWeekRange\(selectedWeekStart\)/);
  assert.match(weekBlock, /formatWeekRange\(option\.week_start\)/);
  assert.match(workoutsSection, /formatWeekRange\(week\.week_start\)/);
  assert.match(workoutsList, /formatWeekRange\(selectedWeekStart\)/);
});


test("activity XP card separates attached achievements from general bonuses", () => {
  assert.match(activityCard, /Достижения за эту тренировку/);
  assert.match(activityCard, /activityAwards\?\.total_xp/);
  assert.match(activityCard, /for_this_activity_xp/);
  assert.doesNotMatch(activityCard, /Общие бонусы дня|Общие бонусы недели|Регулярность \(за день\)|Quality \(за неделю\)|Квесты дня/);
  assert.match(questsBoard, /dailyBonusDays/);
  assert.match(questsBoard, /Дневные бонусы за выбранную неделю/);
});
