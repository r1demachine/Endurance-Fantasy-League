const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", relative), "utf8");
const component = read("src/components/CheckInsPanel.tsx");
const dashboard = read("src/app/dashboard/page.tsx");
const router = read("../backend/app/routers/checkins.py");
const models = read("../backend/app/models.py");

test("morning prompt status and skip timers are persisted and validated by the backend", () => {
  assert.match(component, /\/api\/check-ins\/morning\/prompt/);
  assert.match(component, /\/api\/check-ins\/morning\/skip-warning/);
  assert.match(component, /\/api\/check-ins\/morning\/skip/);
  assert.match(component, /15000/);
  assert.match(component, /5000/);
  assert.match(router, /total_seconds\(\) < 15/);
  assert.match(router, /total_seconds\(\) < 5/);
  assert.match(router, /status = "skipped"/);
  assert.match(router, /status = "completed"/);
});

test("check-in scores allow unknown values and never serialize skipped answers as zeros", () => {
  assert.match(component, /Не указывать/);
  assert.match(component, /Неизвестные показатели можно не указывать/);
  assert.match(component, /не подставляется вместо неизвестных значений/);
  assert.match(models, /readiness = Column\(Integer, nullable=True\)/);
  assert.match(models, /fatigue = Column\(Integer, nullable=True\)/);
  assert.match(models, /soreness = Column\(Integer, nullable=True\)/);
  assert.match(models, /wellbeing = Column\(Integer, nullable=True\)/);
  assert.match(router, /ge=1, le=5/);
});

test("post-workout form is linked to activity IDs, supports edits, and validates RPE", () => {
  assert.match(component, /\/api\/check-ins\/activities/);
  assert.match(component, /rpe: Number\(activityAnswers\.rpe\)/);
  assert.match(component, /load_expectation: activityAnswers\.expectation \|\| null/);
  assert.match(component, /discomfort: activityAnswers\.discomfort \|\| null/);
  assert.match(router, /Activity\.id == activity_id, Activity\.user_id == current\.id/);
  assert.match(router, /rpe: int = Field\(ge=1, le=10\)/);
  assert.match(models, /UniqueConstraint\("activity_id", name="uq_activity_checkins_activity"\)/);
});

test("check-ins are included in the authenticated dashboard only, not public activity output", () => {
  assert.match(dashboard, /<CheckInsPanel/);
  assert.match(component, /\/api\/check-ins\/history\/activities/);
  assert.match(component, /const visibleActivities = activities\.slice\(0, 3\)/);
  assert.match(router, /@router.get\("\/history\/activities"\)/);
  assert.match(dashboard, /<CheckInsPanel key=\{/);
  assert.match(dashboard, /recent_activities\.map/);
  assert.match(router, /Depends\(get_current_user\)/);
  assert.match(router, /ActivityCheckIn\.user_id == current\.id/);
  assert.doesNotMatch(component, /Ответы видны только тебе и не влияют на XP, достижения или рейтинги/);
  assert.doesNotMatch(read("../backend/app/routers/sync.py"), /ActivityCheckIn|MorningCheckIn/);
  assert.doesNotMatch(read("../backend/app/routers/social.py"), /ActivityCheckIn|MorningCheckIn/);
});

test("dashboard shows only the latest three workouts while the private history endpoint stays paginated", () => {
  assert.match(router, /offset: int = Query\(default=0, ge=0\)/);
  assert.match(router, /"next_offset": next_offset if next_offset < total else None/);
  assert.match(component, /const visibleActivities = activities\.slice\(0, 3\)/);
  assert.doesNotMatch(component, /visibleActivityCount|nextActivityOffset|loadMoreActivities|Показать более ранние тренировки|Загрузить предыдущие тренировки/);
});

test("automatic sleep data is labeled as imported and missing sleep is not replaced", () => {
  assert.match(router, /"source": "Intervals\.icu"/);
  assert.match(component, /Автоматически из /);
  assert.match(component, /недоступны\. Пропуск данных не заменяется нулём/);
});
