export function formatNumber(value: string | number) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "—";
}

/** Local date/time with short timezone name (e.g. PDT) — use for scheduled draft starts. */
export function formatDateTimeWithZone(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { timeZoneName: "short" });
}
