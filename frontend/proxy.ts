import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Add paths that require authentication here
const protectedPaths = [
  "/dashboard",
  "/repository",
  "/workspace",
];

const isLocalMode =
  process.env.DEPLOYMENT_TYPE?.toUpperCase() === "LOCAL" ||
  process.env.NEXT_PUBLIC_DEPLOYMENT_TYPE?.toUpperCase() === "LOCAL" ||
  process.env.NODE_ENV !== "production";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Explicitly handle logout route to delete the cookie on client side
  if (pathname === "/logout") {
    const response = NextResponse.redirect(new URL("/", request.url));
    response.cookies.delete("access_token");
    return response;
  }

  // Check if the current path starts with any of the protected paths
  const isProtectedPath = protectedPaths.some((path) => pathname.startsWith(path));
  const token = request.cookies.get("access_token");

  // In production, redirect unauthenticated users without token to landing page
  if (isProtectedPath && !isLocalMode) {
    if (!token) {
      const loginUrl = new URL("/", request.url);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

// Configure the middleware to match specific paths to optimize performance
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
