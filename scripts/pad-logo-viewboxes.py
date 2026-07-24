from pathlib import Path
import re

# Update mark SVGs with padded viewBox
for name in ("mark-matchday.svg", "mark-pitch-night.svg"):
    path = Path("frontend/public/brand") / name
    text = path.read_text(encoding="utf-8")
    text = text.replace('viewBox="0 0 160 64"', 'viewBox="0 0 160 72"')
    text = text.replace('transform="translate(80, 6)"', 'transform="translate(80, 12)"')
    path.write_text(text, encoding="utf-8", newline="\n")
    print("updated", path)

# Update wordmark SVGs
for name in (
    "wordmark-matchday.svg",
    "wordmark-pitch-night.svg",
):
    path = Path("frontend/public/brand") / name
    text = path.read_text(encoding="utf-8")
    text = text.replace('viewBox="0 0 200 56"', 'viewBox="0 0 210 72"')
    text = text.replace('transform="translate(100, 32)"', 'transform="translate(105, 42)"')
    path.write_text(text, encoding="utf-8", newline="\n")
    print("updated", path)

for name in (
    "midtable-wordmark-matchday.svg",
    "midtable-wordmark-pitch-night.svg",
):
    path = Path("brand") / name
    text = path.read_text(encoding="utf-8")
    text = text.replace('viewBox="0 0 200 56"', 'viewBox="0 0 210 72"')
    text = text.replace('transform="translate(100, 32)"', 'transform="translate(105, 42)"')
    path.write_text(text, encoding="utf-8", newline="\n")
    print("updated", path)
