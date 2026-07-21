import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App, { ConfigurationError } from "./App";
import { hasMsalConfiguration, missingMsalSettings, msalConfig } from "./config";
import { applyDeploymentBranding, loadDeploymentConfig, loadExternalStylesheet } from "./deployment-config";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);
loadExternalStylesheet();

async function start(): Promise<void> {
  const deploymentConfigPromise = loadDeploymentConfig();
  if (!hasMsalConfiguration) {
    const deploymentConfig = await deploymentConfigPromise;
    applyDeploymentBranding(deploymentConfig);
    root.render(
      <StrictMode>
        <ConfigurationError config={deploymentConfig} missingSettings={missingMsalSettings} />
      </StrictMode>,
    );
    return;
  }

  try {
    const instance = new PublicClientApplication(msalConfig);
    const authenticationPromise = instance.initialize().then(() => instance.handleRedirectPromise());
    const [, deploymentConfig] = await Promise.all([authenticationPromise, deploymentConfigPromise]);
    applyDeploymentBranding(deploymentConfig);
    root.render(
      <StrictMode>
        <MsalProvider instance={instance}>
          <App config={deploymentConfig} />
        </MsalProvider>
      </StrictMode>,
    );
  } catch (error) {
    const deploymentConfig = await deploymentConfigPromise;
    applyDeploymentBranding(deploymentConfig);
    root.render(
      <StrictMode>
        <ConfigurationError config={deploymentConfig} initializationError={error instanceof Error ? error.message : "MSAL could not initialize."} />
      </StrictMode>,
    );
  }
}

void start();
