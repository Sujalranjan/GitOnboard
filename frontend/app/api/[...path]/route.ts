import { NextRequest, NextResponse } from "next/server";

// 300-second execution limit for long-running AI operations (Ollama local inference)
export const maxDuration = 300;
export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

async function handleProxy(request: NextRequest, { path }: { path: string[] }) {
  const targetPath = path.join("/");
  const search = request.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/${targetPath}${search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    // Exclude host header to let destination handle host routing
    if (key.toLowerCase() !== "host") {
      headers.set(key, value);
    }
  });

  const fetchOptions: RequestInit = {
    method: request.method,
    headers: headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      const bodyBlob = await request.blob();
      if (bodyBlob.size > 0) {
        fetchOptions.body = bodyBlob;
      }
    } catch {
      // No body
    }
  }

  try {
    const isStreamRequest = request.headers.get("accept")?.includes("text/event-stream") ||
                           targetPath.includes("/stream");

    const controller = new AbortController();
    // Only apply timeout if not an infinite streaming request
    let timeoutId: NodeJS.Timeout | null = null;
    if (!isStreamRequest) {
      timeoutId = setTimeout(() => controller.abort(), 300000);
    }
    fetchOptions.signal = controller.signal;

    const response = await fetch(targetUrl, fetchOptions);
    if (timeoutId) clearTimeout(timeoutId);

    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "set-cookie") {
        responseHeaders.set(key, value);
      }
    });

    if (typeof (response.headers as any).getSetCookie === "function") {
      const cookies = (response.headers as any).getSetCookie();
      cookies.forEach((cookie: string) => {
        responseHeaders.append("set-cookie", cookie);
      });
    }

    const contentType = response.headers.get("content-type") || "";

    // For SSE streams (text/event-stream) or stream endpoints, return the body stream immediately
    if (contentType.includes("text/event-stream") || isStreamRequest) {
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    }

    const data = await response.blob();
    return new NextResponse(data, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error: any) {
    console.error(`[API Proxy Error] Failed to proxy to ${targetUrl}:`, error);
    return NextResponse.json(
      { detail: `API proxy error: ${error.message || "Connection failed"}` },
      { status: 504 }
    );
  }
}
