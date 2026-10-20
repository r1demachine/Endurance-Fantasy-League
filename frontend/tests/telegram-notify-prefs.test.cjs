const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "src", "components", "TelegramBind.tsx"),
  "utf8",
);

test("Telegram settings expose four notification categories and persist each toggle", () => {
  for (const label of [
    "Напоминание о дневном бонусе",
    "Меня обошли в лиге",
    "Итоги недели",
    "Лайки и комментарии",
  ]) {
    assert.ok(source.includes(label), `Expected settings label: ${label}`);
  }
  assert.match(source, /authApi\.patch\("\/api\/telegram\/preferences"/);
  assert.match(source, /checked=\{Boolean\(status\.notify_prefs\[item\.key\]\)\}/);
  assert.match(source, /togglePreference\(item\.key, event\.target\.checked\)/);
  assert.match(source, /Не больше одного проактивного сообщения в сутки и четырёх в неделю/);
});
