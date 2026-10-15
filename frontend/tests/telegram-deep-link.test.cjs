const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", "..", relative), "utf8");
const backend = read("backend/app/routers/telegram.py");
const component = read("frontend/src/components/TelegramBind.tsx");

test("Telegram linking exposes a one-time deep link and handles its /start payload", () => {
  assert.match(backend, /"deep_link": _telegram_deep_link\(bot_username, code\)/);
  assert.match(backend, /https:\/\/t\.me\/\{username\}\?start=link_/);
  assert.match(backend, /parts\[1\]\.lower\(\)\.startswith\("link_"\)/);
  assert.match(backend, /await _handle_command\(db, chat_id, f"\/link \{code\}", chat_type\)/);
  assert.match(component, /href=\{deepLink\}/);
  assert.match(component, /Открыть Telegram и привязать/);
  assert.match(component, /Я привязал — проверить статус/);
});
