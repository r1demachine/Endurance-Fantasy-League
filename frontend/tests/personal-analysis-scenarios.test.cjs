const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const page = read("src/app/analysis/page.tsx");

test("end-to-end UI contract validates the API result before accepting interpretation", () => {
  const actionFlow = page.slice(page.indexOf("const runInterpretation"), page.indexOf("const handleDaysChange"));
  assert.match(actionFlow, /authApi\.post\("\/api\/personal-analysis\/interpretation"/);
  assert.match(actionFlow, /payload\.status === "insufficient_data"/);
  assert.match(actionFlow, /payload\.status !== "ready" \|\| !isInterpretation\(payload\.analysis\)/);
  assert.match(actionFlow, /setInterpretationError\("AI-сервис не вернул полный анализ/);
  assert.match(actionFlow, /analysis: payload\.analysis/);
});

test("every validated AI field has an explicit rendered section", () => {
  assert.match(page, /\{interpretation\.analysis\.headline\}/);
  assert.match(page, /\{interpretation\.analysis\.summary\}/);
  assert.match(page, /StringList items=\{interpretation\.analysis\.positive_signals\}/);
  assert.match(page, /StringList items=\{interpretation\.analysis\.caution_signals\}/);
  assert.match(page, /StringList items=\{interpretation\.analysis\.practical_next_steps\}/);
  assert.match(page, /StringList items=\{interpretation\.analysis\.data_limitations\}/);
  assert.match(page, /interpretation\.data_quality\?\.data_gaps/);
  assert.match(page, /interpretation\.disclaimer/);
  assert.doesNotMatch(page, /dangerouslySetInnerHTML/);
});

test("insufficient data and provider errors are displayed as controlled states", () => {
  assert.match(page, /status: "insufficient_data"/);
  assert.match(page, /Недостаточно данных для интерпретации/);
  assert.match(page, /Не удалось получить AI-интерпретацию/);
  assert.match(page, /serverDetail \|\|/);
  assert.match(page, /Повторить AI-запрос/);
});

test("AI work is opt-in by button and the loading state prevents duplicate clicks", () => {
  assert.match(page, /if \(interpretationLoading \|\| !trends \|\| trends\.status !== "ready"\) return/);
  assert.match(page, /onClick=\{\(\) => void runInterpretation\(\)\}/);
  assert.doesNotMatch(page, /useEffect\([^;]*runInterpretation/s);
});
