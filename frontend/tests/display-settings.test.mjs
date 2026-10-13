import assert from "node:assert/strict";
import test from "node:test";

import settingsModule from "../../.tmp/frontend-tests/display-settings.js";

const { restoreDisplaySettings, serializeDisplaySettings } = settingsModule;

test("chosen appearance survives a new page", () => {
  const chosen = { font: "serif", size: "large", layout: "list", theme: "sage" };
  assert.deepEqual(restoreDisplaySettings(serializeDisplaySettings(chosen)), chosen);
});

test("invalid saved appearance falls back to readable defaults", () => {
  assert.equal(restoreDisplaySettings('{"font":"unknown"}').font, "sans");
});
