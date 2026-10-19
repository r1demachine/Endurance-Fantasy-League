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
  assert.match(friendCard, /ActivitySocial(?: key=\{act\.id\})? activityId=\{act\.id\}/);
  assert.match(weekCalendar, /ActivitySocial(?: key=\{selectedActivity\.id\})? activityId=\{selectedActivity\.id\}/);
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


test("activity social UI supports comments and deletes without rendering HTML", () => {
  const component = read("src/components/ActivitySocial.tsx");
  assert.match(component, /\/api\/activities\/\$\{activityId\}\/comments/);
  assert.match(component, /\/api\/comments\/\$\{commentId\}/);
  assert.match(component, /maxLength=\{500\}/);
  assert.match(component, /comment\.body/);
  assert.match(component, /comment\.can_delete/);
  assert.doesNotMatch(component, /dangerouslySetInnerHTML/);
});

test("calendar workout tiles show server-provided like and comment counts", () => {
  const calendar = read("src/components/dashboard/WeekCalendar.tsx");
  assert.match(calendar, /likes_count\?: number/);
  assert.match(calendar, /comments_count\?: number/);
  assert.match(calendar, /♥ \{Math\.max\(0, Number\(activity\.likes_count\)/);
  assert.match(calendar, /💬 \{Math\.max\(0, Number\(activity\.comments_count\)/);
});
