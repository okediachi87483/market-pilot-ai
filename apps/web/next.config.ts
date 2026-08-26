import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    dirs: ["app", "components", "lib", "hooks"],
  },
};

export default nextConfig;
