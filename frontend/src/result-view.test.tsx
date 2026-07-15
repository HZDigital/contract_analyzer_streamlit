import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResultView } from "./result-view";

describe("ResultView", () => {
  it("renders detailed-contract results as document and analysis tables", () => {
    const markup = renderToStaticMarkup(
      <ResultView
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

    expect(markup).toContain("Document overview");
    expect(markup).toContain("Products and services");
    expect(markup).toContain("Key clauses");
    expect(markup).toContain("Risk areas");
    expect(markup).toContain("Example GmbH");
  });

  it("keeps non-document results structured instead of serializing raw JSON", () => {
    const markup = renderToStaticMarkup(
      <ResultView value={{ workflow: "factory_certificate", analysis: { comparisons: [{ parameter: "Weight", status: "match" }] } }} />,
    );

    expect(markup).toContain("Comparisons");
    expect(markup).toContain("Weight");
    expect(markup).not.toContain("&quot;workflow&quot;");
  });
});
