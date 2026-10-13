"""Field definitions moved verbatim from the legacy DissertationPrompts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class FieldSpec:
    name: str
    description: str
    rules: Tuple[str, ...] = ()


DISSERTATION_DESCRIPTION = '\n    You are an archivist creating metadata for thesis and dissertation works being ingested into the Texas ScholarWorks repository. \n    The metadata should support academic discovery for researchers and students. \n    Use your judgment to identify the most important bibliographic and intellectual metadata from the text.\n    '

CONTENT_WARNING_INSTRUCTIONS = "\n        After analyzing the content, assess whether it contains any language or themes that might warrant a content warning. Consider the following categories:\n        1. Racist/ethnically insensitive language\n        2. Sexist/gender-discriminatory content\n        3. Violence/graphic descriptions\n        4. Other potentially offensive/outdated terminology\n\n        If you identify any such content, briefly describe it using the categorization described above.\n        If no sensitive content is present, simply return 'None'.\n        "

ABSTRACT_FIELD = FieldSpec(
    'abstract',
    'The dissertation abstract. Use the formal abstract if present; otherwise, create a brief descriptive abstract.',
    ("Search the entire dissertation text for the formal abstract section (often labeled 'Abstract').", 'If a formal abstract is present, extract the abstract text and reproduce it word-for-word, preserving the original wording and order.', 'You may normalize spacing and line breaks, but do not change the wording or meaning of the formal abstract.', 'If no formal abstract is present in the dissertation, write a concise descriptive abstract (2–5 sentences) that summarizes the overall research problem, methods, and main findings or conclusions, based on the full text.', 'Use neutral, descriptive language rather than promotional language.', "If there is not enough information to infer a meaningful descriptive abstract, return an empty string ('')."),
)

ACCESS_FIELD = FieldSpec(
    'access',
    "Whether access to the work is restricted or unrestricted. If access is unknown, return 'unknown'.",
    (),
)

CONTENT_WARNING_FIELD_TEXT = FieldSpec(
    'contentWarning',
    "Note potentially sensitive content, or 'None' if none exists. Another archivist will assess if any measures are appropriate, your job is just to note if there is anything that may be concerning.",
    ('Consider: Biased language or terminology.', 'Consider: Culturally sensitive material.', 'Consider: Offensive or harmful language.'),
)

CREATOR_FIELD = FieldSpec(
    'creator',
    'The primary author or creator of the dissertation, as stated in the document.',
    ('Copy the author name(s) exactly as they appear in the dissertation (usually on the title page).', 'Do NOT invent or guess names.', 'If multiple authors are listed, include all of them in the order presented.', "If no creator is clearly identified, return an empty string ('')."),
)

DATE_FIELD = FieldSpec(
    'date',
    'The date of completion or publication of the dissertation, as stated in the document.',
    ('Extract the date from the dissertation (e.g., from the title page, approval page, or front matter).', 'Prefer the year of completion/approval if multiple dates appear.', "Do NOT invent a date; if no clear date is present, return an empty string ('').", "Use ISO format 'YYYY' or 'YYYY-MM-DD' if the full date is clearly given."),
)

DEPARTMENT_FIELD = FieldSpec(
    'department',
    'The academic department or program associated with the dissertation, as stated in the document.',
    ("Copy the department or program name from the dissertation (e.g., 'Department of History', 'School of Nursing').", 'Do NOT invent or infer a department solely from subject matter; only use what is explicitly stated.', 'If multiple units are listed (e.g., department and school), include the most specific academic unit (usually the department or program).', "If no department or program is clearly identified, return an empty string ('')."),
)

GEOGRAPHIC_ENTITIES_FIELD_TEXT = FieldSpec(
    'geographicEntities',
    'Geographic references mentioned in the text.',
    ('Format examples:', "- 'City--State (City)' for U.S. Cities e.g. 'New York--New York (City)'.", "- 'City--Province' for Canadian cities e.g. 'Toronto--Ontario (City)'.", "- 'City--Country' for all other Non-U.S. cities e.g. 'London--England (City)'.", "- 'State (State)' for U.S. States e.g. 'Tennessee (State)'.", "- 'Province/State--Country (Province/State)' for non-U.S. Provinces or States e.g. 'Quebec--Canada (Province)'.", "- 'Country (Country)' for Countries e.g. 'France (Country)'.", 'Include all geographic references mentioned in the text.', "Always include full names: 'Georgia' not 'Ga', 'Maryland' not 'Md', 'United States' not 'US'."),
)

LANGUAGE_FIELD = FieldSpec(
    'language',
    'Primary language that the work is written in.',
    (),
)

NAMED_ENTITIES_FIELD = FieldSpec(
    'namedEntities',
    'List non-geographic entities with type in parentheses.',
    ("Format: 'Albert Einstein (Person)', 'John Smith (Advisor)', 'Maria Garcia (CommitteeMember)', 'University of Texas at Austin (Institution)', 'World Health Organization (Organization)', 'Nature (Journal)', etc.", 'Types: (Person), (Advisor), (CommitteeMember), (Organization), (Institution), (Journal), (Publisher), (FundingAgency).', 'Do NOT include geographic locations here - use geographicEntities field instead.', "Limit to entities that are central to the dissertation's argument, methodology, authorship, or historical/intellectual context."),
)

PUBLISHER_FIELD = FieldSpec(
    'publisher',
    "The publisher or disseminating organization, if previously published. If no publisher is associated with the work, return an empty string ('').",
    (),
)

SPONSOR_FIELD = FieldSpec(
    'sponsor',
    "The external agency or organization that sponsored or supported this work. If no sponsor is associated with the work, return an empty string ('').",
    (),
)

SUBJECTS_FIELD = FieldSpec(
    'subjects',
    'Topics that will be used as search terms in controlled vocabulary APIs',
    ('Focus on specific but searchable words or phrases as topics.', 'Cover the breadth of what is discussed in the dissertation.', 'Write each search term as a separate string in the list.', 'Up to 8 terms may be included.', 'Priority topics: main discipline and subfield, key concepts and theories, research methods used, specific topics or phenomena studied, temporal focus (if important analytically), and notable contributions or innovations.', 'For academic content, identify the precise research area, central theoretical constructs, core variables or entities analyzed, and recurring themes or problems addressed.', 'Do not include proper names or geographic locations, as these will be captured in the namedEntities and geographicEntities fields.'),
)

TITLE_FIELD = FieldSpec(
    'title',
    'The exact title of the work as it appears in the document.',
    ('Copy the title from the dissertation (typically from the title page or front matter).', 'Do NOT create or invent a new title.', 'Preserve the original wording and order; you may normalize capitalization and spacing if needed.'),
)

TYPE_FIELD = FieldSpec(
    'type',
    'The nature of the work being submitted (ex. Thesis, dissertation, capstone project, research paper).',
    (),
)

ALL_FIELDS = (
    TITLE_FIELD, CREATOR_FIELD, DATE_FIELD, DEPARTMENT_FIELD, ABSTRACT_FIELD,
    SUBJECTS_FIELD, TYPE_FIELD, ACCESS_FIELD, PUBLISHER_FIELD, SPONSOR_FIELD,
    LANGUAGE_FIELD, NAMED_ENTITIES_FIELD, GEOGRAPHIC_ENTITIES_FIELD_TEXT,
    CONTENT_WARNING_FIELD_TEXT,
)  # legacy output order

FRONT_MATTER_FIELDS = (
    TITLE_FIELD, CREATOR_FIELD, DATE_FIELD, DEPARTMENT_FIELD, ABSTRACT_FIELD,
    TYPE_FIELD, ACCESS_FIELD, PUBLISHER_FIELD, SPONSOR_FIELD, LANGUAGE_FIELD,
)
FULL_TEXT_FIELDS = (
    SUBJECTS_FIELD, NAMED_ENTITIES_FIELD, GEOGRAPHIC_ENTITIES_FIELD_TEXT,
    CONTENT_WARNING_FIELD_TEXT,
)
