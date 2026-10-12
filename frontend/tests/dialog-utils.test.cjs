const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

function loadTypeScript(module, filename) {
  const source = fs.readFileSync(filename, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
    fileName: filename,
  }).outputText;
  module._compile(compiled, filename);
}

require.extensions[".ts"] = loadTypeScript;
require.extensions[".tsx"] = loadTypeScript;

const utils = require("../src/components/dialog-utils.ts");

test("API errors use detail only when it is a non-empty string", () => {
  assert.equal(utils.getApiErrorMessage({ response: { data: { detail: "Пароль неверен" } } }, "Ошибка"), "Пароль неверен");
  assert.equal(utils.getApiErrorMessage({ response: { data: { detail: { message: "bad" } } } }, "Ошибка"), "Ошибка");
  assert.equal(utils.getApiErrorMessage({}, "Ошибка"), "Ошибка");
  assert.equal(utils.getApiErrorMessage({ response: { data: { detail: "  " } } }, "Ошибка"), "Ошибка");
});

test("pause duration accepts only integer values from zero through eight", () => {
  assert.equal(utils.parsePauseWeeks("0"), 0);
  assert.equal(utils.parsePauseWeeks("8"), 8);
  assert.equal(utils.parsePauseWeeks("4"), 4);
  for (const invalid of ["", " ", "1abc", "1.5", "-1", "9", "00", " 2 x "]) {
    assert.equal(utils.parsePauseWeeks(invalid), null, "invalid input: " + JSON.stringify(invalid));
  }
  assert.equal(utils.parsePauseWeeks(3.5), null);
  assert.equal(utils.parsePauseWeeks(9), null);
});

test("DELETE and password requirements block incomplete confirmations and return the password", () => {
  assert.equal(utils.isConfirmDialogValid({ requireDelete: true, confirmation: "delete" }), false);
  assert.equal(utils.isConfirmDialogValid({ requireDelete: true, confirmation: "DELETE", requirePassword: true, password: "" }), false);
  assert.deepEqual(
    utils.buildConfirmPayload(
      { confirmation: " DELETE ", password: "secret" },
      { requireDelete: true, requirePassword: true },
    ),
    { confirmation: "DELETE", password: "secret" },
  );
  assert.deepEqual(utils.buildConfirmPayload({}, {}), { confirmation: "", password: "" });
});

test("pause timestamps without a zone are treated as UTC and formatted", () => {
  assert.equal(utils.parsePauseDate("not-a-date"), null);
  assert.equal(utils.parsePauseDate(null), null);
  assert.equal(utils.parsePauseDate("2026-10-12T00:00:00")?.toISOString(), "2026-10-12T00:00:00.000Z");
  assert.notEqual(utils.formatPauseDate("2026-10-12T00:00:00Z"), "дата не указана");
});

test("Escape closes an idle dialog, but not a busy dialog", () => {
  let closed = 0;
  const event = { key: "Escape", preventDefault() { this.prevented = true; } };
  assert.equal(utils.handleDialogKeyDown(event, {
    dialog: null,
    closeOnEscape: true,
    preventClose: false,
    onClose: () => { closed++; },
    activeElement: null,
  }), "closed");
  assert.equal(closed, 1);
  assert.equal(event.prevented, true);
  assert.equal(utils.handleDialogKeyDown(event, {
    dialog: null,
    closeOnEscape: true,
    preventClose: true,
    onClose: () => { closed++; },
    activeElement: null,
  }), "ignored");
  assert.equal(closed, 1);
});

test("Tab focus stays inside the dialog", () => {
  let firstFocused = 0;
  let lastFocused = 0;
  const first = { focus() { firstFocused++; } };
  const last = { focus() { lastFocused++; } };
  const dialog = {
    querySelectorAll() { return [first, last]; },
    contains(element) { return element === first || element === last; },
    focus() {},
  };
  const forward = { key: "Tab", shiftKey: false, preventDefault() { this.prevented = true; } };
  assert.equal(utils.handleDialogKeyDown(forward, {
    dialog, closeOnEscape: true, preventClose: false, onClose() {}, activeElement: last,
  }), "focused-first");
  assert.equal(firstFocused, 1);
  assert.equal(forward.prevented, true);
  const reverse = { key: "Tab", shiftKey: true, preventDefault() { this.prevented = true; } };
  assert.equal(utils.handleDialogKeyDown(reverse, {
    dialog, closeOnEscape: true, preventClose: false, onClose() {}, activeElement: first,
  }), "focused-last");
  assert.equal(lastFocused, 1);
});

test("ConfirmDialog renders accessible dialog and DELETE/password fields", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const { ConfirmDialog } = require("../src/components/Modal.tsx");
  const html = renderToStaticMarkup(React.createElement(ConfirmDialog, {
    title: "Удалить аккаунт",
    text: "Это действие необратимо.",
    confirmLabel: "Удалить",
    busy: false,
    requireDelete: true,
    requirePassword: true,
    onClose() {},
    onConfirm() {},
  }));
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /aria-labelledby=/);
  assert.match(html, /id="confirm-delete-word"/);
  assert.match(html, /id="confirm-account-password"/);
  assert.match(html, /type="password"/);
  assert.match(html, /disabled=""/);
});
