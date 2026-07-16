import type { WorkflowId } from "./workflows";

export type Retention = "temporary" | "permanent";

export type OptionValue = string | number | boolean;

export interface JobArtifact {
  id: string;
  name: string;
  contentType?: string;
  size?: number;
}

export interface JobSource {
  id: string;
  name: string;
  role: string;
  contentType?: string;
  size?: number;
  previewable: boolean;
}

export interface ResultReference {
  sourceId: string;
  sourceName: string;
  quote?: string;
  page?: number;
  pageEnd?: number;
  section?: string;
}

export interface AnalyzerJob {
  id: string;
  workflow: string;
  status: string;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
  progress?: number;
  message?: string;
  error?: string;
  retention?: Retention;
  retentionDays?: number;
  expiresAt?: string;
  coverage: string[];
  files: string[];
  artifacts: JobArtifact[];
  sources: JobSource[];
  result?: unknown;
  raw: Record<string, unknown>;
}

export interface SubmittedFile {
  role: string;
  file: File;
}

export interface SubmitJobInput {
  workflow: WorkflowId;
  retention: Retention;
  options: Record<string, OptionValue>;
  files: SubmittedFile[];
}

export interface DownloadedArtifact {
  blob: Blob;
  filename: string;
}
