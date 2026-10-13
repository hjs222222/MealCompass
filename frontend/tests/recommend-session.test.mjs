import assert from "node:assert/strict";
import test from "node:test";

import sessionModule from "../../.tmp/frontend-tests/recommend-session.js";

const { restoreRecommendSession, serializeRecommendSession } = sessionModule;

const recipe = { recipe_id: "r1", name: "南瓜汤", reason: "合适", missing_ingredients: [], substitutions: [], steps: [], time_minutes: null, details: null };
const session = {
  draft: { query: "汤", category: "soup", excludedRaw: "花生", topK: "2" },
  lastPayload: { query: "汤", category: "soup", excluded_ingredients: ["花生"], top_k: 2 },
  result: { query: "汤", recommendations: [recipe], candidates_considered: 1, no_solution_reason: null, degraded: false, degradations: [], node_path: ["parse"], trace_id: "trace-1" },
};

test("recommendation and form survive page remount without a new request", () => {
  const restored = restoreRecommendSession(serializeRecommendSession(session));
  assert.deepEqual(restored, session);
});

test("corrupted session falls back to an empty form and no result", () => {
  const restored = restoreRecommendSession("{broken");
  assert.equal(restored.result, null);
  assert.equal(restored.draft.query, "");
});
