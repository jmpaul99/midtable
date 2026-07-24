from pathlib import Path
import re

b64 = Path("docs/brand/_fonts/outfit-extrabold-logo.b64").read_text(encoding="ascii")

font_face = f"""@font-face {{
        font-family: 'Outfit';
        font-style: normal;
        font-weight: 800;
        font-display: block;
        src: url(data:font/ttf;base64,{b64}) format('truetype');
      }}
      .midtable-text {{
        font-family: 'Outfit', 'Segoe UI', ui-sans-serif, system-ui, sans-serif;
        font-weight: 800;
        letter-spacing: -0.02em;
      }}"""

font_face_variants = f"""@font-face {{
        font-family: 'Outfit';
        font-style: normal;
        font-weight: 600;
        font-display: block;
        src: url(data:font/ttf;base64,{b64}) format('truetype');
      }}
      @font-face {{
        font-family: 'Outfit';
        font-style: normal;
        font-weight: 800;
        font-display: block;
        src: url(data:font/ttf;base64,{b64}) format('truetype');
      }}
      .midtable-text {{
        font-family: 'Outfit', 'Segoe UI', ui-sans-serif, system-ui, sans-serif;
        font-weight: 800;
        letter-spacing: -0.02em;
      }}
      .label {{
        font-family: 'Outfit', 'Segoe UI', ui-sans-serif, system-ui, sans-serif;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .swatch-hex {{
        font-family: 'Outfit', 'Segoe UI', ui-sans-serif, system-ui, sans-serif;
        font-weight: 600;
        letter-spacing: 0.02em;
      }}"""

style_re = re.compile(
    r'<style type="text/css"><!\[CDATA\[.*?\]\]></style>',
    re.S,
)

files_simple = [
    Path("brand/midtable-logo-matchday.svg"),
    Path("brand/midtable-logo-pitch-night.svg"),
    Path("frontend/public/brand/lockup-matchday.svg"),
    Path("frontend/public/brand/lockup-pitch-night.svg"),
]

for path in files_simple:
    text = path.read_text(encoding="utf-8")
    new_style = f'<style type="text/css"><![CDATA[\n      {font_face}\n    ]]></style>'
    if not style_re.search(text):
        raise SystemExit(f"No style block in {path}")
    path.write_text(style_re.sub(new_style, text, count=1), encoding="utf-8", newline="\n")
    print(f"updated {path}")

variants = Path("brand/midtable-logo-variants.svg")
variants_text = variants.read_text(encoding="utf-8")
new_style_v = f'<style type="text/css"><![CDATA[\n      {font_face_variants}\n    ]]></style>'
variants.write_text(
    style_re.sub(new_style_v, variants_text, count=1),
    encoding="utf-8",
    newline="\n",
)
print(f"updated {variants}")

for path in [*files_simple, variants]:
    text = path.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in text, path
    assert "base64," in text, path
    print(f"ok {path.name} ({path.stat().st_size} bytes)")
