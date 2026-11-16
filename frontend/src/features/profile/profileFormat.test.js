import { describe, expect, it } from "vitest";

import { formatDate, providerLabel, roleLabel, validateFullName } from "./profileFormat";

describe("profileFormat", () => {
  it("formats roles and providers", () => {
    expect(roleLabel("business_analyst")).toBe("Business Analyst");
    expect(roleLabel(undefined)).toBe("User");
    expect(providerLabel("github")).toBe("GitHub");
    expect(providerLabel("email")).toBe("Email & password");
  });

  it("formats dates defensively", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
    expect(formatDate("2026-03-14T10:00:00Z")).toMatch(/2026/);
  });

  it("validates the full name like the server does", () => {
    expect(validateFullName("A")).toMatch(/at least 2/);
    expect(validateFullName("   ")).toMatch(/at least 2/);
    expect(validateFullName("x".repeat(151))).toMatch(/exceed 150/);
    expect(validateFullName("Asha Verma")).toBe("");
  });
});
