"""
Shared utilities for TSW Dissertation processing pipeline.
Contains common functions and classes used across multiple steps.
"""

import os
import json
import re
from typing import Dict, Any, Optional

class APIStats:
    """Shared API statistics tracking class."""
    
    def __init__(self):
        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.processing_times = []

def find_newest_folder(base_directory: str) -> Optional[str]:
    """Find the newest folder in the base directory."""
    if not os.path.exists(base_directory):
        return None
    
    folders = [f for f in os.listdir(base_directory) 
              if os.path.isdir(os.path.join(base_directory, f))]
    
    if not folders:
        return None
    
    # Sort by modification time (newest first)
    folders.sort(key=lambda x: os.path.getmtime(os.path.join(base_directory, x)), reverse=True)
    
    return os.path.join(base_directory, folders[0])

from typing import Dict, Any

def postprocess_api_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """Post-process the API response for consistency in the dissertation workflow."""
    
    # Helper: convert string to list if needed
    def ensure_list(field_value):
        if isinstance(field_value, str):
            # Split by comma and clean up each item
            items = [item.strip() for item in field_value.split(',') if item.strip()]
            return items
        elif isinstance(field_value, list):
            return field_value
        else:
            return []
    
    # ----- namedEntities -----
    if 'namedEntities' in response_data:
        response_data['namedEntities'] = ensure_list(response_data['namedEntities'])
        # Remove duplicates while preserving order
        response_data['namedEntities'] = list(dict.fromkeys(response_data['namedEntities']))
        # Remove entities that are just single letters or numbers
        response_data['namedEntities'] = [
            entity for entity in response_data['namedEntities']
            if len(entity) > 1 or not entity.isalnum()
        ]
    else:
        # Ensure key exists, even if empty
        response_data.setdefault('namedEntities', [])
    
    # ----- geographicEntities -----
    if 'geographicEntities' in response_data:
        response_data['geographicEntities'] = ensure_list(response_data['geographicEntities'])
        # Remove duplicates while preserving order
        response_data['geographicEntities'] = list(dict.fromkeys(response_data['geographicEntities']))
        # Remove entities that are just single letters or numbers
        response_data['geographicEntities'] = [
            entity for entity in response_data['geographicEntities']
            if len(entity) > 1 or not entity.isalnum()
        ]
    else:
        response_data.setdefault('geographicEntities', [])
    
    # ----- subjects (normalize any variants) -----
    if 'subjects' in response_data:
        response_data['subjects'] = ensure_list(response_data['subjects'])
    elif 'topics' in response_data:
        response_data['subjects'] = ensure_list(response_data.pop('topics'))
    elif 'subjectHeadings' in response_data:
        response_data['subjects'] = ensure_list(response_data.pop('subjectHeadings'))
    else:
        response_data.setdefault('subjects', [])
    
    # ----- contentWarning -----
    if 'contentWarning' not in response_data:
        response_data['contentWarning'] = 'None'
    elif isinstance(response_data['contentWarning'], str):
        cw = response_data['contentWarning'].strip()
        if cw == '' or cw.lower() == 'none':
            response_data['contentWarning'] = 'None'
        else:
            # Capitalize first letter and ensure it ends with a period
            cw = cw[0].upper() + cw[1:]
            response_data['contentWarning'] = cw.rstrip('.') + '.'
    else:
        # Non-string contentWarning → normalize to 'None'
        response_data['contentWarning'] = 'None'
    
    # Optionally: trim whitespace on simple string fields
    for key in [
        "title", "creator", "date", "department", "abstract",
        "type", "access", "publisher", "sponsor", "language"
    ]:
        if key in response_data and isinstance(response_data[key], str):
            response_data[key] = response_data[key].strip()
    
    return response_data

from typing import Dict, Any, Optional, Tuple

def parse_json_response_enhanced(raw_response: str) -> Tuple[Dict[str, Any], Optional[str]]: 
    """Enhanced JSON parsing with multiple recovery strategies."""
    if not raw_response or not raw_response.strip():
        return {}, "Empty response"
    
    try:
        # Strategy 1: Standard cleaning
        cleaned_response = re.sub(r'```json\s*|\s*```', '', raw_response)
        cleaned_response = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', cleaned_response, flags=re.DOTALL)
        cleaned_response = re.sub(r',(\s*[}\]])', r'\1', cleaned_response)
        
        parsed_json = json.loads(cleaned_response)
        return parsed_json, None
        
    except json.JSONDecodeError:
        pass
    
    try:
        # Strategy 2: Extract JSON object more aggressively
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            parsed_json = json.loads(json_str)
            return parsed_json, None
            
    except json.JSONDecodeError:
        pass
    
    try:
        # Strategy 3: Fix common issues
        fixed_response = raw_response
        
        # Fix unquoted keys
        fixed_response = re.sub(r'(\w+):', r'"\1":', fixed_response)
        
        # Fix unquoted string values
        fixed_response = re.sub(r':\s*([^",\[\{][^,\]\}]*)', r': "\1"', fixed_response)
        
        # Remove trailing commas
        fixed_response = re.sub(r',(\s*[}\]])', r'\1', fixed_response)
        
        # Extract JSON part
        json_match = re.search(r'\{.*\}', fixed_response, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group(0))
            return parsed_json, None
            
    except json.JSONDecodeError:
        pass
    
    return {}, "All parsing strategies failed"

import re

def preprocess_ocr_text(text: str) -> str:
    """
    Preprocess dissertation text to fix common OCR or encoding issues.

    For now, this is intentionally minimal assuming that most dissertations are either
    modern, born-digital PDFs or digitized with clean OCR. If you later ingest
    scanned / OCR'd dissertations and notice recurring errors, add specific
    replacements below.
    """
    # 1. Add dissertation-specific corrections here if you discover them.
    # Example (commented out until you have real patterns):
    # replacements = {
    #     "rn": "m",   # if you see "rn" misread for "m" a lot
    #     "ﬁ": "fi",   # common ligature issues
    # }
    # for error, correction in replacements.items():
    #     text = text.replace(error, correction)

    # 2. Optionally normalize weird whitespace
    text = text.replace('\u00a0', ' ')  # non-breaking space → normal space
    text = re.sub(r'[ \t]+', ' ', text)  # collapse multiple spaces
    text = re.sub(r'\n{3,}', '\n\n', text)  # collapse 3+ blank lines to 2

    # 3. Do NOT strip punctuation or non-ASCII characters by default,
    #    to avoid damaging legitimate content (names, formulas, etc.).
    return text