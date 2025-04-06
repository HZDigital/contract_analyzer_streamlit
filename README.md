# Contract Analyzer

A Streamlit-based application for analyzing contract documents using AI and OCR technologies.

## Overview

This application helps legal professionals and business users analyze contract documents by:

- Extracting text from PDF documents (using both native extraction and OCR when needed)
- Analyzing contracts with Azure OpenAI's language models
- Identifying key clauses, risks, and important contract information
- Generating clear summary reports

## Features

- **Document Upload**: Support for single or multiple PDF contract uploads
- **Text Extraction**:
  - Primary method: Native PDF text extraction using PyMuPDF
  - Fallback method: OCR using Tesseract and pdf2image for scanned documents
- **Contract Analysis**:
  - Contract summaries
  - Extraction of key clauses (Termination, Confidentiality, Payment terms, etc.)
  - Identification of unusual or risky contract language
  - Contract date detection
- **Results Storage**: Analysis results saved to text files for future reference

## Installation

### Standard Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/HZDigital/contract_analyzer_streamlit.git
   cd contract_analyzer_streamlit
   ```

2. Install required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Install system dependencies:

   - Tesseract OCR
   - Poppler utils

4. Set environment variables:

   ```bash
   export AZURE_OPENAI_API_KEY=your-api-key
   export AZURE_OPENAI_ENDPOINT=your-azure-endpoint
   ```

5. Run the application:
   ```bash
   streamlit run src/contract_analyzer_app.py
   ```

### Docker Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd contract_analyzer_streamlit
   ```

2. Update environment variables in `docker-compose.yml`

3. Build and run using Docker Compose:

   ```bash
   docker-compose up
   ```

4. Access the application at http://localhost:8501

## Usage

1. Open the application in a web browser
2. Upload one or more PDF contracts using the file uploader
3. For each document:
   - The app extracts text (using OCR if necessary)
   - Adjust the text length slider if needed
   - The app analyzes the contract and displays results
4. Review the analysis which includes:
   - Contract summary
   - Key clauses with direct quotes
   - Identified risks or unusual language
   - Contract dates

## Configuration

### Environment Variables

- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL

### Model Configuration

The application uses the `gpt-4o-mini` deployment by default. This can be changed in the code if needed.

## Project Structure

```
contract_analyzer_streamlit/
├── src/
│   └── contract_analyzer_app.py  # Main application code
├── results/                      # Analysis results storage
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker configuration
├── docker-compose.yml            # Docker Compose configuration
└── README.md                     # This file
```

## Notes

- Results are stored in the `results` directory
- When using Docker, the results directory is mounted as a volume for persistence
