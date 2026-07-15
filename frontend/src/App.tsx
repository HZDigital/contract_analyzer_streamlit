import { InteractionStatus, type AccountInfo, type IPublicClientApplication } from "@azure/msal-browser";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import {
  startTransition,
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
import { hasActiveJobs, isTerminalJob } from "./jobs";
import { ResultView } from "./result-view";
import type { AnalyzerJob, OptionValue, Retention, SubmittedFile } from "./types";
import { workflows, workflowById, workflowTitle, type FileInputDefinition, type OptionDefinition, type WorkflowDefinition, type WorkflowId } from "./workflows";

type View = "dashboard" | "submit" | "history";
type NormalstundenSource = "pdf" | "zip";

const POLLING_INTERVAL_MS = 8_000;

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
  missingSettings,
  initializationError,
}: {
  missingSettings?: string[];
  initializationError?: string;
}) {
  return (
    <main className="setup-page">
      <section className="setup-card" aria-labelledby="setup-title">
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

function SignInScreen() {
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
        <p className="eyebrow">Lizzy</p>
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

function App() {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const activeAccountId = instance.getActiveAccount()?.homeAccountId;
  const account = accounts.find((candidate) => candidate.homeAccountId === activeAccountId) ?? accounts[0];
  const [ssoResolved, setSsoResolved] = useState(false);
  const ssoAttempt = useRef<Promise<AccountInfo | undefined> | undefined>(undefined);
  const [view, setView] = useState<View>("dashboard");
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowId>("product_request");
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const { jobs, loading, error, refresh } = useJobs(instance, account);

  useEffect(() => {
    if (account && !instance.getActiveAccount()) {
      instance.setActiveAccount(account);
    }
  }, [account, instance]);

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

  if (inProgress === InteractionStatus.Startup || inProgress === InteractionStatus.HandleRedirect) {
    return <LoadingScreen />;
  }

  if (!account && !ssoResolved) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated || !account) {
    return <SignInScreen />;
  }

  const activeWorkflow = workflowById(selectedWorkflow) ?? workflows[0];

  function openWorkflow(workflowId: WorkflowId): void {
    setSelectedWorkflow(workflowId);
    setView("submit");
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
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span>
            <strong>Lizzy</strong>
            <small>Contract Analyzer</small>
          </span>
        </div>
        <nav className="primary-nav" aria-label="Main navigation">
          <button className={view === "dashboard" ? "nav-button active" : "nav-button"} type="button" onClick={() => setView("dashboard")}>
            Overview
          </button>
          <button className={view === "history" ? "nav-button active" : "nav-button"} type="button" onClick={() => setView("history")}>
            Job history
          </button>
        </nav>
        <div className="workflow-nav">
          <p>New analysis</p>
          {workflows.map((workflow) => (
            <button
              className={view === "submit" && selectedWorkflow === workflow.id ? "workflow-link active" : "workflow-link"}
              key={workflow.id}
              type="button"
              onClick={() => openWorkflow(workflow.id)}
            >
              <span>{workflow.shortCode}</span>
              {workflow.title}
            </button>
          ))}
        </div>
        <div className="account-panel">
          <span className="account-initial" aria-hidden="true">{(account.name ?? account.username).slice(0, 1).toUpperCase()}</span>
          <span className="account-name" title={account.username}>{account.name ?? account.username}</span>
          <button className="text-button" type="button" onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Secure document workspace</p>
            <h1>{view === "submit" ? activeWorkflow.title : view === "history" ? "Job history" : "Analysis overview"}</h1>
          </div>
          <button className="secondary-button" type="button" onClick={refresh}>Refresh jobs</button>
        </header>
        {error ? <ErrorNotice message={error} onDismiss={refresh} /> : null}
        {view === "dashboard" ? <Dashboard jobs={jobs} loading={loading} onOpenWorkflow={openWorkflow} onOpenJob={openJob} /> : null}
        {view === "submit" ? (
          <WorkflowSubmission
            key={activeWorkflow.id}
            workflow={activeWorkflow}
            instance={instance}
            account={account}
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
  jobs,
  loading,
  onOpenWorkflow,
  onOpenJob,
}: {
  jobs: AnalyzerJob[];
  loading: boolean;
  onOpenWorkflow: (workflow: WorkflowId) => void;
  onOpenJob: (jobId: string) => void;
}) {
  const completed = jobs.filter((job) => job.status === "completed").length;
  const active = jobs.filter((job) => !isTerminalJob(job.status)).length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  const recentJobs = jobs.slice(0, 5);

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Document intelligence</p>
          <h2>Choose a workflow and send the documents that need attention.</h2>
          <p>Every analysis is tracked as a job, with results and generated files available from the history view.</p>
        </div>
        <button className="primary-button" type="button" onClick={() => onOpenWorkflow("detailed_contract")}>Start contract review</button>
      </section>
      <section className="metric-grid" aria-label="Job status summary">
        <article><span>All jobs</span><strong>{loading ? "..." : jobs.length}</strong></article>
        <article><span>In progress</span><strong>{loading ? "..." : active}</strong></article>
        <article><span>Completed</span><strong>{loading ? "..." : completed}</strong></article>
        <article><span>Needs attention</span><strong>{loading ? "..." : failed}</strong></article>
      </section>
      <section>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Workflow library</p>
            <h2>What would you like to analyze?</h2>
          </div>
        </div>
        <div className="workflow-grid">
          {workflows.map((workflow) => (
            <article className="workflow-card" key={workflow.id}>
              <div className="workflow-card-heading">
                <span className="workflow-code">{workflow.shortCode}</span>
                <h3>{workflow.title}</h3>
              </div>
              <p>{workflow.description}</p>
              <button className="card-button" type="button" onClick={() => onOpenWorkflow(workflow.id)}>Open workflow</button>
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
  workflow,
  instance,
  account,
  onSubmitted,
}: {
  workflow: WorkflowDefinition;
  instance: IPublicClientApplication;
  account: AccountInfo;
  onSubmitted: (job: AnalyzerJob | undefined) => void;
}) {
  const [filesByInput, setFilesByInput] = useState<Record<string, File[]>>({});
  const [retention, setRetention] = useState<Retention>("temporary");
  const [options, setOptions] = useState<Record<string, OptionValue>>(() => initialOptions(workflow));
  const [normalstundenSource, setNormalstundenSource] = useState<NormalstundenSource>("pdf");
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  function changeFiles(inputId: string, files: File[]): void {
    setFilesByInput((current) => ({ ...current, [inputId]: files }));
  }

  function updateOption(id: string, value: OptionValue): void {
    setOptions((current) => ({ ...current, [id]: value }));
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

    const files: SubmittedFile[] = inputs.flatMap((input) =>
      (filesByInput[input.id] ?? []).map((file) => ({ role: input.id, file })),
    );
    const submittedOptions = workflow.normalstundenSelection
      ? { ...options, inputMode: normalstundenSource }
      : options;

    setSubmitting(true);
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
    }
  }

  const visibleInputs = workflow.normalstundenSelection
    ? [normalstundenInput(normalstundenSource)]
    : workflow.inputs;

  return (
    <div className="submission-layout">
      <section className="submission-intro">
        <span className="workflow-code large">{workflow.shortCode}</span>
        <div>
          <p className="eyebrow">New analysis</p>
          <h2>{workflow.title}</h2>
          <p>{workflow.detail}</p>
        </div>
      </section>
      <form className="submission-form" onSubmit={(event) => void submit(event)}>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
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
        <fieldset className="retention-panel">
          <legend>Retention</legend>
          <p>Source documents are removed after processing. Choose how long analysis results should remain available.</p>
          <div className="retention-options">
            <label className={retention === "temporary" ? "choice-card selected" : "choice-card"}>
              <input type="radio" name="retention" checked={retention === "temporary"} onChange={() => setRetention("temporary")} />
              <span>Temporary</span>
              <small>Delete analysis results after 60 days.</small>
            </label>
            <label className={retention === "permanent" ? "choice-card selected" : "choice-card"}>
              <input type="radio" name="retention" checked={retention === "permanent"} onChange={() => setRetention("permanent")} />
              <span>Permanent</span>
              <small>Keep analysis results until they are deleted manually.</small>
            </label>
          </div>
        </fieldset>
        <div className="form-footer">
          <p>Files are uploaded only after you start the analysis.</p>
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Submitting job..." : `Run ${workflow.title}`}
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
  onSelectJob: (id: string) => void;
  onDeleted: () => void;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const matchingJobs = deferredQuery
    ? jobs.filter((job) => `${job.id} ${job.workflow} ${job.status} ${job.files.join(" ")}`.toLowerCase().includes(deferredQuery))
    : jobs;
  const selectedSummary = jobs.find((job) => job.id === selectedJobId);

  return (
    <div className="history-layout">
      <section className="history-list-panel">
        <label className="search-field">
          <span>Search jobs</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Workflow, file, or job ID" />
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
                <small>{job.files[0] ?? job.id}</small>
                <small>{formatDate(job.createdAt)}</small>
              </span>
              <StatusBadge status={job.status} />
            </button>
          ))}
        </div>
      </section>
      <section className="job-detail-panel">
        {selectedJobId && selectedSummary ? (
          <JobDetails jobId={selectedJobId} summary={selectedSummary} instance={instance} account={account} onDeleted={onDeleted} />
        ) : (
          <div className="empty-detail">
            <p className="eyebrow">Results and downloads</p>
            <h2>Select a job</h2>
            <p>Choose a job from the history to inspect its status, results, and generated artifacts.</p>
          </div>
        )}
      </section>
    </div>
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

  return (
    <div className="detail-stack">
      <div className="detail-header">
        <div>
          <p className="eyebrow">{workflowTitle(job.workflow)}</p>
          <h2>Job {job.id}</h2>
          <p>{formatDate(job.createdAt)}</p>
        </div>
        <StatusBadge status={job.status} />
      </div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {job.message ? <p className="job-message">{job.message}</p> : null}
      {job.error ? <p className="form-error" role="alert">{job.error}</p> : null}
      {typeof job.progress === "number" ? (
        <div className="progress-section">
          <div><span>Progress</span><strong>{Math.max(0, Math.min(100, Math.round(job.progress)))}%</strong></div>
          <progress value={Math.max(0, Math.min(100, job.progress))} max="100" />
        </div>
      ) : null}
      <div className="detail-meta">
        <span><strong>Started</strong>{formatDate(job.startedAt)}</span>
        <span><strong>Completed</strong>{formatDate(job.completedAt)}</span>
        <span><strong>Files</strong>{job.files.length || "Not reported"}</span>
      </div>
      {job.files.length > 0 ? (
        <section className="detail-section">
          <h3>Source files</h3>
          <ul className="simple-list">{job.files.map((file) => <li key={file}>{file}</li>)}</ul>
        </section>
      ) : null}
      <section className="detail-section">
        <h3>Results</h3>
        {loading ? <p className="empty-state">Refreshing job status...</p> : null}
        {!loading && job.result === undefined ? <p className="empty-state">Results will appear here when this job completes.</p> : null}
        {job.result !== undefined ? <ResultView value={job.result} /> : null}
      </section>
      <section className="detail-section">
        <h3>Downloads</h3>
        {downloadError ? <p className="form-error" role="alert">{downloadError}</p> : null}
        {job.artifacts.length === 0 ? <p className="empty-state">No generated files are available yet.</p> : null}
        <ul className="artifact-list">
          {job.artifacts.map((artifact) => (
            <li key={artifact.id}>
              <span><strong>{artifact.name}</strong><small>{artifact.contentType ?? "Generated file"}{artifact.size ? ` - ${formatFileSize(artifact.size)}` : ""}</small></span>
              <button className="secondary-button compact" type="button" onClick={() => void download(artifact.id, artifact.name)}>Download</button>
            </li>
          ))}
        </ul>
      </section>
      {job.workflow === "large_scanner" ? <QuestionPanel jobId={job.id} instance={instance} account={account} /> : null}
      <div className="detail-actions">
        <button className="danger-button" type="button" onClick={() => void deleteJob()} disabled={deleting}>
          {deleting ? "Deleting..." : "Delete job"}
        </button>
      </div>
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
