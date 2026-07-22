import type { PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { isAuthenticationTransitionError } from "./api";
import type { ResultReference } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface PageMatch {
  itemIndexes: Set<number>;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeText(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/-\s+/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function matchPageItems(items: string[], quote: string): PageMatch | undefined {
  const normalizedItems = items.map(normalizeText);
  const spans: Array<{ start: number; end: number; itemIndex: number }> = [];
  let pageText = "";
  normalizedItems.forEach((item, itemIndex) => {
    if (!item) {
      return;
    }
    if (pageText) {
      pageText += " ";
    }
    const start = pageText.length;
    pageText += item;
    spans.push({ start, end: pageText.length, itemIndex });
  });

  const normalizedQuote = normalizeText(quote);
  if (!normalizedQuote) {
    return undefined;
  }
  const start = pageText.indexOf(normalizedQuote);
  if (start < 0) {
    return undefined;
  }
  const end = start + normalizedQuote.length;
  const itemIndexes = new Set(
    spans.filter((span) => span.start < end && span.end > start).map((span) => span.itemIndex),
  );
  return itemIndexes.size > 0 ? { itemIndexes } : undefined;
}

async function pageMatch(pdf: PDFDocumentProxy, pageNumber: number, quote?: string): Promise<PageMatch | undefined> {
  if (!quote) {
    return undefined;
  }
  const page = await pdf.getPage(pageNumber);
  const content = await page.getTextContent();
  const items = content.items.map((item) => "str" in item ? item.str : "");
  return matchPageItems(items, quote);
}

function candidatePages(reference: ResultReference, pageCount: number): number[] {
  if (!reference.page) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }
  const endReference = reference.pageEnd ?? reference.page;
  if (reference.page > pageCount || endReference > pageCount) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }
  const start = reference.page;
  const end = Math.max(endReference, start);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function invalidPageMessage(reference: ResultReference, pageCount: number): string | undefined {
  if (!reference.page || (reference.page <= pageCount && (reference.pageEnd ?? reference.page) <= pageCount)) {
    return undefined;
  }
  const reported = reference.pageEnd && reference.pageEnd !== reference.page
    ? `${reference.page}-${reference.pageEnd}`
    : String(reference.page);
  return `The reported page ${reported} is outside this ${pageCount}-page document.`;
}

export default function SourcePreviewDrawer({
  reference,
  loadSource,
  onClose,
}: {
  reference: ResultReference;
  loadSource: (signal: AbortSignal) => Promise<Blob>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const loadSourceRef = useRef(loadSource);
  const matchRequestRef = useRef(0);
  loadSourceRef.current = loadSource;
  const [file, setFile] = useState<Blob>();
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [pageWidth, setPageWidth] = useState(720);
  const [highlightedItems, setHighlightedItems] = useState<Set<number>>(() => new Set());
  const [message, setMessage] = useState("Loading source document...");
  const [error, setError] = useState<string>();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
    return () => dialog?.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setFile(undefined);
    setPdf(undefined);
    setError(undefined);
    setMessage("Loading source document...");
    matchRequestRef.current += 1;
    void loadSourceRef.current(controller.signal).then((source) => {
      setFile(source);
    }).catch((loadError: unknown) => {
      if (loadError instanceof DOMException && loadError.name === "AbortError") {
        return;
      }
      if (isAuthenticationTransitionError(loadError)) {
        return;
      }
      setError("The source document could not be loaded. Download it or try again later.");
      setMessage("Source preview unavailable.");
    });
    return () => controller.abort();
  }, [reference.sourceId]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      if (entry) {
        setPageWidth(Math.max(280, Math.floor(entry.contentRect.width - 32)));
      }
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [file]);

  async function showPage(nextPage: number): Promise<void> {
    if (!pdf) {
      return;
    }
    const request = ++matchRequestRef.current;
    const boundedPage = Math.min(Math.max(nextPage, 1), pdf.numPages);
    setPageNumber(boundedPage);
    setHighlightedItems(new Set());
    if (!reference.quote) {
      setMessage(`Viewing page ${boundedPage}.`);
      return;
    }
    let match: PageMatch | undefined;
    try {
      match = await pageMatch(pdf, boundedPage, reference.quote);
    } catch {
      if (request === matchRequestRef.current) {
        setMessage("The page wording could not be read automatically. The PDF page is still available for review.");
      }
      return;
    }
    if (request !== matchRequestRef.current) {
      return;
    }
    if (match) {
      setHighlightedItems(match.itemIndexes);
      setMessage("Exact cited text highlighted.");
    } else {
      setMessage("The cited wording could not be verified on this page.");
    }
  }

  async function documentLoaded(loadedPdf: PDFDocumentProxy): Promise<void> {
    const request = ++matchRequestRef.current;
    setPdf(loadedPdf);
    setPageCount(loadedPdf.numPages);
    const pages = candidatePages(reference, loadedPdf.numPages);
    const invalidPage = invalidPageMessage(reference, loadedPdf.numPages);
    if (!reference.quote) {
      const initialPage = invalidPage ? 1 : reference.page ?? 1;
      setPageNumber(initialPage);
      setHighlightedItems(new Set());
      setMessage(invalidPage ? `${invalidPage} Page 1 is shown.` : `Viewing page ${initialPage}.`);
      return;
    }
    setMessage("Locating cited wording...");
    let textLayerErrors = 0;
    for (const candidate of pages) {
      let match: PageMatch | undefined;
      try {
        match = await pageMatch(loadedPdf, candidate, reference.quote);
      } catch {
        textLayerErrors += 1;
        continue;
      }
      if (request !== matchRequestRef.current) {
        return;
      }
      if (match) {
        setPageNumber(candidate);
        setHighlightedItems(match.itemIndexes);
        const matchMessage = "Exact cited text highlighted.";
        setMessage(invalidPage ? `${invalidPage} ${matchMessage} Found on page ${candidate}.` : matchMessage);
        return;
      }
    }
    setPageNumber(pages[0] ?? 1);
    setHighlightedItems(new Set());
    if (textLayerErrors === pages.length) {
      setMessage(`${invalidPage ? `${invalidPage} ` : ""}The document wording could not be read automatically, so the citation could not be highlighted.`);
    } else {
      setMessage(invalidPage
        ? `${invalidPage} The cited wording could not be matched.`
        : "The cited wording could not be matched. The reported source page is shown when available.");
    }
  }

  function download(): void {
    if (!file) {
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = reference.sourceName;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }

  return createPortal(
    <dialog
      aria-labelledby="source-preview-title"
      className="source-preview-dialog"
      ref={dialogRef}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="source-preview-drawer">
        <header className="source-preview-header">
          <div>
            <p className="eyebrow">Source evidence</p>
            <h2 id="source-preview-title">{reference.sourceName}</h2>
            {reference.section ? <p>{reference.section}</p> : null}
          </div>
          <div className="source-preview-actions">
            <button className="secondary-button compact" type="button" onClick={download} disabled={!file}>Download</button>
            <button aria-label="Close source preview" autoFocus className="source-preview-close" type="button" onClick={onClose}>Close</button>
          </div>
        </header>

        {reference.quote ? <blockquote className="source-preview-quote">{reference.quote}</blockquote> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <p className="source-preview-status" aria-live="polite">{message}</p>

        {file ? (
          <div className="source-preview-document" ref={viewportRef}>
            <Document
              file={file}
              loading={<p className="empty-state">Opening PDF...</p>}
              onLoadError={() => {
                setError("The PDF preview could not be rendered. Download the document to review it.");
                setMessage("This PDF could not be rendered.");
              }}
              onLoadSuccess={(loadedPdf) => void documentLoaded(loadedPdf)}
            >
              <Page
                key={pageNumber}
                pageNumber={pageNumber}
                renderAnnotationLayer={false}
                renderTextLayer
                width={pageWidth}
                customTextRenderer={({ str, itemIndex }) => highlightedItems.has(itemIndex)
                  ? `<mark class="source-text-highlight">${escapeHtml(str)}</mark>`
                  : escapeHtml(str)}
              />
            </Document>
          </div>
        ) : null}

        {pdf && pageCount > 0 ? (
          <footer className="source-preview-pagination">
            <button className="secondary-button compact" type="button" disabled={pageNumber <= 1} onClick={() => void showPage(pageNumber - 1)}>Previous page</button>
            <span>Page {pageNumber} of {pageCount}</span>
            <button className="secondary-button compact" type="button" disabled={pageNumber >= pageCount} onClick={() => void showPage(pageNumber + 1)}>Next page</button>
          </footer>
        ) : null}
      </div>
    </dialog>,
    document.body,
  );
}
