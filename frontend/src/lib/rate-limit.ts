/** Simple in-memory per-IP sliding window (single instance). */

type Bucket = { timestamps: number[] };

const buckets = new Map<string, Bucket>();

export function rateLimitExceeded(
  key: string,
  limit: number,
  windowMs: number,
): boolean {
  const now = Date.now();
  const bucket = buckets.get(key) ?? { timestamps: [] };
  bucket.timestamps = bucket.timestamps.filter((t) => now - t < windowMs);
  if (bucket.timestamps.length >= limit) {
    buckets.set(key, bucket);
    return true;
  }
  bucket.timestamps.push(now);
  buckets.set(key, bucket);
  return false;
}

export function clientIpFromHeaders(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}
