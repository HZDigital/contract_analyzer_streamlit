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
      }),
    ]);
  });

  it("rejects malformed jobs and identifies terminal states", () => {
    expect(normalizeJob({ workflow: "invoice" })).toBeUndefined();
    expect(isTerminalJob("completed")).toBe(true);
    expect(isTerminalJob("running")).toBe(false);
    expect(hasActiveJobs([{ id: "done", workflow: "invoice", status: "completed", files: [], artifacts: [], raw: {} }])).toBe(false);
    expect(hasActiveJobs([{ id: "active", workflow: "invoice", status: "running", files: [], artifacts: [], raw: {} }])).toBe(true);
  });
});
