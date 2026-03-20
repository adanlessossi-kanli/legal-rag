import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  webpack: (config) => {
    // Suppress webpack cache warnings about dynamic imports in next-intl
    // These are harmless warnings from the ICU message format extractor
    config.infrastructureLogging = {
      ...config.infrastructureLogging,
      level: "error",
    };
    return config;
  },
};

export default withNextIntl(nextConfig);
