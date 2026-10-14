const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const home = read("src/app/page.tsx");
const weeklyLeague = read("src/components/compete/WeeklyLeaguePanel.tsx");

test("home page copy is Russian, fantasy-themed, and reflects current mechanics", () => {
  for (const copy of [
    "Endurance Fantasy League",
    "Тренируйся",
    "Прокачивай уровень",
    "Выполняй цель недели",
    "XP",
    "TSS",
    "Начать путь",
    "Мой дашборд",
    "Подключить источник",
    "Сменить атмосферу?",
    "Превращай прогресс в силу.",
  ]) {
    assert.ok(home.includes(copy), `missing home copy: ${copy}`);
  }

  for (const staleCopy of [
    "Sync data",
    "XP = Load × IF × Sleep",
    "Global rating",
    "Start playing",
    "View dashboard",
    "Connect source",
    "We don't follow chaos.",
    "Change theme?",
    "A fantasy league where training plan and rest multiplies your workout.",
    "Strava / Garmin / Wahoo",
    "RideMachine Endurance Fantasy league.",
  ]) {
    assert.ok(!home.includes(staleCopy), `stale/untranslated home copy remains: ${staleCopy}`);
  }
});

test("weekly league localizes the leaderboard label and division names without renaming Weekly League", () => {
  assert.ok(weeklyLeague.includes("Таблица лидеров недели"));
  assert.ok(weeklyLeague.includes(">Weekly League</h2>"));
  assert.ok(weeklyLeague.includes("function divisionLabel"));
  assert.ok(weeklyLeague.includes("Foundation: \"Основа\""));
  assert.ok(weeklyLeague.includes("Legend: \"Легенда\""));
  assert.ok(weeklyLeague.includes("{divisionLabel(entry.division)}"));
  assert.ok(!weeklyLeague.includes(">Weekly leaderboard</p>"));
  assert.ok(!weeklyLeague.includes('<span>{entry.division ?? "Open · provisional"}</span>'));
});
