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

export interface StandardOutputFieldDefinition {
  id: string;
  label: string;
  detail: string;
}

export interface WorkflowDefinition {
  id: WorkflowId;
  modeLabel: string;
  detail: string;
  inputs: FileInputDefinition[];
  options: OptionDefinition[];
  standardOutputFields: StandardOutputFieldDefinition[];
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
    standardOutputFields: [
      { id: "summary", label: "Executive summary", detail: "Concise overview of the document and its commercial purpose." },
      { id: "client_name", label: "Counterparty", detail: "Detected customer, client, or principal party." },
      { id: "contract_type", label: "Contract type", detail: "Classification of the agreement." },
      { id: "start_date", label: "Start date", detail: "Detected contract commencement date." },
      { id: "end_date", label: "End date", detail: "Detected expiry or end date." },
      { id: "products_services", label: "Products and services", detail: "Commercial scope, quantities, units, and rates." },
      { id: "key_clauses", label: "Key clauses", detail: "Material provisions with supporting quotations." },
      { id: "risk_areas", label: "Risks and actions", detail: "Detected commercial or contractual concerns." },
    ],
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
    standardOutputFields: [
      { id: "report", label: "Consultant report", detail: "Synthesized review of the complete analyzed contract." },
      { id: "findings_by_category", label: "Categorized findings", detail: "Evidence-grounded findings grouped by commercial topic." },
      { id: "red_flags", label: "Red flags", detail: "High-priority issues and their business impact." },
      { id: "cross_reference_gaps", label: "Cross-reference gaps", detail: "Missing or unresolved referenced schedules and clauses." },
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
    standardOutputFields: [
      { id: "summary", label: "Comparison summary", detail: "Agreement type, parties, duration, status, and overview." },
      { id: "deviations", label: "Deviations", detail: "Differences between supplier terms and the standard contract." },
      { id: "risks", label: "Risks", detail: "Risk assessment with severity and supporting wording." },
      { id: "key_clauses", label: "Key clauses", detail: "Important provisions and quotations." },
      { id: "recommendations", label: "Recommendations", detail: "Prioritized negotiation and follow-up actions." },
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
    standardOutputFields: [
      { id: "client_name", label: "Customer", detail: "Detected customer or requesting party." },
      { id: "contract_type", label: "Request type", detail: "Detected request or contract classification." },
      { id: "total_estimated_value", label: "Estimated value", detail: "Estimated total value when stated." },
      { id: "products", label: "Products", detail: "Requested products, descriptions, quantities, and units." },
      { id: "consolidated_products", label: "Consolidated demand", detail: "Similar products grouped across uploaded documents." },
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
    standardOutputFields: [
      { id: "invoice_number", label: "Invoice number", detail: "Supplier invoice identifier." },
      { id: "invoice_date", label: "Invoice date", detail: "Date the invoice was issued." },
      { id: "due_date", label: "Due date", detail: "Detected payment due date." },
      { id: "currency", label: "Currency", detail: "Invoice currency." },
      { id: "total_amount", label: "Total amount", detail: "Gross invoice total." },
      { id: "subtotal", label: "Subtotal", detail: "Net amount before tax." },
      { id: "tax_amount", label: "Tax amount", detail: "Total tax charged." },
      { id: "tax_rate_percent", label: "Tax rate", detail: "Detected tax percentage." },
      { id: "payment_terms", label: "Payment terms", detail: "Stated payment conditions." },
      { id: "po_number", label: "Purchase order", detail: "Referenced purchase-order number." },
      { id: "supplier", label: "Supplier details", detail: "Supplier name, address, and tax identifier." },
      { id: "customer", label: "Customer and delivery", detail: "Customer, billing, and ship-to information." },
      { id: "contract_type", label: "Document type", detail: "Detected invoice or contract classification." },
      { id: "notes", label: "Notes", detail: "Additional material invoice information." },
      { id: "products", label: "Line items", detail: "Products, quantities, unit prices, totals, tax, and SKU." },
    ],
  },
  {
    id: "normalstunden",
    modeLabel: "Regular hours and rates",
    detail: "Extract regular working hours and rates from invoices while excluding premiums and supplements.",
    inputs: [],
    options: [
      { id: "includeSubfolders", label: "Include ZIP subfolders", type: "checkbox", defaultValue: true },
    ],
    standardOutputFields: [
      { id: "supplier", label: "Supplier", detail: "Detected supplier name." },
      { id: "hours_total", label: "Regular hours", detail: "Total qualifying regular working hours." },
      { id: "hourly_rates", label: "Hourly rates", detail: "Distinct regular hourly rates." },
      { id: "entries", label: "Matched entries", detail: "Qualifying invoice lines with hours and rates." },
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
    standardOutputFields: [
      { id: "summary", label: "Comparison summary", detail: "Overall specification and certificate assessment." },
      { id: "identified_specs", label: "Identified specifications", detail: "Documents recognized as specifications." },
      { id: "identified_certificates", label: "Identified certificates", detail: "Documents recognized as factory certificates." },
      { id: "comparisons", label: "Parameter comparisons", detail: "Specification limits, measured values, status, and deviation." },
    ],
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
