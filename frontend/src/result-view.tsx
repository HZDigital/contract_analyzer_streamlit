import type { ReactNode } from "react";
import { referenceForRow, sourceNameFromRecord } from "./result-references";
import type { JobSource, ResultReference } from "./types";

type ResultRecord = Record<string, unknown>;

const HIDDEN_KEYS = new Set([
  "qa_context",
  "chunk_results",
  "raw",
  "grouping_error",
  "file_path",
  "supplier_folder",
  "matched_rows",
  "hours_display",
  "hourly_rate_display",
  "chunk_id",
  "chunks_analyzed",
  "standard_topics",
  "settings",
  "errors",
  "confidence",
  "page_start",
  "page_end",
  "Chancen in %",
  "template_name",
  "source_files",
]);
const NARRATIVE_KEYS = new Set(["summary", "report", "german_summary", "notes", "recommendations"]);
const EVIDENCE_KEYS = new Set(["quote", "source", "source_file", "source_files", "page", "page_ref", "pages", "reference", "references", "section_ref", "citation", "citations"]);
const TRUSTED_DYNAMIC_SECTIONS = new Set(["extracted", "field_sources", "tender_fields"]);
const FRIENDLY_LABELS: Record<string, string> = {
  client_name: "Client",
  contract_type: "Contract type",
  start_date: "Start date",
  end_date: "End date",
  products_services: "Commercial scope",
  key_clauses: "Contractual provisions",
  risk_areas: "Risks and actions",
  hourly_rates: "Hourly rates",
  consolidated_products: "Consolidated products",
  market_situation: "External market observations",
  field_sources: "Field sources",
  extraction_errors: "Extraction errors",
  supplier_agreements: "Supplier agreements",
  standard_contract: "Standard contract",
  source_files: "Source files",
  page_count: "Readable pages",
  no_match: "No regular hours found",
  po_number: "Purchase order number",
  tax_id: "Supplier tax ID",
  sku_or_part_number: "SKU or part number",
  measured_from: "Measurement source",
  spec_min: "Specification minimum",
  spec_max: "Specification maximum",
  spec_nominal: "Specification nominal",
  is_complete_document: "Complete document supplied",
  inference: "AI interpretation",
  warnings: "Review notes",
};

const BUSINESS_STATUS_LABELS: Record<string, string> = {
  success: "Analyzed",
  failed: "Could not analyze",
  no_match: "No regular hours found",
  OK: "Within specification",
  OUT: "Out of tolerance",
  MISSING: "Required value missing",
  NO_SPEC: "No matching specification",
};

function asRecord(value: unknown): ResultRecord | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as ResultRecord
    : undefined;
}

function asRecordArray(value: unknown): ResultRecord[] {
  return Array.isArray(value)
    ? value.map(asRecord).filter((item): item is ResultRecord => item !== undefined)
    : [];
}

function isPrimitive(value: unknown): value is string | number | boolean | null | undefined {
  return value === null || value === undefined || ["string", "number", "boolean"].includes(typeof value);
}

function labelFor(key: string): string {
  return FRIENDLY_LABELS[key] ?? key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function resultSectionClass(key: string): string {
  if (key === "risk_areas" || key === "extraction_errors") {
    return "result-section review-risks";
  }
  if (key === "key_clauses" || key === "field_sources" || key === "source_files") {
    return "result-section review-evidence";
  }
  if (key === "products_services" || key === "products" || key === "line_items") {
    return "result-section review-commercial";
  }
  return "result-section";
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) {
    return "Not reported";
  }
  if (value === "") {
    return "Not provided";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return value.toLocaleString();
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(valueText).join(", ");
  }
  const record = asRecord(value);
  if (record) {
    const values = Object.values(record).filter(isPrimitive).map(valueText).filter((item) => item !== "Not reported");
    return values.join(" - ") || "Structured data";
  }
  return String(value);
}

function fieldValueText(key: string, value: unknown): string {
  if (key === "status" && typeof value === "string") {
    return BUSINESS_STATUS_LABELS[value] ?? valueText(value);
  }
  return valueText(value);
}

function documentStatusClass(status: unknown): string {
  if (status === "success") {
    return "status-completed";
  }
  if (status === "no_match") {
    return "status-queued";
  }
  return "status-failed";
}

function safeExternalUrl(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : undefined;
  } catch {
    return undefined;
  }
}

