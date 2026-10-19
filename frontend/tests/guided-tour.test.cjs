const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const tour = read("src/components/GuidedTour.tsx");
const pageTransition = read("src/components/PageTransition.tsx");
const layout = read("src/app/layout.tsx");
const home = read("src/app/page.tsx");
const dashboard = read("src/app/dashboard/page.tsx");
const todayCard = read("src/components/dashboard/TodayCard.tsx");
const compete = read("src/app/compete/page.tsx");
const profile = read("src/app/profile/page.tsx");
const sources = read("src/components/ConnectSources.tsx");

test("guided tour is globally mounted and can be restarted from the home globe", () => {
  assert.match(layout, /import GuidedTour from "@\/components\/GuidedTour"/);
  assert.match(layout, /<GuidedTour \/>/);
  assert.match(home, /data-tour="home-globe"/);
  assert.match(home, /window\.dispatchEvent\(new Event\("efl:start-guided-tour"\)\)/);
  assert.match(home, /Обучение/);
});

test("guided tour includes core dashboard, competition, profile, and Intervals steps", () => {
  for (const target of [
    "home-globe",
    "dashboard-level",
    "dashboard-streak",
    "dashboard-year-chart",
    "dashboard-week-summary",
    "dashboard-achievements",
    "dashboard-workouts",
    "compete-weekly-league",
    "compete-overall-rating",
    "profile-header",
    "profile-intervals-source",
    "profile-telegram-bind",
  ]) {
    assert.ok(tour.includes(`target: "${target}"`), `missing tour step target: ${target}`);
  }

  for (const marker of [
    "dashboard-level",
    "dashboard-year-chart",
    "dashboard-week-summary",
    "dashboard-achievements",
    "dashboard-workouts",
  ]) assert.ok(dashboard.includes(`data-tour="${marker}"`), `missing dashboard marker: ${marker}`);
  assert.ok(todayCard.includes('data-tour="dashboard-streak"'));

  assert.ok(compete.includes('data-tour="compete-weekly-league"'));
  assert.ok(compete.includes('data-tour="compete-overall-rating"'));
  assert.ok(profile.includes('data-tour="profile-header"'));
  assert.ok(sources.includes('data-tour={s.id === "intervals" ? "profile-intervals-source" : undefined}'));
  const telegramBind = read("src/components/TelegramBind.tsx");
  assert.ok(telegramBind.includes('data-tour="profile-telegram-bind"'));
  assert.ok(tour.indexOf('target: "profile-telegram-bind"') > tour.indexOf('target: "profile-intervals-source"'));
  assert.ok(tour.includes("Подключи Telegram-бота"));
});

test("guided tour uses a spotlight mask, blocks outside clicks, and keeps page scrolling enabled", () => {
  assert.match(tour, /createPortal\(/);
  assert.match(tour, /fillRule="evenodd"/);
  assert.match(tour, /Отменить/);
  assert.match(tour, /Дальше/);
  assert.match(tour, /scrollIntoView\(/);
  assert.match(tour, /addEventListener\("scroll", schedulePosition, true\)/);
  assert.match(tour, /markTourSeen\(\)/);
  assert.match(tour, /hasSeenTour\(\)/);
  assert.match(tour, /efl_tour_seen_v1/);
  assert.match(tour, /router\.replace\("\/", \{ scroll: false \}\)/);
});


test("guided tour waits for the entering page animation before placing the spotlight", () => {
  assert.match(tour, /efl:page-transition-complete/);
  assert.match(tour, /lastTargetPathname/);
  assert.match(tour, /transitionFallbackTimer/);
  assert.match(pageTransition, /new CustomEvent\("efl:page-transition-complete"/);
});
