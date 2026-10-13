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

const { formatWeekRange } = loadTypeScript(
  path.join(__dirname, "../src/lib/format.ts"),
);

test("formats a week within one month and year in Russian genitive month form", () => {
  assert.equal(formatWeekRange("2026-10-12"), "12 октября – 18 октября 2026");
});

test("formats a week crossing the month boundary", () => {
  assert.equal(formatWeekRange("2026-10-26"), "26 октября – 1 ноября 2026");
});

test("prints the year on both dates when the week crosses a calendar year", () => {
  assert.equal(formatWeekRange("2026-12-28"), "28 декабря 2026 – 3 января 2027");
});

test("accepts Date instances and uses their calendar date", () => {
  assert.equal(formatWeekRange(new Date(2026, 9, 12)), "12 октября – 18 октября 2026");
});

test("returns a readable fallback for missing or invalid input", () => {
  assert.equal(formatWeekRange(null), "Неделя неизвестна");
  assert.equal(formatWeekRange("2026-13-99"), "Неделя неизвестна");
});
