# Invoice Batch Processing

Use this for large invoice runs, for example 805 PDFs. It uses the same extraction logic as the analyzer API, but writes the CSV after each file so the job can be resumed if it stops.

## Folder Setup

1. Put the invoice PDF files into the existing `input/` folder.
2. Copy `.env.example` to a new file named `.env`.
3. Put the real Azure OpenAI values into `.env`.

Do not share the `.env` file publicly because it contains secrets.

## Install Once

From the repository folder, run:

```bash
pip install -r requirements.txt
```

If scanned PDFs need OCR, Tesseract OCR must also be installed on the computer.

## Run The Batch

From the repository folder, run:

```bash
python scripts/process_invoices_to_csv.py
```

Default behavior:

- Reads PDFs from `input/`.
- Searches subfolders too.
- Writes `invoice_results_table.csv` in the repository folder.
- Uses `;` as the CSV separator, matching the analyzer CSV export.
- Skips files already present in the CSV, so the command can be run again to resume.

## Useful Commands

Run with a custom input folder:

```bash
python scripts/process_invoices_to_csv.py --input-dir "C:\path\to\invoices"
```

Run with a custom output CSV:

```bash
python scripts/process_invoices_to_csv.py --output "C:\path\to\invoice_results.csv"
```

Retry files that previously failed:

```bash
python scripts/process_invoices_to_csv.py --retry-failed
```

Start from scratch and do not skip existing CSV entries:

```bash
python scripts/process_invoices_to_csv.py --no-resume --output invoice_results_table_new.csv
```

Add a small delay after each file to reduce Azure rate-limit pressure:

```bash
python scripts/process_invoices_to_csv.py --delay-seconds 1
```

## Sharing With Colleagues

For non-technical colleagues, the best option is usually a small packaged application or a prepared folder with a one-click runner. Sharing the whole repository works, but they still need Python, dependencies, Tesseract for scanned PDFs, and Azure OpenAI credentials configured correctly.

Recommended options:

1. Best for non-technical users: package this as a simple desktop or internal web app with the credentials handled centrally.
2. Acceptable for semi-technical users: share the repository as a ZIP with this guide, a prepared `.env` process, and clear install steps.
3. Avoid: sending only the script, because it depends on the existing `src/` code and `requirements.txt`.
