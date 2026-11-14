/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // Live updates use Server-Sent Events; compression would buffer them.
  compress: false,
  // The UI calls the backend through the same origin, so it works behind any proxy or preview URL.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default nextConfig;
