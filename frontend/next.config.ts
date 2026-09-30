import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,

  webpack(config) {
    config.ignoreWarnings = [
      ...(config.ignoreWarnings ?? []),
      /Circular dependency between chunks with runtime \(webpack-runtime, compute\)/,
      /Circular dependency between chunks with runtime \(webpack, compute\)/,
    ];

    return config;
  },
};

export default nextConfig;