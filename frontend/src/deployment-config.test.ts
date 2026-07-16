import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deploymentName,
  loadDeploymentConfig,
  loadExternalStylesheet,
  logoUrl,
  parseDeploymentConfig,
} from "./deployment-config";

describe("deployment configuration", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("parses shared branding", () => {
    const config = parseDeploymentConfig({
      company_name: "Acme Procurement",
      header_logo: { light: "light.svg", dark: "dark.svg" },
    });

    expect(deploymentName(config)).toBe("Acme Procurement");
    expect(logoUrl(config.header_logo, "dark")).toBe("dark.svg");
  });

  it("ignores malformed branding values", () => {
    expect(parseDeploymentConfig(undefined)).toEqual({});
    expect(parseDeploymentConfig({ header_logo: { light: "only-one.svg" } }).header_logo).toBeUndefined();
  });

  it("returns a safe empty configuration when the remote request fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(loadDeploymentConfig("https://config.example/config.json")).resolves.toEqual({});
  });

  it("adds the external stylesheet once and updates the existing link", () => {
    const elements = new Map<string, Record<string, unknown>>();
    const appended: Array<Record<string, unknown>> = [];
    vi.stubGlobal("document", {
      getElementById: (id: string) => elements.get(id) ?? null,
      createElement: () => ({ addEventListener: vi.fn() }),
      head: {
        appendChild: (element: Record<string, unknown>) => {
          appended.push(element);
          elements.set(String(element.id), element);
        },
      },
    });

    loadExternalStylesheet("https://cdn.example.com/first.css");
    loadExternalStylesheet("https://cdn.example.com/second.css");

    expect(appended).toHaveLength(1);
    expect(appended[0]).toMatchObject({
      id: "contract-analyzer-deployment-css",
      rel: "stylesheet",
      type: "text/css",
      href: "https://cdn.example.com/second.css",
    });
  });
});
