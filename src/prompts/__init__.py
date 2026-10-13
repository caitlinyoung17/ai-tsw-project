"""Prompt construction package.

Replaces the legacy top-level prompts.py module; 
"""
from .fields import (ALL_FIELDS, FRONT_MATTER_FIELDS, FULL_TEXT_FIELDS,
                     FieldSpec)
from .metadata import (abstract_completion_template, chunk_entities_template,
                       front_matter_template, metadata_extraction_template)
from .params import CHUNK, CLEANUP, EXTRACTION, SELECTION, CallParams
from .vocab_selection import (VOCAB_SELECTION_SYSTEM, render_vocab_selection,
                              vocab_selection_template)
