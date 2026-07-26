/**
 * Copy brand/logos/product/{svg,png,icons} → frontend/public/brand for Next.js.
 * Same behavior as scripts/sync-brand-public.py (Node so Docker/CI need no Python).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const SRC = path.join(ROOT, "brand", "logos", "product");
const DST = path.join(ROOT, "frontend", "public", "brand");

function copyRecursive(src, dst) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dst, { recursive: true });
    for (const name of fs.readdirSync(src)) {
      copyRecursive(path.join(src, name), path.join(dst, name));
    }
    return;
  }
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

if (!fs.existsSync(SRC) || !fs.statSync(SRC).isDirectory()) {
  console.error(`Missing source directory: ${SRC}`);
  process.exit(1);
}

fs.mkdirSync(DST, { recursive: true });
for (const name of fs.readdirSync(DST)) {
  fs.rmSync(path.join(DST, name), { recursive: true, force: true });
}
for (const name of fs.readdirSync(SRC)) {
  const from = path.join(SRC, name);
  const to = path.join(DST, name);
  copyRecursive(from, to);
  console.log(`synced ${name}`);
}
console.log(`ok ${SRC} -> ${DST}`);
