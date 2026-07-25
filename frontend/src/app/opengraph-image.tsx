import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const alt = "Midtable";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const FILL = "#067A4A";
const FRAME_TOP = "#8FD94A";
const FRAME_BOT = "#B9CDC0";
const GAP = "#FFFFFF";
const WORDMARK = "#71717A";
const INK = "#18181B";
const BG = "#F4F4F5";

export default async function Image() {
  const fontData = await readFile(
    join(process.cwd(), "../brand/fonts/Outfit-ExtraBold.ttf"),
  );

  const tile = 56;
  const frame = 84;
  const gap = 68;
  const center = 56;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: BG,
          gap: 36,
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "baseline",
            fontFamily: "Outfit",
            fontSize: 92,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            color: WORDMARK,
            lineHeight: 1,
          }}
        >
          <span style={{ display: "flex", transform: "translateY(-8px)" }}>Mid</span>
          <span style={{ display: "flex", transform: "translateY(8px)" }}>table</span>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "flex-end",
            gap: 18,
            height: frame,
          }}
        >
          <div
            style={{
              width: tile,
              height: tile,
              background: FILL,
              marginBottom: (frame - tile) / 2 - 9,
            }}
          />
          <div
            style={{
              width: frame,
              height: frame,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: `linear-gradient(180deg, ${FRAME_TOP} 0%, ${FRAME_BOT} 100%)`,
            }}
          >
            <div
              style={{
                width: gap,
                height: gap,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: GAP,
              }}
            >
              <div style={{ width: center, height: center, background: FILL }} />
            </div>
          </div>
          <div
            style={{
              width: tile,
              height: tile,
              background: FILL,
              marginBottom: (frame - tile) / 2 - 9,
            }}
          />
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 12,
            fontFamily: "Outfit",
            fontSize: 28,
            fontWeight: 800,
            color: INK,
            opacity: 0.72,
            letterSpacing: "-0.01em",
          }}
        >
          Draft clubs, follow every result, and climb the table.
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        {
          name: "Outfit",
          data: fontData,
          style: "normal",
          weight: 800,
        },
      ],
    },
  );
}
