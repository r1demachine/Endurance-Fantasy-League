const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const dashboard = read("src/app/dashboard/page.tsx");
const profile = read("src/app/profile/page.tsx");
const publicProfile = read("src/app/u/[username]/page.tsx");
const layout = read("src/app/layout.tsx");
const globalCss = read("src/app/globals.css");
const compete = read("src/app/compete/page.tsx");
const pageTransition = read("src/components/PageTransition.tsx");
const floatingTooltip = read("src/components/ui/FloatingTooltip.tsx");
const syncRouter = read("../backend/app/routers/sync.py");
const xpV6 = read("../backend/app/services/xp_v6.py");
const header = read("src/components/Header.tsx");
const yearChart = read("src/components/dashboard/YearWeeksChart.tsx");
const questsBoard = read("src/components/dashboard/QuestsBoard.tsx");
const weekBlock = read("src/components/dashboard/WeekBlock.tsx");
const activityCard = read("src/components/ActivityCard.tsx");
const weekCalendar = read("src/components/dashboard/WeekCalendar.tsx");
const xpDetails = read("src/components/ActivityXpDetails.tsx");
const activityUpload = read("src/components/ActivityUpload.tsx");
const settingsModal = read("src/components/ProfileSettingsModal.tsx");
const modalComponent = read("src/components/Modal.tsx");
const helpTip = read("src/components/ui/HelpTip.tsx");
const xpTooltip = read("src/components/XpTooltip.tsx");
const weeklyLeague = read("src/components/compete/WeeklyLeaguePanel.tsx");
const ratingPanel = read("src/components/compete/RatingPanel.tsx");