function referenceColumn(row: ResultRecord): string | undefined {
  return ["quote", "citation", "page_ref", "page", "pages"].find((key) => row[key] !== undefined);
}

function SourceReferenceButton({ reference, onOpen }: { reference: ResultReference; onOpen: (reference: ResultReference) => void }) {
  const location = reference.page
    ? `Page ${reference.page}${reference.pageEnd && reference.pageEnd !== reference.page ? `-${reference.pageEnd}` : ""}`
    : "Locate quote";
  return (
    <button className="result-reference-link" type="button" onClick={() => onOpen(reference)}>
      <span>View in source</span>
      <small>{location}</small>
    </button>
  );
}

function ResultTable({
  title,
  rows,
  sourceName,
  sources,
  onOpenReference,
}: {
  title: string;
  rows: ResultRecord[];
  sourceName?: string;
  sources: JobSource[];
  onOpenReference?: (reference: ResultReference) => void;
}) {
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row).filter((key) => !HIDDEN_KEYS.has(key)))));
  if (columns.length === 0) {
    return null;
  }

  return (
    <div className="result-table-wrap" tabIndex={0}>
      <table className="result-table">
        <caption>{title}</caption>
        <thead>
          <tr>{columns.map((column) => <th key={column} scope="col">{labelFor(column)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const reference = referenceForRow(row, sourceName, sources);
            const actionColumn = referenceColumn(row);
            return (
              <tr key={`${title}-${index}`}>
                {columns.map((column) => (
                  <td className={EVIDENCE_KEYS.has(column) ? "result-evidence-cell" : undefined} key={column}>
                    {column === "url" && safeExternalUrl(row[column]) ? (
                      <a href={safeExternalUrl(row[column])} rel="noreferrer" target="_blank">Open external source</a>
                    ) : (
                      <span>{fieldValueText(column, row[column])}</span>
                    )}
                    {reference && onOpenReference && column === actionColumn
                      ? <SourceReferenceButton reference={reference} onOpen={onOpenReference} />
                      : null}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FieldTable({ values }: { values: Array<[string, unknown]> }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <dl className="result-profile-grid">
      {values.map(([key, value]) => (
        <div key={key}>
          <dt>{labelFor(key)}</dt>
          <dd>{fieldValueText(key, value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Narrative({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="result-section">
      <h4>{title}</h4>
      <div className="result-narrative">{children}</div>
    </section>
  );
}

function StructuredRecord({
  value,
  depth = 0,
  sourceName,
  sources,
  onOpenReference,
  allowDynamicFields = false,
}: {
  value: ResultRecord;
  depth?: number;
  sourceName?: string;
  sources: JobSource[];
  onOpenReference?: (reference: ResultReference) => void;
  allowDynamicFields?: boolean;
}) {
  const recordSourceName = sourceNameFromRecord(value, sourceName);
  const entries = Object.entries(value).filter(([key]) => (
    !HIDDEN_KEYS.has(key) || (allowDynamicFields && key !== "Chancen in %")
  ));
  const primitiveEntries = entries.filter(([key, item]) => isPrimitive(item) && !NARRATIVE_KEYS.has(key));
  const narrativeEntries = entries.filter(([key, item]) => NARRATIVE_KEYS.has(key) && typeof item === "string" && item.trim());
  const structuredEntries = entries.filter(([, item]) => !isPrimitive(item) && !Array.isArray(item));
  const arrays = entries.filter((entry): entry is [string, unknown[]] => Array.isArray(entry[1]));

  return (
    <div className={depth === 0 ? "result-record" : "nested-result-record"}>
      {narrativeEntries.map(([key, item]) => <Narrative key={key} title={labelFor(key)}>{String(item)}</Narrative>)}
      <FieldTable values={primitiveEntries} />
      {arrays.map(([key, item]) => {
        const rows = asRecordArray(item);
        if (rows.length > 0) {
          return (
            <section className={resultSectionClass(key)} key={key}>
              <h4>{labelFor(key)}</h4>
              <ResultTable title={labelFor(key)} rows={rows} sourceName={recordSourceName} sources={sources} onOpenReference={onOpenReference} />
            </section>
          );
        }
        if (item.length === 0) {
          return null;
        }
        return <Narrative key={key} title={labelFor(key)}>{item.map(valueText).join(", ")}</Narrative>;
      })}
      {depth < 2 && structuredEntries.map(([key, item]) => {
        const nested = asRecord(item);
        return nested ? (
          <section className="result-section" key={key}>
            <h4>{labelFor(key)}</h4>
            <StructuredRecord
              value={nested}
              depth={depth + 1}
              sourceName={recordSourceName}
              sources={sources}
              onOpenReference={onOpenReference}
              allowDynamicFields={TRUSTED_DYNAMIC_SECTIONS.has(key)}
            />
          </section>
        ) : null;
      })}
    </div>
  );
}

function Summary({ value }: { value: ResultRecord }) {
  const entries = Object.entries(value).filter(([, item]) => typeof item === "number");
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="analysis-summary">
      <div className="analysis-summary-heading">
        <p className="eyebrow">Operational summary</p>
        <h4>Analysis at a glance</h4>
      </div>
      <div className="result-summary-grid" aria-label="Analysis summary">
        {entries.map(([key, item]) => <div key={key}><span>{labelFor(key)}</span><strong>{valueText(item)}</strong></div>)}
      </div>
    </section>
  );
}

function DocumentResults({
  results,
  sources,
  onOpenReference,
}: {
  results: ResultRecord[];
  sources: JobSource[];
  onOpenReference?: (reference: ResultReference) => void;
}) {
  const overviewRows = results.map((result) => {
    const analysis = asRecord(result.analysis);
    return {
      file_name: result.file_name,
      status: result.status,
      client_name: analysis?.client_name ?? result.client_name,
      contract_type: analysis?.contract_type ?? result.contract_type,
      summary: analysis?.summary,
      error: result.error,
    };
  });

  return (
    <>
      {results.length > 1 ? (
        <section className="result-section">
          <h4>Document portfolio</h4>
          <ResultTable title="Document portfolio" rows={overviewRows} sources={sources} onOpenReference={onOpenReference} />
        </section>
      ) : null}
      {results.map((result, index) => {
        const details = asRecord(result.analysis) ?? Object.fromEntries(
          Object.entries(result).filter(([key]) => !["file_name", "status", "error"].includes(key)),
        );
        return (
          <article className="document-result-card" key={`${String(result.file_name ?? "document")}-${index}`}>
            <details className="document-result-disclosure" open>
              <summary className="document-result-heading">
                <div>
                  <p className="eyebrow">{results.length > 1 ? `Analyzed document ${index + 1}` : "Analyzed document"}</p>
                  <h4>{valueText(result.file_name) || "Document result"}</h4>
                </div>
                <span className="document-result-heading-actions">
                  <span className={`status-badge ${documentStatusClass(result.status)}`}>
                    {fieldValueText("status", result.status)}
                  </span>
                  <span className="document-result-toggle" aria-hidden="true" />
                </span>
              </summary>
              {result.error || Object.keys(details).length > 0 ? (
                <div className="document-result-content">
                  {result.error ? <p className="inline-error">{valueText(result.error)}</p> : null}
                  {Object.keys(details).length > 0 ? (
                    <StructuredRecord
                      value={details}
                      sourceName={typeof result.file_name === "string" ? result.file_name : undefined}
                      sources={sources}
                      onOpenReference={onOpenReference}
                    />
                  ) : null}
                </div>
              ) : null}
            </details>
          </article>
        );
      })}
    </>
  );
}

export function ResultView({
  value,
  sources = [],
  onOpenReference,
}: {
  value: unknown;
  sources?: JobSource[];
  onOpenReference?: (reference: ResultReference) => void;
}) {
  if (typeof value === "string") {
    return <Narrative title="Analysis result">{value}</Narrative>;
  }

  const result = asRecord(value);
  if (!result) {
    return <pre className="result-value">{JSON.stringify(value, null, 2)}</pre>;
  }

  const results = asRecordArray(result.results);
  const summary = asRecord(result.summary);
  const topLevel = Object.fromEntries(
    Object.entries(result).filter(([key]) => !["workflow", "summary", "results"].includes(key)),
  );

  return (
    <div className="result-stack result-showcase">
      {summary ? <Summary value={summary} /> : null}
       {results.length > 0 ? <DocumentResults results={results} sources={sources} onOpenReference={onOpenReference} /> : null}
       {Object.keys(topLevel).length > 0 ? (
         <StructuredRecord
           value={topLevel}
           sourceName={sourceNameFromRecord(result)}
           sources={sources}
           onOpenReference={onOpenReference}
         />
       ) : null}
    </div>
  );
}
