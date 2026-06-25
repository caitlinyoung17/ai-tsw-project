# University of Texas at Austin Libraries
## Texas ScholarWorks Metadata Project

### Project Overview
This code is part of a set of ongoing projects focused on cataloging the University of Texas at Austin's collections. This research project focuses on evaluating the use of Large Language Models (LLMS) to enhance cataloging workflows. in the first-pass metadata creation process for cataloging digitized dissertations. In previous projects, we've explored the effectiveness of LLMs in enhancing cataloging workflows for architectural archival materials, including architectural drawings and the collection of Southern Architect and Building News journals. We presented on this topic at TCDL 2025, and look forward to presenting our work again this year at the DCMI Annual Conference and the ASIS&T Annual Meeting.

### Project Goals

This project explores how effictive Large Language Models (LLMs) can be for archival metadata creation for Texas ScholarWorks dissertations and theses for key tasks including text extraction, full-text analysis, subject/keyword assignment, controlled vocabularly selection, and named entity creation.

The current implementation is a multi-step workflow that integrates external controlled vocabularies (e.g., LCSH, FAST, Getty AAT/TGN) and produces metadata scholarly-quality suitable for discovery and cataloging. 

### Workflow Architecture

The processing pipeline consists of four integrated modules that takes University of Texas Dissertations and creates comprehensive archival metadata:
Workflow at a Glance:
1. Step 1 – Initial Metadata: full-text → title, abstract, subjects, entities.
2. Step 2 – Vocab Querying: subjects/entities → candidate LCSH/FAST/Getty headings.
3. Step 3 – Term Selection: candidate headings → final controlled terms.
4. Step 4 - Entity Authority: namedEntities → local authority file.

#### PDF/Text Input Handling
**Scripts**: `pdf_to_txt.py`
This module provides two related utilities for handling dissertation input:
- `collect_dissertation_files(input_folder)` (used by the pipeline):
  - Reads `.txt` files or extracts text directly from `.pdf` files using `pdfminer.six`.
  - Returns `(filename, file_path, content)` for each dissertation, which Step 1 uses as input.
  - This is the function called by `tsw_initial_metadata_extraction.py`.

- `convert_pdfs_to_txt(input_folder, output_folder=None)` (optional helper):
  - Converts PDFs in `input_folder` to `.txt` files for debugging or manual inspection.
  - Not required for the pipeline; primarily for users who are either testing the code, or wanting to inspect the extracted text.

---

#### Step 1: Initial Metadata Extraction
**Scripts**: `tsw_initial_metadata_extraction.py`
This step performs work-level metadata extraction for each dissertation. It:
- Reads full text for each dissertation via `collect_dissertation_files`, either from `.txt` files or directly from PDFs using `extract_text`.
- Uses `DissertationPrompts.get_dissertation_metadata_prompt()` with OpenAI models to extract core descriptive and bibliographic metadata, including:
  - Title, creator, date, department, type, access, publisher, sponsor, language
  - Abstract (copied verbatim_ if present, or generated if missing_)
  - Subjects (free-text topics suitable for controlled vocabularies)
  - Named entities and geographic entities
  - Content warnings (if applicable)
- Supports both individual and batch processing via the `BatchProcessor`, with basic cost and token usage tracking.
- Produces a pair of outputs per run:
  - `text_workflow.xlsx` — an Analysis sheet summarizing metadata for each dissertation.
  - `text_workflow.json` — a structured JSON file containing the full `analysis` block for each dissertation, plus API stats.

#### Step 1.5: Batch Cleanup (Automatic)
**Script**: **Scripts**: `tsw_s1.5_batchCleanup.py`
NOTE!! This part is still being worked on
- Automatically detects and fixes failed batch processing items from Step 1
- Runs individual reprocessing with retry logic for any problematic entries
- Ensures clean, complete metadata before downstream processing

#### Step 2: Multi-Vocabulary Enhancement
**Script**: `tsw_vocab_querying.py`
This step enriches the free-text subjects and geographic entities from Step 1 with candidate controlled vocabulary terms. It:
- Reads `text_workflow.json` and extracts:
  - `analysis['subjects']` — free-text subjects for each dissertation.
  - `analysis['geographic_entities']` — normalized geographic references.
