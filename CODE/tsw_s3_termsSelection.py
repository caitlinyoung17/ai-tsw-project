# terms selection - using OpenAI's GPT-4o-mini model

import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
from openai import OpenAI
import tenacity
from openpyxl import load_workbook
from openpyxl.cell import Cell
from openpyxl.styles import Alignment
from prompts import DissertationPrompts
from shared_utilities import APIStats, find_newest_folder

# Import our custom modules
from model_pricing import calculate_cost, get_model_info
from token_logging import create_token_usage_log, log_individual_response
from batch_processor import BatchProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Suppress verbose HTTP logging
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
DEFAULT_MODEL = "gpt-4.1-mini"  # Default model name, change as needed

api_stats = APIStats()

def prepare_batch_requests(entries_with_vocab, vocabulary_selector, model_name):
    """
    Prepare all vocabulary selection requests for batch processing.

    entries_with_vocab: iterable of (entry_index, entry_data) tuples, where
        entry_data contains the subjects and candidate vocab terms for one dissertation.
    vocabulary_selector: object with .system_prompt and .create_user_prompt(entry_data).
    """
    batch_requests = []
    custom_id_mapping = {}
        
    for i, (entry_index, entry_data) in enumerate(entries_with_vocab):
        user_prompt = vocabulary_selector.create_user_prompt(entry_data)
        
        if not user_prompt:
            continue  # Skip entries without vocabulary terms
        
        # Create request data
        request_data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": vocabulary_selector.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1500,
            "temperature": 0.1
        }
        
        batch_requests.append(request_data)
        custom_id_mapping[f"vocab_selection_{i}"] = {
            "entry_index": entry_index,
            "entry_data": entry_data,
            "row_number": entry_index + 2  # +2 for header row if you log to Excel
        }
    
    return batch_requests, custom_id_mapping

class VocabularySelector:
    """
    Class to select the best controlled vocabulary terms for each dissertation using an LLM.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        # System prompt for vocabulary selection (from DissertationPrompts)
        self.system_prompt = DissertationPrompts.get_vocabulary_selection_system_prompt()

    def create_system_prompt(self) -> str:
        """Return the system prompt for vocabulary selection."""
        return self.system_prompt

    def create_user_prompt(self, entry_data: Dict[str, Any]) -> str:
        """
        Create the user prompt for a specific dissertation entry.

        entry_data is expected to contain:
          - 'analysis': {
                'title': str,
                'abstract': str,
                'subjects': list[str] or comma-separated str,
                'vocabulary_search_results': {
                    subject: [ {label, uri, source, ...}, ... ]
                }
            }
        """
        analysis = entry_data.get('analysis', {})
        
        # Build content description
        content_parts = []
        
        title = analysis.get('title', '').strip()
        if title:
            content_parts.append(f"TITLE:\n{title}")
        
        abstract = analysis.get('abstract', '').strip()
        if abstract:
            content_parts.append(f"ABSTRACT:\n{abstract}")
        
        # Add original subjects
        subjects_value = analysis.get('subjects', [])
        if isinstance(subjects_value, list):
            subjects = [s.strip() for s in subjects_value if s and str(s).strip()]
        elif isinstance(subjects_value, str):
            subjects = [s.strip() for s in subjects_value.split(',') if s.strip()]
        else:
            subjects = []
        
        if subjects:
            content_parts.append(f"SUBJECTS (free-text):\n{', '.join(subjects)}")
        
        content_description = "\n\n".join(content_parts) if content_parts else "No detailed description available."
        
        # Candidate vocabulary terms per subject (from Step 2)
        subject_to_terms = analysis.get('vocabulary_search_results', {})
        
        if not subject_to_terms:
            return ''  # No candidate vocabulary terms available
        
        subjects_section = self._build_subject_organized_terms(subject_to_terms)
        
        # Combine everything into the user prompt
        user_prompt = f"""Analyze this dissertation's content and select appropriate controlled vocabulary terms.

{content_description}

AVAILABLE CANDIDATE CONTROLLED TERMS BY SUBJECT:
{subjects_section}

