import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

export function isEmbeddedAnalyzer(
  search = typeof window === "undefined" ? "" : window.location.search,
  inFrame = typeof window !== "undefined" && window.self !== window.top,
): boolean {
  const query = new URLSearchParams(search);
  const isEnabled = (name: string): boolean => {
    const value = query.get(name)?.toLowerCase();
    return value === "" || value === "true" || value === "1";
  };
  return inFrame || isEnabled("embedded") || isEnabled("imbedded");
}

export class EmbeddedAuthenticationRequiredError extends Error {
  constructor() {
    super("Continue with Microsoft to refresh the embedded analyzer session.");
    this.name = "EmbeddedAuthenticationRequiredError";
  }
}

const authenticationListeners = new Set<() => void>();
let popupAttempt: Promise<void> | undefined;

export function requireEmbeddedAuthentication(): void {
  authenticationListeners.forEach((listener) => listener());
}

export function subscribeToEmbeddedAuthentication(listener: () => void): () => void {
  authenticationListeners.add(listener);
  return () => authenticationListeners.delete(listener);
}

export function continueEmbeddedAuthentication(
  instance: IPublicClientApplication,
  account: AccountInfo,
  scopes: string[],
): Promise<void> {
  if (!popupAttempt) {
    popupAttempt = instance.acquireTokenPopup({ account, scopes })
      .then(() => undefined)
      .finally(() => {
        popupAttempt = undefined;
      });
  }
  return popupAttempt;
}
