import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Pitch Night wordmark apple touch icon. */
export default async function AppleIcon() {
  const outfit = await readFile(
    join(process.cwd(), "..", "brand", "fonts", "Outfit-ExtraBold.ttf"),
  );

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0A0F0C",
          fontFamily: "Outfit",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            fontSize: 48,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            color: "#2DD67B",
            lineHeight: 1,
          }}
        >
          <span style={{ transform: "translateY(-4px)" }}>Mid</span>
          <span style={{ transform: "translateY(4px)" }}>table</span>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [{ name: "Outfit", data: outfit, style: "normal", weight: 800 }],
    },
  );
}
