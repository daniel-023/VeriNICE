import { afterEach, describe, expect, it, vi } from "vitest";
import { walkthroughApi } from "@/lib/walkthrough";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("static walkthrough data", () => {
  it("loads case data from static assets instead of the live API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      Promise.resolve(new Response(
        String(input).endsWith("metadata.json")
          ? JSON.stringify({})
          : JSON.stringify([{ id: "case-1" }]),
        { status: 200 },
      )),
    );

    await walkthroughApi.cases();

    expect(fetchMock).toHaveBeenCalledWith("/walkthrough/catalog.json", {
      cache: "no-cache",
    });
    expect(fetchMock).toHaveBeenCalledWith("/walkthrough/metadata.json", {
      cache: "no-cache",
    });
  });
});
