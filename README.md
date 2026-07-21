# Contract Analyzer

Contract Analyzer is a single-container web application for analyzing contracts and related documents. A React single-page application (SPA) is compiled with Vite during the image build and served by the FastAPI application at `src.api.main:app`. The same FastAPI runtime exposes the API, validates Entra ID access tokens, and stores jobs and artifacts in Azure Blob Storage.

## Architecture

- **SPA:** React/Vite frontend, built in a Node 22 LTS stage and copied to `frontend/dist` in the runtime image.
- **API:** FastAPI/Uvicorn serves the SPA and API from the same origin on `PORT` (default `8080`).
- **Jobs:** Azure Blob Storage is the only job and artifact store. The service does not use a `results` directory or a mounted volume.
- **OCR:** DeepSeek-OCR is the primary OCR engine. Its Hugging Face snapshot is downloaded while the image is built; `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` prevent production runtime downloads. Tesseract remains the fallback when DeepSeek-OCR cannot process a page.

The runtime image uses `python:3.13-slim-bookworm`, contains Tesseract and Poppler, and runs as an unprivileged `app` user. Its health endpoint is `GET /health`.

## Analysis Modules

The frontend groups seven active workflow IDs into modules that match day-to-day tasks. The legacy `tender` backend workflow remains available only for historical job compatibility; users cannot start new Tender analyses from the SPA.

| Module | Mode | Backend workflow |
| --- | --- | --- |
| Contract review | Standard review | `detailed_contract` |
| Contract review | Deep review | `large_scanner` |
| Compare with standard | Agreement comparison | `cooperation_review` |
| Product request | Demand extraction | `product_request` |
| Invoice | Invoice extraction | `invoice` |
| Invoice | Regular hours and rates | `normalstunden` |
| Factory certificate | Certificate comparison | `factory_certificate` |

All five modules and all seven user-facing workflows are always available to authenticated users.

### Customized Analysis

Every user-facing workflow has an output editor. Its standard business fields are included by default and can be removed individually when they are not needed. Extraction still uses the stable workflow contract, but removed fields are omitted from the published result and its generated exports. Status, source provenance, validation messages, and retention information remain mandatory.

Users can also enter an optional analysis instruction and define up to 20 additional named output fields. Supported field types are text, number, yes/no, and list. Additional findings and requested fields appear in a separate **Customized output** section and in the curated JSON export.

Customization does not replace the application's fixed system and security rules. The custom analyzer must use only supplied source text, treats instructions inside documents as data, returns only the declared structure, and cannot expose hidden prompts, credentials, or implementation context. Unexpected model keys are discarded. Quotations are retained as evidence only when their normalized wording exists in the named source, and Deep review page references are retained only when they identify pages in the analyzed section.

Each custom-analysis request examines at most 30,000 source characters. Multi-document comparisons distribute that allowance across their source files; Deep review applies customization to each existing page-labelled chunk and merges the results. Customized analysis adds model calls and can therefore increase processing time and cost. When no custom instruction or output field is supplied, no custom model call is made.

## Required Configuration

Copy `.env.example` to `.env` and replace every placeholder before running the stack. Do not commit `.env`.

| Setting | Purpose |
| --- | --- |
| `AZURE_STORAGE_CONTAINER_NAME` | Must be `contract-analyzer`, the private container used for analyzer jobs and artifacts. |
| `AZURE_STORAGE_CONNECTION_STRING` | Required Blob Storage connection string. Store it as a Container App secret in Azure and keep it out of source control. |
| `ENTRA_API_AUDIENCE` | Required exact audience of analyzer API v2 access tokens: the bare `<application-client-id>`. |
| `ENTRA_ALLOWED_TENANT_IDS` | Optional comma-separated tenant allow-list. Omit it to accept signed analyzer tokens from every organizational Entra tenant. |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI endpoint, key, and deployed model name. |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version; defaults to `2024-12-01-preview`. |
| `SEARXNG_URL` | SearXNG base URL used by market-research workflows. |
| `PORT` | FastAPI listener port. Defaults to `8080`. |

