import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/auth/callback/microsoft"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasRefreshCookie = request.cookies.has("refresh_token");
  const isPublicPath = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  // No cookie + protected route → redirect to login
  if (!hasRefreshCookie && !isPublicPath) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Has cookie + public route → redirect to the risk board
  if (hasRefreshCookie && isPublicPath) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Match all paths except API routes, static files, and metadata files
    "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|sitemap.xml|robots.txt).*)",
  ],
};
