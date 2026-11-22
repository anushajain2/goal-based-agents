import { NextRequest, NextResponse } from "next/server";

// Pages that need an account. The backend checks the session on every API call; this
// only saves a round trip by sending signed-out visitors straight to the login page.
const APP_PATHS = ["/home", "/goals", "/work", "/approvals", "/capabilities", "/settings", "/team", "/welcome"];

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (APP_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/")) && !req.cookies.get("autopilot_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/home/:path*", "/goals/:path*", "/work/:path*", "/approvals/:path*", "/capabilities/:path*", "/settings/:path*", "/team/:path*", "/welcome"],
};
