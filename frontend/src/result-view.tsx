import type { ReactNode } from "react";

type ResultRecord = Record<string, unknown>;

const HIDDEN_KEYS = new Set(["qa_context", "chunk_results", "raw"]);
const NARRATIVE_KEYS = new Set(["report", "german_summary", "notes"]);
const FRIENDLY_LABELS: Record<string, string> = {
  client_name: "Client",
  contract_type: "Contract type",
  start_date: "Start date",
  end_date: "End date",
  products_services: "Products and services",
  key_clauses: "Key clauses",
  risk_areas: "Risk areas",
  hourly_rates: "Hourly rates",
  consolidated_products: "Consolidated products",
  market_situation: "Market situation",
  field_sources: "Field sources",
  extraction_errors: "Extraction errors",
  supplier_agreements: "Supplier agreements",
  standard_contract: "Standard contract",
  source_files: "Source files",
  page_count: "Readable pages",
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

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
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
    const values = Object.values(record).filter(isPrimitive).map(valueText).filter((item) => item !== "-");
    return values.join(" - ") || "Structured data";
  }
  return String(value);
}

function ResultTable({ title, rows }: { title: string; rows: ResultRecord[] }) {
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
          {rows.map((row, index) => (
            <tr key={`${title}-${index}`}>
              {columns.map((column) => <td key={column}>{valueText(row[column])}</td>)}
            </tr>
          ))}
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
    <div className="result-table-wrap compact-table" tabIndex={0}>
      <table className="result-table">
        <tbody>
          {values.map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{labelFor(key)}</th>
              <td>{valueText(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

function StructuredRecord({ value, depth = 0 }: { value: ResultRecord; depth?: number }) {
  const entries = Object.entries(value).filter(([key]) => !HIDDEN_KEYS.has(key));
  const primitiveEntries = entries.filter(([key, item]) => isPrimitive(item) && !NARRATIVE_KEYS.has(key));
  const narrativeEntries = entries.filter(([key, item]) => NARRATIVE_KEYS.has(key) && typeof item === "string" && item.trim());
  const structuredEntries = entries.filter(([, item]) => !isPrimitive(item) && !Array.isArray(item));
  const arrays = entries.filter((entry): entry is [string, unknown[]] => Array.isArray(entry[1]));

  return (
    <div className={depth === 0 ? "result-record" : "nested-result-record"}>
      <FieldTable values={primitiveEntries} />
      {narrativeEntries.map(([key, item]) => <Narrative key={key} title={labelFor(key)}>{String(item)}</Narrative>)}
      {arrays.map(([key, item]) => {
        const rows = asRecordArray(item);
        if (rows.length > 0) {
          return <section className="result-section" key={key}><h4>{labelFor(key)}</h4><ResultTable title={labelFor(key)} rows={rows} /></section>;
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
            <StructuredRecord value={nested} depth={depth + 1} />
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
    <div className="result-summary-grid" aria-label="Analysis summary">
      {entries.map(([key, item]) => <div key={key}><span>{labelFor(key)}</span><strong>{valueText(item)}</strong></div>)}
    </div>
  );
}

function DocumentResults({ results }: { results: ResultRecord[] }) {
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
      <section className="result-section">
        <h4>Document overview</h4>
        <ResultTable title="Document overview" rows={overviewRows} />
      </section>
      {results.map((result, index) => {
        const details = asRecord(result.analysis) ?? Object.fromEntries(
          Object.entries(result).filter(([key]) => !["file_name", "status", "error"].includes(key)),
        );
        return (
          <article className="document-result-card" key={`${String(result.file_name ?? "document")}-${index}`}>
            <div className="document-result-heading">
              <div>
                <p className="eyebrow">Document {index + 1}</p>
                <h4>{valueText(result.file_name) || "Document result"}</h4>
              </div>
              <span className={`status-badge ${String(result.status) === "success" ? "status-completed" : "status-failed"}`}>
                {valueText(result.status)}
              </span>
            </div>
            {result.error ? <p className="inline-error">{valueText(result.error)}</p> : null}
            {Object.keys(details).length > 0 ? <StructuredRecord value={details} /> : null}
          </article>
        );
      })}
    </>
  );
}

export function ResultView({ value }: { value: unknown }) {
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
    <div className="result-stack">
      {summary ? <Summary value={summary} /> : null}
      {results.length > 0 ? <DocumentResults results={results} /> : null}
      {Object.keys(topLevel).length > 0 ? <StructuredRecord value={topLevel} /> : null}
    </div>
  );
}
