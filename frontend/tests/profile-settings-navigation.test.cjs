const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

const read = (path) => fs.readFileSync(path, "utf8");
const profile = read("src/app/profile/page.tsx");
const transition = read("src/components/PageTransition.tsx");
const modal = read("src/components/Modal.tsx");
const dashboard = read("src/app/dashboard/page.tsx");
const workoutsList = read("src/components/dashboard/WorkoutsList.tsx");
const workoutsSection = read("src/components/dashboard/DashboardWorkoutsSection.tsx");
const compete = read("src/app/compete/page.tsx");

test("profile settings state is read from Next URL search params only", () => {
  assert.match(profile, /useSearchParams/);
  assert.match(profile, /searchParams\.get\("settings"\)/);
  assert.doesNotMatch(profile, /window\.history\.(pushState|replaceState)/);
  assert.doesNotMatch(profile, /addEventListener\(["']popstate/);
  assert.doesNotMatch(profile, /useState<SettingsTab/);
});

test("profile settings navigation keeps URL state and guards rapid duplicate clicks", () => {
  assert.match(profile, /router\.push\(target, \{ scroll: false \}\)/);
  assert.match(profile, /router\.replace\(target, \{ scroll: false \}\)/);
  assert.match(profile, /pendingSettingsUrlRef\.current === nextQuery/);
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
  assert.match(modal, /useSyncExternalStore/);
  assert.match(modal, /getPortalRootSnapshot/);
  assert.match(modal, /getServerPortalRootSnapshot/);
  assert.match(modal, /portalToBody = variant === "settings"/);
  assert.match(modal, /return portalRoot \? createPortal\(modalContent, portalRoot\) : null/);
  assert.match(modal, /portalRoot,/);
});


test("competition tab follows the URL and active panels render immediately", () => {
  assert.match(compete, /useSearchParams/);
  assert.match(compete, /searchParams\.get\("tab"\)/);
  assert.doesNotMatch(compete, /window\.location\.search/);
  assert.doesNotMatch(compete, /useState<CompeteTab>/);
  assert.doesNotMatch(compete, /initialized/);
  assert.match(compete, /visitedTabs\.rating \|\| activeTab === "rating"/);
  assert.match(compete, /visitedTabs\.duels \|\| activeTab === "duels"/);
  assert.match(compete, /visitedTabs\.teams \|\| activeTab === "teams"/);
  assert.match(compete, /<Suspense fallback={<CompeteFallback \/>}>/);
});

test("settings dialog establishes a theme-aware foreground instead of inheriting body text-white", () => {
  assert.match(modal, /bg-\[\#f4f4f0\] text-\[\#111\] shadow-none/);
});


test("dashboard opens source settings in a portal without navigating away from dashboard", () => {
  assert.match(dashboard, /const \[settingsTab, setSettingsTab\] = useState<SettingsTab \| null>\(null\)/);
  assert.match(dashboard, /setSettingsTab\("sources"\)/);
  assert.match(dashboard, /onClick=\{openSourceSettings\}/);
  assert.match(dashboard, /<ProfileSettingsModal/);
  assert.match(dashboard, /userData=\{userData \?\? data\}/);
  assert.match(dashboard, /onTabChange=\{setSettingsTab\}/);
  assert.doesNotMatch(dashboard, /router\.push\("\/profile\?settings=sources"/);
  assert.doesNotMatch(dashboard, /href="\/profile\?settings=sources"/);
});


test("source CTA keeps the current page and opens the shared settings portal", () => {
  assert.match(workoutsList, /onClick=\\{onOpenSources\\}/);
  assert.doesNotMatch(workoutsList, /\\/profile\\?settings=sources/);
  assert.match(workoutsSection, /onOpenSources=\\{onOpenSources\\}/);
  assert.match(dashboard, /onOpenSources=\\{openSourceSettings\\}/);
  assert.match(dashboard, /setSettingsTab\\("sources"\\)/);
  assert.match(dashboard, /onDataUpdated=\\{\\(\\) => void loadQuests\\(\\)\\}/);
});
