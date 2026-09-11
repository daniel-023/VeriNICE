import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const MAX_REQUEST_BYTES = 1_500_000;
const DEFAULT_BACKEND_TIMEOUT_MS = 250_000;

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function firstForwardedValue(value: string | null): string | null {
  return value?.split(",", 1)[0]?.trim() || null;
}

function isSameOrigin(request: NextRequest): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") {
    return false;
  }

  const origin = request.headers.get("origin");
  if (!origin) {
    return true;
  }

  const host =
    firstForwardedValue(request.headers.get("x-forwarded-host")) ??
    request.headers.get("host");
  if (!host) {
    return false;
  }

  try {
    const originUrl = new URL(origin);
    if (originUrl.host !== host) {
      return false;
    }
    const forwardedProtocol = firstForwardedValue(
      request.headers.get("x-forwarded-proto"),
    );
    return !forwardedProtocol || originUrl.protocol === `${forwardedProtocol}:`;
  } catch {
    return false;
  }
}

function backendTimeoutMs(): number {
  const configured = Number(process.env.VERIGRAPH_BACKEND_TIMEOUT_MS);
  return Number.isFinite(configured) && configured > 0
    ? configured
    : DEFAULT_BACKEND_TIMEOUT_MS;
}

async function proxy(request: NextRequest, context: RouteContext) {
  if (process.env.NEXT_PUBLIC_VERIGRAPH_MODE === "walkthrough") {
    return Response.json(
      { detail: "Live analysis is available only in the local VeriNICE demo." },
      { status: 503 },
    );
  }
  if (!isSameOrigin(request)) {
    return Response.json(
      { detail: "Cross-origin requests are not allowed." },
      { status: 403 },
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_REQUEST_BYTES) {
    return Response.json(
      { detail: "Request body is too large." },
      { status: 413 },
    );
  }

  const { path } = await context.params;
  const configuredBackend = process.env.VERIGRAPH_BACKEND_URL;
  if (!configuredBackend) {
    return Response.json(
      { detail: "The live VeriNICE backend is not configured for this deployment." },
      { status: 503 },
    );
  }
  const backendBase = configuredBackend.replace(/\/$/, "");
  const backendUrl = new URL(
    `${backendBase}/api/v1/${path.map(encodeURIComponent).join("/")}`,
  );
  backendUrl.search = request.nextUrl.search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  headers.set("accept", "application/json");

  try {
    const body =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer();
    if (body && body.byteLength > MAX_REQUEST_BYTES) {
      return Response.json(
        { detail: "Request body is too large." },
        { status: 413 },
      );
    }

    const response = await fetch(backendUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(backendTimeoutMs()),
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { detail: "The VeriNICE backend is unavailable." },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
