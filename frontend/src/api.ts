import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import { analyzerApiScopes } from "./config";
import { normalizeJob, normalizeJobs, normalizeSubmittedJob } from "./jobs";
import type { AnalyzerJob, DownloadedArtifact, SubmitJobInput } from "./types";

const API_ROOT = "/api";

export class AnalyzerApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "AnalyzerApiError";
  }
}

export class AuthRedirectStartedError extends Error {
  constructor() {
    super("Authentication redirect started.");
    this.name = "AuthRedirectStartedError";
  }
}

function isInteractionRequired(error: unknown): boolean {
  if (error instanceof InteractionRequiredAuthError) {
    return true;
  }
  return (
    typeof error === "object" &&
    error !== null &&
    "errorCode" in error &&
    typeof error.errorCode === "string" &&
    error.errorCode.toLowerCase().includes("interaction_required")
  );
}

function readContentDispositionFilename(value: string | null): string | undefined {
  if (!value) {
    return undefined;
  }
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    return decodeURIComponent(encoded);
  }
  return value.match(/filename="?([^";]+)"?/i)?.[1];
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  const body = await response.text();
  if (!body) {
    return undefined;
  }
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return body;
  }
}

function messageFromBody(body: unknown, fallback: string): string {
  if (typeof body === "string" && body.trim()) {
    return body;
  }
  if (typeof body === "object" && body !== null) {
    const record = body as Record<string, unknown>;
    if (typeof record.message === "string") {
      return record.message;
    }
    if (typeof record.error === "string") {
      return record.error;
    }
  }
  return fallback;
}

export function errorMessage(error: unknown): string {
  if (error instanceof AnalyzerApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "An unexpected error occurred.";
}

export class AnalyzerApi {
  constructor(
    private readonly msal: IPublicClientApplication,
    private readonly account: AccountInfo,
  ) {}

  private async acquireAccessToken(forceRefresh = false): Promise<string> {
    try {
      const response = await this.msal.acquireTokenSilent({
        account: this.account,
        scopes: analyzerApiScopes,
        forceRefresh,
      });
      return response.accessToken;
    } catch (error) {
      if (isInteractionRequired(error)) {
        await this.msal.loginRedirect({
          account: this.account,
          scopes: analyzerApiScopes,
        });
        throw new AuthRedirectStartedError();
      }
      throw new AnalyzerApiError("Unable to acquire an analyzer API access token.", undefined, error);
    }
  }

  private async fetchWithToken(path: string, init: RequestInit, retry = true): Promise<Response> {
    const accessToken = await this.acquireAccessToken(!retry);
    let response: Response;
    try {
      response = await fetch(`${API_ROOT}${path}`, {
        ...init,
        headers: {
          ...init.headers,
          Authorization: `Bearer ${accessToken}`,
        },
      });
    } catch (error) {
      throw new AnalyzerApiError("The analyzer API could not be reached. Check your connection and try again.", undefined, error);
    }

    if (response.status === 401 && retry) {
      return this.fetchWithToken(path, init, false);
    }

    return response;
  }

  private async request(path: string, init: RequestInit = {}): Promise<unknown> {
    const response = await this.fetchWithToken(path, init);
    const body = await readResponseBody(response);
    if (!response.ok) {
      throw new AnalyzerApiError(
        messageFromBody(body, `Analyzer API request failed (${response.status}).`),
        response.status,
        body,
      );
    }
    return body;
  }

  async getJobs(): Promise<AnalyzerJob[]> {
    return normalizeJobs(await this.request("/jobs"));
  }

  async getJob(id: string): Promise<AnalyzerJob> {
    const response = await this.request(`/jobs/${encodeURIComponent(id)}`);
    const record = typeof response === "object" && response !== null ? response as Record<string, unknown> : undefined;
    const data = typeof record?.data === "object" && record.data !== null
      ? record.data as Record<string, unknown>
      : undefined;
    const job = normalizeJob(record?.job ?? data?.job ?? record?.data ?? response);
    if (!job) {
      throw new AnalyzerApiError("The analyzer API returned an invalid job response.");
    }
    return job;
  }

  async submitJob(input: SubmitJobInput): Promise<AnalyzerJob | undefined> {
    const formData = new FormData();
    const retentionDays = input.retention === "temporary" ? 60 : undefined;
    const fileRoles = input.files.map(({ role, file }) => ({ role, name: file.name }));

    formData.append("workflow", input.workflow);
    formData.append("retention", input.retention);
    if (retentionDays) {
      formData.append("retentionDays", String(retentionDays));
      formData.append("retention_days", String(retentionDays));
    }
    formData.append("options", JSON.stringify(input.options));
    formData.append("fileRoles", JSON.stringify(fileRoles));
    formData.append(
      "metadata",
      JSON.stringify({
        retention: input.retention,
        retentionDays,
        options: input.options,
        fileRoles,
      }),
    );
    for (const { file } of input.files) {
      formData.append("files", file, file.name);
    }

    return normalizeSubmittedJob(await this.request("/jobs", { method: "POST", body: formData }));
  }

  async deleteJob(id: string): Promise<void> {
    await this.request(`/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  async askQuestion(id: string, question: string): Promise<unknown> {
    return this.request(`/jobs/${encodeURIComponent(id)}/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  }

  async downloadArtifact(jobId: string, artifactId: string, fallbackFilename: string): Promise<DownloadedArtifact> {
    const response = await this.fetchWithToken(
      `/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`,
      { method: "GET" },
    );
    if (!response.ok) {
      const body = await readResponseBody(response);
      throw new AnalyzerApiError(
        messageFromBody(body, `Artifact download failed (${response.status}).`),
        response.status,
        body,
      );
    }
    return {
      blob: await response.blob(),
      filename: readContentDispositionFilename(response.headers.get("content-disposition")) ?? fallbackFilename,
    };
  }
}
