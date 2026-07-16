import { describe, expect, it } from "vitest";
import { parsePageRange, referenceForRow } from "./result-references";

const sources = [{
  id: "source-1",
  name: "agreement.pdf",
  role: "contracts",
  contentType: "application/pdf",
  previewable: true,
}];

describe("result references", () => {
  it("resolves an inherited file, quote, and page range", () => {
    expect(referenceForRow(
      { quote: "Either party may terminate.", page_ref: "Pages 12-13", section_ref: "Clause 8" },
      "agreement.pdf",
      sources,
    )).toEqual({
      sourceId: "source-1",
      sourceName: "agreement.pdf",
      quote: "Either party may terminate.",
      page: 12,
      pageEnd: 13,
      section: "Clause 8",
    });
  });

  it("does not create links for ambiguous or historical findings", () => {
    expect(referenceForRow({ quote: "Text" }, undefined, sources)).toBeUndefined();
    expect(referenceForRow({ quote: "Text" }, "missing.pdf", sources)).toBeUndefined();
    expect(referenceForRow({ quote: "Text" }, "agreement.pdf", [])).toBeUndefined();
    expect(referenceForRow(
      { quote: "Text" },
      "agreement.pdf",
      [...sources, { ...sources[0], id: "source-2", name: "Agreement.pdf" }],
    )).toBeUndefined();
    expect(referenceForRow(
      { quote: "Text", file_name: "missing.pdf" },
      "agreement.pdf",
      sources,
    )).toBeUndefined();
    expect(referenceForRow(
      { quote: "Text", source: "https://example.com/agreement.pdf" },
      undefined,
      sources,
    )).toBeUndefined();
  });

  it("parses only positive page references", () => {
    expect(parsePageRange("p. 4 to 6")).toEqual({ page: 4, pageEnd: 6 });
    expect(parsePageRange("appendix")).toEqual({});
  });
});
