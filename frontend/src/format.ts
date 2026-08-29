export type StatusTone = "ok" | "warning" | "critical" | "muted" | "action";

export function displayValue(value: unknown, suffix = ""): string {
  if (value === null || value === undefined || value === "") {
    return "UNKNOWN";
  }
  return `${String(value)}${suffix}`;
}

export function displayBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "UNKNOWN";
  }
  return value ? "YES" : "NO";
}

export function displayMoney(value: string | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === "") {
    return "UNKNOWN";
  }
  return currency ? `${value} ${currency}` : value;
}

export function displayPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "UNKNOWN";
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return `${(parsed * 100).toFixed(1)}%`;
}

export function displayDateTime(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "UNKNOWN";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

export function displayWatchTrigger(
  ruleType: string | null | undefined,
  threshold: string | null | undefined,
): string {
  if (!ruleType) {
    return "DEFAULT_RELEVANT_CHANGE";
  }
  if (ruleType === "PRICE_BELOW") {
    return `PRICE_BELOW ${displayValue(threshold)}`;
  }
  if (ruleType === "PRICE_DROP_PERCENT") {
    return `PRICE_DROP_PERCENT ${displayPercent(threshold)}`;
  }
  return ruleType;
}

export function statusTone(status: string | null | undefined): StatusTone {
  if (!status) {
    return "muted";
  }
  if (["BLOCK", "FAILED", "INVALID_OUTPUT"].includes(status)) {
    return "critical";
  }
  if (["STALE", "VERIFY", "INSUFFICIENT_DATA", "PENDING", "RUNNING"].includes(status)) {
    return "warning";
  }
  if (["URGENT_CALL", "CALL"].includes(status)) {
    return "action";
  }
  if (["PASS", "SUCCESS", "HEALTHY", "SENT"].includes(status)) {
    return "ok";
  }
  return "muted";
}
