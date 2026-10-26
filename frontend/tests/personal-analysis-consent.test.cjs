const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const page = read("src/app/analysis/page.tsx");
const policy = read("src/app/data-policy/page.tsx");
const router = read("../backend/app/routers/personal_analysis.py");
const provider = read("../backend/app/services/personal_ai_provider.py");
const interpretation = read("../backend/app/services/personal_interpretation.py");
const model = read("../backend/app/models.py");
const migration = read("../backend/app/main.py");

test("personal AI is consent-gated and exposes an exact payload preview", () => {
  assert.ok(page.includes("Разрешить отправлять агрегированную статистику"));
  assert.ok(page.includes("Показать, что именно будет отправлено"));
  assert.ok(page.includes("/api/personal-analysis/payload-preview"));
  assert.ok(page.includes('authApi.put("/api/personal-analysis/consent"'));
  assert.ok(page.includes('checked={aiConsent}'));
  assert.ok(router.includes('raise HTTPException(status_code=403'));
  assert.ok(router.includes('return _model_input(trends)'));
  assert.ok(interpretation.includes("def _model_input(trends: dict[str, Any])"));
});

test("BYOK provider choices, test and delete controls are present", () => {
  assert.ok(page.includes("Сервер (по умолчанию)"));
  assert.ok(page.includes("Свой ключ (OpenAI-совместимый"));
  assert.ok(page.includes("Свой ключ (Claude)"));
  assert.ok(page.includes('type="password"'));
  assert.ok(page.includes('autoComplete="off"'));
  assert.ok(page.includes("Проверить"));
  assert.ok(page.includes("Удалить ключ"));
  assert.ok(page.includes('authApi.post("/api/personal-analysis/provider/test")'));
  assert.ok(page.includes('authApi.delete("/api/personal-analysis/provider")'));
  assert.ok(router.includes('@router.put("/provider")'));
  assert.ok(router.includes('@router.delete("/provider")'));
  assert.ok(router.includes('@router.post("/provider/test")'));
});

test("privacy policy documents aggregate sharing, consent revocation and encrypted keys", () => {
  assert.ok(policy.includes("Policy v2026-10-26-v1"));
  assert.ok(policy.includes('title: "7. ИИ-анализ"'));
  assert.ok(policy.includes("агрегированный JSON"));
  assert.ok(policy.includes("зашифрованном виде"));
  assert.ok(policy.includes("отозвать"));
});

test("server-side model input is allowlisted and BYOK transport blocks SSRF", () => {
  assert.ok(interpretation.includes('"period": {"days":'));
  assert.ok(interpretation.includes('"comparison_windows":'));
  assert.ok(interpretation.includes('"observations": observations'));
  assert.ok(provider.includes("class _PinnedNetworkBackend"));
  assert.ok(provider.includes("resolve_public_addresses(self.hostname)"));
  assert.ok(provider.includes("follow_redirects=False"));
  assert.ok(provider.includes("MAX_PROVIDER_RESPONSE_BYTES = 256 * 1024"));
  assert.ok(provider.includes('content_type != "application/json"'));
  assert.ok(provider.includes("ANTHROPIC_MESSAGES_URL"));
  assert.ok(provider.includes('"type": "json_schema"'));
  assert.ok(provider.includes('payload["response_format"] = {"type": "json_object"}'));
  assert.ok(model.includes("ai_analysis_consent"));
  assert.ok(model.includes("ai_api_key_encrypted"));
  assert.ok(migration.includes('ALTER TABLE users ADD COLUMN ai_analysis_consent BOOLEAN'));
  assert.ok(migration.includes('ALTER TABLE users ADD COLUMN ai_api_key_encrypted VARCHAR(1200)'));
});
