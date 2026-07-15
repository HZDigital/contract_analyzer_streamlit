# Contract Analyzer frontend

Standalone Vite SPA for the contract-analyzer job API.

## Run

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set `VITE_MSAL_CLIENT_ID` and `VITE_MSAL_AUTHORITY` to the existing shared app registration. The SPA requests `<client-id>/.default`, matching ProcurementSuite. The configured redirect URI must be registered in Azure AD.

The browser only calls same-origin `/api` endpoints. Authentication is provided by MSAL through `acquireTokenSilent`; no application code reads or stores access tokens.

```bash
npm run test
npm run build
```
