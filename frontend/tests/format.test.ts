import assert from "node:assert/strict";
import test from "node:test";

import {
  displayBoolean,
  displayMoney,
  displayPercent,
  displayValue,
  statusTone,
} from "../src/format.js";

test("displayValue preserves unknown values", () => {
  assert.equal(displayValue(null), "UNKNOWN");
  assert.equal(displayValue(undefined), "UNKNOWN");
  assert.equal(displayValue(""), "UNKNOWN");
  assert.equal(displayValue("0"), "0");
});

test("displayBoolean preserves unknown instead of false", () => {
  assert.equal(displayBoolean(null), "UNKNOWN");
  assert.equal(displayBoolean(false), "NO");
  assert.equal(displayBoolean(true), "YES");
});

test("money and percent formatting uses backend-provided values", () => {
  assert.equal(displayMoney(null, "EUR"), "UNKNOWN");
  assert.equal(displayMoney("125000.00", "EUR"), "125000.00 EUR");
  assert.equal(displayPercent(null), "UNKNOWN");
  assert.equal(displayPercent("0.125000"), "12.5%");
});

test("status tones make stale, failed, and block states visible", () => {
  assert.equal(statusTone("STALE"), "warning");
  assert.equal(statusTone("INSUFFICIENT_DATA"), "warning");
  assert.equal(statusTone("FAILED"), "critical");
  assert.equal(statusTone("BLOCK"), "critical");
  assert.equal(statusTone("SUCCESS"), "ok");
});
