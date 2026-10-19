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

const calendar = loadTypeScript(path.join(__dirname, "../src/lib/week-calendar.ts"));

test("formats sleep duration as hours and zero-padded minutes", () => {
  assert.equal(calendar.formatSleepDuration(7 * 3600 + 12 * 60), "7ч 12м");
  assert.equal(calendar.formatSleepDuration(6 * 3600), "6ч 00м");
});

test("formats workout duration in minutes or hours and minutes", () => {
  assert.equal(calendar.formatActivityDuration(45), "45 мин");
  assert.equal(calendar.formatActivityDuration(72), "1ч 12м");
  assert.equal(calendar.formatActivityDuration(120), "2ч");
  assert.equal(calendar.formatActivityDuration(0), "0 мин");
});

test("calendar week contains exactly seven consecutive dates", () => {
  const dates = calendar.getCalendarWeekDates("2026-10-12");
  assert.equal(dates.length, 7);
  assert.deepEqual(dates, [
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-17",
    "2026-10-18",
  ]);
});

test("calendar dates handle month and year boundaries and reject invalid starts", () => {
  assert.deepEqual(calendar.getCalendarWeekDates("2026-12-28"), [
    "2026-12-28",
    "2026-12-29",
    "2026-12-30",
    "2026-12-31",
    "2027-01-01",
    "2027-01-02",
    "2027-01-03",
  ]);
  assert.deepEqual(calendar.getCalendarWeekDates("2026-13-99"), []);
  assert.deepEqual(calendar.getCalendarWeekDates("bad"), []);
});
