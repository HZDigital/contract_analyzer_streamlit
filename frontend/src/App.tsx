import { InteractionStatus, type AccountInfo, type IPublicClientApplication } from "@azure/msal-browser";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import {
  lazy,
  startTransition,
  Suspense,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { AnalyzerApi, AuthRedirectStartedError, errorMessage } from "./api";
import { getOrStartSsoAttempt } from "./auth-bootstrap";
import { analyzerApiScopes } from "./config";
import { deploymentName, logoUrl, type DeploymentConfig } from "./deployment-config";
import { hasActiveJobs, isTerminalJob } from "./jobs";
import { ResultView } from "./result-view";
import type {
  AnalyzerJob,
  CustomOutputField,
  CustomOutputType,
  OptionValue,
  ResultReference,
  Retention,
  SubmittedFile,
} from "./types";
import {
  analysisModules,
  moduleById,
  workflowById,
  workflowTitle,
  type AnalysisModuleDefinition,
  type AnalysisModuleId,
  type FileInputDefinition,
  type OptionDefinition,
  type WorkflowDefinition,
  type WorkflowId,
} from "./workflows";

type View = "dashboard" | "submit" | "history";
type NormalstundenSource = "pdf" | "zip";

const POLLING_INTERVAL_MS = 8_000;
const MAX_CUSTOM_INSTRUCTION_LENGTH = 6_000;
const MAX_CUSTOM_OUTPUT_FIELDS = 20;
let customFieldSequence = 0;
const SourcePreviewDrawer = lazy(() => import("./source-preview-drawer"));

function formatDate(value?: string): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function fileTypeLabel(contentType?: string, filename?: string): string {
  const extension = filename?.split(".").pop()?.toLowerCase();
  if (contentType === "application/pdf" || extension === "pdf") {
    return "PDF document";
  }
  if (contentType?.includes("spreadsheet") || extension === "xlsx") {
    return "Excel workbook";
  }
  if (contentType?.includes("wordprocessingml") || contentType === "application/msword" || extension === "docx" || extension === "doc") {
    return "Word document";
  }
  if (contentType === "text/csv" || contentType?.startsWith("text/csv;") || extension === "csv") {
    return "CSV data";
  }
  if (contentType?.includes("json") || extension === "json") {
    return "JSON data";
  }
  if (contentType?.includes("markdown") || extension === "md") {
    return "Review report";
  }
  if (contentType?.includes("zip") || extension === "zip") {
    return "ZIP archive";
  }
  return "File";
}

function sourceRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    requests: "Request document",
    invoices: "Invoice",
    normalstundenPdfs: "Invoice",
    normalstundenArchive: "Invoice archive",
    normalstundenArchivePdf: "Invoice from archive",
    contracts: "Contract",
    contract: "Contract",
    tenderDocuments: "Tender document",
    tenderTemplate: "Tender template",
    supplierAgreements: "Supplier agreement",
    standardContract: "Standard contract",
    comparisonDocuments: "Specification or certificate",
  };
  return labels[role] ?? "Source document";
}

function statusClass(status: string): string {
  if (status === "completed") {
    return "status-completed";
  }
  if (status === "failed") {
    return "status-failed";
  }
  if (status === "running" || status === "processing" || status === "in_progress") {
    return "status-running";
  }
  if (status === "cancelled" || status === "canceled") {
    return "status-cancelled";
  }
  return "status-queued";
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function initialOptions(workflow: WorkflowDefinition): Record<string, OptionValue> {
  return Object.fromEntries(workflow.options.map((option) => [option.id, option.defaultValue]));
}

function newCustomOutputField(): CustomOutputField {
  customFieldSequence += 1;
  return { id: `custom-field-${customFieldSequence}`, name: "", instruction: "", type: "text" };
}

function answerText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "object" && value !== null) {
    const response = value as Record<string, unknown>;
    const directAnswer = response.answer ?? response.response ?? response.result;
    if (typeof directAnswer === "string") {
      return directAnswer;
    }
  }
  return JSON.stringify(value, null, 2);
}

