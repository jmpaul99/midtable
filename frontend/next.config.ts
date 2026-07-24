import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Avoid picking a parent lockfile (e.g. under the user home) as the workspace root.
  outputFileTracingRoot: path.join(__dirname),
  async redirects() {
    return [
      {
        source: "/leagues/:id/members/:managerId",
        destination: "/leagues/:id/managers/:managerId",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
