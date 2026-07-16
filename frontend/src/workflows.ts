import type { OptionValue } from "./types";

export type WorkflowId =
  | "product_request"
  | "invoice"
  | "normalstunden"
  | "detailed_contract"
  | "tender"
  | "cooperation_review"
  | "factory_certificate"
  | "large_scanner";

export type AnalysisModuleId =
  | "contract_review"
  | "standard_comparison"
  | "product_request"
  | "invoice"
  | "factory_certificate";

export interface FileInputDefinition {
  id: string;
  label: string;
  hint: string;
  accept: string;
  multiple: boolean;
  minimum: number;
}

export interface OptionDefinition {
  id: string;
  label: string;
  type: "checkbox" | "select" | "number" | "range";
  defaultValue: OptionValue;
  help?: string;
  min?: number;
  max?: number;
  step?: number;
  choices?: Array<{ label: string; value: string }>;
}

export interface WorkflowDefinition {
  id: WorkflowId;
  modeLabel: string;
  detail: string;
  inputs: FileInputDefinition[];
  options: OptionDefinition[];
  normalstundenSelection?: boolean;
}

export interface AnalysisModuleDefinition {
  id: AnalysisModuleId;
  shortCode: string;
  title: string;
  description: string;
  defaultWorkflowId: WorkflowId;
  workflowIds: WorkflowId[];
}

const pdfFiles = ".pdf,application/pdf";
const officeFiles = ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export const workflows: WorkflowDefinition[] = [
  {
    id: "detailed_contract",
    modeLabel: "Standard review",
    detail: "Review one or more contracts for key commercial terms, clauses, obligations, and risks.",
    inputs: [
      { id: "contracts", label: "Contract PDFs", hint: "Each contract is reviewed separately.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [],
  },
  {
    id: "large_scanner",
    modeLabel: "Deep review",
    detail: "Analyze one long contract in cited chunks and ask follow-up questions against its stored evidence.",
    inputs: [
      { id: "contract", label: "Large contract PDF", hint: "Upload one complete long-form contract.", accept: pdfFiles, multiple: false, minimum: 1 },
    ],
    options: [
      { id: "maxChars", label: "Chunk size (characters)", type: "number", defaultValue: 18000, min: 8000, max: 30000, step: 1000 },
      { id: "overlapPages", label: "Overlap pages", type: "number", defaultValue: 1, min: 0, max: 3, step: 1 },
      { id: "isCompleteDocument", label: "Uploaded PDF is the complete contract", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "cooperation_review",
    modeLabel: "Agreement comparison",
    detail: "Compare supplier agreements with your standard contract to identify deviations, risks, and negotiation points.",
    inputs: [
      { id: "supplierAgreements", label: "Supplier cooperation agreements", hint: "One or more PDF, DOC, or DOCX proposals.", accept: officeFiles, multiple: true, minimum: 1 },
      { id: "standardContract", label: "Standard contract", hint: "The required PDF comparison baseline.", accept: pdfFiles, multiple: false, minimum: 1 },
    ],
    options: [
      { id: "includeRiskAssessment", label: "Include risk assessment", type: "checkbox", defaultValue: true },
      { id: "includeRecommendations", label: "Include recommendations", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "product_request",
    modeLabel: "Demand extraction",
    detail: "Upload request PDFs to consolidate customers, products, quantities, and common demand.",
    inputs: [
      { id: "requests", label: "Request documents", hint: "Add one or more PDF requests.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [
      { id: "groupSimilarProducts", label: "Group similar products across documents", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "invoice",
    modeLabel: "Invoice extraction",
    detail: "Extract suppliers, totals, taxes, payment terms, and line items from one or more invoices.",
    inputs: [
      { id: "invoices", label: "Invoice PDFs", hint: "Upload one or more invoices.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [],
  },
  {
    id: "normalstunden",
    modeLabel: "Regular hours and rates",
    detail: "Extract regular working hours and rates from invoices while excluding premiums and supplements.",
    inputs: [],
    options: [
      { id: "includeSubfolders", label: "Include ZIP subfolders", type: "checkbox", defaultValue: true },
    ],
    normalstundenSelection: true,
  },
  {
    id: "factory_certificate",
    modeLabel: "Certificate comparison",
    detail: "Compare technical specifications with factory certificates and identify tolerance deviations.",
    inputs: [
      { id: "comparisonDocuments", label: "Specifications and certificates", hint: "Upload all related PDFs in one set; at least two are required.", accept: pdfFiles, multiple: true, minimum: 2 },
    ],
    options: [],
  },
];

export const analysisModules: AnalysisModuleDefinition[] = [
  {
    id: "contract_review",
    shortCode: "CR",
    title: "Contract review",
    description: "Review commercial terms and risks, with a deeper evidence-grounded mode for long contracts.",
    defaultWorkflowId: "detailed_contract",
    workflowIds: ["detailed_contract", "large_scanner"],
  },
  {
    id: "standard_comparison",
    shortCode: "CS",
    title: "Compare with standard",
    description: "Compare supplier agreements against your standard contract and prepare negotiation points.",
    defaultWorkflowId: "cooperation_review",
    workflowIds: ["cooperation_review"],
  },
  {
    id: "product_request",
    shortCode: "PR",
    title: "Product request",
    description: "Consolidate products, quantities, customers, and shared demand across request documents.",
    defaultWorkflowId: "product_request",
    workflowIds: ["product_request"],
  },
  {
    id: "invoice",
    shortCode: "IN",
    title: "Invoice",
    description: "Extract complete invoice data or focus specifically on regular hours and hourly rates.",
    defaultWorkflowId: "invoice",
    workflowIds: ["invoice", "normalstunden"],
  },
  {
    id: "factory_certificate",
    shortCode: "FC",
    title: "Factory certificate",
    description: "Compare manufacturing specifications with certificates and highlight tolerance deviations.",
    defaultWorkflowId: "factory_certificate",
    workflowIds: ["factory_certificate"],
  },
];

export function workflowById(id: string): WorkflowDefinition | undefined {
  return workflows.find((workflow) => workflow.id === id);
}

export function moduleById(id: string): AnalysisModuleDefinition | undefined {
  return analysisModules.find((module) => module.id === id);
}

export function moduleForWorkflow(id: string): AnalysisModuleDefinition | undefined {
  return analysisModules.find((module) => module.workflowIds.some((workflowId) => workflowId === id));
}

export function workflowTitle(id: string): string {
  const module = moduleForWorkflow(id);
  const workflow = workflowById(id);
  if (!module || !workflow) {
    if (id === "tender") {
      return "Tender";
    }
    return id.replaceAll("_", " ");
  }
  return module.workflowIds.length > 1 ? `${module.title} - ${workflow.modeLabel}` : module.title;
}
