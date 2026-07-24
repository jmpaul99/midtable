from pathlib import Path
import re

lockup = Path("frontend/public/brand/lockup-matchday.svg").read_text(encoding="utf-8")
match = re.search(r"<style type=\"text/css\"><!\[CDATA\[(.*?)\]\]></style>", lockup, re.S)
if not match:
    raise SystemExit("Could not find style block in lockup-matchday.svg")
style = match.group(1).strip()


def make(path: str, fill: str) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 56" role="img" aria-label="Midtable wordmark">
  <defs>
    <style type="text/css"><![CDATA[
      {style}
    ]]></style>
  </defs>

  <g transform="translate(100, 32)">
    <text font-size="46" fill="{fill}" class="midtable-text">
      <tspan x="-95" y="-4">Mid</tspan>
      <tspan x="-14" y="4">table</tspan>
    </text>
  </g>
</svg>
"""
    out = Path(path)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


make("frontend/public/brand/wordmark-matchday.svg", "#71717A")
make("frontend/public/brand/wordmark-pitch-night.svg", "#2DD67B")
make("brand/midtable-wordmark-matchday.svg", "#71717A")
make("brand/midtable-wordmark-pitch-night.svg", "#2DD67B")
