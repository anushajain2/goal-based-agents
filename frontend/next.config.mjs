/** @type {import('next').NextConfig} */
// Where the backend API is. Locally: http://localhost:8000. On Render, BACKEND_HOSTPORT is the
// API's private address (host:port), filled in by render.yaml; traffic stays on the private network.
// Rewrites are fixed when the app is built, so this must be set at build time.
const backend =
  process.env.BACKEND_URL ||
  (process.env.BACKEND_HOSTPORT ? `http://${process.env.BACKEND_HOSTPORT}` : "http://localhost:8000");

const nextConfig = {
  reactStrictMode: true,
  // Live updates use Server-Sent Events; compression would buffer them.
  compress: false,
  // Keep the live-update stream open through the proxy (the default cuts it after 30 s).
  experimental: { proxyTimeout: 10 * 60 * 1000 },
  poweredByHeader: false,
  // The UI calls the backend through the same origin, so it works behind any proxy or preview URL.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Old links from before goals were called goals.
  async redirects() {
    return [
      { source: "/campaigns/new", destination: "/goals/new", permanent: false },
      { source: "/campaigns/:id", destination: "/goals/:id", permanent: false },
    ];
  },
};
export default nextConfig;