The backend reads `.env`. Browser `VITE_*` variables belong only in `frontend/.env`; they are embedded into static files at build time and are public application metadata, not secrets. Changing them requires rebuilding the image; setting them only on a running Container App does not change the SPA.

### Shared Branding

The analyzer accepts the same external deployment files as ProcurementSuite:

| Build setting | Purpose |
| --- | --- |
| `VITE_DEPLOYMENT_CONFIGURATION` | URL of the shared JSON configuration fetched by the browser at startup. |
| `VITE_DEPLOYMENT_CSS` | URL of an optional tenant stylesheet loaded once after the bundled stylesheet. |

The JSON can use ProcurementSuite's existing `company_name`, `assistant_name`, `header_logo`, `login_logo`, `favicon`, and `tab_text` fields. A logo can be a URL string or `{ "light": "...", "dark": "..." }`. Configuration and stylesheet hosts must permit cross-origin browser requests from the analyzer. The external stylesheet can override ProcurementSuite-compatible, space-separated HSL variables such as `--head`, `--hand`, `--heart`, `--primary`, `--primary-hover`, `--background`, `--foreground`, `--border`, and `--sidebar-background`:

```css
:root {
  --head: 210 80% 42%;
  --primary: var(--head);
  --sidebar-background: 220 24% 16%;
}
```

## Azure Storage Access And Retention

Configure `AZURE_STORAGE_CONNECTION_STRING` as a Container App secret and expose that secret to the application environment. It permits job creation, status updates, artifact uploads, and downloads in the private analyzer container. Do not place the connection string in repository variables, Docker build arguments, or frontend settings.

The deployment workflow merges and reads back `infra/storage-lifecycle-policy.json` before each deployment, preserving lifecycle rules owned by other workloads on a shared storage account. Set the repository variable `AZURE_STORAGE_ACCOUNT_NAME` and grant the deployment identity permission to manage the storage account's lifecycle policy. The policy targets the required `contract-analyzer` container:

- Delete blobs tagged `kind=manifest`, `kind=artifact`, `kind=context`, or `kind=source` with `retention=temporary` 60 days after last modification.
- Do not add a deletion rule matching those result kinds with `retention=permanent`; permanent results are exempt from automatic deletion.
- Delete blobs tagged `kind=input` after one day. The service deletes inputs when a job reaches a terminal state; this is a safeguard for interrupted uploads.
- Delete `kind=source`, `kind=artifact`, and `kind=context` blobs with `retention=transient` after a seven-day recovery window. Sources, exports, and analysis context are promoted to the selected job retention only after their private manifest checkpoint is durable.
- Delete private `kind=outcome`, `retention=transient` workflow checkpoints after the same seven-day recovery window. These contain the result and export bytes only long enough to make interrupted finalization replayable without another model call.

Transient processing inputs are removed after every terminal job. After a successful analysis, the original source files are copied into the private job prefix so authenticated users can reopen evidence from the result view. For Normalstunden ZIP uploads, eligible member PDFs are retained as private derived sources alongside the original archive so their result evidence can open in the PDF review drawer. Retained sources follow the job's selected retention: temporary sources expire after 60 days, permanent sources remain until the job is deleted manually, and deleting a job removes its manifest, outputs, context, and sources. Jobs completed before source retention was introduced cannot provide a source preview.

The API exposes retained documents only through owner-scoped opaque source IDs. It does not return Blob paths or SAS URLs. PDF references with a source filename and quote or page open in a lazy-loaded review drawer. The browser highlights only an exact normalized quote match in the PDF text layer; scanned documents without a text layer can be opened at the reported page but require OCR coordinates for pixel-accurate highlighting.

## Public Result Contract

`GET /api/jobs` returns register summaries only: analysis ID, workflow, status, timestamps used for sorting/polling, progress, and source filenames. It does not transfer completed result bodies, source selectors, artifact selectors, or detailed errors. `GET /api/jobs/{id}` returns the owner-scoped detail only when a user opens that analysis.

