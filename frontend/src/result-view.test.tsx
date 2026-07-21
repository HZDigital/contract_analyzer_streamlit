import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResultView } from "./result-view";

describe("ResultView", () => {
  it("renders detailed-contract results as document and analysis tables", () => {
    const markup = renderToStaticMarkup(
      <ResultView
        sources={[{ id: "source-1", name: "agreement.pdf", role: "contracts", contentType: "application/pdf", previewable: true }]}
        onOpenReference={() => undefined}
        value={{
          workflow: "detailed_contract",
          summary: { total: 1, successful: 1, failed: 0 },
          results: [{
            file_name: "agreement.pdf",
            status: "success",
            analysis: {
              summary: "Supply agreement for industrial fabric.",
              client_name: "Example GmbH",
              contract_type: "Supply agreement",
              products_services: [{ name: "Fabric", quantity: "100", unit: "m", rate: "12 EUR" }],
              key_clauses: [{ type: "Termination", description: "30 days", quote: "Either party may terminate." }],
              risk_areas: [{ concern: "Price changes", quote: "Prices may be adjusted." }],
            },
          }],
        }}
      />,
    );

    expect(markup).toContain("Analysis at a glance");
    expect(markup).toContain("Commercial scope");
    expect(markup).toContain("Contractual provisions");
    expect(markup).toContain("Risks and actions");
    expect(markup).toContain("Example GmbH");
    expect(markup).toContain("result-evidence-cell");
    expect(markup).toContain("View in source");
    expect(markup).toContain("Locate quote");
    expect(markup).toContain("document-result-disclosure");
    expect(markup).toContain("document-result-toggle");
    expect(markup).not.toContain("Document overview");
  });

  it("keeps non-document results structured instead of serializing raw JSON", () => {
    const markup = renderToStaticMarkup(
      <ResultView value={{ workflow: "factory_certificate", analysis: { comparisons: [{ parameter: "Weight", status: "match" }] } }} />,
    );

    expect(markup).toContain("Comparisons");
    expect(markup).toContain("Weight");
    expect(markup).not.toContain("&quot;workflow&quot;");
  });

  it("hides implementation fields and treats no-match as a neutral outcome", () => {
    const markup = renderToStaticMarkup(
      <ResultView value={{
        workflow: "normalstunden",
        summary: { total: 1, successful: 0, failed: 0, no_match: 1 },
        results: [{
          file_name: "invoice.pdf",
          status: "no_match",
          supplier: "Example GmbH",
          file_path: "/private/input.pdf",
          supplier_folder: "internal-folder",
          matched_rows: 0,
        }],
      }} />,
    );

    expect(markup).toContain("No regular hours found");
    expect(markup).toContain("status-queued");
    expect(markup).not.toContain("private/input.pdf");
    expect(markup).not.toContain("internal-folder");
    expect(markup).not.toContain("Matched Rows");
  });

  it("renders curated customized output with business labels", () => {
    const markup = renderToStaticMarkup(
      <ResultView value={{
        workflow: "invoice",
        results: [{
          file_name: "invoice.pdf",
          status: "success",
          custom_analysis: {
            summary: "Payment approval is required.",
            fields: [{ field: "Approval required", type: "yes_no", value: true }],
          },
        }],
      }} />,
    );

    expect(markup).toContain("Customized output");
    expect(markup).toContain("Requested fields");
    expect(markup).toContain("Approval required");
    expect(markup).toContain("Yes / No");
  });
});
