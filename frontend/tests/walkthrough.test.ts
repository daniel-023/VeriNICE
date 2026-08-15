import { afterEach, describe, expect, it, vi } from "vitest";
import { walkthroughApi } from "@/lib/walkthrough";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("static walkthrough data", () => {
  it("loads case data from static assets instead of the live API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([{ id: "case-1" }]), { status: 200 }),
    );

    await walkthroughApi.cases();

    expect(fetchMock).toHaveBeenCalledWith("/walkthrough/catalog.json", {
      cache: "force-cache",
    });
  });
});
