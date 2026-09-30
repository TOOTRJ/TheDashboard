import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";

const require = createRequire(import.meta.url);
// Resolve from Recharts itself: checking only the app's react-is could miss a
// nested incompatible copy that fails to recognize React 19 elements.
const requireFromRecharts = createRequire(require.resolve("recharts"));
const reactIs = requireFromRecharts("react-is");
const { Area, Line } = requireFromRecharts("recharts");

test("Recharts resolves a React-compatible classifier for fragment-wrapped chart series", () => {
  // NesteggProjectionChart groups Area/Line series inside React fragments.
  const area = React.createElement(Area, {
    key: "balance", dataKey: "balance", isAnimationActive: false,
  });
  const line = React.createElement(Line, {
    key: "contributions", dataKey: "contributions", isAnimationActive: false,
  });
  const fragment = React.createElement(React.Fragment, null, area, line);

  assert.equal(reactIs.isFragment(fragment), true,
    `Recharts must recognize fragments created by React ${React.version}`);
  assert.equal(reactIs.isElement(area), true,
    "Recharts must recognize the Area element inside the fragment");
  assert.equal(reactIs.isElement(line), true,
    "Recharts must recognize the Line element inside the fragment");
  assert.equal(reactIs.isFragment(line), false,
    "Ordinary series elements must not be classified as fragments");
});
