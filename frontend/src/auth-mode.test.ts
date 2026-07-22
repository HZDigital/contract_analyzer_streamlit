import { describe, expect, it } from "vitest";
import { isEmbeddedAnalyzer } from "./auth-mode";

describe("embedded analyzer mode", () => {
  it("uses popup authentication in an iframe or when explicitly requested", () => {
    expect(isEmbeddedAnalyzer("", true)).toBe(true);
    expect(isEmbeddedAnalyzer("?embedded=true", false)).toBe(true);
    expect(isEmbeddedAnalyzer("?imbedded", false)).toBe(true);
  });

  it("keeps redirect authentication for the standalone analyzer", () => {
    expect(isEmbeddedAnalyzer("", false)).toBe(false);
    expect(isEmbeddedAnalyzer("?embedded=false", false)).toBe(false);
    expect(isEmbeddedAnalyzer("?imbedded=0", false)).toBe(false);
  });
});
