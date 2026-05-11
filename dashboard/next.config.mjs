/** @type {import('next').NextConfig} */
const apiBase = process.env.NEXT_PUBLIC_DASHBOARD_API_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
