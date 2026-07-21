import type { AnalyzerJob, CustomOutputType, JobArtifact, JobCustomization, JobSource } from "./types";

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return undefined;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (typeof item === "string") {
      return [item];
    }
    if (isRecord(item)) {
      const name = asString(item.name ?? item.fileName ?? item.filename);
      return name ? [name] : [];
    }
    return [];
  });
}

function normalizeArtifact(value: unknown): JobArtifact | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  const id = asString(value.id ?? value.artifactId ?? value._id);
  if (!id) {
    return undefined;
  }

  return {
    id,
    name: asString(value.name ?? value.fileName ?? value.filename) ?? `Artifact ${id}`,
    contentType: asString(value.contentType ?? value.mimeType ?? value.type),
    size: asNumber(value.size ?? value.byteSize),
  };
}

function normalizeArtifacts(value: unknown): JobArtifact[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((artifact) => {
    const normalized = normalizeArtifact(artifact);
    return normalized ? [normalized] : [];
  });
}

function normalizeSource(value: unknown): JobSource | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  const id = asString(value.id ?? value.sourceId ?? value._id);
  const name = asString(value.name ?? value.fileName ?? value.filename);
  if (!id || !name) {
    return undefined;
  }

  return {
    id,
    name,
    role: asString(value.role) ?? "source",
    contentType: asString(value.contentType ?? value.mimeType ?? value.type),
    size: asNumber(value.size ?? value.byteSize),
    previewable: value.previewable === true,
  };
}

function normalizeSources(value: unknown): JobSource[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((source) => {
    const normalized = normalizeSource(source);
    return normalized ? [normalized] : [];
  });
}

function normalizeCustomization(value: unknown): JobCustomization | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const instructions = typeof value.instructions === "string" ? value.instructions : "";
  const standardOutputFieldsValue = value.standardOutputFields;
  const hasStandardOutputFields = Array.isArray(standardOutputFieldsValue);
  const standardOutputFields = hasStandardOutputFields
    ? standardOutputFieldsValue.filter((item): item is string => typeof item === "string")
    : undefined;
  const outputFields = Array.isArray(value.outputFields)
    ? value.outputFields.flatMap((item) => {
        if (!isRecord(item)) {
          return [];
        }
        const name = asString(item.name);
        const outputType = asString(item.type);
        if (!name || !["text", "number", "yes_no", "list"].includes(outputType ?? "")) {
          return [];
        }
        return [{
          name,
          instruction: typeof item.instruction === "string" ? item.instruction : "",
          type: outputType as CustomOutputType,
        }];
      })
    : [];
  return instructions || outputFields.length > 0 || hasStandardOutputFields
    ? { instructions, standardOutputFields, outputFields }
    : undefined;
}

export function normalizeJob(value: unknown): AnalyzerJob | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  const id = asString(value.id ?? value.jobId ?? value._id);
  if (!id) {
    return undefined;
  }

  const nestedProgress = isRecord(value.progress) ? value.progress : undefined;
  const nestedError = isRecord(value.error) ? value.error : undefined;
  const result = value.result ?? value.results ?? value.output ?? value.analysis;
  const retentionValue = asString(value.retention)?.toLowerCase();
  const retention = retentionValue === "temporary" || retentionValue === "permanent"
    ? retentionValue
    : undefined;

  return {
    id,
    workflow: asString(value.workflow ?? value.workflowType ?? value.type) ?? "unknown",
    status: (asString(value.status ?? value.state) ?? "queued").toLowerCase(),
    createdAt: asString(value.createdAt ?? value.created_at ?? value.submittedAt),
    updatedAt: asString(value.updatedAt ?? value.updated_at),
    startedAt: asString(value.startedAt ?? value.started_at),
    completedAt: asString(value.completedAt ?? value.completed_at ?? value.finishedAt),
    progress: asNumber(nestedProgress?.percent ?? nestedProgress?.value ?? value.progress),
    message: asString(value.message ?? value.statusMessage ?? nestedProgress?.message),
    error: asString(value.errorMessage ?? nestedError?.message ?? value.error),
    retention,
    retentionDays: asNumber(value.retentionDays ?? value.retention_days),
    expiresAt: asString(value.expiresAt ?? value.expires_at),
    coverage: asStringList(value.coverage),
    customization: normalizeCustomization(value.customization),
    files: asStringList(value.files ?? value.documents ?? value.inputFiles),
    artifacts: normalizeArtifacts(value.artifacts ?? value.outputs ?? value.downloads),
    sources: normalizeSources(value.sources ?? value.sourceDocuments),
    result,
    raw: value,
  };
}

export function normalizeJobs(value: unknown): AnalyzerJob[] {
  const record = isRecord(value) ? value : undefined;
  const data = isRecord(record?.data) ? record.data : record;
  const candidates = Array.isArray(value)
    ? value
    : Array.isArray(data?.jobs)
      ? data.jobs
      : Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data?.results)
          ? data.results
          : [];

  return candidates.flatMap((candidate) => {
    const job = normalizeJob(candidate);
    return job ? [job] : [];
  });
}

export function normalizeSubmittedJob(value: unknown): AnalyzerJob | undefined {
  const record = isRecord(value) ? value : undefined;
  const data = isRecord(record?.data) ? record.data : record;
  return normalizeJob(data?.job ?? data);
}

export function isTerminalJob(status: string): boolean {
  return ["completed", "failed", "cancelled", "canceled", "deleted"].includes(status.toLowerCase());
}

export function hasActiveJobs(jobs: AnalyzerJob[]): boolean {
  return jobs.some((job) => !isTerminalJob(job.status));
}
