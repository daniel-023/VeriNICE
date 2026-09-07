import { NextRequest, NextResponse } from "next/server";

const BASIC_AUTH_REALM = "VeriTrace Demo";
const noStoreHeaders = { "Cache-Control": "no-store" };

function basicAuthHeader(username: string, password: string): string | null {
  try {
    return `Basic ${btoa(`${username}:${password}`)}`;
  } catch {
    return null;
  }
}

function authenticationDecision(
  authorization: string | null,
  username: string | undefined,
  password: string | undefined,
): "unconfigured" | "unauthorized" | "authorized" {
  if (!username || !password) return "unconfigured";
  const expected = basicAuthHeader(username, password);
  return expected && authorization === expected ? "authorized" : "unauthorized";
}

export function proxy(request: NextRequest) {
  // Keep native local development frictionless. Vercel enables the gate by
  // default; local users can opt in with VERIGRAPH_AUTH_REQUIRED=1.
  const authenticationRequired =
    process.env.VERCEL === "1" || process.env.VERIGRAPH_AUTH_REQUIRED === "1";
  if (!authenticationRequired) return NextResponse.next();

  const decision = authenticationDecision(
    request.headers.get("authorization"),
    process.env.BASIC_AUTH_USER,
    process.env.BASIC_AUTH_PASSWORD,
  );

  if (decision === "unconfigured") {
    return new NextResponse("VeriTrace authentication is not configured.", {
      status: 503,
      headers: noStoreHeaders,
    });
  }

  if (decision === "unauthorized") {
    return new NextResponse("Authentication required.", {
      status: 401,
      headers: {
        ...noStoreHeaders,
        "WWW-Authenticate": `Basic realm="${BASIC_AUTH_REALM}", charset="UTF-8"`,
      },
    });
  }

  return NextResponse.next();
}

// Protect the app, API proxy, walkthrough JSON, and generated assets.
export const config = { matcher: "/:path*" };
