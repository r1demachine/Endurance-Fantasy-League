const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

function loadTypeScript(filename) {
  const source = fs.readFileSync(filename, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });
  const loaded = { exports: {} };
  const runModule = new Function("require", "module", "exports", compiled.outputText);
  runModule(require, loaded, loaded.exports);
  return loaded.exports;
}

const helpers = loadTypeScript(path.join(__dirname, "../src/lib/today-card.ts"));
const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");

test("formats the API date as a Russian weekday and calendar date", () => {
  assert.equal(helpers.formatTodayDate("2026-10-20"), "вт, 20 окт");
  assert.equal(helpers.formatTodayDate("invalid"), "дата неизвестна");
});

test("morning countdown and end-of-day countdown show distinct useful states", () => {
  assert.equal(helpers.formatSecondsLeftToday(5 * 3600 + 20 * 60), "Осталось 5 ч 20 м");
  assert.equal(helpers.formatSecondsLeftToday(8 * 60), "Осталось 8 м");
  assert.equal(helpers.formatSecondsLeftToday(0), "День завершён");
});

test("series uses the API streak and Russian day plurals", () => {
  assert.equal(helpers.formatStreak(1), "Серия 1 день");
  assert.equal(helpers.formatStreak(2), "Серия 2 дня");
  assert.equal(helpers.formatStreak(7), "Серия 7 дней");
  assert.equal(helpers.formatStreak(0), "Серия 0 дней");
});

test("checklist shows open weekly tasks, tasks completed today, and only lifetime rewards received today", () => {
  const model = helpers.todayChecklistModel({
    weekly_achievements: [
      { slug: "long_workout_2h", status: "open", actionable_today: true },
      { slug: "qualifying_days_5", status: "earned", completed_today: true },
      { slug: "goal_100", status: "earned", completed_before_today: true },
      { slug: "trainer_week", status: "open", actionable_today: false },
    ],
    achievements_today: [
      { slug: "goal_met", title: "Цель выполнена", kind: "lifetime", status: "earned", earned_today: true },
      { slug: "old_award", title: "Старая награда", kind: "lifetime", status: "earned", earned_today: false },
      { slug: "open_award", title: "Ещё не получено", kind: "lifetime", status: "open", earned_today: true },
      { slug: "weekly_award", title: "Недельная награда", kind: "weekly", status: "earned", earned_today: true },
    ],
  });

  assert.deepEqual(model.visibleWeekly.map((quest) => quest.slug), ["long_workout_2h", "qualifying_days_5"]);
  assert.deepEqual(model.completedEarlier.map((quest) => quest.slug), ["goal_100"]);
  assert.deepEqual(model.lifetimeReceivedToday.map((quest) => quest.slug), ["goal_met"]);
});

test("weekly progress formats days, nights, and percentage goals", () => {
  assert.equal(
    helpers.formatWeeklyProgress({ slug: "qualifying_days_5", title: "Дни", reward: 20, status: "open", progress: { current: 3, target: 5, unit: "дней" } }),
    "3/5 дней",
  );
  assert.equal(
    helpers.formatWeeklyProgress({ slug: "good_sleep_5", title: "Сон", reward: 20, status: "open", progress: { current: 4, target: 5, unit: "ночей" } }),
    "4/5 ночей",
  );
  assert.equal(
    helpers.formatWeeklyProgress({ slug: "goal_100", title: "Цель", reward: 20, status: "open", progress: { current: 73, target: 100, unit: "%" } }),
    "73% цели",
  );
});

test("dashboard uses only /api/today as the TodayCard data source and keeps the level pill", () => {
  const dashboard = read("src/app/dashboard/page.tsx");
  const card = read("src/components/dashboard/TodayCard.tsx");
  const sync = read("../backend/app/routers/sync.py");
  assert.match(dashboard, /authApi\.get\("\/api\/today"\)/);
  assert.match(dashboard, /<TodayCard[\s\S]*?data=\{todayData\}/);
  assert.match(dashboard, /data-tour="dashboard-level"/);
  assert.match(card, /data-tour="dashboard-streak"/);
  assert.match(card, /Можно сделать сегодня/);
  assert.match(card, /Уже получено на этой неделе/);
  assert.match(card, /Подключить источник/);
  assert.match(sync, /"weekly_achievements": weekly_achievements/);
  assert.match(sync, /"achievements_today": achievements_today/);
  assert.match(sync, /"has_source": bool\(current\.api_key_encrypted\)/);
  assert.doesNotMatch(dashboard, /dashboard-week-goal|week_goal_hours/);
});
