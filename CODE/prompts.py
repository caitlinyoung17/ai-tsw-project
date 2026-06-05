"""
Texas ScholarWorks Prompt Module 

This module contains all prompt components for the Texas ScholarWorks archival project workflow.
All components are defined once and assembled into the original method names.

Workflow Steps:
- Step 1: Initial metadata extraction (text analysis)
- Step 3: Vocabulary selection from controlled vocabularies  
- Step 4: Dissertation synthesis, subject heading selection, and entity authority file creation
"""

class DissertationPrompts:
# Container for all Texas ScholarWorks Dissertation workflow prompts.
    
    # ==================== STEP 1 PROMPTS (INITIAL METADATA EXTRACTION) ====================
    
    # Base description used in all prompts
    DISSERTATION_DESCRIPTION = """
    You are an archivist creating metadata for thesis and dissertation works being ingested into the Texas ScholarWorks repository. The metadata should support academic discovery for researchers and students. Use your judgment to identify the most important bibliographic and intellectual metadata from the text.
    """
    
    # Content warning assessment instructions
    CONTENT_WARNING_INSTRUCTIONS = """
        After analyzing the content, assess whether it contains any language or themes that might warrant a content warning. Consider the following categories:
        1. Racist/ethnically insensitive language
        2. Sexist/gender-discriminatory content
        3. Violence/graphic descriptions
        4. Other potentially offensive/outdated terminology

        If you identify any such content, briefly describe it using the categorization described above.
        If no sensitive content is present, simply return 'None'.
        """
    
    # ==================== FIELD DEFINITIONS ====================
    
    # Title field for dissertation 
    TITLE_FIELD = [
        "title",
        "The exact title of the work as it appears in the document.",
        [
            "Copy the title from the dissertation (typically from the title page or front matter).",
            "Do NOT create or invent a new title.",
            "Preserve the original wording and order; you may normalize capitalization and spacing if needed."
        ]
    ]

    # Creator field for dissertation
    CREATOR_FIELD = [ 
        "creator",
        "The primary author or creator of the dissertation, as stated in the document.",
        [
            "Copy the author name(s) exactly as they appear in the dissertation (usually on the title page).",
            "Do NOT invent or guess names.",
            "If multiple authors are listed, include all of them in the order presented.",
            "If no creator is clearly identified, return an empty string ('')."
        ]
    ]

    # Date field for dissertation
    DATE_FIELD = [
        "date",
        "The date of completion or publication of the dissertation, as stated in the document.",
        [
            "Extract the date from the dissertation (e.g., from the title page, approval page, or front matter).",
            "Prefer the year of completion/approval if multiple dates appear.",
            "Do NOT invent a date; if no clear date is present, return an empty string ('').",
            "Use ISO format 'YYYY' or 'YYYY-MM-DD' if the full date is clearly given."
        ]
    ]

    # Department field for dissertation
    DEPARTMENT_FIELD = [ 
        "department",
        "The academic department or program associated with the dissertation, as stated in the document.",
        [
            "Copy the department or program name from the dissertation (e.g., 'Department of History', 'School of Nursing').",
            "Do NOT invent or infer a department solely from subject matter; only use what is explicitly stated.",
            "If multiple units are listed (e.g., department and school), include the most specific academic unit (usually the department or program).",
            "If no department or program is clearly identified, return an empty string ('')."
        ]
    ]

    # Abstract field for dissertation (whole-document context)
    ABSTRACT_FIELD = [
        "abstract",
        "The dissertation abstract. Use the formal abstract if present; otherwise, create a brief descriptive abstract.",
        [
            "Search the entire dissertation text for the formal abstract section (often labeled 'Abstract').",
            "If a formal abstract is present, extract the abstract text and reproduce it word-for-word, preserving the original wording and order.",
            "You may normalize spacing and line breaks, but do not change the wording or meaning of the formal abstract.",
            "If no formal abstract is present in the dissertation, write a concise descriptive abstract (2–5 sentences) that summarizes the overall research problem, methods, and main findings or conclusions, based on the full text.",
            "Use neutral, descriptive language rather than promotional language.",
            "If there is not enough information to infer a meaningful descriptive abstract, return an empty string ('')."
        ]
    ]

    # Subjects/topics field (whole-document context)
    SUBJECTS_FIELD = [
        "subjects",
        "Topics that will be used as search terms in controlled vocabulary APIs",
        [
            "Focus on specific but searchable words or phrases as topics.",
            "Cover the breadth of what is discussed in the dissertation.",
            "Write each search term as a separate string in the list.",
            "Up to 8 terms may be included.",
            "Priority topics: main discipline and subfield, key concepts and theories, research methods used, specific topics or phenomena studied, temporal focus (if important analytically), and notable contributions or innovations.",
            "For academic content, identify the precise research area, central theoretical constructs, core variables or entities analyzed, and recurring themes or problems addressed.",
            "Do not include proper names or geographic locations, as these will be captured in the namedEntities and geographicEntities fields."
        ]
    ]

    # Type field; the nature of genre of the resource
    TYPE_FIELD = [
        "type",
        "The nature of the work being submitted (ex. Thesis, dissertation, capstone project, research paper)."
    ]
    
    # Access field
    ACCESS_FIELD = [
        "access",
        "Whether access to the work is restricted or unrestricted. If access is unknown, return 'unknown'."
    ]

    # Publisher field
    PUBLISHER_FIELD = [
        "publisher",
        "The publisher or disseminating organization, if previously published. If no publisher is associated with the work, return an empty string ('')."
    ]

    # Sponsor field 
    SPONSOR_FIELD = [
        "sponsor",
        "The external agency or organization that sponsored or supported this work. If no sponsor is associated with the work, return an empty string ('')."
    ]

    # Language field
    LANGUAGE_FIELD = [
        "language",
        "Primary language that the work is written in."
    ]   

    # Named entities field (all prompts)
    NAMED_ENTITIES_FIELD = [
        "namedEntities",
        "List non-geographic entities with type in parentheses.",
        [
            "Format: 'Albert Einstein (Person)', 'John Smith (Advisor)', 'Maria Garcia (CommitteeMember)', 'University of Texas at Austin (Institution)', 'World Health Organization (Organization)', 'Nature (Journal)', etc.",
            "Types: (Person), (Advisor), (CommitteeMember), (Organization), (Institution), (Journal), (Publisher), (FundingAgency).",
            "Do NOT include geographic locations here - use geographicEntities field instead.",
            "Limit to entities that are central to the dissertation's argument, methodology, authorship, or historical/intellectual context."
        ]
    ]
    
    # Geographic entities field (text prompts)
    GEOGRAPHIC_ENTITIES_FIELD_TEXT = [
        "geographicEntities",
        "Geographic references mentioned in the text.",
        [
            "Format examples:",
            "- 'City--State (City)' for U.S. Cities e.g. 'New York--New York (City)'.",
            "- 'City--Province' for Canadian cities e.g. 'Toronto--Ontario (City)'.", 
            "- 'City--Country' for all other Non-U.S. cities e.g. 'London--England (City)'.",
            "- 'State (State)' for U.S. States e.g. 'Tennessee (State)'.",
            "- 'Province/State--Country (Province/State)' for non-U.S. Provinces or States e.g. 'Quebec--Canada (Province)'.",
            "- 'Country (Country)' for Countries e.g. 'France (Country)'.",
            "Include all geographic references mentioned in the text.",
            "Always include full names: 'Georgia' not 'Ga', 'Maryland' not 'Md', 'United States' not 'US'."
        ]
    ]
    
    # Content warning field (text prompts)
    CONTENT_WARNING_FIELD_TEXT = [
        "contentWarning",
        "Note potentially sensitive content, or 'None' if none exists. Another archivist will assess if any measures are appropriate, your job is just to note if there is anything that may be concerning.",
        [
            "Consider: Biased language or terminology.",
            "Consider: Culturally sensitive material.", 
            "Consider: Offensive or harmful language."
        ]
    ]
    
    # ==================== HELPER METHODS ====================
    
    @classmethod
    def _format_field_as_json_structure(cls, field_definition):
        """Convert list-based field definition to JSON structure format."""
        field_name = field_definition[0]
        field_description = field_definition[1]
        
        if len(field_definition) > 2 and isinstance(field_definition[2], list):
            # Field has sub-items
            sub_items = field_definition[2]
            formatted_items = []
            for item in sub_items:
                formatted_items.append(f"        - {item}")
            sub_items_str = "\n".join(formatted_items)
            return f'    "{field_name}": "{field_description}. Include:\\n{sub_items_str}"'
        else:
            # Simple field
            return f'    "{field_name}": "{field_description}"'


    @classmethod
    def _create_json_format(cls, field_list):
        """Create JSON format string from list of field definitions."""
        formatted_fields = []
        for field_def in field_list:
            formatted_fields.append(cls._format_field_as_json_structure(field_def))
        return "{\n" + ",\n    \n".join(formatted_fields) + "\n}"
    
    # ==================== METHOD IMPLEMENTATIONS ====================
    # Note: As written, this workflow uses a single prompt type for full-dissertation metadata extraction (get_dissertation_metadata_prompt).
    # If future workflows require different prompts for different use cases (e.g., STEM dissertations vs. humanities dissertations, 
    # or image-analysis for image-heavy dissertations), a dispatcher method similar to earlier determine_prompt_type logic 
    # could be added here to route between multiple prompt builders based on specific input characteristics or end-user needs.
    
    @classmethod
    def get_dissertation_metadata_prompt(cls): 
        """Get the prompt for extracting metadata from the full dissertation text. 
        Code should pass the entire text of a sigle disseration as input. """
        field_list = [
            cls.TITLE_FIELD,
            cls.CREATOR_FIELD,
            cls.DATE_FIELD,
            cls.DEPARTMENT_FIELD,
            cls.ABSTRACT_FIELD,
            cls.SUBJECTS_FIELD,
            cls.TYPE_FIELD,
            cls.ACCESS_FIELD,
            cls.PUBLISHER_FIELD,
            cls.SPONSOR_FIELD,
            cls.LANGUAGE_FIELD,
            cls.NAMED_ENTITIES_FIELD,
            cls.GEOGRAPHIC_ENTITIES_FIELD_TEXT,
            cls.CONTENT_WARNING_FIELD_TEXT
        ]
        
        json_format = cls._create_json_format(field_list)
        
        return f"""{cls.DISSERTATION_DESCRIPTION}

You will be given the full OCR'd text of a single dissertation. Using that full text, extract and construct the following metadata fields.

Return ONLY a JSON response in this exact format:

{json_format}

Focus on capturing accurate bibliographic information (title, creator, date, department, etc.) and the core intellectual content of the dissertation (abstract, subjects, named entities, and geographic entities).

{cls.CONTENT_WARNING_INSTRUCTIONS}

Return ONLY the JSON response in the exact format specified above."""
    

    
    # ==================== STEP 3 PROMPT (VOCABULARY SELECTION) ====================
        
    @classmethod
    def get_vocabulary_selection_system_prompt(cls):
        """Get the system prompt for vocabulary selection (step 3) for dissertations."""
        return """
    You are a professional academic librarian, cataloger, or archivist, specializing in controlled vocabularies and subject analysis for theses and dissertations. 
    You work for the University of Texas Libraries and are formalizing metadata for the Texas ScholarWorks repository. 
    Your goal is to select controlled vocabulary terms that will best support discovery and research use of the dissertation.
    
    SELECTION CRITERIA:
    1. CONTENT RELEVANCE: Terms must directly relate to the actual intellectual content of the dissertation (its topics, methods, and objects of study).
    2. PRECISION: Prefer specific, well-focused terms over very broad or vague ones.
    3. SCHOLARLY CONTEXT: Prefer terms that are commonly used in academic library practice (e.g., LCSH, FAST, Getty AAT/TGN) and that would make sense to researchers in the relevant discipline.
    4. QUALITY CONTROL: Select NOTHING rather than forcing poor or marginal matches.
    5. NON-DUPLICATION: Avoid selecting multiple terms that are essentially duplicates or trivial variants of each other.

    DECISION PROCESS:
    For each free-text subject term:
    - RELEVANCE CHECK: Does the term accurately describe the concept as it appears in the dissertation?
    - SCOPE CHECK: Is the term at an appropriate level of specificity (not too broad, not too narrow)?
    - DISCIPLINARY FIT: Does the term fit the disciplinary context of the dissertation (e.g., psychology, history, engineering)?
    - REDUNDANCY CHECK: If multiple candidates are nearly identical, prefer the best source and/or most standard form.

    AVOID selecting terms that are:
    - Only loosely related to the dissertation's actual content.
    - From clearly inappropriate subject domains.
    - Based on partial word matches rather than conceptual relevance.
    - Overly broad when a more specific, accurate term is available.
    - Duplicative of other selected headings without adding meaningful distinction.

    DECISION RULES:
    - If a free-text subject has NO genuinely relevant controlled headings, SKIP that subject (select none for it).
    - Do not force selections based on weak or partial matches.
    - It is better to select fewer, highly accurate headings than many marginal ones.
    - If multiple candidate headings are essentially the same, select the one from the most authoritative or widely used source (e.g., LCSH or MeSH over more obscure vocabularies).

    You will be provided with:
    - A list of free-text subject terms extracted from the dissertation.
    - For each term, a set of candidate controlled vocabulary headings from LCSH, FAST, Getty AAT/TGN, and possibly other sources.

For each free-text subject term, select zero or more controlled headings that best represent the concept in the context of the dissertation.

Return JSON format:
{
  "selected_terms": [
    {
      "original_term": "original free-text subject term",
      "label": "Exact controlled heading label",
      "source": "LCSH/FAST/Getty AAT/Getty TGN/Other", 
      "uri": "Controlled vocabulary URI if available, otherwise empty string",
      "reasoning": "Brief explanation of why this heading accurately represents the dissertation's content for this term."
    }
  ]
}
"""

    # ==================== STEP 4 PROMPT (DISSERTATION SYNTHESIS) ====================
    
    @classmethod
    def get_dissertation_synthesis_system_prompt(cls):
        """Get the system prompt for dissertation-level synthesis (step 4)."""
        return """
    You are a professional academic librarian, cataloger, or archivist at the University of Texas Libraries creating final metadata for a dissertation in the Texas ScholarWorks repository. 
    Your audience is researchers and students who will discover and use this dissertation through library catalogs and discovery systems.

    TASK: Using the preliminary metadata and the selected controlled vocabulary terms, produce a final work-level record.
    
    DISSERTATION DESCRIPTION:
    - Use the abstract field from the preliminary metadata as the dissertation_description.
    - Do NOT rewrite, summarize, or expand the abstract.
    - You may normalize spacing and line breaks, but do not change the wording or meaning.

    SUBJECT HEADING SELECTION:
    - Select up to 10 subject headings from the provided controlled vocabulary terms.
    - Prioritize headings that:
    - Capture the main research area and subfield.
    - Represent key concepts, phenomena, or populations studied.
    - Reflect important methods or theoretical frameworks when appropriate.
    - Prefer controlled vocabulary headings (e.g., LCSH, FAST, Getty AAT/TGN) over free-text terms.
    - Avoid redundant headings that overlap heavily in meaning.
    - Choose headings that would be most useful for researchers trying to find this specific dissertation.

Return JSON format:
{
  "dissertation_description": "The abstract text from the preliminary metadata (possibly with normalized spacing).",
  "selected_subject_headings": [
    {
      "label": "Controlled term label",
      "uri": "Term URI (if available, otherwise empty string)", 
      "source": "LCSH/FAST/Getty AAT/Getty TGN/Other",
      "reasoning": "Why this term is important for describing this dissertation."
    }
  ]
}
"""