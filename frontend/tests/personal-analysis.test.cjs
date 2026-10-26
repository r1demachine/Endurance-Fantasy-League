const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const page = read("src/app/analysis/page.tsx");
const header = read("src/components/Header.tsx");
const backend = read("../backend/app/routers/personal_analysis.py");
const service = read("../backend/app/services/personal_interpretation.py");
const policy = read("src/app/data-policy/page.tsx");
const userModel = read("../backend/app/models.py");
const mainMigration = read("../backend/app/main.py");
const aiPrivacyTests = read("../backend/tests/test_personal_analysis_ai_privacy.py");

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


test("AI interpretation requires explicit consent and shows the exact allow-listed payload before opt-in", () => {
  assert.match(page, /Разрешить отправлять агрегированную статистику/);
  assert.match(page, /средние значения сна, нагрузки, самочувствия за период/);
  assert.match(page, /Показать, что именно будет отправлено/);
  assert.match(page, /authApi\.get\("\/api\/personal-analysis\/payload-preview"/);
  assert.match(page, /setPayloadPreview\(response\.data\)/);
  assert.match(page, /JSON\.stringify\(payloadPreview, null, 2\)/);
  assert.match(page, /authApi\.put\("\/api\/personal-analysis\/consent", \{ enabled \}\)/);
  assert.match(page, /if \(!aiConsent \|\| interpretationLoading/);
  assert.match(backend, /_require_ai_consent\(db, current\)/);
  assert.match(backend, /status_code=403/);
  assert.match(aiPrivacyTests, /test_interpretation_without_consent_is_403_and_never_calls_any_http_client/);
});

test("BYOK source selector masks credentials and offers provider test/delete controls", () => {
  assert.match(page, /Сервер \(по умолчанию\)/);
  assert.match(page, /Свой ключ \(OpenAI-совместимый/);
  assert.match(page, /Свой ключ \(Claude\)/);
  assert.match(page, /https:\/\/api\.openai\.com\/v1/);
  assert.match(page, /https:\/\/api\.groq\.com\/openai\/v1/);
  assert.match(page, /https:\/\/openrouter\.ai\/api\/v1/);
  assert.match(page, /type="password"/);
  assert.match(page, /autoComplete="off"/);
  assert.match(page, /authApi\.put\("\/api\/personal-analysis\/provider", body\)/);
  assert.match(page, /authApi\.post\("\/api\/personal-analysis\/provider\/test"\)/);
  assert.match(page, /authApi\.delete\("\/api\/personal-analysis\/provider"\)/);
  assert.match(page, /key_last4/);
  assert.match(backend, /encrypt_secret\(supplied_key\)/);
  assert.match(backend, /decrypt_secret\(user\.ai_api_key_encrypted\)/);
  assert.match(aiPrivacyTests, /test_overlong_api_key_is_rejected_without_echoing_the_key/);
});

test("AI consent and provider settings are additive, opt-in database fields", () => {
  for (const field of [
    "ai_analysis_consent", "ai_analysis_consent_at", "ai_provider",
    "ai_base_url", "ai_model", "ai_api_key_encrypted"
  ]) {
    assert.match(userModel, new RegExp(field));
    assert.match(mainMigration, new RegExp("ALTER TABLE users ADD COLUMN " + field));
  }
  assert.match(userModel, /ai_analysis_consent = Column\(Boolean, nullable=False, default=False/);
  assert.match(policy, /title: "7\. ИИ-анализ"/);
  assert.match(policy, /Policy v2026-10-26-v1/);
  assert.match(policy, /не отправляются отдельные тренировки/);
  assert.match(policy, /зашифрованном виде/);
  assert.match(policy, /отозвать в любой момент/);
});

test("provider request security blocks SSRF and uses pinned destination IPs", () => {
  assert.match(service, /_resolve_public_endpoint/);
  assert.match(service, /_PinnedNetworkBackend/);
  assert.match(service, /socket\.create_connection\(/);
  assert.match(service, /follow_redirects=False/);
  assert.match(service, /MAX_PROVIDER_RESPONSE_BYTES = 256 \* 1024/);
  assert.match(service, /MAX_PROVIDER_TIMEOUT_SECONDS = 30\.0/);
  assert.match(service, /Content-Type/);
  assert.match(service, /redirect_blocked/);
  assert.match(aiPrivacyTests, /test_domain_resolving_to_private_ip_is_rejected_without_http_request/);
  assert.match(aiPrivacyTests, /test_internal_redirect_is_rejected_and_redirect_following_is_disabled/);
  assert.match(aiPrivacyTests, /test_connection_uses_only_the_pinned_numeric_ip/);
});
