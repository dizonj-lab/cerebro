import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SESSION_COOKIE = process.env.NEXT_PUBLIC_SESSION_COOKIE ?? "cerebro_session";

/** Routes that require a session. */
const PROTECTED_PREFIXES = ["/construct"];

/** Routes that an already-authenticated user has no reason to see. */
const AUTH_ROUTES = ["/login", "/signup"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  if (PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    if (!hasSession) {
      const login = new URL("/login", request.url);
      // Remember where the user was heading so login can return them there.
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }
  }

  if (AUTH_ROUTES.includes(pathname) && hasSession) {
    return NextResponse.redirect(new URL("/construct", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/construct/:path*", "/login", "/signup"],
};