function useJobs(instance: IPublicClientApplication, account: AccountInfo | undefined) {
  const [jobs, setJobs] = useState<AnalyzerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [reloadKey, setReloadKey] = useState(0);
  const accountId = account?.homeAccountId;
  const accountRef = useRef(account);
  accountRef.current = account;

  useEffect(() => {
    const activeAccount = accountRef.current;
    if (!activeAccount) {
      setJobs([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let inFlight = false;
    let timer: number | undefined;

    function scheduleNextPoll(): void {
      if (!cancelled) {
        timer = window.setTimeout(() => void load(false), POLLING_INTERVAL_MS);
      }
    }

    async function load(showLoading: boolean): Promise<void> {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      let shouldPoll = false;
      if (showLoading) {
        setLoading(true);
      }
      try {
        const accountForRequest = accountRef.current;
        if (!accountForRequest) {
          return;
        }
        const nextJobs = await new AnalyzerApi(instance, accountForRequest).getJobs();
        if (!cancelled) {
          startTransition(() => setJobs(nextJobs));
          setError(undefined);
          shouldPoll = hasActiveJobs(nextJobs);
        }
      } catch (requestError) {
        if (!cancelled && !(requestError instanceof AuthRedirectStartedError)) {
          setError(errorMessage(requestError));
        }
      } finally {
        inFlight = false;
        if (!cancelled && showLoading) {
          setLoading(false);
        }
        if (shouldPoll) {
          scheduleNextPoll();
        }
      }
    }

    void load(true);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  // MSAL can recreate AccountInfo objects from its cache, so object identity
  // must not restart the polling lifecycle after every state update.
  }, [accountId, instance, reloadKey]);

  return {
    jobs,
    loading,
    error,
    refresh: () => setReloadKey((value) => value + 1),
  };
}

export function ConfigurationError({
  config,
  missingSettings,
  initializationError,
}: {
  config: DeploymentConfig;
  missingSettings?: string[];
  initializationError?: string;
}) {
  return (
    <main className="setup-page">
      <section className="setup-card" aria-labelledby="setup-title">
        <BrandLogo config={config} logo={config.login_logo ?? config.header_logo} surface="light" />
        <p className="eyebrow">Contract analyzer</p>
        <h1 id="setup-title">Authentication needs configuration</h1>
        <p>
          Add the shared Azure AD registration settings before opening the analyzer.
        </p>
        {missingSettings && missingSettings.length > 0 ? (
          <p className="inline-error">Missing: {missingSettings.join(", ")}</p>
        ) : null}
        {initializationError ? <p className="inline-error">{initializationError}</p> : null}
        <code>cp .env.example .env.local</code>
      </section>
    </main>
  );
}

function SignInScreen({ config }: { config: DeploymentConfig }) {
  const { instance, inProgress } = useMsal();
  const [error, setError] = useState<string>();

  async function signIn(): Promise<void> {
    setError(undefined);
    try {
      await instance.loginRedirect({ scopes: analyzerApiScopes });
    } catch (loginError) {
      setError(errorMessage(loginError));
    }
  }

  return (
    <main className="setup-page">
      <section className="setup-card" aria-labelledby="sign-in-title">
        <BrandLogo config={config} logo={config.login_logo ?? config.header_logo} surface="light" />
        <p className="eyebrow">{deploymentName(config)}</p>
        <h1 id="sign-in-title">Contract Analyzer</h1>
        <p>Analyze commercial documents, review contracts, and retrieve auditable results in one secure workspace.</p>
        {error ? <p className="inline-error" role="alert">{error}</p> : null}
        <button className="primary-button" type="button" onClick={() => void signIn()} disabled={inProgress !== InteractionStatus.None}>
          Sign in with Microsoft
        </button>
      </section>
    </main>
  );
}

function App({ config }: { config: DeploymentConfig }) {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const activeAccountId = instance.getActiveAccount()?.homeAccountId;
  const account = accounts.find((candidate) => candidate.homeAccountId === activeAccountId) ?? accounts[0];
  const [ssoResolved, setSsoResolved] = useState(false);
  const ssoAttempt = useRef<Promise<AccountInfo | undefined> | undefined>(undefined);
  const [view, setView] = useState<View>("dashboard");
  const [selectedModuleId, setSelectedModuleId] = useState<AnalysisModuleId>("contract_review");
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowId>("detailed_contract");
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [desktopNavigation, setDesktopNavigation] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(min-width: 769px)").matches === true,
  );
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [submissionPending, setSubmissionPending] = useState(false);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const { jobs, loading, error, refresh } = useJobs(instance, account);
  const modules = analysisModules;
  const query = typeof window === "undefined" ? undefined : new URLSearchParams(window.location.search);
  const hideAccountPanel = query?.has("imbedded") === true || query?.has("embedded") === true;

  useEffect(() => {
    if (account && !instance.getActiveAccount()) {
      instance.setActiveAccount(account);
    }
  }, [account, instance]);

  useEffect(() => {
    if (!window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(min-width: 769px)");
    const updateDesktopNavigation = (): void => setDesktopNavigation(media.matches);
    updateDesktopNavigation();
    media.addEventListener("change", updateDesktopNavigation);
    return () => media.removeEventListener("change", updateDesktopNavigation);
  }, []);

  useEffect(() => {
    if (account) {
      setSsoResolved(true);
      return;
    }
    if (ssoResolved) {
      return;
    }

    let attempt = ssoAttempt.current;
    if (!attempt) {
      if (inProgress !== InteractionStatus.None) {
        return;
      }
      // React Strict Mode remounts effects in development. Keep the request in
      // a ref so the replacement effect still observes its completion.
      attempt = getOrStartSsoAttempt(ssoAttempt, () =>
        instance
          .ssoSilent({ scopes: analyzerApiScopes })
          .then((result) => result.account)
          // A missing Entra browser session is expected for first-time visitors.
          // The sign-in screen below starts an interactive redirect only then.
          .catch(() => undefined),
      );
    }

    let cancelled = false;
    void attempt.then((ssoAccount) => {
      if (cancelled) {
        return;
      }
      if (ssoAccount) {
        instance.setActiveAccount(ssoAccount);
      }
      setSsoResolved(true);
    });
    return () => {
      cancelled = true;
    };
  }, [account, inProgress, instance, ssoResolved]);

  useEffect(() => {
    if (!mobileSidebarOpen) {
      return;
    }
    mobileCloseRef.current?.focus();
    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setMobileSidebarOpen(false);
        window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileSidebarOpen]);

  useEffect(() => {
    if (!accountMenuOpen) {
      return;
    }

    function closeOnOutsidePointer(event: PointerEvent): void {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountMenuOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setAccountMenuOpen(false);
      }
    }

    window.addEventListener("pointerdown", closeOnOutsidePointer);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnOutsidePointer);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountMenuOpen]);

  if (inProgress === InteractionStatus.Startup || inProgress === InteractionStatus.HandleRedirect) {
    return <LoadingScreen />;
  }

  if (!account && !ssoResolved) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated || !account) {
    return <SignInScreen config={config} />;
  }

  const activeModule = moduleById(selectedModuleId) ?? modules[0];
  const activeWorkflow = workflowById(selectedWorkflow) ?? workflowById(activeModule.defaultWorkflowId)!;
  const navigationTitleVisible = desktopNavigation && !sidebarCollapsed;

  function openModule(moduleId: AnalysisModuleId): void {
    if (submissionPending) {
      return;
    }
    const module = moduleById(moduleId);
    if (!module) {
      return;
    }
    setSelectedModuleId(moduleId);
    setSelectedWorkflow(module.defaultWorkflowId);
    setView("submit");
    setMobileSidebarOpen(false);
  }

  function openView(nextView: View): void {
    if (submissionPending) {
      return;
    }
    if (nextView === "history") {
      setSelectedJobId(undefined);
    }
    setView(nextView);
    setMobileSidebarOpen(false);
  }

  function openJob(jobId: string): void {
    setSelectedJobId(jobId);
    setView("history");
  }

  function jobSubmitted(job: AnalyzerJob | undefined): void {
    if (job) {
      setSelectedJobId(job.id);
    }
    setView("history");
    refresh();
  }

  async function signOut(): Promise<void> {
    await instance.logoutRedirect({ account });
  }

  return (
    <div className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <button
        className={mobileSidebarOpen ? "sidebar-backdrop open" : "sidebar-backdrop"}
        type="button"
        aria-label="Close navigation"
        onClick={() => {
          setMobileSidebarOpen(false);
          window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
        }}
      />
      <aside className={mobileSidebarOpen ? "sidebar mobile-open" : "sidebar"}>
        <div className="sidebar-header">
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
            title={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
            onClick={() => setSidebarCollapsed((current) => !current)}
          >
            <SidebarToggleIcon />
          </button>
          <button
            className="mobile-close"
            ref={mobileCloseRef}
            type="button"
            aria-label="Close navigation"
            onClick={() => {
              setMobileSidebarOpen(false);
              window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
            }}
          >
            Close
          </button>
        </div>
        <nav className="primary-nav" aria-label="Main navigation">
          <button className={view === "dashboard" ? "nav-button active" : "nav-button"} type="button" title={navigationTitleVisible ? "Overview" : undefined} aria-label="Overview" disabled={submissionPending} onClick={() => openView("dashboard")}>
            <span className="nav-icon" aria-hidden="true">OV</span><span className="nav-label">Overview</span>
          </button>
          <button className={view === "history" ? "nav-button active" : "nav-button"} type="button" title={navigationTitleVisible ? "Job history" : undefined} aria-label="Job history" disabled={submissionPending} onClick={() => openView("history")}>
            <span className="nav-icon" aria-hidden="true">JB</span><span className="nav-label">Job history</span>
          </button>
        </nav>
        <div className="workflow-nav">
          <p>New analysis</p>
          {modules.map((module) => (
            <button
              className={view === "submit" && selectedModuleId === module.id ? "workflow-link active" : "workflow-link"}
              key={module.id}
              type="button"
              title={navigationTitleVisible ? module.title : undefined}
              aria-label={module.title}
              disabled={submissionPending}
              onClick={() => openModule(module.id)}
            >
              <span>{module.shortCode}</span>
              <span className="nav-label">{module.title}</span>
            </button>
          ))}
        </div>
        {hideAccountPanel ? null : (
          <div className={accountMenuOpen ? "account-panel open" : "account-panel"} ref={accountMenuRef}>
            <button
              className="account-trigger"
              type="button"
              aria-label={`Account menu for ${account.name ?? account.username}`}
              aria-expanded={accountMenuOpen}
              aria-haspopup="menu"
              onClick={() => setAccountMenuOpen((open) => !open)}
            >
              <span className="account-initial" aria-hidden="true">{(account.name ?? account.username).slice(0, 1).toUpperCase()}</span>
              <span className="account-name nav-label" title={account.username}>{account.name ?? account.username}</span>
              <svg className="account-chevron nav-label" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m9 18 6-6-6-6" />
              </svg>
            </button>
            {accountMenuOpen ? (
              <div className="account-popover" role="menu" aria-label="Account options">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountMenuOpen(false);
                    void signOut();
                  }}
                >
                  <SignOutIcon />
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        )}
      </aside>
      <main className="main-content">
        <header className={view === "submit" ? "topbar settings-page-header" : "topbar"}>
          <button className="mobile-menu" ref={mobileMenuRef} type="button" aria-label="Open navigation" aria-expanded={mobileSidebarOpen} onClick={() => setMobileSidebarOpen(true)}>Menu</button>
          <div className="topbar-copy">
            <h1>{view === "submit" ? activeModule.title : view === "history" ? selectedJobId ? "Analysis result" : "Job history" : "Analysis overview"}</h1>
            {view === "submit" ? <p>{activeWorkflow.detail}</p> : null}
          </div>
          <button className="secondary-button" type="button" onClick={refresh}>Refresh jobs</button>
        </header>
        {error ? <ErrorNotice message={error} onDismiss={refresh} /> : null}
        {view === "dashboard" ? <Dashboard modules={modules} jobs={jobs} loading={loading} onOpenModule={openModule} onOpenJob={openJob} /> : null}
        {view === "submit" ? (
          <WorkflowSubmission
            key={activeWorkflow.id}
            module={activeModule}
            workflow={activeWorkflow}
            instance={instance}
            account={account}
            onSelectWorkflow={setSelectedWorkflow}
            onSubmittingChange={setSubmissionPending}
            onSubmitted={jobSubmitted}
          />
        ) : null}
        {view === "history" ? (
          <HistoryPage
            jobs={jobs}
            loading={loading}
            selectedJobId={selectedJobId}
            instance={instance}
            account={account}
            onSelectJob={setSelectedJobId}
            onDeleted={() => {
              setSelectedJobId(undefined);
              refresh();
            }}
          />
        ) : null}
      </main>
    </div>
  );
}

function SidebarToggleIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m10 17 5-5-5-5" />
      <path d="M15 12H3" />
      <path d="M21 19V5a2 2 0 0 0-2-2h-6" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

function BrandLogo({
  config,
  logo,
  surface,
  compact = false,
}: {
  config: DeploymentConfig;
  logo: DeploymentConfig["header_logo"];
  surface: "light" | "dark";
  compact?: boolean;
}) {
  const source = logoUrl(logo, surface);
  return source
    ? <img className={compact ? "brand-logo compact-logo" : "brand-logo"} src={source} alt={deploymentName(config)} />
    : <span className={compact ? "brand-mark compact-logo" : "brand-mark"} aria-hidden="true">{deploymentName(config).slice(0, 1).toUpperCase()}</span>;
}

function LoadingScreen() {
  return (
    <main className="setup-page">
      <section className="setup-card loading-card" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <p>Preparing your secure workspace.</p>
      </section>
    </main>
  );
}

function ErrorNotice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="error-notice" role="alert">
      <span>{message}</span>
      <button type="button" onClick={onDismiss}>Retry</button>
    </div>
  );
}

