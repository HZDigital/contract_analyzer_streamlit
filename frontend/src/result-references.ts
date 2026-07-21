import type { JobSource, ResultReference } from "./types";

type ResultRecord = Record<string, unknown>;

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function basename(value: string): string {
  return value.replaceAll("\\", "/").split("/").at(-1)?.trim().toLowerCase() ?? "";
}

function sourceForName(name: string | undefined, sources: JobSource[]): JobSource | undefined {
  if (!name || /^[a-z][a-z\d+.-]*:\/\//i.test(name)) {
    return undefined;
  }
  const normalized = basename(name);
  const matches = sources.filter((source) => source.previewable && basename(source.name) === normalized);
  return matches.length === 1 ? matches[0] : undefined;
}

export function parsePageRange(value: unknown): { page?: number; pageEnd?: number } {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return { page: value, pageEnd: value };
  }
  if (typeof value !== "string") {
    return {};
  }
  const labelled = value.match(/(?:pages?|pp?\.?)\s*(\d+)(?:\s*(?:-|–|to)\s*(\d+))?/i);
  const pages = labelled
    ? labelled.slice(1).filter(Boolean).map(Number)
    : value.match(/\d+/g)?.map(Number).filter((page) => page > 0) ?? [];
  if (pages.length === 0) {
    return {};
  }
  if (pages.length > 1 && (pages[1] < pages[0] || pages[1] - pages[0] > 1_000)) {
    return {};
  }
  return {
    page: pages[0],
    pageEnd: pages.length > 1 ? Math.max(pages[0], pages[1]) : pages[0],
  };
}

export function sourceNameFromRecord(value: ResultRecord, inherited?: string): string | undefined {
  return text(value.source_file) ?? text(value.file_name) ?? inherited;
}

export function referenceForRow(
  row: ResultRecord,
  inheritedSourceName: string | undefined,
  sources: JobSource[],
): ResultReference | undefined {
  const explicitCandidates = [
    text(row.source_file),
    text(row.file_name),
    text(row.measured_from),
  ].filter((candidate): candidate is string => Boolean(candidate));
  const genericSource = text(row.source);
  const candidates = explicitCandidates.length > 0
    ? explicitCandidates
    : genericSource
      ? [genericSource]
      : inheritedSourceName
        ? [inheritedSourceName]
        : [];
  const matches = candidates.map((candidate) => sourceForName(candidate, sources));
  if (matches.some((match) => !match)) {
    return undefined;
  }
  const uniqueMatches = new Map(matches.map((match) => [match?.id, match]));
  const source = uniqueMatches.size === 1 ? matches[0] : undefined;
  if (!source) {
    return undefined;
  }

  const quote = text(row.quote) ?? text(row.citation);
  const pages = parsePageRange(row.page ?? row.page_ref ?? row.pages);
  if (!quote && !pages.page) {
    return undefined;
  }

  return {
    sourceId: source.id,
    sourceName: source.name,
    quote,
    ...pages,
    section: text(row.section_ref) ?? text(row.section) ?? text(row.affected_section),
  };
}
