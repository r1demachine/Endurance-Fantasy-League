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
  assert.ok(home.includes('className="min-w-0 flex-1 text-xs md:text-sm font-bold uppercase tracking-wide leading-snug"'));
  assert.equal(home.includes("max-w-[240px]"), false);
  assert.ok(home.includes('className="flex items-center gap-3 shrink-0"'));
});

test("Lenis provides eased global wheel and anchor scrolling while respecting reduced motion", () => {
  assert.equal(packageJson.dependencies.lenis, "1.3.27");
  assert.equal(packageLock.packages[""].dependencies.lenis, "1.3.27");
  assert.equal(packageLock.packages["node_modules/lenis"].version, "1.3.27");
  assert.ok(layout.includes('import SmoothScroll from "@/components/SmoothScroll"'));
  assert.ok(layout.includes('import "lenis/dist/lenis.css"'));
  assert.ok(layout.includes("<SmoothScroll />"));
  assert.ok(smoothScroll.includes('import Lenis from "lenis"'));
  assert.ok(smoothScroll.includes("autoRaf: true"));
  assert.ok(smoothScroll.includes("duration: 1.1"));
  assert.ok(smoothScroll.includes("easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t))"));
  assert.ok(smoothScroll.includes("smoothWheel: true"));
  assert.ok(smoothScroll.includes("anchors: true"));
  assert.ok(smoothScroll.includes("allowNestedScroll: true"));
  assert.ok(smoothScroll.includes('window.matchMedia("(prefers-reduced-motion: reduce)")'));
  assert.ok(smoothScroll.includes('reducedMotion.addEventListener("change", syncMotionPreference)'));
  assert.ok(smoothScroll.includes("lenis?.destroy()"));
  assert.equal(pageTransition.includes('window.addEventListener("wheel", onWheel'), false);
  assert.equal(pageTransition.includes("canInnerPanelScroll"), false);
  assert.ok(css.includes("scroll-behavior: auto"));
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
});
