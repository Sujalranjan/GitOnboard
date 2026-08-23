import { NextRequest, NextResponse } from "next/server";

// 600-second execution limit for long-running AI operations (Ollama local inference)
export const maxDuration = 600;
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

async function executeFetchWithOptionalRetry(
  targetUrl: string,
  fetchOptions: RequestInit,
  isIdempotent: boolean
): Promise<Response> {
  try {
    return await fetch(targetUrl, fetchOptions);
  } catch (err: any) {
    // Only retry idempotent GET/HEAD requests once on transient socket/connection errors
    const isNetworkError =
      err?.name === "TypeError" ||
      err?.message?.includes("fetch failed") ||
      err?.message?.includes("other side closed") ||
      err?.cause?.code === "ECONNRESET" ||
      err?.cause?.code === "UND_ERR_SOCKET";

    if (isIdempotent && isNetworkError) {
      // 100ms backoff before single retry
      await new Promise((resolve) => setTimeout(resolve, 100));
      return await fetch(targetUrl, fetchOptions);
    }
    throw err;
  }
}

async function handleProxy(request: NextRequest, { path }: { path: string[] }) {
  const targetPath = path.join("/");
  const search = request.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/${targetPath}${search}`;
  const isIdempotent = request.method === "GET" || request.method === "HEAD";

  const headers = new Headers();
  const hopByHopHeaders = new Set(["host", "connection", "keep-alive", "transfer-encoding", "content-length"]);

  request.headers.forEach((value, key) => {
    if (!hopByHopHeaders.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  const fetchOptions: RequestInit = {
    method: request.method,
    headers: headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (!isIdempotent) {
    try {
      const bodyBlob = await request.blob();
      if (bodyBlob.size > 0) {
        fetchOptions.body = bodyBlob;
      }
    } catch {
      // No body
    }
  }

  const isStreamRequest =
    request.headers.get("accept")?.includes("text/event-stream") ||
    targetPath.includes("/stream") ||
    targetPath.includes("/terminal");

  const controller = new AbortController();
  let timeoutId: NodeJS.Timeout | null = null;

  if (!isStreamRequest) {
    timeoutId = setTimeout(() => controller.abort(), 600000);
  }
  fetchOptions.signal = controller.signal;

  try {
    const response = await executeFetchWithOptionalRetry(targetUrl, fetchOptions, isIdempotent);
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

    // For SSE streams or terminal streams, return the body stream immediately
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
    if (timeoutId) clearTimeout(timeoutId);
    console.error(`[API Proxy Error] Failed to proxy to ${targetUrl}:`, error);

    const isTimeout = error?.name === "AbortError" || error?.message?.includes("abort");
    const status = isTimeout ? 504 : 502;
    const detail = isTimeout
      ? "API Gateway Timeout: Backend took too long to respond"
      : `API Proxy Error: ${error.message || "Connection failed to backend service"}`;

    return NextResponse.json(
      { detail, error: isTimeout ? "GATEWAY_TIMEOUT" : "BAD_GATEWAY" },
      { status }
    );
  }
}
