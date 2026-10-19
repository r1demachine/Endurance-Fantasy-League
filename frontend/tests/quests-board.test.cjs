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

const model = loadTypeScript(path.join(__dirname, "../src/lib/quests-board.ts"));
const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");

test("all obtainable one-time achievements count toward the completed collapsed heading", () => {
  const quests = [
    ...Array.from({ length: 6 }, (_, index) => ({
      slug: `earned-${index}`, kind: "lifetime", status: "earned",
    })),
    { slug: "power-locked", kind: "lifetime", status: "unavailable" },
    { slug: "ftp-locked", kind: "lifetime", status: "unavailable" },
  ];

  const result = model.getLifetimeAchievementModel(quests);
  assert.equal(result.availableCount, 6);
  assert.equal(result.earnedCount, 6);
  assert.equal(result.allAvailableEarned, true);
  assert.equal(result.all.length, 8);
  assert.equal(result.earned.length, 6);
});

test("when one-time achievements remain open, separate unearned and received lists are available", () => {
  const quests = [
    { slug: "earned-one", kind: "lifetime", status: "earned" },
    { slug: "open-one", kind: "lifetime", status: "open" },
    { slug: "locked-one", kind: "lifetime", status: "unavailable" },
  ];
  const result = model.getLifetimeAchievementModel(quests);
  assert.equal(result.availableCount, 2);
  assert.equal(result.earnedCount, 1);
  assert.equal(result.allAvailableEarned, false);
  assert.deepEqual(result.unearned.map((quest) => quest.slug), ["open-one", "locked-one"]);
  assert.deepEqual(result.earned.map((quest) => quest.slug), ["earned-one"]);
});

test("QuestsBoard uses persisted collapsed state, shows earned separately, and has no old daily bonus prop", () => {
  const board = read("src/components/dashboard/QuestsBoard.tsx");
  const dashboard = read("src/app/dashboard/page.tsx");
  assert.match(board, /useState\(false\)/);
  assert.match(board, /LIFETIME_EXPANDED_STORAGE_KEY/);
  assert.match(board, /LIFETIME_EARNED_VISIBLE_STORAGE_KEY/);
  assert.match(board, /window\.localStorage\.getItem/);
  assert.match(board, /window\.localStorage\.setItem/);
  assert.match(board, /catch\s*\{/);
  assert.match(board, /"Развернуть"/);
  assert.match(board, /Показать полученные/);
  assert.match(board, /: lifetimeModel\.unearned;/);
  assert.match(board, /showEarnedLifetime && renderCards\(lifetimeModel\.earned\)/);
  assert.ok(board.includes('title={step.date ? `${step.label}: ${step.date}` : step.label}'));
  assert.match(board, /\{step\.label\}<\/span>/);
  assert.match(board, /quest\.reward_kind === "per_item"/);
  assert.doesNotMatch(board, /dailyBonusDays|Дневные бонусы за выбранную неделю|showAll/);
  assert.doesNotMatch(dashboard, /dailyBonusDays/);
});
