import { describe, expect, it } from "vitest";

// The upload validation rule the Analyse page enforces before any network call.
function validate(name: string, size: number, maxMB = 2) {
  if (!/\.(png|jpe?g|tif?f|webp|bmp)$/i.test(name)) return "type";
  if (size > maxMB * 1024 * 1024) return "size";
  return "ok";
}

describe("upload validation", () => {
  it("accepts a small png", () => expect(validate("patch.png", 1000)).toBe("ok"));
  it("rejects a non-image", () => expect(validate("notes.txt", 10)).toBe("type"));
  it("rejects an oversized image", () => expect(validate("big.png", 5 * 1024 * 1024)).toBe("size"));
  it("accepts a geotiff", () => expect(validate("scene.tif", 2000)).toBe("ok"));
});
