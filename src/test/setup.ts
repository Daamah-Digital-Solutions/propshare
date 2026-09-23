import "@testing-library/jest-dom";

// jsdom lacks ResizeObserver, which Radix UI primitives (Slider, etc.) require.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as never);

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// jsdom lacks elementFromPoint, which input-otp (the 2FA code field) polls on a timer.
if (!document.elementFromPoint) {
  document.elementFromPoint = () => null;
}
