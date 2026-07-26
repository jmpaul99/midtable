import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Avoid picking a parent lockfile (e.g. under the user home) as the workspace root.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