test("dashboard removes weekly XP events and puts workouts after the complete achievements list", () => {
  const positions = [
    dashboard.indexOf("<YearWeeksChart"),
    dashboard.indexOf("<WeekBlock"),
    dashboard.indexOf("<QuestsBoard"),
    dashboard.indexOf("<WeekCalendar"),
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
  assert.match(weekCalendar, /<button[\s\S]*?onClick=\{onOpenSources\}/);
  assert.match(weekCalendar, /Источники/);
  assert.match(dashboard, /onOpenSources=\{openSourceSettings\}/);
  assert.match(dashboard, /<WeekCalendar[\s\S]*?weekData=\{weekData\}/);
  assert.doesNotMatch(dashboard, /WorkoutsList|DashboardWorkoutsSection|weekActivities/);
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
  assert.match(weekCalendar, /aria-label="Выбрать неделю календаря"/);
});

test("all visible week selectors use the shared Russian week formatter", () => {
  assert.match(weekBlock, /formatWeekRange\(selectedWeekStart\)/);
  assert.match(weekBlock, /formatWeekRange\(option\.week_start\)/);
  assert.match(weekCalendar, /formatWeekRange\(activeWeek\)/);
  assert.match(weekCalendar, /weekOptions\.map/);
});


test("activity XP card separates attached achievements from general bonuses", () => {
  assert.match(xpDetails, /Достижения за эту тренировку/);
  assert.match(xpDetails, /activityAwardsTotal/);
  assert.match(xpDetails, /for_this_activity_xp/);
  assert.match(activityCard, /<ActivityXpDetails act=\{act\} \/>/);
  assert.doesNotMatch(xpDetails, /Общие бонусы дня|Общие бонусы недели|Регулярность \(за день\)|Quality \(за неделю\)|Квесты дня/);
  assert.match(questsBoard, /dailyBonusDays/);
  assert.match(questsBoard, /Дневные бонусы за выбранную неделю/);
});



test("weekly execution bonuses are rendered through the existing weekly quest cards", () => {
  assert.match(questsBoard, /goal_100:/);
  assert.match(questsBoard, /ideal_week:/);
  assert.match(questsBoard, /Получите \+20 XP один раз за неделю/);
  assert.match(questsBoard, /Получите \+40 XP один раз за неделю/);
  assert.match(questsBoard, /Недельные достижения/);
  assert.match(questsBoard, /quest\.reward/);
  assert.match(questsBoard, /quest\.progress/);
  assert.match(read("../backend/app/services/quests.py"), /"slug": "goal_100"/);
  assert.match(read("../backend/app/services/quests.py"), /"slug": "ideal_week"/);
  assert.match(read("../backend/app/services/quests.py"), /"quest:goal_100:/);
  assert.match(read("../backend/app/services/quests.py"), /"quest:ideal_week:/);
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
  assert.ok(pageTransition.includes('window.addEventListener("wheel", onWheel, { passive: false })'));
  assert.ok(pageTransition.includes("requestAnimationFrame(animateScroll)"));
  assert.ok(pageTransition.includes("canInnerPanelScroll"));
  assert.ok(pageTransition.includes("event.preventDefault()"));
  assert.ok(pageTransition.includes("prefers-reduced-motion: reduce"));
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


test("XP explanations use viewport portals and achievement descriptions stay hidden until hover", () => {
  assert.ok(floatingTooltip.includes("createPortal("));
  assert.ok(floatingTooltip.includes("z-[9999]"));
  assert.ok(helpTip.includes("<FloatingTooltip"));
  assert.ok(xpTooltip.includes("<FloatingTooltip"));
  assert.ok(questsBoard.includes("<FloatingTooltip"));
  assert.ok(questsBoard.includes("anchorRef={anchorRef}"));
  assert.ok(questsBoard.includes("QUEST_EXPLANATIONS"));
  assert.ok(questsBoard.includes("onMouseEnter"));
  assert.equal(questsBoard.includes("group-hover:opacity-100"), false);
  assert.ok(!questsBoard.includes('className="mt-1 text-[9px] font-bold uppercase tracking-widest text-[#666]">{quest.desc}'));
  assert.ok(xpDetails.includes('label="Итого"'));
  assert.ok(xpDetails.includes("Потолок — 300 TSS в день"));
  assert.ok(!activityCard.includes('XpTooltip label="Достижения за эту тренировку"'));
});

test("the obsolete per-workout +12 XP bonus is no longer generated or displayed", () => {
  assert.ok(!syncRouter.includes('key = `activity_bonus:45m:'));
  assert.ok(!syncRouter.includes("Тренировка ≥45 минут +"));
  assert.ok(!xpV6.includes("\nWORKOUT_BONUS_XP ="));
  assert.ok(!xpV6.includes("\nWORKOUT_BONUS_MIN_DURATION_SECONDS ="));
  assert.ok(xpV6.includes("DAILY_WORKOUT_BONUS_XP = 20.0"));
  assert.ok(syncRouter.includes("_is_retired_activity_duration_bonus"));
  assert.ok(xpDetails.includes("activityEvents = (activityAwards?.events ?? []).filter"));
});

test("global typography grows one point but restores heading and display scales", () => {
  const css = read("src/app/globals.css");
  assert.ok(css.includes("font-size: calc(1rem + 1pt)"));
  assert.ok(css.includes("--text-sm: calc(0.875rem + 1pt)"));
  assert.ok(css.includes(":where(h1, h2, h3, h4, h5, h6)"));
  assert.ok(css.includes("font-size: calc(10px + 1pt)"));
  assert.ok(css.includes("prefers-reduced-motion: reduce"));
});


test("beta league uses one shared league and invites the first athlete instead of showing formation progress", () => {
  assert.match(xpV6, /MIN_LEAGUE_SIZE = 1/);
  assert.match(xpV6, /BETA_SINGLE_LEAGUE_UNTIL_USERS = 20/);
  assert.match(syncRouter, /group_key="beta"/);
  assert.match(syncRouter, /league_ranking_key\(/);
  assert.match(weeklyLeague, /board\?\.beta/);
  assert.match(weeklyLeague, /Ты первый, позови друзей/);
  assert.match(weeklyLeague, /Скопировать ссылку/);
  assert.equal(weeklyLeague.includes("Лига формируется"), false);
  assert.match(ratingPanel, /isBeta &&/);
  assert.match(ratingPanel, /scope: "weekly", limit: 1/);
});

test("season display is API-backed and no longer rotates as demo state", () => {
  const seasons = read("src/lib/seasons.ts");
  const seasonService = read("../backend/app/services/seasons.py");
  const seasonRouter = read("../backend/app/routers/season.py");
  assert.match(seasons, /authApi\.get\("\/api\/season"/);
  assert.equal(seasons.includes("setInterval"), false);
  assert.match(seasonService, /SEASON_EPOCH = date\(2026, 9, 1\)/);
  assert.match(seasonService, /SEASONS\[number % len\(SEASONS\)\]/);
  assert.match(seasonRouter, /@router\.get\("\/season"\)/);
});

test("timezone is explicitly confirmed before timezone-dependent reminders can rely on it", () => {
  const timezonePrompt = read("src/components/TimezoneConfirmation.tsx");
  const seasonRouter = read("../backend/app/routers/season.py");
  const models = read("../backend/app/models.py");
  const main = read("../backend/app/main.py");
  assert.match(models, /timezone_confirmed = Column\(Boolean/);
  assert.match(main, /ADD COLUMN timezone_confirmed BOOLEAN/);
  assert.match(timezonePrompt, /Intl\.DateTimeFormat\(\)\.resolvedOptions\(\)\.timeZone/);
  assert.match(timezonePrompt, /authApi\.patch\("\/api\/timezone"/);
  assert.match(seasonRouter, /@router\.patch\("\/timezone"\)/);
});


test("week calendar renders seven ledger days and shares the XP breakdown component", () => {
  assert.match(dashboard, /<WeekCalendar/);
  assert.match(dashboard, /days: Array\.isArray\(result\.days\)/);
  assert.match(weekCalendar, /getCalendarWeekDates\(start\)/);
  assert.ok(weekCalendar.includes("return dates.map"));
  assert.match(weekCalendar, /lg:grid-cols-7/);
  assert.match(weekCalendar, /grid-cols-1 gap-3/);
  assert.match(weekCalendar, /weekData\?\.days/);
  assert.match(weekCalendar, /weekData\?\.week_bonuses/);
  assert.match(weekCalendar, /Сон/);
  assert.match(weekCalendar, /Sleep score/);
  assert.match(weekCalendar, /HRV/);
  assert.match(weekCalendar, /Пульс покоя/);
  assert.match(weekCalendar, /is_deload/);
  assert.match(weekCalendar, /weekData\?\.paused/);
  assert.match(weekCalendar, /focus-visible:outline/);
  assert.match(weekCalendar, /useReducedMotion/);
  assert.match(xpDetails, /\/api\/activities\/\$\{act\.id\}\/xp/);
  assert.match(publicProfile, /<ActivityCard act=\{act\} \/>/);
  assert.match(activityCard, /ActivityXpDetails act=\{act\}/);
  assert.doesNotMatch(dashboard, /WorkoutsList|DashboardWorkoutsSection/);
});

test("the retired dashboard list component is no longer referenced or kept", () => {
  assert.equal(fs.existsSync(path.join(__dirname, "..", "src/components/dashboard/WorkoutsList.tsx")), false);
  assert.equal(fs.existsSync(path.join(__dirname, "..", "src/components/dashboard/DashboardWorkoutsSection.tsx")), false);
});