- Queries multiple authoritative sources to find candidate controlled headings:
  - **LCSH** (Library of Congress Subject Headings)
  - **FAST** (Faceted Application of Subject Terminology)
  - **Getty AAT** (Art & Architecture Thesaurus)
  - **Getty TGN** (Thesaurus of Geographic Names)
  - **FAST Geographic** (for geographic entities)
- Uses caching and comprehensive API logging via `APIStatsTracker`, including per-API request counts, success rates, and timing.
- Limits the number of candidate terms to keep downstream inputs manageable:
  - Up to **3 terms per vocabulary per subject** (LCSH, FAST, Getty AAT/TGN).
  - Up to **1 term per geographic entity** (FAST Geographic).
- Writes the results back into:
  - `text_workflow.json` — under `analysis['vocabulary_search_results']` and `analysis['geographic_vocabulary_search_results']`.
  - `text_workflow.xlsx` — adding “Subject Vocabulary Terms” and “Geographic Vocabulary Terms” columns on the Analysis sheet.
  - `vocabulary_mapping_report.txt` — a human-readable report summarizing vocab mappings and API usage.

#### Step 3: AI-Powered Vocabulary Selection
**Script**: `tsw_terms_selection.py`
This step uses a small OpenAI model to choose the best controlled vocabulary terms from the candidate headings generated in Step 2. It:
- Reads `text_workflow.json` and, for each dissertation with `analysis['vocabulary_search_results']`, builds prompts that include:
  - The dissertation’s title and abstract.
  - The free-text subjects from Step 1.
  - The candidate controlled terms per subject from Step 2 (LCSH, FAST, Getty AAT/TGN).
- Uses `DissertationPrompts.get_vocabulary_selection_system_prompt()` to apply scholarly criteria for relevance and precision, guiding the model to:
  - Select zero or more controlled headings per free-text subject.
  - Avoid weak or partial matches.
  - Prefer authoritative sources when multiple candidates are equivalent.
- Supports both batch and individual processing via `BatchProcessor`, with token usage and cost logging.
- Writes the selected terms back into the metadata:
  - `text_workflow.json` — under `analysis['final_selected_terms']` for each dissertation.
  - `text_workflow.xlsx` — updating the “Subject Vocabulary Terms” column to “Selected Subject Vocabulary Terms” containing only the chosen headings.
- Produces a `vocabulary_selection_report.txt` that summarizes, for each dissertation:
  - Free-text subjects.
  - Candidate controlled terms from Step 2.
  - The final selected controlled terms from Step 3.

#### Step 4: Entity Authority File Creation
**Script**: `entity_authority.py`
This step builds a local authority file for named entities extracted from dissertation metadata. It:
- Reads `text_workflow.json` and aggregates `analysis['namedEntities']` across all processed dissertations.
- Parses typed entity strings (e.g., `Jane Doe (Advisor)`, `University of Texas at Austin (Institution)`) to extract:
  - A normalized entity name.
  - An inferred or explicit entity type (Person, Advisor, CommitteeMember, Institution, Organization, etc.).
- Uses fuzzy matching (`rapidfuzz`) to:
  - Cluster semantically similar entity names (e.g., `UT Austin` vs. `University of Texas at Austin`).
  - Choose canonical forms and record variant spellings.
- Tracks basic statistics for each entity cluster:
  - Frequency (number of dissertations in which the entity appears).
  - Original forms and clustered variants.
  - Example contexts (title/abstract snippets).
- Produces two outputs:
  - `dissertation_entity_authority.json` — a structured authority file with metadata, entity records, and summary statistics.
  - `entity_authority_report.txt` — a human-readable report summarizing entity types, clustering results, and examples.

## Installation & Setup

### Prerequisites
- Python 3.8 or newer
- An OpenAI API key with access to the models used in this project
- Required Python packages (see `requirements.txt`), including:
  - `openai`
  - `pdfminer.six`
  - `rapidfuzz` (for entity authority fuzzy matching)
  - `openpyxl`
  - Others listed in `requirements.txt`

