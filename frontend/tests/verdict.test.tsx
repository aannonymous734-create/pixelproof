import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VerdictBadge } from "@/components/Verdict";

describe("VerdictBadge", () => {
  it("shows each verdict as text, not colour alone", () => {
    render(<VerdictBadge verdict="ALTERED_AFTER_CAPTURE" />);
    expect(screen.getByText(/ALTERED AFTER CAPTURE/)).toBeInTheDocument();
  });
  it("renders VERIFIED", () => {
    render(<VerdictBadge verdict="VERIFIED" />);
    expect(screen.getByText(/VERIFIED/)).toBeInTheDocument();
  });
});
