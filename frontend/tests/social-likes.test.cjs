const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

test("activity likes use social endpoints and render ordinary text", () => {
  const component = read("src/components/ActivitySocial.tsx");
  assert.match(component, /\/api\/activities\/\$\{activityId\}\/social/);
  assert.match(component, /\/api\/activities\/\$\{activityId\}\/reaction/);
  assert.match(component, /aria-pressed=/);
  assert.doesNotMatch(component, /dangerouslySetInnerHTML/);
});

test("friend activity cards and expanded calendar activity show likes", () => {
  const friendCard = read("src/components/ActivityCard.tsx");
  const weekCalendar = read("src/components/dashboard/WeekCalendar.tsx");
  assert.match(friendCard, /ActivitySocial activityId=\{act\.id\}/);
  assert.match(weekCalendar, /ActivitySocial activityId=\{selectedActivity\.id\}/);
  assert.match(weekCalendar, /initialActivityId/);
});

test("social notifications expose their link and open the selected activity", () => {
  const notifType = read("src/lib/notifications.ts");
  const bell = read("src/components/NotificationBell.tsx");
  const dashboard = read("src/app/dashboard/page.tsx");
  assert.match(notifType, /link: string \| null/);
  assert.match(bell, /type === "activity_like"/);
  assert.match(bell, /href=\{n\.link\}/);
  assert.match(dashboard, /activity_id/);
  assert.match(dashboard, /initialActivityId=\{deepLinkActivityId\}/);
});
