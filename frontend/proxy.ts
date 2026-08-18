import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Add paths that require authentication here
const protectedPaths = [
  '/dashboard',
  '/repository',
  '/workspace'
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // Explicitly handle logout route to delete the cookie on client side
  if (pathname === '/logout') {
    const response = NextResponse.redirect(new URL('/', request.url));
    response.cookies.delete('access_token');
    return response;
  }

  // Check if the current path starts with any of the protected paths
  const isProtectedPath = protectedPaths.some(path => pathname.startsWith(path));
  
  const token = request.cookies.get('access_token');

  // If trying to access protected route without token, redirect to landing page
  if (isProtectedPath) {
    if (!token) {
      const loginUrl = new URL('/', request.url);
      return NextResponse.redirect(loginUrl);
    }
  }

  // If trying to access landing page while already logged in, redirect to dashboard
  if (pathname === '/') {
    if (token) {
      const dashboardUrl = new URL('/dashboard', request.url);
      return NextResponse.redirect(dashboardUrl);
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
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
};