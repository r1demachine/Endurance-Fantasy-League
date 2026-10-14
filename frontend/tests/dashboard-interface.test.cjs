const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const dashboard = read("src/app/dashboard/page.tsx");
const profile = read("src/app/profile/page.tsx");
const layout = read("src/app/layout.tsx");
const globalCss = read("src/app/globals.css");
const compete = read("src/app/compete/page.tsx");
const pageTransition = read("src/components/PageTransition.tsx");
const header = read("src/components/Header.tsx");
const yearChart = read("src/components/dashboard/YearWeeksChart.tsx");
const questsBoard = read("src/components/dashboard/QuestsBoard.tsx");
const weekBlock = read("src/components/dashboard/WeekBlock.tsx");
const activityCard = read("src/components/ActivityCard.tsx");
const workoutsSection = read("src/components/dashboard/DashboardWorkoutsSection.tsx");
const workoutsList = read("src/components/dashboard/WorkoutsList.tsx");
const activityUpload = read("src/components/ActivityUpload.tsx");
const settingsModal = read("src/components/ProfileSettingsModal.tsx");
const modalComponent = read("src/components/Modal.tsx");
const helpTip = read("src/components/ui/HelpTip.tsx");
const weeklyLeague = read("src/components/compete/WeeklyLeaguePanel.tsx");
const ratingPanel = read("src/components/compete/RatingPanel.tsx");

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

test("long dashboard explanations are tucked behind accessible HelpTip controls", () => {
  assert.match(helpTip, /aria-label=\{label\}/);
  assert.match(helpTip, /aria-expanded=\{open\}/);
  assert.match(helpTip, /aria-describedby=\{open \? tooltipId : undefined\}/);
  assert.match(helpTip, /onMouseEnter/);
  assert.match(helpTip, /onPointerDown/);
  assert.match(helpTip, /closeOnOutsidePointer/);
  assert.match(helpTip, /closeOnEscape/);
  assert.match(weekBlock, /<HelpTip label="Пояснение к разбивке XP">/);
  assert.doesNotMatch(weekBlock, /<p className="mt-2 text-\[10px\] leading-relaxed text-\[#666\]">/);
  assert.match(weekBlock, /<HelpTip label="Что такое League Score">/);
  assert.match(questsBoard, /<HelpTip label="О прогрессе недельных достижений">/);
  assert.doesNotMatch(questsBoard, /<p className="mt-1 text-xs text-\[#666\]">Прогресс считается/);
  assert.match(questsBoard, /<HelpTip label="Как работают дневные бонусы">/);
  assert.match(weeklyLeague, /<HelpTip label="Как работает Weekly League">/);
  assert.doesNotMatch(weeklyLeague, /Недельный League Score с группировкой по дивизионам\. Пока участников/);
  assert.match(ratingPanel, /<HelpTip label="Как устроен общий рейтинг">/);
  assert.match(workoutsSection, /<HelpTip label="Как выбрать неделю тренировок">/);
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


test("global gradient stays fixed while dashboard and profile sections stagger top to bottom", () => {
  assert.ok(layout.includes("fixed inset-0 z-0 bg-gradient-to-br from-[#171a38]"));
  assert.equal(pageTransition.includes("bg-gradient-to-br"), false);
  assert.equal(pageTransition.includes('x: "100%"'), false);
  assert.equal(pageTransition.includes('x: "-100%"'), false);
  assert.equal(pageTransition.includes("clipPath:"), false);
  assert.equal(pageTransition.includes("filter:"), false);
  assert.ok(pageTransition.includes("key={pathname}"));
  assert.ok(pageTransition.includes("staggerChildren: 0.05, staggerDirection: 1"));
  assert.ok(pageTransition.includes('x: direction > 0 ? "100%" : "-100%"'));
  assert.ok(pageTransition.includes('x: direction > 0 ? "-100%" : "100%"'));
  assert.ok(pageTransition.includes('"/dashboard": 1'));
  assert.ok(pageTransition.includes('"/compete": 2'));
  assert.ok(pageTransition.includes('"/profile": 3'));
  assert.ok(dashboard.includes("variants={sectionStaggerVariants}"));
  assert.ok(profile.includes("variants={sectionStaggerVariants}"));
  assert.ok(dashboard.includes("variants={sectionItemVariants}"));
  assert.ok(profile.includes("variants={sectionItemVariants}"));
  assert.ok(compete.includes("variants={sectionStaggerVariants}"));
  assert.ok(compete.includes("custom={transitionDirection}"));
  assert.equal((activityUpload.match(/timeout: UPLOAD_REQUEST_TIMEOUT_MS/g) || []).length, 2);
  assert.ok(globalCss.includes("scroll-behavior: smooth"));
  assert.ok(globalCss.includes("@media (prefers-reduced-motion: reduce)"));
  assert.ok(globalCss.includes("overflow-x: hidden"));
  assert.ok(modalComponent.includes("overflow-y-auto scroll-smooth"));
  assert.ok(settingsModal.includes("overflow-y-auto scroll-smooth"));
  assert.equal(globalCss.includes("scroll-snap-"), false);

  for (const routeFile of [
    "src/app/page.tsx",
    "src/app/login/page.tsx",
    "src/app/dashboard/page.tsx",
    "src/app/profile/page.tsx",
    "src/app/compete/page.tsx",
    "src/app/u/[username]/page.tsx",
  ]) {
    assert.equal(
      read(routeFile).includes("bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2]"),
      false,
      routeFile
    );
  }
});
