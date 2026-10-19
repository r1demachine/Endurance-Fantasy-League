const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

function loadShareImageModule() {
  const source = read("src/lib/shareImage.ts");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const module = { exports: {} };
  const context = { module, exports: module.exports };
  vm.runInNewContext(compiled, context);
  return module.exports;
}

test("activity share text contains sport, duration, and TSS", () => {
  const { formatShareLines } = loadShareImageModule();
  const lines = formatShareLines({
    kind: "activity",
    xp: 93,
    sport: "Велосипед",
    durationMinutes: 62,
    tss: 84.5,
    distanceKm: 31.2,
    date: "2026-10-20",
  });
  assert.match(lines[0], /Велосипед/);
  assert.match(lines[0], /62 мин/);
  assert.match(lines[0], /TSS 84,5/);
  assert.ok(lines.some((line) => line.includes("31,2 км")));
});

test("league rank is omitted unless the explicit checkbox option is enabled", () => {
  const { formatShareLines } = loadShareImageModule();
  const data = { kind: "week", xp: 200, goalPercent: 92, trainingDays: 4, leagueRank: 3 };
  const withoutRank = formatShareLines(data);
  const withRank = formatShareLines(data, { includeLeagueRank: true });
  assert.ok(!withoutRank.some((line) => line.includes("#3")));
  assert.ok(withRank.some((line) => line.includes("#3")));
});

test("season share format includes metrics and duel balance", () => {
  const { formatShareLines } = loadShareImageModule();
  const lines = formatShareLines({
    kind: "season",
    xp: 700,
    totalKm: 380,
    totalHours: 22.5,
    totalElevation: 4200,
    totalWorkouts: 19,
    bestWeekXp: 230,
    longestStreakDays: 5,
    achievementsCount: 8,
    bestLeagueRank: 2,
    duelWins: 3,
    duelDraws: 1,
    duelLosses: 2,
  });
  assert.ok(lines.some((line) => line.includes("380 км")));
  assert.ok(lines.some((line) => line.includes("22,5 ч")));
  assert.ok(lines.some((line) => line.includes("Дуэли: 3–1–2")));
});

test("share layouts use portrait 1080×1920 and optional square 1080×1080", () => {
  const { calculateShareLayout } = loadShareImageModule();
  assert.deepEqual(
    { width: calculateShareLayout().width, height: calculateShareLayout().height },
    { width: 1080, height: 1920 },
  );
  assert.deepEqual(
    { width: calculateShareLayout(true).width, height: calculateShareLayout(true).height },
    { width: 1080, height: 1080 },
  );
});

test("share image is local, transparent, waits for local fonts, and does not require upload", () => {
  const source = read("src/lib/shareImage.ts");
  const button = read("src/components/ShareButton.tsx");
  assert.match(source, /document\.fonts\.load/);
  assert.match(source, /canvas\.toBlob/);
  assert.match(source, /ctx\.clearRect/);
  assert.match(source, /#ff4b26/);
  assert.doesNotMatch(source, /fetch\(|axios\.|XMLHttpRequest/);
  assert.match(button, /navigator\.canShare/);
  assert.match(button, /Скачать PNG/);
  assert.match(button, /Изображение создаётся локально в браузере/);
  assert.match(button, /checked=\{includeName\}/);
});
