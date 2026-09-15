import "@testing-library/jest-dom/vitest";

globalThis.requestAnimationFrame = (callback: FrameRequestCallback) =>
  globalThis.setTimeout(() => callback(performance.now()), 0) as unknown as number;
globalThis.cancelAnimationFrame = (handle: number) =>
  globalThis.clearTimeout(handle as unknown as NodeJS.Timeout);

Element.prototype.scrollIntoView = () => {};
