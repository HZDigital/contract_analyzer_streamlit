import { describe, expect, it, vi } from "vitest";
import { getOrStartSsoAttempt } from "./auth-bootstrap";

describe("silent SSO bootstrap", () => {
  it("reuses one request when Strict Mode remounts the effect", async () => {
    const start = vi.fn(async () => "account");
    const attempt: { current: Promise<string> | undefined } = { current: undefined };

    const first = getOrStartSsoAttempt(attempt, start);
    const second = getOrStartSsoAttempt(attempt, start);

    expect(start).toHaveBeenCalledOnce();
    expect(second).toBe(first);
    await expect(second).resolves.toBe("account");
  });
});
