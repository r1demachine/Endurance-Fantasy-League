const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

const read = (path) => fs.readFileSync(path, "utf8");
const profile = read("src/app/profile/page.tsx");
const transition = read("src/components/PageTransition.tsx");
const modal = read("src/components/Modal.tsx");
const dashboard = read("src/app/dashboard/page.tsx");

test("profile settings state is read from Next URL search params only", () => {
  assert.match(profile, /useSearchParams/);
  assert.match(profile, /searchParams\.get\("settings"\)/);
  assert.doesNotMatch(profile, /window\.history\.(pushState|replaceState)/);
  assert.doesNotMatch(profile, /addEventListener\(["']popstate/);
  assert.doesNotMatch(profile, /useState<SettingsTab/);
});

test("settings navigation uses router with scroll disabled and guards rapid duplicate clicks", () => {
  assert.match(profile, /router\.push\(target, \{ scroll: false \}\)/);
  assert.match(profile, /router\.replace\(target, \{ scroll: false \}\)/);
  assert.match(profile, /pendingSettingsUrlRef\.current === nextQuery/);
  assert.match(dashboard, /sourceNavigationStartedRef\.current = true/);
  assert.match(dashboard, /event\.preventDefault\(\)/);
});

test("query-only changes do not create new PageTransition instances", () => {
  assert.match(transition, /key=\{pathname\}/);
  assert.match(transition, /mode="wait"/);
  assert.doesNotMatch(transition, /cache\.current/);
});

test("completed page transitions clear fixed-position containing-block styles", () => {
  assert.match(transition, /onAnimationComplete=\{clearAnimationStyles\}/);
  assert.match(transition, /removeProperty\("transform"\)/);
  assert.match(transition, /removeProperty\("filter"\)/);
});

test("modal overlays use document.body portal and initialize after mount", () => {
  assert.match(modal, /createPortal/);
  assert.match(modal, /setPortalRoot\(document\.body\)/);
  assert.match(modal, /portalToBody = variant === "settings"/);
  assert.match(modal, /return portalRoot \? createPortal\(modalContent, portalRoot\) : null/);
  assert.match(modal, /portalRoot,/);
});