### Environment Setup
```bash
# Clone repository
git clone <ai-tsw-project>
cd <ai-tsw-project>

# (Optional but recommended) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# or
.\.venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-api-key-here"        # Mac/Linux
# or
set OPENAI_API_KEY="your-api-key-here"          # Windows (cmd)
$Env:OPENAI_API_KEY="your-api-key-here"         # Windows (PowerShell)
```

### Directory Structure
```text
<ai-tsw-project>/
├── CODE/
│   ├── pdf_to_txt.py                     # Input handling (PDF/Text) utilities
│   ├── tsw_s1_initialMetadataExtraction.py  # Step 1: Initial metadata extraction
│   ├── tsw_s2-vocabQuerying.py           # Step 2: Multi-vocabulary enhancement
│   ├── tsw_s3_termsSelection.py            # Step 3: AI-powered vocabulary selection
│   ├── tsw_s4_entityAuthority.py           # Step 4: Entity authority file creation 
│   ├── prompts.py                        # DissertationPrompts and other prompt definitions
│   ├── shared_utilities.py               # JSON parsing, entity normalization, and helper classes
│   ├── batch_processor.py                # Batch API submission and result handling
│   ├── model_pricing.py                  # Cost estimation helpers
│   ├── token_logging.py                  # Token usage logging utilities
│   └── [other support scripts...]
│
├── DigitizedDissertationTest/            # Example input folder with PDFs/.txt (for testing)
│   ├── MyDissertation.pdf
│   └── ...
│
├── output_folders/                       # Auto-generated by the scripts
│   ├── Dissertation_Metadata_Created_YYYY-MM-DD_Time_HH-MM-SS/
│   │   ├── metadata/
│   │   │   ├── collection_metadata/
│   │   │   │   ├── text_workflow.xlsx
│   │   │   │   ├── text_workflow.json
│   │   │   │   ├── vocabulary_mapping_report.txt          # Step 2 report
│   │   │   │   ├── vocabulary_selection_report.txt        # Step 3 report
│   │   │   │   ├── dissertation_entity_authority.json     # Step 4 JSON authority file
│   │   │   │   ├── entity_authority_report.txt            # Step 4 human-readable authority report
│   │   │   │   └── [other metadata files...]
│   │   │   └── ...
│   │   ├── logs/
│   │   │   ├── [token usage logs, vocab API logs, etc.]
│   │   └── ...
│   └── ...
│
├── requirements.txt
└── README.md
```

## Usage

### Complete Workflow (Recommended) - !Still working on this workflow!


## Cost Management

**Note:** See `model_pricing.py` - Updated as of July 2025

### Cost Optimization Strategies
1. **Batch Processing**: Use for 50% cost reduction on large collections
2. **Model Selection**: Use GPT-4o-mini for cost-sensitive operations
3. **Input Format**: Text processing typically more cost-effective than images, though image processing may produce better quality outputs

## Output Files

### Excel Workbooks
- Analysis spreadsheets summarizing work-level metadata for each dissertation (title, creator, date, department, abstract, subjects, entities, content warnings).
- Raw responses and issues tracking sheets for debugging and quality control.
- Vocabulary enhancement columns from Step 2 (Subject/Geographic Vocabulary Terms) and Step 3 (Selected Subject Vocabulary Terms with sources and URIs).

### JSON Data
- Structured metadata for programmatic access (`text_workflow.json`), including:
  - The full `analysis` block for each dissertation (bibliographic and descriptive fields).
  - Vocabulary search results (`vocabulary_search_results`, `geographic_vocabulary_search_results`) from Step 2.
  - Final selected controlled terms (`final_selected_terms`) from Step 3.
- API statistics and processing metadata (e.g., token usage, timing).
- Entity authority records (`dissertation_entity_authority.json`) capturing clustered named entities, types, variants, and summary statistics (Step 4).