function Dashboard({
  modules,
  jobs,
  loading,
  onOpenModule,
  onOpenJob,
}: {
  modules: AnalysisModuleDefinition[];
  jobs: AnalyzerJob[];
  loading: boolean;
  onOpenModule: (module: AnalysisModuleId) => void;
  onOpenJob: (jobId: string) => void;
}) {
  const completed = jobs.filter((job) => job.status === "completed").length;
  const active = jobs.filter((job) => !isTerminalJob(job.status)).length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  const recentJobs = jobs.slice(0, 5);
  const primaryModule = modules[0];

  return (
    <div className="page-stack">
      <section className="metric-grid" aria-label="Job status summary">
        <article><span>All jobs</span><strong>{loading ? "..." : jobs.length}</strong></article>
        <article><span>In progress</span><strong>{loading ? "..." : active}</strong></article>
        <article><span>Completed</span><strong>{loading ? "..." : completed}</strong></article>
        <article><span>Needs attention</span><strong>{loading ? "..." : failed}</strong></article>
      </section>
      <section>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Analysis modules</p>
            <h2>What would you like to analyze?</h2>
          </div>
        </div>
        <div className="workflow-grid">
          {modules.map((module) => (
            <article className="workflow-card" key={module.id}>
              <button
                className="workflow-card-button"
                type="button"
                aria-label={`Open ${module.title} module`}
                onClick={() => onOpenModule(module.id)}
              >
                <div className="workflow-card-heading">
                  <span className="workflow-code">{module.shortCode}</span>
                  <h3>{module.title}</h3>
                </div>
                <p>{module.description}</p>
                <span className="workflow-card-action">
                  Open module
                  <ArrowRightIcon />
                </span>
              </button>
            </article>
          ))}
        </div>
      </section>
      <section className="recent-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Recent activity</p>
            <h2>Latest jobs</h2>
          </div>
        </div>
        {loading ? <p className="empty-state">Loading jobs...</p> : null}
        {!loading && recentJobs.length === 0 ? <p className="empty-state">No jobs yet. Start with a workflow above.</p> : null}
        {recentJobs.length > 0 ? (
          <div className="recent-list">
            {recentJobs.map((job) => (
              <button className="recent-job" key={job.id} type="button" onClick={() => onOpenJob(job.id)}>
                <span>
                  <strong>{workflowTitle(job.workflow)}</strong>
                  <small>{formatDate(job.createdAt)}</small>
                </span>
                <StatusBadge status={job.status} />
              </button>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function WorkflowSubmission({
  module,
  workflow,
  instance,
  account,
  onSelectWorkflow,
  onSubmittingChange,
  onSubmitted,
}: {
  module: AnalysisModuleDefinition;
  workflow: WorkflowDefinition;
  instance: IPublicClientApplication;
  account: AccountInfo;
  onSelectWorkflow: (workflow: WorkflowId) => void;
  onSubmittingChange: (submitting: boolean) => void;
  onSubmitted: (job: AnalyzerJob | undefined) => void;
}) {
  const [filesByInput, setFilesByInput] = useState<Record<string, File[]>>({});
  const [retention, setRetention] = useState<Retention>("temporary");
  const [options, setOptions] = useState<Record<string, OptionValue>>(() => initialOptions(workflow));
  const [customInstructions, setCustomInstructions] = useState("");
  const [standardOutputFields, setStandardOutputFields] = useState<string[]>(() =>
    workflow.standardOutputFields.map((field) => field.id),
  );
  const [customOutputFields, setCustomOutputFields] = useState<CustomOutputField[]>([]);
  const [normalstundenSource, setNormalstundenSource] = useState<NormalstundenSource>("pdf");
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  function changeFiles(inputId: string, files: File[]): void {
    setFilesByInput((current) => ({ ...current, [inputId]: files }));
  }

  function updateOption(id: string, value: OptionValue): void {
    setOptions((current) => ({ ...current, [id]: value }));
  }

  function updateCustomField(id: string, update: Partial<Omit<CustomOutputField, "id">>): void {
    setCustomOutputFields((current) => current.map((field) => field.id === id ? { ...field, ...update } : field));
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(undefined);

    const inputs = workflow.normalstundenSelection
      ? [normalstundenInput(normalstundenSource)]
      : workflow.inputs;
    const missingInputs = inputs.filter((input) => (filesByInput[input.id]?.length ?? 0) < input.minimum);
    if (missingInputs.length > 0) {
      setError(`Add the required file${missingInputs.length > 1 ? "s" : ""}: ${missingInputs.map((input) => input.label).join(", ")}.`);
      return;
    }
    if (customOutputFields.some((field) => !field.name.trim())) {
      setError("Give every custom output field a name or remove the empty field.");
      return;
    }
    const normalizedNames = customOutputFields.map((field) => field.name.trim().toLowerCase());
    if (new Set(normalizedNames).size !== normalizedNames.length) {
      setError("Custom output field names must be unique.");
      return;
    }

    const files: SubmittedFile[] = inputs.flatMap((input) =>
      (filesByInput[input.id] ?? []).map((file) => ({ role: input.id, file })),
    );
    const submittedOptions: Record<string, unknown> = workflow.normalstundenSelection
      ? { ...options, inputMode: normalstundenSource }
      : { ...options };
    submittedOptions.standardOutputFields = standardOutputFields;
    if (customInstructions.trim()) {
      submittedOptions.customInstructions = customInstructions.trim();
    }
    if (customOutputFields.length > 0) {
      submittedOptions.customOutputFields = customOutputFields.map(({ name, instruction, type }) => ({
        name: name.trim(),
        instruction: instruction.trim(),
        type,
      }));
    }

    setSubmitting(true);
    onSubmittingChange(true);
    try {
      const job = await new AnalyzerApi(instance, account).submitJob({
        workflow: workflow.id,
        retention,
        options: submittedOptions,
        files,
      });
      setFilesByInput({});
      onSubmitted(job);
    } catch (submissionError) {
      if (!(submissionError instanceof AuthRedirectStartedError)) {
        setError(errorMessage(submissionError));
      }
    } finally {
      setSubmitting(false);
      onSubmittingChange(false);
    }
  }

  const visibleInputs = workflow.normalstundenSelection
    ? [normalstundenInput(normalstundenSource)]
    : workflow.inputs;

  return (
    <div className="submission-layout">
      <form className="submission-form" onSubmit={(event) => void submit(event)}>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {module.workflowIds.length > 1 ? (
          <fieldset className="mode-selector">
            <legend>Analysis mode</legend>
            <div className="mode-options">
              {module.workflowIds.map((workflowId) => {
                const mode = workflowById(workflowId)!;
                return (
                  <button className={workflowId === workflow.id ? "mode-button selected" : "mode-button"} key={workflowId} type="button" disabled={submitting} onClick={() => onSelectWorkflow(workflowId)}>
                    <strong>{mode.modeLabel}</strong>
                    <span>{mode.detail}</span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        ) : null}
        {workflow.normalstundenSelection ? (
          <fieldset className="source-selector">
            <legend>Invoice input type</legend>
            <label className={normalstundenSource === "pdf" ? "choice-card selected" : "choice-card"}>
              <input
                type="radio"
                name="normalstunden-source"
                checked={normalstundenSource === "pdf"}
                onChange={() => setNormalstundenSource("pdf")}
              />
              <span>Invoice PDFs</span>
              <small>Select one or more PDF invoices.</small>
            </label>
            <label className={normalstundenSource === "zip" ? "choice-card selected" : "choice-card"}>
              <input
                type="radio"
                name="normalstunden-source"
                checked={normalstundenSource === "zip"}
                onChange={() => setNormalstundenSource("zip")}
              />
              <span>ZIP archive</span>
              <small>Select one archive containing invoice PDFs.</small>
            </label>
          </fieldset>
        ) : null}
        <div className="file-input-grid">
          {visibleInputs.map((input) => (
            <FileInput
              definition={input}
              files={filesByInput[input.id] ?? []}
              key={input.id}
              onChange={(files) => changeFiles(input.id, files)}
            />
          ))}
        </div>
        {workflow.options.length > 0 ? (
          <fieldset className="options-panel">
            <legend>Analysis settings</legend>
            <div className="options-grid">
              {workflow.options.map((option) => (
                <OptionInput
                  definition={option}
                  key={option.id}
                  value={options[option.id]}
                  onChange={(value) => updateOption(option.id, value)}
                />
              ))}
            </div>
          </fieldset>
        ) : null}
        <fieldset className="custom-analysis-panel">
          <legend>Customize analysis</legend>
          <p>Choose which standard results to include, then add any fields or instructions specific to this review. Fixed source-grounding and security rules remain active.</p>
          <label className="field-label custom-instructions-field">
            <span>Instruction prompt <small>Optional</small></span>
            <textarea
              value={customInstructions}
              maxLength={MAX_CUSTOM_INSTRUCTION_LENGTH}
              rows={5}
              placeholder="Example: Focus on price-adjustment mechanisms, renewal deadlines, and obligations that require procurement action."
              onChange={(event) => setCustomInstructions(event.target.value)}
            />
            <small>{customInstructions.length.toLocaleString()} / {MAX_CUSTOM_INSTRUCTION_LENGTH.toLocaleString()} characters</small>
          </label>
          <div className="custom-fields-heading standard-fields-heading">
            <div>
              <strong>Standard output fields</strong>
              <small>Included by default. Remove any result that is not needed for this analysis.</small>
            </div>
            {standardOutputFields.length < workflow.standardOutputFields.length ? (
              <button
                className="secondary-button compact-button"
                type="button"
                disabled={submitting}
                onClick={() => setStandardOutputFields(workflow.standardOutputFields.map((field) => field.id))}
              >
                Restore all
              </button>
            ) : null}
          </div>
          {standardOutputFields.length > 0 ? (
            <div className="standard-field-list">
              {workflow.standardOutputFields.filter((field) => standardOutputFields.includes(field.id)).map((field, index) => (
                <div className="standard-field-row" key={field.id}>
                  <span className="custom-field-index" aria-hidden="true">{index + 1}</span>
                  <span className="standard-field-copy">
                    <strong>{field.label}</strong>
                    <small>{field.detail}</small>
                  </span>
                  <span className="standard-field-type">Standard</span>
                  <button
                    className="remove-custom-field"
                    type="button"
                    aria-label={`Remove standard field ${field.label}`}
                    disabled={submitting}
                    onClick={() => setStandardOutputFields((current) => current.filter((id) => id !== field.id))}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="custom-fields-empty">No standard business fields selected. Status, source provenance, and validation messages will still be shown.</p>
          )}
          <div className="custom-fields-heading extra-fields-heading">
            <div>
              <strong>Additional output fields</strong>
              <small>Add up to {MAX_CUSTOM_OUTPUT_FIELDS} named fields. These appear in a separate Customized output section.</small>
            </div>
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={submitting || customOutputFields.length >= MAX_CUSTOM_OUTPUT_FIELDS}
              onClick={() => setCustomOutputFields((current) => [...current, newCustomOutputField()])}
            >
              Add field
            </button>
          </div>
          {customOutputFields.length > 0 ? (
            <div className="custom-field-list">
              {customOutputFields.map((field, index) => (
                <div className="custom-field-row" key={field.id}>
                  <span className="custom-field-index" aria-hidden="true">{index + 1}</span>
                  <label className="field-label">
                    <span>Field name</span>
                    <input
                      type="text"
                      value={field.name}
                      maxLength={80}
                      placeholder="Termination notice period"
                      onChange={(event) => updateCustomField(field.id, { name: event.target.value })}
                    />
                  </label>
                  <label className="field-label">
                    <span>Output type</span>
                    <select value={field.type} onChange={(event) => updateCustomField(field.id, { type: event.target.value as CustomOutputType })}>
                      <option value="text">Text</option>
                      <option value="number">Number</option>
                      <option value="yes_no">Yes / No</option>
                      <option value="list">List</option>
                    </select>
                  </label>
                  <label className="field-label custom-field-instruction">
                    <span>Field instructions <small>Optional</small></span>
                    <input
                      type="text"
                      value={field.instruction}
                      maxLength={500}
                      placeholder="What should be extracted and how should it be interpreted?"
                      onChange={(event) => updateCustomField(field.id, { instruction: event.target.value })}
                    />
                  </label>
                  <button
                    className="remove-custom-field"
                    type="button"
                    aria-label={`Remove custom field ${index + 1}`}
                    disabled={submitting}
                    onClick={() => setCustomOutputFields((current) => current.filter((item) => item.id !== field.id))}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="custom-fields-empty">No additional fields requested.</p>
          )}
        </fieldset>
        <fieldset className="retention-panel">
          <legend>Retention</legend>
          <p>Source documents are retained with the analysis so evidence references can be reviewed later.</p>
          <div className="retention-options">
            <button
              className={retention === "temporary" ? "choice-card selected" : "choice-card"}
              type="button"
              aria-pressed={retention === "temporary"}
              disabled={submitting}
              onClick={() => setRetention("temporary")}
            >
              <span>Temporary</span>
              <small>Delete the analysis, exports, and source documents after 60 days.</small>
            </button>
            <button
              className={retention === "permanent" ? "choice-card selected" : "choice-card"}
              type="button"
              aria-pressed={retention === "permanent"}
              disabled={submitting}
              onClick={() => setRetention("permanent")}
            >
              <span>Permanent</span>
              <small>Keep the analysis, exports, and source documents until they are deleted manually.</small>
            </button>
          </div>
        </fieldset>
        <div className="form-footer">
          <p>Files are uploaded only after you start the analysis.</p>
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Submitting job..." : `Run ${workflow.modeLabel}`}
          </button>
        </div>
      </form>
    </div>
  );
}

function normalstundenInput(source: NormalstundenSource): FileInputDefinition {
  return source === "pdf"
    ? {
        id: "normalstundenPdfs",
        label: "Invoice PDFs",
        hint: "Choose one or more PDF invoices.",
        accept: ".pdf,application/pdf",
        multiple: true,
        minimum: 1,
      }
    : {
        id: "normalstundenArchive",
        label: "Invoice ZIP archive",
        hint: "Choose one ZIP archive containing invoice PDFs.",
        accept: ".zip,application/zip,application/x-zip-compressed",
        multiple: false,
        minimum: 1,
      };
}

function FileInput({
  definition,
  files,
  onChange,
}: {
  definition: FileInputDefinition;
  files: File[];
  onChange: (files: File[]) => void;
}) {
  function selectFiles(event: ChangeEvent<HTMLInputElement>): void {
    const nextFiles = Array.from(event.target.files ?? []);
    onChange(definition.multiple ? [...files, ...nextFiles] : nextFiles.slice(0, 1));
  }

  function removeFile(index: number): void {
    onChange(files.filter((_, currentIndex) => currentIndex !== index));
  }

  return (
    <fieldset className="file-field">
      <legend>{definition.label}</legend>
      <p>{definition.hint}</p>
      <label className="file-picker">
        <input
          key={files.map((file) => `${file.name}-${file.lastModified}`).join("|")}
          type="file"
          accept={definition.accept}
          multiple={definition.multiple}
          onChange={selectFiles}
        />
        <span>Select {definition.multiple ? "files" : "file"}</span>
      </label>
      {files.length > 0 ? (
        <ul className="file-list">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.lastModified}-${index}`}>
              <span><strong>{file.name}</strong><small>{formatFileSize(file.size)}</small></span>
              <button type="button" onClick={() => removeFile(index)} aria-label={`Remove ${file.name}`}>Remove</button>
            </li>
          ))}
        </ul>
      ) : null}
    </fieldset>
  );
}

function OptionInput({
  definition,
  value,
  onChange,
}: {
  definition: OptionDefinition;
  value: OptionValue | undefined;
  onChange: (value: OptionValue) => void;
}) {
  if (definition.type === "checkbox") {
    return (
      <label className="checkbox-option">
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        <span>{definition.label}</span>
        {definition.help ? <small>{definition.help}</small> : null}
      </label>
    );
  }

  if (definition.type === "select") {
    return (
      <label className="field-label">
        <span>{definition.label}</span>
        <select value={String(value ?? "")} onChange={(event) => onChange(event.target.value)}>
          {definition.choices?.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </select>
      </label>
    );
  }

  if (definition.type === "range") {
    const numericValue = typeof value === "number" ? value : Number(value ?? definition.defaultValue);
    return (
      <label className="field-label">
        <span>{definition.label}: <strong>{numericValue.toLocaleString()}</strong></span>
        <input
          type="range"
          value={numericValue}
          min={definition.min}
          max={definition.max}
          step={definition.step}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {definition.help ? <small>{definition.help}</small> : null}
      </label>
    );
  }

  return (
    <label className="field-label">
      <span>{definition.label}</span>
      <input
        type="number"
        value={typeof value === "number" ? value : Number(value ?? definition.defaultValue)}
        min={definition.min}
        max={definition.max}
        step={definition.step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      {definition.help ? <small>{definition.help}</small> : null}
    </label>
  );
}

function HistoryPage({
  jobs,
  loading,
  selectedJobId,
  instance,
  account,
  onSelectJob,
  onDeleted,
}: {
  jobs: AnalyzerJob[];
  loading: boolean;
  selectedJobId?: string;
  instance: IPublicClientApplication;
  account: AccountInfo;
  onSelectJob: (id: string | undefined) => void;
  onDeleted: () => void;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const matchingJobs = deferredQuery
    ? jobs.filter((job) => `${job.id} ${job.workflow} ${workflowTitle(job.workflow)} ${job.status} ${job.files.join(" ")}`.toLowerCase().includes(deferredQuery))
    : jobs;
  const selectedSummary = jobs.find((job) => job.id === selectedJobId);

  if (selectedJobId && selectedSummary) {
    return (
      <div className="result-workspace">
        <div className="result-workspace-navigation">
          <button className="secondary-button compact" type="button" onClick={() => onSelectJob(undefined)}>
            <span aria-hidden="true">&larr;</span> All analyses
          </button>
          <span>Analysis register / {workflowTitle(selectedSummary.workflow)}</span>
        </div>
        <JobDetails jobId={selectedJobId} summary={selectedSummary} instance={instance} account={account} onDeleted={onDeleted} />
      </div>
    );
  }

  return (
    <section className="history-index">
      <div className="history-index-heading">
        <div>
          <p className="eyebrow">Analysis register</p>
          <h2>Completed and active analyses</h2>
          <p>Open an analysis to review extracted business data, findings, evidence, and exports.</p>
        </div>
        <span>{matchingJobs.length} {matchingJobs.length === 1 ? "analysis" : "analyses"}</span>
      </div>
      <div className="history-list-panel">
        <label className="search-field">
          <span>Search jobs</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Workflow, file, or analysis ID" />
        </label>
        {loading ? <p className="empty-state">Loading job history...</p> : null}
        {!loading && matchingJobs.length === 0 ? <p className="empty-state">No jobs match this search.</p> : null}
        <div className="history-list">
          {matchingJobs.map((job) => (
            <button
              className={job.id === selectedJobId ? "history-job selected" : "history-job"}
              key={job.id}
              type="button"
              onClick={() => onSelectJob(job.id)}
            >
              <span className="history-job-main">
                <strong>{workflowTitle(job.workflow)}</strong>
                <small>{job.files[0] ?? "No source filename"}{job.files.length > 1 ? ` + ${job.files.length - 1} more` : ""}</small>
                <small>{formatDate(job.createdAt)}</small>
              </span>
              <StatusBadge status={job.status} />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge ${statusClass(status)}`}>{statusLabel(status)}</span>;
}

function JobDetails({
  jobId,
  summary,
  instance,
  account,
  onDeleted,
}: {
  jobId: string;
  summary: AnalyzerJob;
  instance: IPublicClientApplication;
  account: AccountInfo;
  onDeleted: () => void;
}) {
  const [job, setJob] = useState<AnalyzerJob>(summary);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [downloadError, setDownloadError] = useState<string>();
  const [deleting, setDeleting] = useState(false);
  const [selectedReference, setSelectedReference] = useState<ResultReference>();
  const accountId = account.homeAccountId;
  const accountRef = useRef(account);
  accountRef.current = account;

  useEffect(() => {
    setJob((current) => current.id === summary.id
      ? { ...current, status: summary.status, progress: summary.progress ?? current.progress, updatedAt: summary.updatedAt ?? current.updatedAt }
      : summary);
  }, [summary.id, summary.progress, summary.status, summary.updatedAt]);

  useEffect(() => {
    const activeAccount = accountRef.current;
    let cancelled = false;
    let inFlight = false;
    let timer: number | undefined;
    setJob(summary);

    function scheduleNextPoll(): void {
      if (!cancelled) {
        timer = window.setTimeout(() => void loadJob(false), POLLING_INTERVAL_MS);
      }
    }

    async function loadJob(showLoading: boolean): Promise<void> {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      let shouldPoll = false;
      if (showLoading) {
        setLoading(true);
      }
      try {
        const loadedJob = await new AnalyzerApi(instance, activeAccount).getJob(jobId);
        if (!cancelled) {
          setJob(loadedJob);
          setError(undefined);
          shouldPoll = !isTerminalJob(loadedJob.status);
        }
      } catch (detailError) {
        if (!cancelled && !(detailError instanceof AuthRedirectStartedError)) {
          setError(errorMessage(detailError));
        }
      } finally {
        inFlight = false;
        if (!cancelled && showLoading) {
          setLoading(false);
        }
        if (shouldPoll) {
          scheduleNextPoll();
        }
      }
    }

    void loadJob(true);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [accountId, instance, jobId]);

  useEffect(() => {
    setSelectedReference(undefined);
  }, [jobId]);

  async function download(artifactId: string, name: string): Promise<void> {
    setDownloadError(undefined);
    try {
      const downloaded = await new AnalyzerApi(instance, account).downloadArtifact(job.id, artifactId, name);
      const objectUrl = URL.createObjectURL(downloaded.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = downloaded.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (downloadRequestError) {
      if (!(downloadRequestError instanceof AuthRedirectStartedError)) {
        setDownloadError(errorMessage(downloadRequestError));
      }
    }
  }

  async function downloadSource(sourceId: string, name: string): Promise<void> {
    setDownloadError(undefined);
    try {
      const downloaded = await new AnalyzerApi(instance, account).downloadSource(job.id, sourceId, name);
      const objectUrl = URL.createObjectURL(downloaded.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = downloaded.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (downloadRequestError) {
      if (!(downloadRequestError instanceof AuthRedirectStartedError)) {
        setDownloadError(errorMessage(downloadRequestError));
      }
    }
  }

  async function deleteJob(): Promise<void> {
    if (!window.confirm("Delete this job and its retained files? This cannot be undone.")) {
      return;
    }
    setDeleting(true);
    try {
      await new AnalyzerApi(instance, account).deleteJob(job.id);
      onDeleted();
    } catch (deleteError) {
      if (!(deleteError instanceof AuthRedirectStartedError)) {
        setError(errorMessage(deleteError));
      }
    } finally {
      setDeleting(false);
    }
  }

  const jobWorkflow = workflowById(job.workflow);
  const selectedStandardFields = job.customization?.standardOutputFields?.flatMap((id) => {
    const field = jobWorkflow?.standardOutputFields.find((candidate) => candidate.id === id);
    return field ? [field] : [];
  });

  return (
    <div className="detail-stack result-workspace-detail">
      <div className="detail-header result-detail-header">
        <div>
          <p className="eyebrow">{workflowTitle(job.workflow)}</p>
          <h2>{job.files[0] ?? "Analysis result"}</h2>
          <p>Created {formatDate(job.createdAt)}{job.files.length > 1 ? ` / ${job.files.length} source files` : ""}</p>
        </div>
        <StatusBadge status={job.status} />
      </div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {job.message && !isTerminalJob(job.status) ? <p className="job-message">{job.message}</p> : null}
      {job.error ? <p className="form-error" role="alert">{job.error}</p> : null}
      <div className="result-workspace-grid">
        <div className="result-primary-column">
          <section className="detail-section results-showcase">
            <div className="result-section-heading">
              <div>
                <p className="eyebrow">Consultant review</p>
                <h3>Analysis findings</h3>
              </div>
            </div>
            {loading ? <p className="empty-state">Refreshing job status...</p> : null}
            {!loading && job.result === undefined ? <p className="empty-state">Results will appear here when this job completes.</p> : null}
            {job.result !== undefined ? <ResultView value={job.result} sources={job.sources} onOpenReference={setSelectedReference} /> : null}
          </section>
          {job.workflow === "large_scanner" && job.status === "completed" ? <QuestionPanel jobId={job.id} instance={instance} account={account} /> : null}
        </div>
        <aside className="result-context-panel" aria-label="Analysis details and exports">
          {typeof job.progress === "number" && !isTerminalJob(job.status) ? (
            <div className="progress-section">
              <div><span>Progress</span><strong>{Math.max(0, Math.min(100, Math.round(job.progress)))}%</strong></div>
              <progress value={Math.max(0, Math.min(100, job.progress))} max="100" />
            </div>
          ) : null}
          {job.progressLog.length > 0 ? (
            <details className="result-context-section progress-log">
              <summary>Analysis activity ({job.progressLog.length})</summary>
              <ol aria-live="polite">
                {[...job.progressLog].reverse().map((entry) => (
                  <li key={`${entry.at}-${entry.progress}-${entry.message}`}>
                    <time dateTime={entry.at}>{formatDate(entry.at)}</time>
                    <span>{entry.progress}%</span>
                    <p>{entry.message}</p>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
          <section className="result-context-section">
            <p className="eyebrow">Run details</p>
            <dl className="job-facts">
              <div>
                <dt>Retention</dt>
                <dd>{!job.retention && loading ? "Loading..." : job.retention === "permanent" ? "Kept until deleted" : job.expiresAt ? `Scheduled deletion ${formatDate(job.expiresAt)}` : "Deleted 60 days after completion"}</dd>
              </div>
              <div><dt>Source files</dt><dd>{job.sources.length || job.files.length || "Not reported"}</dd></div>
              <div><dt>Exports</dt><dd>{job.artifacts.length}</dd></div>
            </dl>
          </section>
          {job.coverage.length > 0 ? (
            <section className="result-context-section analysis-coverage">
              <h3>Coverage and limitations</h3>
              <ul>{job.coverage.map((note) => <li key={note}>{note}</li>)}</ul>
            </section>
          ) : null}
          {job.customization ? (
            <details className="result-context-section customization-details">
              <summary>Output configuration</summary>
              {job.customization.standardOutputFields ? (
                <div>
                  <strong>Included standard fields</strong>
                  {selectedStandardFields && selectedStandardFields.length > 0 ? (
                    <ul>
                      {selectedStandardFields.map((field) => (
                        <li key={field.id}><span>{field.label}</span></li>
                      ))}
                    </ul>
                  ) : (
                    <p>No optional standard business fields were included.</p>
                  )}
                </div>
              ) : null}
              {job.customization.instructions ? (
                <div className="customization-instructions">
                  <strong>Instruction prompt</strong>
                  <p>{job.customization.instructions}</p>
                </div>
              ) : null}
              {job.customization.outputFields.length > 0 ? (
                <div>
                  <strong>Requested output fields</strong>
                  <ul>
                    {job.customization.outputFields.map((field) => (
                      <li key={`${field.name}-${field.type}`}>
                        <span>{field.name}</span>
                        <small>{field.type.replace("yes_no", "yes / no")}{field.instruction ? ` / ${field.instruction}` : ""}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </details>
          ) : null}
          {job.sources.length > 0 ? (
            <section className="result-context-section">
              <h3>Source documents</h3>
              <ul className="source-document-list">
                {job.sources.map((source) => (
                  <li key={source.id}>
                    <span>
                      <strong>{source.name}</strong>
                      <small>{sourceRoleLabel(source.role)} / {fileTypeLabel(source.contentType, source.name)}{source.size ? ` / ${formatFileSize(source.size)}` : ""}</small>
                    </span>
                    {source.previewable ? (
                      <button
                        className="secondary-button compact"
                        type="button"
                        onClick={() => setSelectedReference({ sourceId: source.id, sourceName: source.name })}
                      >
                        Open
                      </button>
                    ) : (
                      <button className="secondary-button compact" type="button" onClick={() => void downloadSource(source.id, source.name)}>Download</button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ) : job.files.length > 0 ? (
            <section className="result-context-section">
              <h3>Source documents</h3>
              <p className="empty-state">
                {job.status === "completed"
                  ? "Source previews are unavailable for analyses completed before evidence retention was enabled."
                  : job.status === "failed"
                    ? "Source documents are retained only when an analysis completes successfully."
                    : "Source documents will become available when the analysis completes."}
              </p>
              <ul className="simple-list">{job.files.map((file) => <li key={file}>{file}</li>)}</ul>
            </section>
          ) : null}
          <section className="result-context-section">
            <h3>Exports</h3>
            {downloadError ? <p className="form-error" role="alert">{downloadError}</p> : null}
            {job.artifacts.length === 0 ? <p className="empty-state">No generated files are available yet.</p> : null}
            <ul className="artifact-list">
              {job.artifacts.map((artifact) => (
                <li key={artifact.id}>
                  <span><strong>{artifact.name}</strong><small>{fileTypeLabel(artifact.contentType, artifact.name)}{artifact.size ? ` / ${formatFileSize(artifact.size)}` : ""}</small></span>
                  <button className="secondary-button compact" type="button" onClick={() => void download(artifact.id, artifact.name)}>Download</button>
                </li>
              ))}
            </ul>
          </section>
          <details className="technical-details result-context-section">
            <summary>Technical details</summary>
            <dl className="job-facts">
              <div><dt>Analysis ID</dt><dd className="technical-id">{job.id}</dd></div>
              <div><dt>Started</dt><dd>{formatDate(job.startedAt)}</dd></div>
              <div><dt>Completed</dt><dd>{formatDate(job.completedAt)}</dd></div>
            </dl>
          </details>
          <div className="detail-actions">
            <button className="danger-button" type="button" onClick={() => void deleteJob()} disabled={deleting}>
              {deleting ? "Deleting..." : "Delete analysis"}
            </button>
          </div>
        </aside>
      </div>
      {selectedReference ? (
        <Suspense fallback={null}>
          <SourcePreviewDrawer
            key={`${selectedReference.sourceId}-${selectedReference.page ?? "search"}-${selectedReference.quote ?? ""}`}
            reference={selectedReference}
            loadSource={(signal) => new AnalyzerApi(instance, account)
              .downloadSource(job.id, selectedReference.sourceId, selectedReference.sourceName, signal)
              .then((downloaded) => downloaded.blob)}
            onClose={() => setSelectedReference(undefined)}
          />
        </Suspense>
      ) : null}
    </div>
  );
}

function QuestionPanel({
  jobId,
  instance,
  account,
}: {
  jobId: string;
  instance: IPublicClientApplication;
  account: AccountInfo;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string>();
  const [error, setError] = useState<string>();
  const [asking, setAsking] = useState(false);

  async function ask(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      return;
    }
    setAsking(true);
    setError(undefined);
    try {
      const response = await new AnalyzerApi(instance, account).askQuestion(jobId, trimmedQuestion);
      setAnswer(answerText(response));
      setQuestion("");
    } catch (questionError) {
      if (!(questionError instanceof AuthRedirectStartedError)) {
        setError(errorMessage(questionError));
      }
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="detail-section question-panel">
      <h3>Ask about this contract</h3>
      <p>Answers are generated from this large scan's stored evidence.</p>
      <form onSubmit={(event) => void ask(event)}>
        <label className="field-label">
          <span>Question</span>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What are the termination rights?" rows={3} />
        </label>
        <button className="primary-button compact" type="submit" disabled={asking || !question.trim()}>
          {asking ? "Answering..." : "Ask question"}
        </button>
      </form>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {answer ? <pre className="result-value question-answer">{answer}</pre> : null}
    </section>
  );
}

export default App;