Completed results pass through a workflow-specific allow-list before they are stored in the public manifest or returned by the API. The projection preserves business fields, structured findings, exact quotations, page references, and recommendations while removing private scanner context, chunk identifiers, processing settings, raw provider errors, and unexpected model keys. User-facing errors use stable remediation text; raw exception details belong in server logs. JSON exports use the same curated projection. In particular, the large-scanner evidence export does not include `qa_context`, extracted working chunks, or raw chunk responses.

The detail view displays the selected retention and scheduled temporary expiry, source roles, and workflow-specific coverage limitations. Current material limitations include:

- Standard contract review automatically analyzes up to the first 30,000 characters; Deep review should be used for longer documents, schedules, and complete page-level evidence.
- Cooperation comparison truncates the combined supplier side and standard side to the configured limit and does not reliably attribute a combined finding to one supplier document.
- Factory comparison examines the first 8,000 characters per readable document and its tolerance statuses remain AI interpretations.
- Tender market observations are external research hypotheses; uncalibrated win-probability fields are not published.
- Invoice extraction does not perform ERP, purchase-order, supplier-master, or duplicate-invoice reconciliation.
- Regular-hours mode excludes detected surcharge lines; `no_match` is a neutral outcome rather than a processing failure.

## Entra ID Setup

The SPA and API use the same Entra app registration.

1. Under **Supported account types**, select **Accounts in any organizational directory**.
2. Register the deployed application URL, `http://localhost:8080`, and `http://localhost:5173` as **Single-page application** redirect URIs. Add any additional environment origins explicitly.
3. Grant users or groups access as required by each tenant policy. Tenant administrators must consent when their policy requires it.
4. Set `ENTRA_API_AUDIENCE=<application-client-id>` for API token validation. Entra v2 access tokens use the bare client ID in their `aud` claim, even though the SPA requests `<application-client-id>/.default`. The API accepts valid Entra v1 (`sts.windows.net`) and v2 (`login.microsoftonline.com`) issuer formats, each bound to the signed tenant ID. Do not set a tenant ID to restrict the API; by default it validates organizational tokens whose signed `tid` and issuer agree. Set `ENTRA_ALLOWED_TENANT_IDS` only when an explicit allow-list is required.
5. Set the SPA build variables: `VITE_MSAL_CLIENT_ID=<application-client-id>` and `VITE_MSAL_AUTHORITY=https://login.microsoftonline.com/organizations`. The SPA requests `<application-client-id>/.default`, matching ProcurementSuite. `VITE_MSAL_REDIRECT_URI` is optional and otherwise uses the current origin. Set `VITE_DEPLOYMENT_CONFIGURATION` and `VITE_DEPLOYMENT_CSS` when shared tenant branding is required.

For GitHub deployment, configure the same `VITE_*` values as repository variables. The workflow passes them as Docker build arguments so they are included in the compiled SPA.

## Local Development

### Full Container Stack

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
set -a
. frontend/.env
set +a
docker-compose up --build
```

Open `http://localhost:8080`; the health check is available at `http://localhost:8080/health`.

### API And SPA Separately

Install Python 3.13, Node 22 LTS, Tesseract, and Poppler. Run these commands from the repository root. The API reads `.env`; Vite reads `frontend/.env` and proxies `/api` to FastAPI during development.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# Required once for DeepSeek-primary OCR in local development.
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='deepseek-ai/DeepSeek-OCR')"
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8080
```

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Open `http://localhost:5173`. The Vite dev server forwards `/api/*` to `http://localhost:8080`, so the SPA uses the same API paths as production. If you instead run a compiled SPA through FastAPI, open `http://localhost:8080`.

The DeepSeek snapshot is intentionally not downloaded at API startup. If it is absent locally, OCR falls back to Tesseract; use the one-time command above to match the production DeepSeek-primary behavior.

Run backend tests with `pip install -r requirements-dev.txt` followed by `pytest`.

## Deployment

The GitHub Actions workflow builds the multi-stage image, deploys it to the `contractanalyzer` Azure Container App with external ingress targeting port `8080`, and then sets the app's minimum replica count to one. Configure the Container App with the required runtime settings and its managed identity before deployment. The workflow does not inject secrets into the image.