### Text Reports
- Human-readable vocabulary mapping report from Step 2 (`vocabulary_mapping_report.txt`).
- Vocabulary selection report from Step 3 (`vocabulary_selection_report.txt`) summarizing subjects, candidate terms, and selected headings.
- Entity authority report (`entity_authority_report.txt`) with type breakdowns, clustering results, and examples (Step 4).
- Processing logs and API usage summaries in the `logs/` directory (token usage logs, vocab API logs, batch processing logs).

## Features

### Batch Processing
- Automatic batch API usage for large sets of dissertations (via `BatchProcessor`).
- Progress monitoring and estimated completion times for long-running jobs.
- Comprehensive error handling and retry logic for API calls.
- Batch processing windows of up to 24 hours per batch for steps that use the Batch API (initial metadata extraction, vocabulary querying, term selection).

### Geographic Entity Processing
- Standardized geographic name formatting (e.g., `City--State (City)`, `State (State)`, `Country (Country)`).
- Separate vocabulary lookup for FAST Geographic terms to provide controlled headings for places.
- Integration into both JSON and Excel outputs for consistent geographic access.

### Content Warnings
- Automatic detection of potentially sensitive content (biased language, culturally sensitive material, offensive terminology) based on configurable criteria.
- Preservation of historical and scholarly context while flagging content that may warrant review.
- Storage of content warning notes in the metadata so archivists can decide on appropriate handling.

### Verified Subject Headings
- Tool-based vocabulary integration: Subject headings are sourced directly from authoritative controlled vocabularies (LCSH, FAST, Getty AAT, Getty TGN) rather than generated free-form by the LLM.
- Quality assurance through structured lookup: The LLM selects from pre-verified terms returned by vocabulary APIs, ensuring all subject headings are legitimate and include proper URIs.
- Multi-vocabulary coverage: Combines complementary controlled vocabularies to provide comprehensive subject access across general topics, disciplinary concepts, and geographic entities.
- Scholarly selection criteria: AI applies consistent evaluation standards for relevance, precision, and archival appropriateness when choosing from verified vocabulary options, helping to align subject headings with research and cataloging best practices.

## Privacy & Data Security

### Quality Assurance
- In all AI assisted workflows, we recommend: comprehensive oversight *and* complete transparency about the process of metadata creation
- Comprehensive logging is in place so that any issues that arise may be tracked

### API Usage
- **OpenAI**: Assurances that OpenAI does not use API data for training: [OpenAI Enterprise Privacy](https://openai.com/enterprise-privacy/)

## Team
This project represents ongoing research into AI applications for archival metadata. Contributions are welcome! 
For questions about implementation or research collaboration, please reach out via email. 

- Luz Gonzalez, Scholars Lab GRA: [mg47333@my.utexas.edu](mailto:mg47333@my.utexas.edu)
- Hannah Moutran: Library Specialist, AI Implementation: [hlm2454@my.utexas.edu](mailto:hlm2454@my.utexas.edu)
- Devon Murphy, Metadata Analyst: [devon.murphy@austin.utexas.edu​](mailto:devon.murphy@austin.utexas.edu​)
- Karina Sanchez, Scholars Lab Librarian: [karinasanchez@austin.utexas.edu](mailto:karinasanchez@austin.utexas.edu)
- Katie Pierce Meyer, Head of Architectural Collections: [katiepiercemeyer@austin.utexas.edu](mailto:katiepiercemeyer@austin.utexas.edu)
- Caitlin Young, Scholars Lab GRA: [cy4633@my.utexas.edu](mailto:cy4633@my.utexas.edu)

## Development

This repository was adapted from the [Southern Architect AI Metadata Project](https://github.com/hannahmoutran/ai-architectural-journals-project) and built with the assistance of [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's AI coding assistant in VS Code, and [OpenAI](https://openai.com/index/gpt-5-1/)'s GPT-5.1.

For questions about this repository, please contact [Karina Sanchez](mailto:karinasanchez@austin.utexas.edu) or [Caitlin Young](mailto:cy4633@my.utexas.edu)

#### Special thanks to Aaron Choate, Director of Research & Strategy at UT Libraries
---

*This pipeline demonstrates the practical application of Large Language Models for archival metadata creation, using controlled vocabularies as tools whereby LLMs can produce high quality first-pass metadata appropriate for academic institutions.*