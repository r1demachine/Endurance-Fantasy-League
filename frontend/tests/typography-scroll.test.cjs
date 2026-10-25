const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const calendar = read("src/components/dashboard/WeekCalendar.tsx");
const ratingBoard = read("src/components/dashboard/RatingBoard.tsx");
const ratingPanel = read("src/components/compete/RatingPanel.tsx");
const css = read("src/app/globals.css");
const home = read("src/app/page.tsx");
const dashboard = read("src/app/dashboard/page.tsx");
const layout = read("src/app/layout.tsx");
const smoothScroll = read("src/components/SmoothScroll.tsx");
const pageTransition = read("src/components/PageTransition.tsx");
const profileSettings = read("src/components/ProfileSettingsModal.tsx");
const modal = read("src/components/Modal.tsx");
const notificationBell = read("src/components/NotificationBell.tsx");
const trainingGlossary = read("src/components/dashboard/TrainingGlossary.tsx");
const floatingTooltip = read("src/components/ui/FloatingTooltip.tsx");
const checkInsPanel = read("src/components/CheckInsPanel.tsx");
const shareButton = read("src/components/ShareButton.tsx");
const yearWeeksChart = read("src/components/dashboard/YearWeeksChart.tsx");
const guidedTour = read("src/components/GuidedTour.tsx");
const packageJson = JSON.parse(read("package.json"));
const packageLock = JSON.parse(read("package-lock.json"));

test("calendar day numbers cannot split or wrap on narrow screens", () => {
  assert.ok(calendar.includes('className="inline-flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-white font-display text-base tabular-nums whitespace-nowrap leading-none"'));
  assert.ok(calendar.includes('style={{ whiteSpace: "nowrap", wordBreak: "normal", overflowWrap: "normal" }}'));
});

test("weekly, global, and friends leaderboard ranks stay on one line", () => {
  const rankClass = 'inline-flex w-8 shrink-0 items-center justify-center font-display text-lg tabular-nums whitespace-nowrap leading-none';
  assert.equal(ratingBoard.split(rankClass).length - 1, 2);
  assert.ok(ratingBoard.includes('String(p.rank).padStart(2, "0")'));
  assert.ok(ratingBoard.includes('String(player.rank).padStart(2, "0")'));
  assert.ok(ratingPanel.includes(rankClass));
  for (const source of [ratingBoard, ratingPanel]) {
    assert.ok(source.includes('whiteSpace: "nowrap", wordBreak: "normal", overflowWrap: "normal"'));
  }
});

test("display typography only uses anywhere wrapping when explicitly requested", () => {
  assert.ok(css.includes('.font-display {\n  overflow-wrap: break-word;\n  word-break: normal;'));
  assert.ok(css.includes('.font-display-wrap {\n  overflow-wrap: anywhere;\n  word-break: break-word;'));
  assert.equal(css.includes('.font-display {\n  overflow-wrap: anywhere;'), false);
  assert.ok(css.includes('[class~="whitespace-nowrap"]'));
  assert.ok(home.includes("font-display font-display-wrap uppercase leading"));
  assert.ok(dashboard.includes("font-display font-display-wrap text-4xl uppercase"));
});

test("home explainer uses the available flex width rather than a fixed 240px limit", () => {
  assert.ok(home.includes('className="min-w-0 flex-1 text-xs md:text-sm font-bold uppercase tracking-wide leading-snug hyphens-none [overflow-wrap:break-word] [word-break:normal]"'));
  assert.ok(home.includes('<main className="min-h-screen p-2 sm:p-4 md:p-6 text-[#111] relative flex flex-col overflow-x-clip">'));
  assert.ok(home.includes('className="relative flex-1 min-w-0 max-w-full bg-[#ff4b26] overflow-hidden flex items-center justify-center"'));
  assert.equal(home.includes("max-w-[240px]"), false);
  assert.ok(home.includes('className="flex items-center gap-3 shrink-0"'));
});

