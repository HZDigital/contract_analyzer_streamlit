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
  shortCode: string;
  title: string;
  description: string;
  detail: string;
  inputs: FileInputDefinition[];
  options: OptionDefinition[];
  normalstundenSelection?: boolean;
}

const pdfFiles = ".pdf,application/pdf";
const officeFiles = ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export const workflows: WorkflowDefinition[] = [
  {
    id: "product_request",
    shortCode: "PR",
    title: "Product request",
    description: "Extract customers, requested products, quantities, and common demand across documents.",
    detail: "Upload the contract or request PDFs you want grouped into a consolidated order view.",
    inputs: [
      { id: "requests", label: "Request documents", hint: "PDF documents. You can add more than one.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [
      { id: "groupSimilarProducts", label: "Group similar products across documents", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "invoice",
    shortCode: "IN",
    title: "Invoice",
    description: "Extract invoice details, suppliers, line items, values, and payment information.",
    detail: "Upload one or more invoice PDFs for structured extraction.",
    inputs: [
      { id: "invoices", label: "Invoice PDFs", hint: "Upload one or more invoices.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [],
  },
  {
    id: "normalstunden",
    shortCode: "NH",
    title: "Normalstunden",
    description: "Extract regular hours and rates from invoices while excluding premiums and supplements.",
    detail: "Choose either individual PDFs or a ZIP archive containing the invoice PDFs.",
    inputs: [],
    options: [
      { id: "includeSubfolders", label: "Include ZIP subfolders", type: "checkbox", defaultValue: true },
    ],
    normalstundenSelection: true,
  },
  {
    id: "detailed_contract",
    shortCode: "DC",
    title: "Detailed contract",
    description: "Review clauses, parties, dates, obligations, products, and risk language in contracts.",
    detail: "Upload one or more PDF contracts for a detailed legal and commercial analysis.",
    inputs: [
      { id: "contracts", label: "Contract PDFs", hint: "One or more contracts can be analyzed together.", accept: pdfFiles, multiple: true, minimum: 1 },
    ],
    options: [
      {
        id: "truncateLength",
        label: "Maximum characters per contract",
        type: "range",
        defaultValue: 3500,
        help: "Use more text for lengthy contracts when a deeper review is required.",
        min: 1000,
        max: 30000,
        step: 500,
      },
    ],
  },
  {
    id: "tender",
    shortCode: "TD",
    title: "Tender",
    description: "Extract and translate tender information into a completed internal tender list.",
    detail: "Upload tender documents and the internal XLSX tender-list template that should be completed.",
    inputs: [
      { id: "tenderDocuments", label: "Tender documents", hint: "One or more tender PDFs.", accept: pdfFiles, multiple: true, minimum: 1 },
      { id: "tenderTemplate", label: "Tender list template", hint: "The XLSX file to populate.", accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", multiple: false, minimum: 1 },
    ],
    options: [
      { id: "includeMarketResearch", label: "Include market situation research", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "cooperation_review",
    shortCode: "CR",
    title: "Cooperation review",
    description: "Compare supplier cooperation agreements against an internal standard contract.",
    detail: "Add supplier proposals and the required standard contract used as the comparison baseline.",
    inputs: [
      { id: "supplierAgreements", label: "Supplier cooperation agreements", hint: "One or more PDF, DOC, or DOCX proposals.", accept: officeFiles, multiple: true, minimum: 1 },
      { id: "standardContract", label: "Standard contract", hint: "The required PDF baseline contract.", accept: pdfFiles, multiple: false, minimum: 1 },
    ],
    options: [
      { id: "includeRiskAssessment", label: "Include risk assessment", type: "checkbox", defaultValue: true },
      { id: "includeRecommendations", label: "Include recommendations", type: "checkbox", defaultValue: true },
    ],
  },
  {
    id: "factory_certificate",
    shortCode: "FC",
    title: "Factory certificate",
    description: "Compare technical specifications with certificates and identify tolerance deviations.",
    detail: "Upload the specification and certificate PDFs together. At least two documents are required.",
    inputs: [
      { id: "comparisonDocuments", label: "Specifications and certificates", hint: "Upload all related PDFs in one set.", accept: pdfFiles, multiple: true, minimum: 2 },
    ],
    options: [],
  },
  {
    id: "large_scanner",
    shortCode: "LS",
    title: "Large scanner",
    description: "Analyze a long contract in cited chunks and ask follow-up questions against its evidence.",
    detail: "Upload one complete long-form contract PDF. Questions become available after the scan finishes.",
    inputs: [
      { id: "contract", label: "Large contract PDF", hint: "One PDF contract only.", accept: pdfFiles, multiple: false, minimum: 1 },
    ],
    options: [
      { id: "maxChars", label: "Chunk size (characters)", type: "number", defaultValue: 18000, min: 8000, max: 30000, step: 1000 },
      { id: "overlapPages", label: "Overlap pages", type: "number", defaultValue: 1, min: 0, max: 3, step: 1 },
      { id: "isCompleteDocument", label: "Uploaded PDF is the complete contract", type: "checkbox", defaultValue: true },
    ],
  },
];

export function workflowById(id: string): WorkflowDefinition | undefined {
  return workflows.find((workflow) => workflow.id === id);
}

export function workflowTitle(id: string): string {
  return workflowById(id)?.title ?? id.replaceAll("_", " ");
}
