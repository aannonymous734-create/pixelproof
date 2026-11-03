import { describe, expect, it } from "vitest";
import { shortHash, timeAgo } from "@/lib/utils";

describe("timeAgo", () => {
  const now = "2026-11-02T12:00:00Z";
  it("formats seconds, minutes, hours and days", () => {
    expect(timeAgo("2026-11-02T11:59:48Z", now)).toBe("12 s ago");
    expect(timeAgo("2026-11-02T11:57:00Z", now)).toBe("3 min ago");
    expect(timeAgo("2026-11-02T10:00:00Z", now)).toBe("2 h ago");
    expect(timeAgo("2026-10-29T12:00:00Z", now)).toBe("4 d ago");
  });
  it("is safe on missing or invalid input", () => {
    expect(timeAgo(null, now)).toBe("—");
    expect(timeAgo("not a date", now)).toBe("—");
  });
  it("never goes negative when the clock is slightly ahead", () => {
    expect(timeAgo("2026-11-02T12:00:05Z", now)).toBe("0 s ago");
  });
});

describe("shortHash", () => {
  it("shortens long hashes and keeps short ones", () => {
    expect(shortHash("a".repeat(64))).toBe("aaaaaaaa…aaaaaa");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash(undefined)).toBe("—");
  });
});
