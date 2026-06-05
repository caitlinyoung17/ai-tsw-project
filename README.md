# University of Texas at Austin Libraries
## Texas ScholarWorks Metadata Project

### Project Overview
This code is part of an ongoing project focused on cataloging the University of Texas at Austin's collection of Southern Architect and Building News journals using Large Language Models (LLMs) to assist in the first-pass metadata creation process. Our research project evaluates the effectiveness of LLMs in enhancing cataloging workflows. In the larger project, we considered both API and web-based interaction with Large Language Models for metadata creation. We presented on this topic at TCDL 2025, and look forward to presenting our work again this year at the DCMI Annual Conference and the ASIS&T Annual Meeting.
 !!!!! REWRITE !!!!

### Project Goals
Initially, we tested Large Language Models' ability to contribute effectively in the following metadata tasks: OCR creation/improvement, summarization, named entity extraction, and subject heading assignment. The current implementation has evolved into a comprehensive 5-step workflow that integrates controlled vocabularies and produces scholarly-quality archival metadata.
!!!!! REWRITE !!!!

### Workflow Architecture

The processing pipeline consists of five integrated modules that takes University of Texas Dissertations and creates comprehensive archival metadata:

#### Step 1: PDF to TXT
**Scripts**: `pdf_to_txt.py`
- !!! explain what happens here !!!

#### Step 1: Initial Metadata Extraction
**Scripts**: `tsw_initial_metadata_extraction.py`
- Processes OCR text files or image files using OpenAI models
- Generates comprehensive metadata including text transcriptions, content summaries, visual descriptions (image script only), topic search terms, and initial entity extraction
- Supports both individual and batch processing with automatic cost optimization
- Creates Excel workbooks with thumbnails and detailed analysis sheets

#### Step 1.5: Batch Cleanup (Automatic)
**Script**: `southern_architect_step1.5.py`
- Automatically detects and fixes failed batch processing items from Step 1
- Runs individual reprocessing with retry logic for any problematic entries
- Ensures clean, complete metadata before downstream processing

#### Step 2: Multi-Vocabulary Enhancement
**Script**: `tsw_vocab_querying.py`
- Uses topics and geographic entities to search for controlled vocabulary terms
- Queries multiple authoritative sources:
  - **LCSH** (Library of Congress Subject Headings)
  - **FAST** (Faceted Application of Subject Terminology)
  - **Getty AAT** (Art & Architecture Thesaurus)
  - **Getty TGN** (Thesaurus of Geographic Names)
- Caching and comprehensive API logging
- Limited to 3 terms per vocabulary per topic to limit text size of inputs in the next step

#### Step 3: AI-Powered Vocabulary Selection
**Script**: `tsw_terms_selection.py`
- Uses OpenAI models to select the most appropriate terms from Step 2 results
- Prompt applies scholarly criteria for historical accuracy and geographical relevance
- Generates page-level metadata files that include OCR
- Creates issue content indexes with comprehensive metadata
- Produces vocabulary mapping report with selection indicators

#### Step 5: Entity Authority File Creation
**Script**: `southern_architect_step5.py`
- Builds comprehensive authority record for named entities
- Classifies entities by type (Person, Firm, Building, Organization, etc.)
- Tracks frequency, temporal distribution, and variant forms
- Creates both structured JSON and human-readable authority files

## Installation & Setup

### Prerequisites
- Python 3.8 or newer
- OpenAI API key
- Required Python packages (see requirements.txt)

### Environment Setup
```bash
# Clone repository
git clone [southern-architect-git-url]

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-api-key-here"
```

### Directory Structure - this must be aligned
```
southern_architect/
├── southern_architect_run.py
├── southern_architect_step1_text.py
├── southern_architect_step1_image.py
├── [other script files...]
├── image_folders/
│   └── 2_issues/                    # Your collection folder, named as you choose
│       ├── 1917-05-39/            # Issue folder (date format)
│       │   ├── page01.jpg          # Numbered page files (.txt, .jpg, .png)
│       │   ├── page02.jpg         # For text workflow, include 'cover' in file name for issue covers (e.g. page01-cover.txt)      
│       │   └── ...                 
│       ├── 1924-10-50/
│       │   ├── page01.jpg
│       │   └── ...
│       └── ...
└── output_folders/                 # This directory is auto-generated as are all the subfolders
└── SABN_Metadata_Created_2025-01-15_Time_14-30-22/
```