For each free-text subject, select zero or more controlled headings that best represent the concept in the context of the dissertation.
Use the exact controlled labels (without [source] brackets).
Skip subjects where no candidate headings are genuinely relevant.
Return ONLY the JSON object in the format specified in the system prompt.
"""
        
        return user_prompt

    def _build_subject_organized_terms(self, subject_to_terms: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        Build a human-readable section listing candidate terms organized by subject.

        subject_to_terms: subject -> list of term dicts with keys like 'label', 'uri', 'source'.
        """
        lines = []
        for subject, terms in subject_to_terms.items():
            lines.append(f"Subject: {subject}")
            if not terms:
                lines.append("  (No candidate controlled terms)")
                lines.append("")
                continue
            
            for term in terms:
                label = term.get('label', 'N/A')
                uri = term.get('uri', '')
                source = term.get('source', 'Unknown')
                if uri:
                    lines.append(f"  - {label} ({uri}) [{source}]")
                else:
                    lines.append(f"  - {label} [{source}]")
            lines.append("")
        
        return "\n".join(lines)
    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(5),
        retry=tenacity.retry_if_exception_type(Exception)
    )
    def select_vocabulary_terms(self, entry_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str, Any, float]:
        """
        Select controlled vocabulary terms for a single dissertation entry.

        Returns:
            parsed_response: dict with at least 'selected_terms' key
            raw_response: raw text returned by the model
            usage: response.usage (or dict-like) for token logging
            processing_time: float seconds
        """
        user_prompt = self.create_user_prompt(entry_data)
        
        if not user_prompt:
            # No candidate vocabulary terms available
            return {
                "selected_terms": []
            }, "No vocabulary terms available for selection", None, 0.0
        
        api_stats.total_requests += 1
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1500,
            temperature=0.1  # Low temperature for consistent, precise selections
        )
        
        processing_time = time.time() - start_time
        api_stats.processing_times.append(processing_time)
        
        # Safely handle usage
        usage = response.usage or {}
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        
        api_stats.total_input_tokens += prompt_tokens
        api_stats.total_output_tokens += completion_tokens
        
        # Safely get the first choice's content
        if not response.choices:
            raise Exception("No choices returned from OpenAI API during vocabulary selection")
        
        message_content = response.choices[0].message.content or ""
        raw_response = message_content.strip()
        
        # Parse JSON response
        try:
            parsed_response = self.parse_json_response(raw_response)
            return parsed_response, raw_response, usage, processing_time
        except Exception as e:
            logging.error(f"Error parsing vocabulary selection response: {e}")
            # Return empty selection on parsing error
            return {
                "selected_terms": []
            }, raw_response, usage, processing_time

    def parse_json_response(self, raw_response: str) -> Dict[str, Any]:
        """Parse JSON response from the API and ensure it has the expected structure."""
        from shared_utilities import parse_json_response_enhanced
        
        parsed_json, error = parse_json_response_enhanced(raw_response)
        
        if parsed_json is None:
            raise ValueError(f"Could not parse JSON response: {error}")
        
        # Validate structure
        if 'selected_terms' not in parsed_json:
            parsed_json['selected_terms'] = []
        
        return parsed_json


