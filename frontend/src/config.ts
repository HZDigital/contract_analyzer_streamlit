import { BrowserCacheLocation, type Configuration } from "@azure/msal-browser";

const configuredClientId = import.meta.env.VITE_MSAL_CLIENT_ID?.trim() ?? "";
const configuredAuthority = import.meta.env.VITE_MSAL_AUTHORITY?.trim() ?? "";

export const msalClientId = configuredClientId;
// Match ProcurementSuite: request the app registration's static permissions.
export const analyzerApiScopes = configuredClientId ? [`${configuredClientId}/.default`] : [];

export const missingMsalSettings = [
  !configuredClientId ? "VITE_MSAL_CLIENT_ID" : "",
  !configuredAuthority ? "VITE_MSAL_AUTHORITY" : "",
].filter(Boolean);

export const hasMsalConfiguration = missingMsalSettings.length === 0;

export const msalConfig: Configuration = {
  auth: {
    clientId: configuredClientId,
    authority: configuredAuthority,
    redirectUri: import.meta.env.VITE_MSAL_REDIRECT_URI?.trim() || window.location.origin,
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: BrowserCacheLocation.SessionStorage,
    storeAuthStateInCookie: false,
  },
};
