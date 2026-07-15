export type Retention = "temporary" | "permanent";

export type OptionValue = string | number | boolean;

export interface JobArtifact {
  id: string;
  name: string;
  contentType?: string;
  size?: number;
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
  files: string[];
  artifacts: JobArtifact[];
  result?: unknown;
  raw: Record<string, unknown>;
}

export interface SubmittedFile {
  role: string;
  file: File;
}

export interface SubmitJobInput {
  workflow: string;
  retention: Retention;
  options: Record<string, OptionValue>;
  files: SubmittedFile[];
}

export interface DownloadedArtifact {
  blob: Blob;
  filename: string;
}