class DissertationVocabularyProcessor:
    """
    Main class for vocabulary selection and clean output generation for dissertations.
    Uses an LLM to select controlled vocabulary terms from candidate headings.
    """

    def __init__(self, folder_path: str, model_name: str = DEFAULT_MODEL):
        """
        folder_path: path to a single dissertation output folder from Step 1/2
                     (e.g., output_folders/Dissertation_Metadata_Created_YYYY-MM-DD_Time_HH-MM-SS)
        """
        self.folder_path = folder_path
        self.model_name = model_name
        self.workflow_type = ''
        self.json_data = []
        self.excel_path = ''
        self.vocabulary_selector = VocabularySelector(model_name)
        self.was_batch_processed = False

    def detect_workflow_type(self) -> bool:
        """
        Detect workflow type and check that vocabulary enhancement (Step 2) has been run.

        For dissertations we expect only text workflow files:
        - metadata/collection_metadata/text_workflow.xlsx
        - metadata/collection_metadata/text_workflow.json
        and a vocabulary_mapping_report.txt from Step 2.
        """
        metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        text_files = ['text_workflow.xlsx', 'text_workflow.json']
        
        has_text_files = all(os.path.exists(os.path.join(metadata_dir, f)) for f in text_files)
        
        if has_text_files:
            self.workflow_type = 'text'
            self.excel_path = os.path.join(metadata_dir, 'text_workflow.xlsx')
        else:
            logging.error("Could not find text workflow files (text_workflow.xlsx/json) in the metadata folder.")
            return False
        
        # Check if vocabulary enhancement has been run (Step 2)
        vocab_report_path = os.path.join(metadata_dir, 'vocabulary_mapping_report.txt')
        if not os.path.exists(vocab_report_path):
            logging.error("Vocabulary enhancement (step 2) must be run before step 3.")
            return False

        return True 
    
    def load_json_data(self) -> bool:
        """
        Load JSON data for the detected workflow type and verify that vocabulary terms exist.

        Expects that Step 2 has populated analysis['vocabulary_search_results'] for at least one item.
        """
        json_filename = f"{self.workflow_type}_workflow.json"
        metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        json_path = os.path.join(metadata_dir, json_filename)
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
            
            # Check if vocabulary terms exist in the data
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            
            has_vocab_terms = False
            for item in data_items:
                if 'analysis' in item and 'vocabulary_search_results' in item['analysis']:
                    vocab_terms = item['analysis']['vocabulary_search_results']
                    if vocab_terms:  # Check if there are any vocabulary terms
                        has_vocab_terms = True
                        break
            
            if not has_vocab_terms:
                logging.error("No vocabulary terms found in JSON. Please run Step 2 (vocab querying) first.")
                return False
            
            print(f"Loaded JSON data from {json_filename}")
            return True
            
        except Exception as e:
            logging.error(f"Error loading JSON data: {e}")
            return False  
                 
    def find_entries_with_vocabulary(self) -> List[Tuple[int, Dict[str, Any]]]:
        """Find entries that have vocabulary terms available for selection."""
        entries_with_vocab = []
        
        # Skip the last item if it's API stats
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
        if data_items is None:
            return entries_with_vocab

        for i, item in enumerate(data_items):
            if 'analysis' in item and 'vocabulary_search_results' in item['analysis']:
                vocab_terms = item['analysis']['vocabulary_search_results']
                if vocab_terms:  # Only include items with vocabulary terms
                    entries_with_vocab.append((i, item))
        
        return entries_with_vocab
    
    def process_vocabulary_selection(self, entries_with_vocab: List[Tuple[int, Dict[str, Any]]]) -> Dict[int, Dict[str, Any]]:
        """
        Process vocabulary selection using batch processing when appropriate.

        entries_with_vocab: list of (entry_index, entry_data) tuples, where entry_data
        is a JSON item with analysis['vocabulary_search_results'] populated.
        """
        selection_results: Dict[int, Dict[str, Any]] = {}
        
        # Create logs folder
        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)
        
        total_entries = len(entries_with_vocab)
        
        # Initialize batch processor and check if we should use batch processing
        processor = BatchProcessor()
        use_batch = processor.should_use_batch(total_entries)
        
        print(f"Processing mode: {'BATCH' if use_batch else 'INDIVIDUAL'}")
        
        if use_batch:
            print(f"Preparing {total_entries} requests for batch processing...")
            
            # Prepare batch requests
            batch_requests, custom_id_mapping = prepare_batch_requests(
                entries_with_vocab, self.vocabulary_selector, self.model_name
            )
            
            if not batch_requests:
                print("No valid requests to process")
                return selection_results
            
            # Estimate costs
            cost_estimate = processor.estimate_batch_cost(batch_requests, self.model_name)
            print(f"Cost estimate: ${cost_estimate['batch_cost']:.4f} (${cost_estimate['savings']:.4f} savings)")
            
            # Convert to batch format
            formatted_requests = processor.create_batch_requests(batch_requests, "vocab_selection")
            
            # Submit batch
            batch_id = processor.submit_batch(
                formatted_requests, 
                f"Dissertation Vocabulary Selection - {len(batch_requests)} entries - {datetime.now().strftime('%Y-%m-%d')}"
            )
            
            # Wait for completion
            batch_results = processor.wait_for_completion(batch_id, max_wait_hours=24, check_interval_minutes=5)
            
            if batch_results:
                # Process batch results
                processed_results = processor.process_batch_results(batch_results, custom_id_mapping)
                
                print(f"Processing batch results...")
                
                # Track tokens for logging
                api_stats.total_input_tokens = processed_results["summary"]["total_prompt_tokens"]
                api_stats.total_output_tokens = processed_results["summary"]["total_completion_tokens"]
                
                self.was_batch_processed = True
                
                # Process results
                for custom_id, result_data in processed_results["results"].items():
                    if custom_id.startswith("vocab_selection_"):
                        # Extract the index from custom_id: vocab_selection_{i}_xxxx
                        parts = custom_id.split("_")
                        if len(parts) >= 3:
                            try:
                                index = int(parts[2])
                                mapping_key = f"vocab_selection_{index}"
                                
                                if mapping_key in custom_id_mapping:
                                    entry_index = custom_id_mapping[mapping_key]["entry_index"]
                                    entry_data = custom_id_mapping[mapping_key]["entry_data"]
                                    row_number = custom_id_mapping[mapping_key]["row_number"]
                                    
                                    if result_data["success"]:
                                        raw_response = result_data["content"]
                                        usage = result_data["usage"]
                                        
                                        # Parse the vocabulary selection response
                                        try:
                                            selection_result = self.vocabulary_selector.parse_json_response(raw_response)
                                        except Exception as e:
                                            logging.error(f"Error parsing vocabulary selection response: {e}")
                                            selection_result = {"selected_terms": []}
                                        
                                        # Log individual response
                                        log_individual_response(
                                            logs_folder_path=logs_folder_path,
                                            script_name="dissertation_vocabulary_selection",
                                            row_number=row_number,
                                            barcode=f"entry_{entry_index}",
                                            response_text=raw_response,
                                            model_name=self.model_name,
                                            prompt_tokens=usage.get("prompt_tokens", 0) if usage else 0,
                                            completion_tokens=usage.get("completion_tokens", 0) if usage else 0,
                                            processing_time=0  # Batch processing doesn't track individual timing
                                        )
                                        
                                        selection_results[entry_index] = {
                                            'selection_result': selection_result,
                                            'raw_response': raw_response,
                                            'processing_time': 0
                                        }
                                        
                                        selected_count = len(selection_result.get('selected_terms', []))
                                        print(f"   Entry {entry_index}: Selected {selected_count} vocabulary terms")
                                        
                                    else:
                                        # Handle error case
                                        error_msg = result_data['error']
                                        raw_response = f"Error: {error_msg}"
                                        
                                        # Log error
                                        log_individual_response(
                                            logs_folder_path=logs_folder_path,
                                            script_name="dissertation_vocabulary_selection",
                                            row_number=row_number,
                                            barcode=f"entry_{entry_index}",
                                            response_text=raw_response,
                                            model_name=self.model_name,
                                            prompt_tokens=0,
                                            completion_tokens=0,
                                            processing_time=0
                                        )
                                        
                                        selection_results[entry_index] = {
                                            'selection_result': {'selected_terms': []},
                                            'raw_response': raw_response,
                                            'processing_time': 0
                                        }
                                        
                                        print(f"   Entry {entry_index}: Processing failed: {error_msg}")
                                        
                            except (ValueError, IndexError) as e:
                                logging.error(f"Error processing custom_id {custom_id}: {e}")
                                continue
                
                processed_entries = len(selection_results)
                print(f"\nBatch processing completed: {processed_entries}/{total_entries} entries processed")
                return selection_results
        
        # Fall back to individual processing
        print(f"Using individual processing:")
        self.was_batch_processed = False
        return self.process_vocabulary_selection_individual(entries_with_vocab, logs_folder_path)
                     
    def process_vocabulary_selection_individual(
        self,
        entries_with_vocab: List[Tuple[int, Dict[str, Any]]],
        logs_folder_path: str
    ) -> Dict[int, Dict[str, Any]]:
        """Process vocabulary selection using individual API calls."""
        self.was_batch_processed = False
        selection_results: Dict[int, Dict[str, Any]] = {}
        total_entries = len(entries_with_vocab)
        processed_entries = 0
        
        for i, (entry_index, entry_data) in enumerate(entries_with_vocab):
            print(f"\nProcessing entry {i+1}/{total_entries}")
            print(f"   Entry index: {entry_index}")
            print(f"   Progress: {((i+1)/total_entries)*100:.1f}%")
            
            try:
                selection_result, raw_response, usage, processing_time = self.vocabulary_selector.select_vocabulary_terms(entry_data)
                
                # Log individual response
                log_individual_response(
                    logs_folder_path=logs_folder_path,
                    script_name="dissertation_vocabulary_selection",
                    row_number=entry_index + 2,  # +2 for header row if logging to Excel
                    barcode=f"entry_{entry_index}",
                    response_text=raw_response,
                    model_name=self.model_name,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                    processing_time=processing_time
                )
                
                selection_results[entry_index] = {
                    'selection_result': selection_result,
                    'raw_response': raw_response,
                    'processing_time': processing_time
                }
                
                selected_count = len(selection_result.get('selected_terms', []))
                print(f"   Selected {selected_count} vocabulary terms")
                processed_entries += 1
                
            except Exception as e:
                logging.error(f"Error processing entry {entry_index}: {e}")
                selection_results[entry_index] = {
                    'selection_result': {'selected_terms': []},
                    'raw_response': f"Error: {str(e)}",
                    'processing_time': 0
                }
                print(f"   Processing failed: {str(e)}")
            
            # Add delay between requests
            time.sleep(0.5)
        
        print(f"\nIndividual processing completed: {processed_entries}/{total_entries} entries processed")
        return selection_results
    
    def normalize_label_for_matching(self, label: str) -> str:
        """Normalize labels for better matching."""
        import re
        
        # Convert to lowercase
        normalized = label.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common punctuation that might cause mismatches
        normalized = re.sub(r'[.,;:!?]$', '', normalized)
        
        return normalized
    
    def deduplicate_vocabulary_terms(self, matched_terms: List[Dict]) -> List[Dict]:
        """
        Deduplicate vocabulary terms when they have the same words (same order or different order).
        Priority order: Getty AAT > LCSH > FAST > others
        """
        if not matched_terms:
            return matched_terms
        
        # Define source priority (lower number = higher priority)
        source_priority = {
            'Getty AAT': 1,
            'LCSH': 2, 
            'FAST': 3
        }
        
        def normalize_for_comparison(label: str) -> str:
            """Convert to lowercase letters only, preserving word order."""
            import re
            
            # Convert to lowercase and keep only letters and spaces
            normalized = re.sub(r'[^a-z\s]', '', label.lower())
            
            # Normalize whitespace
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            
            return normalized
        
        def are_semantically_equivalent(term1: Dict, term2: Dict) -> bool:
            """Check if two terms have the same words (same or different order)."""
            label1 = term1.get('label', '')
            label2 = term2.get('label', '')
            
            norm1 = normalize_for_comparison(label1)
            norm2 = normalize_for_comparison(label2)
            
            # Exact match after normalization (same words, same order)
            if norm1 == norm2:
                return True
            
            # Same words, different order
            words1 = set(norm1.split())
            words2 = set(norm2.split())
            
            return words1 == words2 and len(words1) > 0
        
        # Group terms by semantic equivalence
        equivalence_groups = []
        
        for term in matched_terms:
            # Find if this term belongs to an existing group
            added_to_group = False
            
            for group in equivalence_groups:
                if any(are_semantically_equivalent(term, existing_term) for existing_term in group):
                    group.append(term)
                    added_to_group = True
                    break
            
            # If not added to any group, create a new group
            if not added_to_group:
                equivalence_groups.append([term])
        
        # For each group, select the best term based on source priority
        deduplicated_terms = []
        
        for group in equivalence_groups:
            if len(group) == 1:
                # No duplicates, keep the term
                deduplicated_terms.append(group[0])
            else:
                # Multiple equivalent terms, choose based on priority
                best_term = min(group, key=lambda t: source_priority.get(t.get('source', ''), 999))
                deduplicated_terms.append(best_term)
                
                # Log the deduplication for debugging
                removed_terms = [t for t in group if t != best_term]
                removed_labels = [f"{t.get('label')} [{t.get('source')}]" for t in removed_terms]
                best_label = f"{best_term.get('label')} [{best_term.get('source')}]"

        return deduplicated_terms

    def match_selected_labels_to_original_terms(
        self,
        selected_labels: List[str],
        vocab_search_results: Dict[str, List[Dict]]
    ) -> List[Dict]:
        """
        Match LLM-selected labels back to the original candidate term objects,
        finding all semantically equivalent terms and applying source priority.

        This fixes the issue where the LLM selects one source but we end up with a different source in output.
        """
        
        # Create a comprehensive mapping of all available terms
        all_available_terms: List[Dict] = []
        for subject, terms in vocab_search_results.items():
            for term in terms:
                if isinstance(term, dict):
                    all_available_terms.append(term)
        
        def normalize_for_comparison(label: str) -> str:
            """Normalize labels for semantic comparison - remove punctuation, lowercase, normalize spaces."""
            import re
            normalized = re.sub(r'[^a-z\s]', '', label.lower())
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return normalized
        
        # Define source priority (lower number = higher priority)
        source_priority = {
            'Getty AAT': 1,
            'LCSH': 2, 
            'FAST': 3,
            'Getty TGN': 4
        }
        
        matched_terms: List[Dict] = []
        
        for selected_label in selected_labels:            
            # Find all terms that could semantically match this selected label
            candidate_matches: List[Dict] = []
            
            # Normalize the selected label for comparison
            selected_words = set(normalize_for_comparison(selected_label).split())
            
            # Search through all available terms for semantic matches
            for term in all_available_terms:
                term_label = term.get('label', '').strip()
                term_words = set(normalize_for_comparison(term_label).split())
                
                # Check if they have the same words (order doesn't matter)
                if selected_words == term_words and len(selected_words) > 0:
                    candidate_matches.append(term)
                    
            # If we found semantic matches, apply source priority
            if candidate_matches:
                best_match = min(candidate_matches, key=lambda t: source_priority.get(t.get('source', ''), 999))
                matched_terms.append(best_match)
                
                # Optional: rejected terms for debugging
                # rejected_terms = [t for t in candidate_matches if t != best_match]
                # rejected_labels = [f"{t.get('label')} [{t.get('source')}]" for t in rejected_terms]
            
            else:
                # If no semantic matches, try exact string matching as fallback
                selected_normalized = selected_label.lower().strip()
                candidate_matches = []
                
                for term in all_available_terms:
                    term_label = term.get('label', '').strip()
                    term_normalized = term_label.lower().strip()
                    
                    if selected_normalized == term_normalized:
                        candidate_matches.append(term)
                
                if candidate_matches:
                    # Apply priority even for exact matches
                    best_match = min(candidate_matches, key=lambda t: source_priority.get(t.get('source', ''), 999))
                    matched_terms.append(best_match)
        
        # Deduplicate by URI (keep first occurrence)
        seen_uris = set()
        deduplicated_terms: List[Dict] = []
        for term in matched_terms:
            uri = term.get('uri', '')
            if uri and uri not in seen_uris:
                deduplicated_terms.append(term)
                seen_uris.add(uri)
            elif not uri:  # Keep terms without URIs, though they should be rare
                deduplicated_terms.append(term)
        
        return deduplicated_terms

    def update_json_data(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """
        Update JSON data with selected vocabulary terms only.

        For each entry, this replaces the LLM's selected labels with the full term objects
        from analysis['vocabulary_search_results'], and stores them under
        analysis['final_selected_terms'].
        """
        try:
            # Skip the last item if it's API stats
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            api_stats_item = self.json_data[-1] if self.json_data and 'api_stats' in self.json_data[-1] else None
            
            updated_items = []
            if data_items is None:
                data_items = []

            for i, item in enumerate(data_items):
                if i in selection_results:
                    # Get selected term labels from LLM response
                    selected_term_responses = selection_results[i]['selection_result'].get('selected_terms', [])
                    
                    # Extract clean labels
                    selected_labels = []
                    for term in selected_term_responses:
                        if isinstance(term, dict):
                            label = term.get('label', '').strip()
                            if label:
                                selected_labels.append(label)
                    
                    # Match labels to full term objects from vocabulary_search_results
                    vocab_search_results = item['analysis'].get('vocabulary_search_results', {})
                    matched_terms = self.match_selected_labels_to_original_terms(selected_labels, vocab_search_results)
                    
                    # ONLY store final_selected_terms (remove all other redundant data)
                    item['analysis']['final_selected_terms'] = matched_terms
                else:
                    # Keep empty for entries without vocabulary terms
                    item['analysis']['final_selected_terms'] = []
                
                updated_items.append(item)
            
            # Add API stats back if it existed
            if api_stats_item:
                updated_items.append(api_stats_item)
            
            # Save updated JSON
            json_filename = f"{self.workflow_type}_workflow.json"
            metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            json_path = os.path.join(metadata_dir, json_filename)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(updated_items, f, indent=2, ensure_ascii=False)
            
            print(f"Updated JSON file with selected vocabulary terms")
            return True
            
        except Exception as e:
            logging.error(f"Error updating JSON data: {e}")
            return False
        
    def update_excel_file(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """
        Update Excel file with selected vocabulary terms.

        This replaces the Step 2 "Subject Vocabulary Terms" column with
        "Selected Subject Vocabulary Terms" containing only the final chosen terms.
        """
        try:
            # Load the existing workbook
            wb = load_workbook(self.excel_path)
            analysis_sheet = wb['Analysis']
            
            # Find the Subject Vocabulary Terms column (from Step 2)
            subject_vocab_col = None
            for col in range(1, analysis_sheet.max_column + 1):
                header_value = analysis_sheet.cell(row=1, column=col).value
                if header_value and "Subject Vocabulary Terms" in str(header_value):
                    subject_vocab_col = col
                    break
            
            if subject_vocab_col is None:
                logging.error("Subject Vocabulary Terms column not found. Please run Step 2 first.")
                return False
            
            # Update header to reflect that these are selected terms
            header_cell = analysis_sheet.cell(row=1, column=subject_vocab_col)
            # double-check that this is a Cell and not a MergedCell
            if isinstance(header_cell, Cell):    
                header_cell.value = "Selected Subject Vocabulary Terms"
            
            # Get the data for processing
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            
            updated_rows = 0
            for entry_index, result_data in selection_results.items():
                row_num = entry_index + 2  # +2 for header row
                
                # Get final selected terms
                if entry_index < len(data_items):
                    selected_vocab_terms = data_items[entry_index]['analysis'].get('final_selected_terms', [])
                    
                    # Format for Excel display
                    if selected_vocab_terms:
                        formatted_terms = []
                        for term in selected_vocab_terms:
                            if isinstance(term, dict):
                                label = term.get('label', '')
                                uri = term.get('uri', '')
                                source = term.get('source', '')
                                if label and uri:
                                    formatted_terms.append(f"{label} ({uri}) [{source}]")
                                elif label:
                                    formatted_terms.append(f"{label} [{source}]")
                        
                        cell_value = "; ".join(formatted_terms)
                        updated_rows += 1
                    else:
                        cell_value = ""
                else:
                    cell_value = ""
                
                # Set the cell value
                cell = analysis_sheet.cell(row=row_num, column=subject_vocab_col)
                if isinstance(cell, Cell):
                    cell.value = cell_value 
                cell.alignment = Alignment(vertical='top', wrap_text=True)
            
            # Clear vocabulary terms for entries that weren't processed
            for row_num in range(2, analysis_sheet.max_row + 1):
                entry_index = row_num - 2
                if entry_index not in selection_results:
                    cell = analysis_sheet.cell(row=row_num, column=subject_vocab_col)
                    if not isinstance(cell, Cell):
                        continue
                    cell.value = ""
            
            # Save the updated workbook
            wb.save(self.excel_path)
            print(f"Updated Excel file with selected vocabulary terms in {updated_rows} rows")
            return True
            
        except Exception as e:
            logging.error(f"Error updating Excel file: {e}")
            return False

    def create_vocabulary_mapping_report(self, selection_results: Dict[int, Dict[str, Any]]) -> bool:
        """
        Create a dissertation-level vocabulary selection report.

        For each dissertation entry, this report shows:
          - Free-text subjects
          - Candidate controlled terms per subject (from Step 2)
          - Selected controlled terms (from Step 3)
        """
        try:
            # Save vocabulary report in the collection_metadata folder
            metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            report_path = os.path.join(metadata_dir, "vocabulary_selection_report.txt")
            
            # Skip the last item if it's API stats
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("DISSERTATION VOCABULARY SELECTION REPORT (STEP 3)\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Workflow Type: {self.workflow_type.upper()}\n\n")
                
                for i, item in enumerate(data_items):
                    analysis = item.get('analysis', {})
                    title = analysis.get('title', 'Unknown title')
                    subjects_value = analysis.get('subjects', [])
                    vocab_search_results = analysis.get('vocabulary_search_results', {})
                    final_selected_terms = analysis.get('final_selected_terms', [])
                    
                    # Normalize subjects to list
                    if isinstance(subjects_value, str):
                        subjects = [s.strip() for s in subjects_value.split(',') if s.strip()]
                    else:
                        subjects = subjects_value if isinstance(subjects_value, list) else []
                    
                    f.write(f"ENTRY {i}:\n")
                    f.write(f"Title: {title}\n")
                    if subjects:
                        f.write(f"Subjects (free-text): {', '.join(subjects)}\n")
                    else:
                        f.write("Subjects (free-text): None\n")
                    f.write("-" * 60 + "\n")
                    
                    # Candidate terms per subject
                    if vocab_search_results:
                        f.write("CANDIDATE CONTROLLED TERMS BY SUBJECT (from Step 2):\n")
                        for subject, terms in vocab_search_results.items():
                            f.write(f"  Subject: {subject}\n")
                            if terms:
                                for term in terms:
                                    if isinstance(term, dict):
                                        label = term.get('label', '')
                                        uri = term.get('uri', '')
                                        source = term.get('source', '')
                                        if uri:
                                            f.write(f"    - {label} ({uri}) [{source}]\n")
                                        else:
                                            f.write(f"    - {label} [{source}]\n")
                            else:
                                f.write("    - No candidate terms\n")
                            f.write("\n")
                    else:
                        f.write("No candidate controlled terms found for this entry (Step 2).\n\n")
                    
                    # Selected terms
                    if final_selected_terms:
                        f.write("SELECTED CONTROLLED TERMS (Step 3):\n")
                        for term in final_selected_terms:
                            if isinstance(term, dict):
                                label = term.get('label', '')
                                uri = term.get('uri', '')
                                source = term.get('source', '')
                                if uri:
                                    f.write(f"  - {label} ({uri}) [{source}]\n")
                                else:
                                    f.write(f"  - {label} [{source}]\n")
                        f.write("\n")
                    else:
                        f.write("No controlled terms selected for this entry.\n\n")
                    
                    f.write("=" * 60 + "\n\n")
            
            print(f"Created vocabulary selection report: {report_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error creating vocabulary selection report: {e}")
            return False

    def run(self) -> bool:
        """
        Main execution method for Step 3: vocabulary selection for dissertations.

        Uses a small LLM to select controlled vocabulary terms from the candidate
        headings produced in Step 2, then updates JSON/Excel and logs usage.
        """
        print(f"\nDISSERTATION STEP 3 - VOCABULARY SELECTION")
        print(f"Processing folder: {self.folder_path}")
        print(f"Model: {self.model_name}")
        print("-" * 50)
        
        # Detect workflow type and confirm Step 2 has run
        if not self.detect_workflow_type():
            return False
        
        print(f"Detected workflow type: {self.workflow_type.upper()}")
        
        # Load JSON data and verify vocabulary terms exist
        if not self.load_json_data():
            return False
        
        # Find entries with vocabulary terms
        entries_with_vocab = self.find_entries_with_vocabulary()
        if not entries_with_vocab:
            print("No entries with vocabulary terms found (analysis['vocabulary_search_results'] is empty).")
            return False
        
        print(f"Found {len(entries_with_vocab)} entries with vocabulary terms")
        
        # Show model pricing info
        model_info = get_model_info(self.model_name)
        if model_info:
            print(f"Pricing: ${model_info['input_per_1k']:.5f}/1K input, ${model_info['output_per_1k']:.5f}/1K output")
        
        # Process vocabulary selection
        print(f"\nSelecting best controlled vocabulary terms for each dissertation entry...")
        selection_results = self.process_vocabulary_selection(entries_with_vocab)
        
        if not selection_results:
            print("Vocabulary selection failed or returned no results.")
            return False
        
        # Update JSON data with selected terms only
        if not self.update_json_data(selection_results):
            return False
        
        # Update Excel file with selected terms only
        if not self.update_excel_file(selection_results):
            return False
        
        # Create a vocabulary selection report (optional but useful)
        if not self.create_vocabulary_mapping_report(selection_results):
            return False
        
        # Calculate and log final metrics
        total_processing_time = sum(result.get('processing_time', 0) for result in selection_results.values())
        
        # Calculate cost
        estimated_cost = calculate_cost(
            model_name=self.model_name,
            prompt_tokens=api_stats.total_input_tokens,
            completion_tokens=api_stats.total_output_tokens,
            is_batch=self.was_batch_processed
        )
        
        # Create logs folder and token usage log
        logs_folder_path = os.path.join(self.folder_path, "logs")
        if not os.path.exists(logs_folder_path):
            os.makedirs(logs_folder_path)
        
        create_token_usage_log(
            logs_folder_path=logs_folder_path,
            script_name="dissertation_vocabulary_selection",
            model_name=self.model_name,
            total_items=len(selection_results),
            items_with_issues=0,  # you can refine this if you track per-entry errors
            total_time=total_processing_time,
            total_prompt_tokens=api_stats.total_input_tokens,
            total_completion_tokens=api_stats.total_output_tokens,
            additional_metrics={
                "Processing mode": "BATCH" if self.was_batch_processed else "INDIVIDUAL",
                "Actual cost": f"${estimated_cost:.4f}",
                "Average tokens per entry": f"{(api_stats.total_input_tokens + api_stats.total_output_tokens)/len(selection_results):.0f}" if selection_results else "0",
                "Batch processing used": "Yes" if self.was_batch_processed else "No"
            }
        )
        
        # Show final summary
        total_selected = sum(len(result['selection_result'].get('selected_terms', [])) for result in selection_results.values())
        entries_with_selections = sum(1 for result in selection_results.values() if result['selection_result'].get('selected_terms'))
        
        print("\n" + "=" * 50)
        print("FINAL SUMMARY:")
        print(f"\n ✅ STEP 3 COMPLETE: Selected vocabulary terms in {os.path.basename(self.folder_path)}")
        print(f"Updated Excel/JSON and vocabulary selection report created")
        print(f"Entries processed: {len(selection_results)}")
        print(f"Total vocabulary terms selected: {total_selected}")
        print(f"Entries with selections: {entries_with_selections}/{len(selection_results)}")
        print(f"Selection rate: {(entries_with_selections/len(selection_results)*100):.1f}%")
        print(f"Total tokens: {api_stats.total_input_tokens + api_stats.total_output_tokens:,}")
        print(f"Estimated cost: ${estimated_cost:.4f}")
        
        return True

def main():
    
    # Default base directory for dissertation output folders (from Steps 1 and 2)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_output_dir = os.path.join(script_dir, "output_folders")

    # Allow overriding the model via environment variable; default to DEFAULT_MODEL
    model_name = os.getenv('MODEL_NAME', DEFAULT_MODEL)

    # Default folder path (newest folder if not specified)
    folder_path = find_newest_folder(base_output_dir)
    if not folder_path:
        print(f"No folders found in: {base_output_dir}")
        return 1
    print(f"Auto-selected newest folder: {os.path.basename(folder_path)}")

    # Create and run the processor
    processor = DissertationVocabularyProcessor(folder_path, model_name)
    success = processor.run()
    
    if not success:
        print("Vocabulary selection (Step 3) failed")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())                                