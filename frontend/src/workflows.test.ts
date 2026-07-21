import { describe, expect, it } from "vitest";
import {
  analysisModules,
  moduleForWorkflow,
  workflowById,
  workflowTitle,
  workflows,
} from "./workflows";

describe("analysis module catalog", () => {
  it("always exposes every analysis module in canonical order", () => {
    expect(analysisModules.map((module) => module.id)).toEqual([
      "contract_review",
      "standard_comparison",
      "product_request",
      "invoice",
      "factory_certificate",
    ]);
  });

  it("groups deep review and regular-hours extraction without changing backend IDs", () => {
    expect(analysisModules).toHaveLength(5);
    expect(moduleForWorkflow("large_scanner")?.id).toBe("contract_review");
    expect(moduleForWorkflow("normalstunden")?.id).toBe("invoice");
    expect(workflowById("large_scanner")?.inputs[0].id).toBe("contract");
    expect(workflowById("detailed_contract")?.options).toEqual([]);
    expect(workflowById("normalstunden")?.normalstundenSelection).toBe(true);
  });

  it("maps every user-facing workflow to exactly one module", () => {
    const mappedWorkflowIds = analysisModules.flatMap((module) => module.workflowIds);
    expect(mappedWorkflowIds).toHaveLength(7);
    expect(new Set(mappedWorkflowIds).size).toBe(7);
    expect(new Set(mappedWorkflowIds)).toEqual(new Set(workflows.map((workflow) => workflow.id)));
    expect(workflowById("tender")).toBeUndefined();
  });

  it("preserves historical and unknown workflow titles", () => {
    expect(workflowTitle("large_scanner")).toBe("Contract review - Deep review");
    expect(workflowTitle("normalstunden")).toBe("Invoice - Regular hours and rates");
    expect(workflowTitle("tender")).toBe("Tender");
    expect(workflowTitle("future_workflow")).toBe("future workflow");
  });

  it("defines removable standard output fields for every active workflow", () => {
    for (const workflow of workflows) {
      expect(workflow.standardOutputFields.length).toBeGreaterThan(0);
      expect(new Set(workflow.standardOutputFields.map((field) => field.id)).size).toBe(workflow.standardOutputFields.length);
    }
    expect(workflowById("detailed_contract")?.standardOutputFields.map((field) => field.id)).toContain("risk_areas");
    expect(workflowById("invoice")?.standardOutputFields.map((field) => field.id)).toContain("products");
  });
});
