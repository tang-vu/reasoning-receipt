/** @type {import('next').NextConfig} */
const apiBase = process.env.NEXT_PUBLIC_DASHBOARD_API_URL || "http://localhost:8000";
const useSnapshot = process.env.NEXT_PUBLIC_USE_SNAPSHOT === "1";

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Static export when running against a snapshot — needed for Cloudflare Pages / GH Pages.
  ...(useSnapshot ? { output: "export", trailingSlash: true, images: { unoptimized: true } } : {}),
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
