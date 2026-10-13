# University of Texas at Austin Libraries
## Texas ScholarWorks Metadata Project

### Project Overview
This src is part of a set of ongoing projects focused on cataloging the University of Texas at Austin's collections. This research project focuses on evaluating the use of Large Language Models (LLMS) to enhance cataloging workflows. in the first-pass metadata creation process for cataloging digitized dissertations. In previous projects, we've explored the effectiveness of LLMs in enhancing cataloging workflows for architectural archival materials, including architectural drawings and the collection of Southern Architect and Building News journals. We presented on this topic at TCDL 2025, and look forward to presenting our work again this year at the DCMI Annual Conference and the ASIS&T Annual Meeting.

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
**Module**: `src/processors/metadata_extraction/collector.py`
Reads `.txt` files, or extracts text from `.pdf` files with `pdfminer.six` (imported lazily, only when a PDF is actually read). Returns the filename, path and content of each dissertation for Step 1.

---

#### Step 1: Initial Metadata Extraction
**Package**: `src/processors/metadata_extraction`
This step performs work-level metadata extraction for each dissertation. It:
- Reads full text for each dissertation via the collector, either from `.txt` files or directly from PDFs.
- Uses the templates in `src/prompts` with OpenAI models to extract core descriptive and bibliographic metadata, including:
  - Title, creator, date, department, type, access, publisher, sponsor, language
  - Abstract (copied verbatim_ if present, or generated if missing_)
  - Subjects (free-text topics suitable for controlled vocabularies)
  - Named entities and geographic entities
  - Content warnings (if applicable)
- Supports individual and batch processing through the `LLMProvider` abstraction (`src/api`). Failed batches are reported as errors; they no longer silently fall back to individual paid calls. Chunking (see below) never uses provider-batch calls.
- Produces a pair of outputs per run:
  - `text_workflow.xlsx` — an Analysis sheet summarizing metadata for each dissertation.
  - `text_workflow.json` — a structured JSON file containing the full `analysis` block for each dissertation, plus API stats.

#### Step 1.5: Batch Cleanup
**Package**: `src/processors/batch_cleanup`
- Detects failed or incomplete items from a Step 1 batch run
- Reprocesses them individually with retry logic
- Ensures clean, complete metadata before downstream processing

#### Step 2: Multi-Vocabulary Enhancement
**Package**: `src/processors/vocab_enhancement` (HTTP clients in `src/api/vocab`)
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
**Package**: `src/processors/vocab_selection`
This step uses a small OpenAI model to choose the best controlled vocabulary terms from the candidate headings generated in Step 2. It:
- Reads `text_workflow.json` and, for each dissertation with `analysis['vocabulary_search_results']`, builds prompts that include:
  - The dissertation’s title and abstract.
  - The free-text subjects from Step 1.
  - The candidate controlled terms per subject from Step 2 (LCSH, FAST, Getty AAT/TGN).
- Uses `prompts.render_vocab_selection` to apply scholarly criteria for relevance and precision, guiding the model to:
  - Select zero or more controlled headings per free-text subject.
  - Avoid weak or partial matches.
  - Prefer authoritative sources when multiple candidates are equivalent.
- Supports batch and individual processing via the `LLMProvider`.
- Writes the selected terms back into the metadata:
  - `text_workflow.json` — under `analysis['final_selected_terms']` for each dissertation.
  - `text_workflow.xlsx` — updating the “Subject Vocabulary Terms” column to “Selected Subject Vocabulary Terms” containing only the chosen headings.
- Produces a `vocabulary_selection_report.txt` that summarizes, for each dissertation:
  - Free-text subjects.
  - Candidate controlled terms from Step 2.
  - The final selected controlled terms from Step 3.

#### Step 4: Entity Authority File Creation
**Package**: `src/processors/entity_authority`
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
- Python 3.9 or newer
- A Portkey API key configured for the OpenAI provider
- Packages in `requirements.txt` (`portkey-ai`, `openpyxl`, `rapidfuzz`, `requests`, `pdfminer.six`, `pytest`)

### Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PORTKEY_API_KEY="your-key"
export MODEL_NAME="gpt-4o-mini"      # default model for LLM steps
```

### Directory Structure
```text
src/
  utils/               run folder, workflow store, text/subject helpers, logging setup, exceptions
  api/llm_core/        LLMProvider ABC, requests/responses, pricing, usage logging
  api/open_ai/         Portkey-backed provider and batch client
  api/vocab/           LCSH / FAST / Getty HTTP clients with caching
  prompts/             prompt templates and call parameters
  metadata_standard/   per-run vocabulary candidates and term matching
  processors/          metadata_extraction (+ chunking), batch_cleanup, vocab_enhancement,
                       vocab_selection, entity_authority
  pipeline/            runner (python -m pipeline)
  southern_architect_run.py   out of scope, untouched
output_folders/  tested_documents/  test_documents/  (data; not deleted)
```

## Usage

Run from `src/`:
```bash
python -m pipeline --input <folder of .txt/.pdf> --steps 1,1.5,2,3,4
python -m pipeline --folder <existing run folder> --steps 2,3,4   # resume
python -m pipeline --help
```
Flags: `--model`, `--batch/--no-batch`, `--keep-going`, `--log-level`, `--output-root`.

### Chunking options
`--full-text-scan` (process the whole text in chunks), `--chunk-size N`, `--abstract-scan-max-chunks N`, `--max-chunks N`. Chunk calls are always individual (no provider batch).

### Tests
```bash
cd src && pytest
```
All tests use fakes (no network, no API keys).

### Known limitations
- Geographic terms are looked up in Step 2 but not sent to the LLM in Step 3.
- Steps 1 and 3 no longer write the legacy token/cost usage log.
- Pricing is a static table (July 2025 rates) in `api/open_ai/pricing.py`.
- `southern_architect_run.py` is a separate legacy workflow and was not refactored.

## Cost Management

**Note:** See `src/api/open_ai/pricing.py` - Updated as of July 2025

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
- Automatic batch API usage for large sets of dissertations (via the provider batch client).
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

This repository was adapted from the [Southern Architect AI Metadata Project](https://github.com/hannahmoutran/ai-architectural-journals-project) and built with the assistance of [Claude src](https://src.claude.com/docs/en/overview), Anthropic's AI coding assistant in VS src, and [OpenAI](https://openai.com/index/gpt-5-1/)'s GPT-5.1.

For questions about this repository, please contact [Karina Sanchez](mailto:karinasanchez@austin.utexas.edu) or [Caitlin Young](mailto:cy4633@my.utexas.edu)

#### Special thanks to Aaron Choate, Director of Research & Strategy at UT Libraries
---

*This pipeline demonstrates the practical application of Large Language Models for archival metadata creation, using controlled vocabularies as tools whereby LLMs can produce high quality first-pass metadata appropriate for academic institutions.*