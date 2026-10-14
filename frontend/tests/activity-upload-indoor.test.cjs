const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const read = (relative) => fs.readFileSync(path.join(__dirname, "..", "..", relative), "utf8");
const parser = read("backend/app/routers/upload.py");
const service = read("backend/app/services/activity_upload.py");
const uploader = read("frontend/src/components/ActivityUpload.tsx");

test("FIT virtual/trainer detection is passed through preview and saved on confirmation", () => {
  assert.match(parser, /fit\.get_messages\(message_name\)/);
  assert.match(parser, /_is_indoor_fit_activity\(session, metadata_records\)/);
  assert.match(parser, /upload_preview\["is_indoor"\] = data\.is_indoor_override/);
  assert.match(service, /is_indoor = bool\(parsed\.get\("is_indoor", False\)\)/);
  assert.match(service, /is_indoor=is_indoor/);
  assert.match(uploader, /is_indoor\?: boolean/);
  assert.match(uploader, /Виртуальная \/ станок/);
  assert.match(uploader, /is_indoor_override: indoorOverride/);
  assert.match(uploader, /Исправить метку/);
});
