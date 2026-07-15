import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App, { ConfigurationError } from "./App";
import { hasMsalConfiguration, missingMsalSettings, msalConfig } from "./config";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

async function start(): Promise<void> {
  if (!hasMsalConfiguration) {
    root.render(
      <StrictMode>
        <ConfigurationError missingSettings={missingMsalSettings} />
      </StrictMode>,
    );
    return;
  }

  try {
    const instance = new PublicClientApplication(msalConfig);
    await instance.initialize();
    await instance.handleRedirectPromise();
    root.render(
      <StrictMode>
        <MsalProvider instance={instance}>
          <App />
        </MsalProvider>
      </StrictMode>,
    );
  } catch (error) {
    root.render(
      <StrictMode>
        <ConfigurationError initializationError={error instanceof Error ? error.message : "MSAL could not initialize."} />
      </StrictMode>,
    );
  }
}

void start();