test("Lenis uses lerp for wheel input and leaves touch inertia native", () => {
  assert.equal(packageJson.dependencies.lenis, "1.3.27");
  assert.equal(packageLock.packages[""].dependencies.lenis, "1.3.27");
  assert.equal(packageLock.packages["node_modules/lenis"].version, "1.3.27");
  assert.ok(layout.includes('import SmoothScroll from "@/components/SmoothScroll"'));
  assert.ok(layout.includes('import "lenis/dist/lenis.css"'));
  assert.ok(layout.includes("<SmoothScroll />"));
  assert.ok(smoothScroll.includes('import Lenis from "lenis"'));
  assert.ok(smoothScroll.includes("autoRaf: false"));
  assert.ok(smoothScroll.includes("lerp: 0.085"));
  assert.ok(smoothScroll.includes("wheelMultiplier: 1"));
  assert.ok(smoothScroll.includes("smoothWheel: true"));
  assert.ok(smoothScroll.includes("syncTouch: false"));
  assert.equal(smoothScroll.includes("syncTouch: true"), false);
  assert.equal(smoothScroll.includes("touchMultiplier"), false);
  assert.equal(smoothScroll.includes("duration: 1.35"), false);
  assert.equal(smoothScroll.includes("easing:"), false);
  assert.ok(smoothScroll.includes("activeLenis?.raf(time)"));
  assert.ok(smoothScroll.includes("window.requestAnimationFrame(tick)"));
  assert.ok(smoothScroll.includes("window.cancelAnimationFrame(rafId)"));
  assert.ok(smoothScroll.includes("smoothWheel: true"));
  assert.ok(smoothScroll.includes("anchors: true"));
  assert.equal(smoothScroll.includes("allowNestedScroll"), false);
  assert.ok(smoothScroll.includes('window.matchMedia("(prefers-reduced-motion: reduce)")'));
  assert.ok(smoothScroll.includes("SMOOTH_SCROLL_MODE_CHANGE_EVENT"));
  assert.ok(smoothScroll.includes("readSmoothScrollMode"));
  assert.ok(smoothScroll.includes("applySmoothScrollMode"));
  assert.ok(smoothScroll.includes("getActiveLenis"));
  assert.ok(smoothScroll.includes("pauseSmoothScroll"));
  assert.ok(smoothScroll.includes("resumeSmoothScroll"));
  assert.ok(smoothScroll.includes('reducedMotionQuery.addEventListener("change", onReducedMotionChange)'));
  assert.ok(smoothScroll.includes("respectReducedMotion: mode !== \"enabled\""));
  assert.ok(smoothScroll.includes("activeLenis?.destroy()"));
  assert.equal(pageTransition.includes('window.addEventListener("wheel", onWheel'), false);
  assert.equal(pageTransition.includes("canInnerPanelScroll"), false);
  assert.ok(css.includes("scroll-behavior: auto"));
  assert.ok(css.includes("hyphens: none"));
  assert.ok(css.includes("word-break: normal"));
  assert.ok(css.includes("overflow-wrap: break-word"));
  assert.ok(css.includes("overflow-x: clip"));
  assert.equal(css.includes("hyphens: auto"), false);
  assert.equal(css.includes("overflow-x: hidden;"), false);
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
});


test("smooth-scroll preference offers auto, enabled, and disabled modes without reload", () => {
  assert.ok(profileSettings.includes('useState<SmoothScrollMode>("auto")'));
  assert.ok(profileSettings.includes('label: "Авто"'));
  assert.ok(profileSettings.includes('label: "Включена"'));
  assert.ok(profileSettings.includes('label: "Выключена"'));
  assert.ok(profileSettings.includes('aria-label="Режим плавной прокрутки"'));
  assert.ok(profileSettings.includes("Если колесо мыши прыгает по строкам"));
  assert.ok(profileSettings.includes("changeSmoothScrollMode(option.value)"));
  assert.ok(smoothScroll.includes('SMOOTH_SCROLL_STORAGE_KEY = "efl:smooth-scroll-mode"'));
  assert.ok(smoothScroll.includes("window.localStorage.getItem(SMOOTH_SCROLL_STORAGE_KEY)"));
  assert.ok(smoothScroll.includes("window.localStorage.setItem(SMOOTH_SCROLL_STORAGE_KEY, mode)"));
  assert.ok(smoothScroll.includes("window.dispatchEvent("));
});

test("nested scroll regions opt out of Lenis and dialogs pause it", () => {
  for (const source of [
    modal, profileSettings, notificationBell, trainingGlossary,
    floatingTooltip, calendar, checkInsPanel, shareButton,
    yearWeeksChart, guidedTour
  ]) {
    assert.ok(source.includes("data-lenis-prevent"));
  }
  assert.ok(modal.includes("pauseSmoothScroll()"));
  assert.ok(modal.includes("resumeSmoothScroll()"));
  assert.ok(smoothScroll.includes("modalPauseCount"));
  assert.ok(guidedTour.includes("lenis.scrollTo(found, { offset, duration: 1 })"));
  assert.ok(smoothScroll.includes("export function getActiveLenis()"));
});
