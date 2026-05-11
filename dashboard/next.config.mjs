/** @type {import('next').NextConfig} */
const apiBase = process.env.NEXT_PUBLIC_DASHBOARD_API_URL || "http://localhost:8000";
const useSnapshot = process.env.NEXT_PUBLIC_USE_SNAPSHOT === "1";
// GitHub Pages serves at /<repo-name>/ so the static build needs a basePath.
// Override at build time with NEXT_PUBLIC_BASE_PATH="" for root-domain hosting
// (custom domain, *.pages.dev, *.github.io org root, etc.).
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? (useSnapshot ? "/reasoning-receipt" : "");

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Static export when running against a snapshot — works for any static host.
  ...(useSnapshot
    ? {
        output: "export",
        trailingSlash: true,
        images: { unoptimized: true },
        basePath: basePath || undefined,
        assetPrefix: basePath || undefined,
      }
    : {}),
  // Rewrites only apply in server mode (skipped under output: 'export').
  ...(useSnapshot
    ? {}
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
        },
      }),
};

export default nextConfig;
