const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const page = read("src/app/analysis/page.tsx");
const header = read("src/components/Header.tsx");
const backend = read("../backend/app/routers/personal_analysis.py");
const service = read("../backend/app/services/personal_interpretation.py");

test("personal analysis is linked from both shared navigation layouts and requires login", () => {
  assert.match(header, /href: "\/analysis", label: "Анализ"/);
  assert.match(page, /<AuthGuard>/);
  assert.match(page, /export default function PersonalAnalysisPage/);
});

test("period selector stays inside backend-supported bounds and reload cancels stale requests", () => {
  assert.match(page, /value: 14, label: "14 дней"/);
  assert.match(page, /value: 28, label: "28 дней"/);
  assert.match(page, /value: 56, label: "56 дней"/);
  assert.match(page, /value: 90, label: "90 дней"/);
  assert.match(page, /signal: controller\.signal/);
  assert.match(page, /return \(\) => controller\.abort\(\)/);
});

test("trend and interpretation APIs use authenticated client and explicit user action", () => {
  assert.match(page, /authApi\.get\("\/api\/personal-analysis\/trends"/);
  assert.match(page, /authApi\.post\("\/api\/personal-analysis\/interpretation"/);
  assert.match(page, /onClick=\{\(\) => void runInterpretation\(\)\}/);
  assert.match(backend, /Depends\(get_current_user\)/);
  assert.match(backend, /@limiter\.limit\("5\/minute"\)/);
});

test("UI includes loading, retry, insufficient-data, rate-limit, upstream-failure and missing-value states", () => {
  assert.match(page, /role="status"/);
  assert.match(page, /role="alert"/);
  assert.match(page, /Повторить загрузку/);
  assert.match(page, /Повторить AI-запрос/);
  assert.match(page, /Недостаточно данных/);
  assert.match(page, /Слишком много запросов/);
  assert.match(page, /AI-сервис временно недоступен/);
  assert.match(page, /serverDetail \|\|/);
  assert.match(page, /503/);
  assert.match(page, /"—"/);
});

test("model content is schema-checked and rendered as text rather than injected HTML", () => {
  assert.match(page, /function isInterpretation\(/);
  assert.match(page, /typeof value\[field\] === "string"/);
  assert.doesNotMatch(page, /dangerouslySetInnerHTML/);
  assert.match(service, /ConfigDict\(extra="forbid"/);
  assert.match(service, /PersonalInterpretation\.model_validate\(decoded\)/);
});

test("interface explains local limits, coverage gaps and non-medical purpose", () => {
  assert.match(page, /не медицинская оценка/);
  assert.match(page, /Пропуски и ограничения/);
  assert.match(page, /Полнота последней синхронизации отдельно не проверяется/);
  assert.match(page, /Пропущенные значения не заменяются нулями/);
});
