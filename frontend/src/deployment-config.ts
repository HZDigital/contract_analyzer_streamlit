export type DeploymentLogo = string | { light: string; dark: string };

export interface DeploymentConfig {
  company_name?: string;
  assistant_name?: string;
  header_logo?: DeploymentLogo;
  login_logo?: DeploymentLogo;
  favicon?: string;
  tab_text?: string;
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function parseLogo(value: unknown): DeploymentLogo | undefined {
  const direct = nonEmptyString(value);
  if (direct) {
    return direct;
  }
  if (typeof value !== "object" || value === null) {
    return undefined;
  }
  const logo = value as Record<string, unknown>;
  const light = nonEmptyString(logo.light);
  const dark = nonEmptyString(logo.dark);
  return light && dark ? { light, dark } : undefined;
}

export function parseDeploymentConfig(value: unknown): DeploymentConfig {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return {};
  }
  const raw = value as Record<string, unknown>;

  return {
    company_name: nonEmptyString(raw.company_name),
    assistant_name: nonEmptyString(raw.assistant_name),
    header_logo: parseLogo(raw.header_logo),
    login_logo: parseLogo(raw.login_logo),
    favicon: nonEmptyString(raw.favicon),
    tab_text: nonEmptyString(raw.tab_text),
  };
}

export async function loadDeploymentConfig(url = import.meta.env.VITE_DEPLOYMENT_CONFIGURATION?.trim()): Promise<DeploymentConfig> {
  if (!url) {
    return {};
  }
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(5_000) });
    if (!response.ok) {
      throw new Error(`Configuration request failed (${response.status}).`);
    }
    return parseDeploymentConfig(await response.json());
  } catch (error) {
    console.error("Unable to load Contract Analyzer deployment configuration.", error);
    return {};
  }
}

export function deploymentName(config: DeploymentConfig): string {
  return config.company_name ?? config.assistant_name ?? "Lizzy";
}

export function logoUrl(logo: DeploymentLogo | undefined, surface: "light" | "dark"): string | undefined {
  return typeof logo === "string" ? logo : logo?.[surface];
}

function upsertLink(rel: string, href: string): void {
  let link = document.querySelector<HTMLLinkElement>(`link[rel='${rel}']`);
  if (!link) {
    link = document.createElement("link");
    link.rel = rel;
    document.head.appendChild(link);
  }
  link.href = href;
}

export function applyDeploymentBranding(config: DeploymentConfig): void {
  const title = config.tab_text ?? `${deploymentName(config)} Contract Analyzer`;
  document.title = title;
  for (const name of ["application-name", "apple-mobile-web-app-title"]) {
    let meta = document.querySelector<HTMLMetaElement>(`meta[name='${name}']`);
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = name;
      document.head.appendChild(meta);
    }
    meta.content = title;
  }
  if (config.favicon) {
    upsertLink("icon", config.favicon);
    upsertLink("apple-touch-icon", config.favicon);
  }
}

export function loadExternalStylesheet(url = import.meta.env.VITE_DEPLOYMENT_CSS?.trim()): void {
  if (!url) {
    return;
  }
  const id = "contract-analyzer-deployment-css";
  const current = document.getElementById(id) as HTMLLinkElement | null;
  if (current) {
    current.href = url;
    return;
  }
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.type = "text/css";
  link.href = url;
  link.addEventListener("error", () => console.error(`Unable to load deployment stylesheet: ${url}`));
  document.head.appendChild(link);
}
