import { describe, expect, it } from "vitest";
import { hasActiveJobs, isTerminalJob, normalizeJob, normalizeJobs } from "./jobs";

describe("job response normalization", () => {
  it("normalizes a wrapped job list and common artifact fields", () => {
    const jobs = normalizeJobs({
      data: {
        jobs: [
          {
            jobId: "job-1",
            workflowType: "invoice",
            state: "COMPLETED",
            inputFiles: [{ filename: "invoice.pdf" }],
            outputs: [{ artifactId: "report", fileName: "report.csv", byteSize: "42" }],
            sources: [{ sourceId: "source", fileName: "invoice.pdf", role: "invoices", previewable: true }],
            retention: "temporary",
            retentionDays: 60,
            expiresAt: "2026-09-01T12:00:00Z",
            coverage: ["Review extracted values against the source."],
            customization: {
              instructions: "Focus on payment controls.",
              standardOutputFields: ["invoice_number", "supplier"],
              outputFields: [{ name: "Approval required", instruction: "Explicit clauses only.", type: "yes_no" }],
            },
          },
        ],
      },
    });

    expect(jobs).toEqual([
      expect.objectContaining({
        id: "job-1",
        workflow: "invoice",
        status: "completed",
        files: ["invoice.pdf"],
        artifacts: [{ id: "report", name: "report.csv", size: 42 }],
        sources: [{ id: "source", name: "invoice.pdf", role: "invoices", previewable: true }],
        retention: "temporary",
        retentionDays: 60,
        coverage: ["Review extracted values against the source."],
        customization: {
          instructions: "Focus on payment controls.",
          standardOutputFields: ["invoice_number", "supplier"],
          outputFields: [{ name: "Approval required", instruction: "Explicit clauses only.", type: "yes_no" }],
        },
      }),
    ]);
  });

  it("rejects malformed jobs and identifies terminal states", () => {
    expect(normalizeJob({ workflow: "invoice" })).toBeUndefined();
    expect(isTerminalJob("completed")).toBe(true);
    expect(isTerminalJob("running")).toBe(false);
    expect(hasActiveJobs([{ id: "done", workflow: "invoice", status: "completed", coverage: [], files: [], artifacts: [], sources: [], raw: {} }])).toBe(false);
    expect(hasActiveJobs([{ id: "active", workflow: "invoice", status: "running", coverage: [], files: [], artifacts: [], sources: [], raw: {} }])).toBe(true);
  });
});
