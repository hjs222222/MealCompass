import assert from "node:assert/strict";
import test from "node:test";

import extraModule from "../../.tmp/frontend-tests/recipe-extra.js";

const { parseRecipeExtra } = extraModule;

test("extra markdown displays an existing recipe image instead of its raw reference", () => {
  const blocks = parseRecipeExtra(
    "### 成品\n\n![海边落日](./海边落日.jpg)\n\n制作完成。",
    ["drink/海边落日/海边落日.jpg"],
    [],
  );
  assert.deepEqual(blocks, [
    { kind: "heading", text: "成品" },
    { kind: "image", alt: "海边落日", src: "http://localhost:8000/recipe-images/drink/%E6%B5%B7%E8%BE%B9%E8%90%BD%E6%97%A5/%E6%B5%B7%E8%BE%B9%E8%90%BD%E6%97%A5.jpg" },
    { kind: "text", text: "制作完成。" },
  ]);
});

test("unknown image references never become arbitrary image URLs", () => {
  assert.deepEqual(parseRecipeExtra("![未知](../../secret.jpg)", [], []), [
    { kind: "text", text: "配图暂不可用：未知" },
  ]);
});
