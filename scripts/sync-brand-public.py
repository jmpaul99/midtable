"""Copy brand/logos/product/{svg,png,icons} → frontend/public/brand for Next.js.

Prefer frontend/scripts/sync-brand-public.mjs (used by npm run sync-brand).
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "brand" / "logos" / "product"
DST = ROOT / "frontend" / "public" / "brand"


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"Missing source directory: {SRC}")
    DST.mkdir(parents=True, exist_ok=True)
    for path in DST.iterdir():
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    for path in SRC.iterdir():
        target = DST / path.name
        if path.is_file():
            shutil.copy2(path, target)
        elif path.is_dir():
            shutil.copytree(path, target)
        print(f"synced {path.name}")
    print(f"ok {SRC} -> {DST}")


if __name__ == "__main__":
    main()