## Usage

### Complete Workflow (Recommended)
```bash
# Interactive mode - this will prompt for workflow type
python southern_architect_run.py

# Specify workflow type
python southern_architect_run.py --workflow text
python southern_architect_run.py --workflow image # best results

```

## Cost Management

**Note:** See `model_pricing.py` - Updated as of July 2025

### Cost Optimization Strategies
1. **Batch Processing**: Use for 50% cost reduction on large collections
2. **Model Selection**: Use GPT-4o-mini for cost-sensitive operations
3. **Input Format**: Text processing typically more cost-effective than images, though image processing may produce better quality outputs

## Output Files

### Excel Workbooks
- Comprehensive spreadsheets with analysis, raw responses, and issues tracking
- Image thumbnails for visual verification
- Selected vocabulary terms with sources and URIs

### JSON Data
- Structured metadata for programmatic access
- Complete API responses and processing metadata
- Issue synthesis and entity authority records

### Text Reports
- Human-readable vocabulary mapping report
- Dissertation metadata
- Entity authority report
- Processing logs and API usage summaries

## Features

### Batch Processing
- Automatic batch API usage for large collections
- Progress monitoring and estimated completion times
- Comprehensive error handling and retry logic
- Batch processing could potentially take up to 24 hours for *each step* where it is used.  

### Geographic Entity Processing
- Standardized geographic name formatting
- Separate vocabulary lookup for FAST geographic terms

### Content Warnings
- Automatic detection of potentially sensitive content
- Historical context preservation while flagging concerns

### Verified Subject Headings
- Tool-based vocabulary integration: Subject headings are sourced directly from authoritative controlled vocabularies (LCSH, FAST, Getty AAT, Getty TGN) rather than generated by the LLM
- Quality assurance through structured lookup: The LLM selects from pre-verified terms returned by vocabulary APIs, ensuring all subject headings are legitimate and include proper URIs
- Multi-vocabulary coverage: Combines complementary controlled vocabularies to provide comprehensive subject access across general topics, architectural terminology, and geographic entities
- Scholarly selection criteria: AI applies consistent evaluation standards for historical accuracy, geographical relevance, and archival appropriateness when choosing from verified vocabulary options

## Privacy & Data Security

### Quality Assurance
- In all AI assisted workflows, we recommend: comprehensive oversight *and* complete transparency about the process of metadata creation
- Comprehensive logging is in place so that any issues that arise may be tracked

### API Usage
- **OpenAI**: Assurances that OpenAI does not use API data for training: [OpenAI Enterprise Privacy](https://openai.com/enterprise-privacy/)

## Team
This project represents ongoing research into AI applications for archival metadata. Contributions are welcome! 
For questions about implementation or research collaboration, please reach out via email. 

- Hannah Moutran: Library Specialist, AI Implementation: [hlm2454@my.utexas.edu](mailto:hlm2454@my.utexas.edu)
- Devon Murphy, Metadata Analyst: [devon.murphy@austin.utexas.edu​](mailto:devon.murphy@austin.utexas.edu​)
- Karina Sanchez, Scholars Lab Librarian: [karinasanchez@austin.utexas.edu](mailto:karinasanchez@austin.utexas.edu)
- Katie Pierce Meyer, Head of Architectural Collections: [katiepiercemeyer@austin.utexas.edu](mailto:katiepiercemeyer@austin.utexas.edu)
- Caitlin Young, Scholars Lab GRA

## Development

This repository was built with the assistance of [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's AI coding assistant in VS Code.

For questions about this repository, please contact [Hannah Moutran](mailto:hlm2454@my.utexas.edu)

#### Special thanks to Aaron Choate, Director of Research & Strategy at UT Libraries
---

*This pipeline demonstrates the practical application of Large Language Models for archival metadata creation, using controlled vocabularies as tools whereby LLMs can produce high quality first-pass metadata appropriate for academic institutions.*