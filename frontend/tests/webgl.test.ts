import { describe, expect, it, vi } from "vitest";
import { hasWebGL, prefersReducedMotion } from "@/lib/webgl";

describe("webgl detection", () => {
  it("returns false when getContext yields null (jsdom, no GPU)", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null as any);
    expect(hasWebGL()).toBe(false);
  });
  it("reduced-motion query does not throw", () => {
    expect(typeof prefersReducedMotion()).toBe("boolean");
  });
});
