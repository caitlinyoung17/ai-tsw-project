# Controlled Vocabulary API querying - LCSH, FAST, Getty AAT/TGN Subject Headings

import os
import json
import logging
import time
from openpyxl.cell import Cell
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Tuple
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from collections import defaultdict
import re
from shared_utilities import find_newest_folder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_vocab_api_usage_log(logs_folder_path: str, script_name: str, total_subjects: int, 
                               api_stats: Dict[str, Any]) -> bool:
    """
    Create vocabulary API usage log for dissertation subject and geographic term lookups.
    """
    try:
        log_filename = f"{script_name}_vocab_api_usage_log.txt"
        log_path = os.path.join(logs_folder_path, log_filename)
        
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("DISSERTATION VOCABULARY API USAGE LOG\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Script: {script_name}\n\n")
            
            # Summary statistics
            f.write("SUMMARY STATISTICS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Total subjects processed: {total_subjects}\n")
            f.write(f"Total API requests made: {api_stats.get('total_requests', 0)}\n")
            f.write(f"Total processing time: {api_stats.get('total_time', 0):.2f} seconds\n")
            f.write(f"Average time per subject: {api_stats.get('avg_time_per_subject', 0):.2f} seconds\n\n")
            
            # API-specific statistics
            for api_name, stats in api_stats.get('api_breakdown', {}).items():
                f.write(f"{api_name.upper()} API STATISTICS:\n")
                f.write("-" * (len(api_name) + 16) + "\n")
                f.write(f"Requests made: {stats.get('requests', 0)}\n")
                f.write(f"Successful responses: {stats.get('successful', 0)}\n")
                f.write(f"Failed responses: {stats.get('failed', 0)}\n")
                f.write(f"Success rate: {stats.get('success_rate', 0):.1f}%\n")
                f.write(f"Total processing time: {stats.get('total_time', 0):.2f} seconds\n")
                f.write(f"Average time per request: {stats.get('avg_time', 0):.2f} seconds\n")
                f.write(f"Terms found: {stats.get('terms_found', 0)}\n")
                f.write(f"Cache hits: {stats.get('cache_hits', 0)}\n\n")
            
            # Subject-level results summary
            f.write("SUBJECT PROCESSING RESULTS:\n")
            f.write("-" * 25 + "\n")
            subject_results = api_stats.get('subject_results', {})
            for subject, result in subject_results.items():
                f.write(f"Subject: {subject}\n")
                f.write(f"  Total terms found: {result.get('total_terms', 0)}\n")
                for api_name, count in result.get('terms_by_api', {}).items():
                    f.write(f"  {api_name}: {count} terms\n")
                f.write(f"  Processing time: {result.get('processing_time', 0):.2f}s\n\n")
        
        print(f"Vocabulary API usage log created: {log_path}")
        return True
        
    except Exception as e:
        logging.error(f"Error creating vocabulary API usage log: {e}")
        return False
    
def log_individual_vocab_response(logs_folder_path: str, script_name: str, subject: str, 
                                  api_name: str, query: str, response_data: List[Dict], 
                                  processing_time: float, error: str = "") -> bool:
    """
    Log individual vocabulary API response for a single subject term or geographic entity.
    """
    try:
        log_filename = f"{script_name}_vocab_full_responses_log.txt"
        log_path = os.path.join(logs_folder_path, log_filename)
        
        # Create file with header if it doesn't exist
        if not os.path.exists(log_path):
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("DISSERTATION VOCABULARY API DETAILED RESPONSES LOG\n")
                f.write("=" * 60 + "\n\n")
        
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"API: {api_name}\n")
            f.write(f"QUERY: {query}\n")
            f.write(f"PROCESSING TIME: {processing_time:.3f}s\n")
            
            if error:
                f.write(f"ERROR: {error}\n")
                f.write("RESPONSE: Failed\n")
            else:
                f.write(f"TERMS FOUND: {len(response_data)}\n")
                f.write("RESPONSE:\n")
                for i, term in enumerate(response_data, 1):
                    label = term.get('label', 'N/A')
                    uri = term.get('uri', 'N/A')
                    source = term.get('source', 'N/A')
                    f.write(f"  {i}. {label}\n")
                    f.write(f"     URI: {uri}\n")
                    f.write(f"     Source: {source}\n")
            
            f.write("-" * 60 + "\n\n")
        
        return True
        
    except Exception as e:
        logging.error(f"Error logging individual vocabulary response: {e}")
        return False    
    
class APIStatsTracker:
    """Track API statistics across all vocabulary services."""
    
    def __init__(self):
        self.start_time = time.time()
        self.api_breakdown = {
            'LCSH': {'requests': 0, 'successful': 0, 'failed': 0, 'total_time': 0.0, 'terms_found': 0, 'cache_hits': 0},
            'FAST': {'requests': 0, 'successful': 0, 'failed': 0, 'total_time': 0.0, 'terms_found': 0, 'cache_hits': 0},
            'FAST Geographic': {'requests': 0, 'successful': 0, 'failed': 0, 'total_time': 0.0, 'terms_found': 0, 'cache_hits': 0},
            'Getty AAT': {'requests': 0, 'successful': 0, 'failed': 0, 'total_time': 0.0, 'terms_found': 0, 'cache_hits': 0},
            'Getty TGN': {'requests': 0, 'successful': 0, 'failed': 0, 'total_time': 0.0, 'terms_found': 0, 'cache_hits': 0}
        }
        
        self.subject_results = {}
        self.geographic_results = {}  # Track geographic results separately if needed
        self.total_requests = 0
    
    def record_api_call(self, api_name: str, subject: str, query: str, success: bool, 
                        processing_time: float, terms_found: int, from_cache: bool = False):
        """Record an API call for a given subject term or geographic entity."""
        if api_name in self.api_breakdown:
            stats = self.api_breakdown[api_name]
            stats['requests'] += 1
            stats['total_time'] += processing_time
            
            if from_cache:
                stats['cache_hits'] += 1
            
            if success:
                stats['successful'] += 1
                stats['terms_found'] += terms_found
            else:
                stats['failed'] += 1
        
        # Track subject-level results
        if subject not in self.subject_results:
            self.subject_results[subject] = {
                'total_terms': 0,
                'terms_by_api': defaultdict(int),
                'processing_time': 0
            }
        
        self.subject_results[subject]['terms_by_api'][api_name] += terms_found
        self.subject_results[subject]['total_terms'] += terms_found
        self.subject_results[subject]['processing_time'] += processing_time
        
        self.total_requests += 1
    
    def get_summary_stats(self, total_subjects: int) -> Dict[str, Any]:
        """Get summary statistics."""
        total_time = time.time() - self.start_time
        
        # Calculate success rates for each API
        for api_name in self.api_breakdown:
            stats = self.api_breakdown[api_name]
            total_api_requests = stats['requests']
            if total_api_requests > 0:
                stats['success_rate'] = (stats['successful'] / total_api_requests) * 100
                stats['avg_time'] = stats['total_time'] / total_api_requests
            else:
                stats['success_rate'] = 0
                stats['avg_time'] = 0
        
        return {
            'total_requests': self.total_requests,
            'total_time': total_time,
            'avg_time_per_subject': total_time / total_subjects if total_subjects > 0 else 0,
            'subject_results': self.subject_results,
            'api_breakdown': self.api_breakdown
        }

class FASTTermFinder:
    """FAST term finder for dissertation subjects and geographic entities."""
    
    def __init__(self, wskey=None, stats_tracker=None, logs_folder_path=None):
        # Updated API endpoints
        self.suggest_url = "https://fast.oclc.org/searchfast/fastsuggest"
        self.search_url = "http://fast.oclc.org/search"
        
        self.headers = {
            'User-Agent': 'Python-FAST-Term-Finder/1.0 (Educational/Research Use)'
        }
        self.max_results = 3      # Strict limit to 3 terms per subject
        self.max_geo_results = 1  # Strict limit to 1 geographic term
        self.request_delay = 0.5
        self.cache = {}
        self.wskey = wskey  # OCLC WSKey for authentication (optional)
        self.stats_tracker = stats_tracker
        self.logs_folder_path = logs_folder_path
        
    def search(self, query: str, subject: str = "") -> List[Dict[str, str]]:
        """Search FAST for subject terms using the updated API format with logging."""
        cache_key = f"fast_new_{query}"
        from_cache = cache_key in self.cache
        
        start_time = time.time()
        
        if from_cache:
            results = self.cache[cache_key]
            processing_time = time.time() - start_time
            
            # Log cache hit
            if self.stats_tracker:
                self.stats_tracker.record_api_call(
                    'FAST', subject or query, query, True, processing_time, len(results), from_cache=True
                )
            
            if self.logs_folder_path:
                log_individual_vocab_response(
                    self.logs_folder_path,
                    "dissertation_step2",          # updated script name
                    subject or query,
                    "FAST",
                    f"{query} (CACHED)",
                    results,
                    processing_time
                )
            
            return results
        
        results = []
        error_msg = ""
        
        try:
            # Try method 1: New suggest API without WSKey (usually works)
            results = self._try_suggest_api(query)
            
            # Try method 2: If no results and multi-word, try key terms
            if not results and ' ' in query:
                words = query.split()
                for word in words:
                    if len(word) > 3:  # Skip short words
                        word_results = self._try_suggest_api(word)
                        # Filter word results for relevance to original query
                        for result in word_results:
                            if self._is_relevant_to_query(result, query):
                                results.append(result)
                        if len(results) >= self.max_results:  # Stop when we have enough
                            break
            
            # Remove duplicates based on URI and STRICT LIMIT TO 3
            seen_uris = set()
            unique_results = []
            for result in results:
                if result['uri'] not in seen_uris and len(unique_results) < self.max_results:
                    unique_results.append(result)
                    seen_uris.add(result['uri'])
            
            results = unique_results
            success = True
            
        except Exception as e:
            error_msg = str(e)
            success = False
            results = []
        
        processing_time = time.time() - start_time
        
        # Cache results
        self.cache[cache_key] = results
        
        # Log the API call
        if self.stats_tracker:
            self.stats_tracker.record_api_call(
                'FAST', subject or query, query, success, processing_time, len(results)
            )
        
        if self.logs_folder_path:
            log_individual_vocab_response(
                self.logs_folder_path,
                "dissertation_step2",          # updated script name
                subject or query,
                "FAST",
                query,
                results,
                processing_time,
                error_msg
            )
        
        time.sleep(self.request_delay)
        return results
    
    def search_geographic(self, query: str, entity: str = "") -> List[Dict[str, str]]:
        """Search FAST for geographic entities with additional metadata and logging."""
        cache_key = f"fast_geo_{query}"
        from_cache = cache_key in self.cache
        
        start_time = time.time()
        
        if from_cache:
            results = self.cache[cache_key]
            processing_time = time.time() - start_time
            
            if self.stats_tracker:
                self.stats_tracker.record_api_call(
                    'FAST Geographic', entity or query, query, True, processing_time, len(results), from_cache=True
                )
            
            if self.logs_folder_path:
                log_individual_vocab_response(
                    self.logs_folder_path,
                    "dissertation_step2",
                    entity or query,
                    "FAST Geographic",
                    f"{query} (CACHED)",
                    results,
                    processing_time
                )
            
            return results
        
        results: List[Dict[str, str]] = []
        error_msg = ""
        
        try:
            # Try method 1: Suggest API focusing on geographic facets
            params = {
                'query': query,
                'queryReturn': 'suggestall,idroot,auth,type,tag',
                'suggest': 'autoSubject',
                'rows': self.max_geo_results * 2,
                'sort': 'usage desc',
                'facet': 'type',
                'facet.field': 'type',
                'fq': 'type:Geographic'
            }
            
            if self.wskey:
                params['wskey'] = self.wskey
            
            resp = requests.get(self.suggest_url, params=params, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            results = self._parse_geographic_response(data)
            
            # If no results with geographic filter, try broader search
            if not results:
                params.pop('fq', None)  # Remove geographic filter
                resp = requests.get(self.suggest_url, params=params, headers=self.headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                # Parse and filter for geographic relevance
                all_results = self._parse_geographic_response(data)
                results = [r for r in all_results if self._is_geographic_relevant(r, query)][:self.max_geo_results]
            
            success = True
            
        except Exception as e:
            error_msg = str(e)
            success = False
            results = []
        
        processing_time = time.time() - start_time
        
        # Cache results
        self.cache[cache_key] = results
        
        # Log the API call
        if self.stats_tracker:
            self.stats_tracker.record_api_call(
                'FAST Geographic', entity or query, query, success, processing_time, len(results)
            )
        
        if self.logs_folder_path:
            log_individual_vocab_response(
                self.logs_folder_path,
                "dissertation_step2",
                entity or query,
                "FAST Geographic",
                query,
                results,
                processing_time,
                error_msg
            )
        
        time.sleep(self.request_delay)
        return results

    def _try_suggest_api(self, query: str) -> List[Dict[str, str]]:
        """Try the suggest API with the working parameters."""
        params = {
            'query': query,
            'queryReturn': 'suggestall,idroot,auth,type',
            'suggest': 'autoSubject',
            'rows': self.max_results * 2,  # Get a few more to filter
            'sort': 'usage desc'
        }
        
        # Add WSKey if available
        if self.wskey:
            params['wskey'] = self.wskey
        
        resp = requests.get(self.suggest_url, params=params, headers=self.headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        return self._parse_suggest_response(data)
    
    def _parse_suggest_response(self, data: dict) -> List[Dict[str, str]]:
        """Parse the suggest API response format."""
        results = []
        
        if 'response' in data and 'docs' in data['response']:
            docs = data['response']['docs']
            
            for doc in docs:
                if len(results) >= self.max_results:
                    break
                
                # Extract fields from response
                suggest_all = doc.get('suggestall', '')
                id_root = doc.get('idroot', '')
                auth = doc.get('auth', '')
                doc_type = doc.get('type', '')
                
                # Handle fields that might be lists or strings
                if isinstance(id_root, list) and id_root:
                    id_root = id_root[0]
                elif not isinstance(id_root, str):
                    id_root = str(id_root) if id_root else ''
                
                if isinstance(suggest_all, list) and suggest_all:
                    suggest_all = suggest_all[0]
                elif not isinstance(suggest_all, str):
                    suggest_all = str(suggest_all) if suggest_all else ''
                
                if isinstance(auth, list) and auth:
                    auth = auth[0]
                elif not isinstance(auth, str):
                    auth = str(auth) if auth else ''
                
                if isinstance(doc_type, list) and doc_type:
                    doc_type = doc_type[0]
                elif not isinstance(doc_type, str):
                    doc_type = str(doc_type) if doc_type else ''
                
                # Only include if we have the essential fields
                if suggest_all and id_root:
                    results.append({
                        'label': auth if auth else suggest_all,
                        'uri': f"http://id.worldcat.org/fast/{id_root}",
                        'type': doc_type,
                        'source': 'FAST',
                        'idroot': id_root
                    })
        
        return results

    def _parse_geographic_response(self, data: dict) -> List[Dict[str, str]]:
        """Parse the geographic API response format with additional metadata."""
        results = []
        
        if 'response' in data and 'docs' in data['response']:
            docs = data['response']['docs']
            
            for doc in docs:
                if len(results) >= self.max_geo_results:  # CHANGED: Use max_geo_results
                    break
                
                # Extract fields from response
                suggest_all = doc.get('suggestall', '')
                id_root = doc.get('idroot', '')
                auth = doc.get('auth', '')
                doc_type = doc.get('type', '')
                tag = doc.get('tag', '')
                
                # Handle fields that might be lists or strings
                if isinstance(id_root, list) and id_root:
                    id_root = id_root[0]
                elif not isinstance(id_root, str):
                    id_root = str(id_root) if id_root else ''
                
                if isinstance(suggest_all, list) and suggest_all:
                    suggest_all = suggest_all[0]
                elif not isinstance(suggest_all, str):
                    suggest_all = str(suggest_all) if suggest_all else ''
                
                if isinstance(auth, list) and auth:
                    auth = auth[0]
                elif not isinstance(auth, str):
                    auth = str(auth) if auth else ''
                
                if isinstance(doc_type, list) and doc_type:
                    doc_type = doc_type[0]
                elif not isinstance(doc_type, str):
                    doc_type = str(doc_type) if doc_type else ''
                
                if isinstance(tag, list):
                    tag = ', '.join(str(t) for t in tag if t)
                elif not isinstance(tag, str):
                    tag = str(tag) if tag else ''
                
                # Only include if we have the essential fields
                if suggest_all and id_root:
                    result = {
                        'label': auth if auth else suggest_all,
                        'uri': f"http://id.worldcat.org/fast/{id_root}",
                        'type': doc_type,
                        'source': 'FAST Geographic',
                        'idroot': id_root
                    }
                    
                    # Add additional metadata for geographic entities
                    if tag:
                        result['tag'] = tag
                        result['sources_and_links'] = tag  # For vocabulary mapping report
                    
                    results.append(result)
        
        return results
    
    def _is_relevant_to_query(self, result: Dict[str, str], original_query: str) -> bool:
        """Check if a result from word search is relevant to original query."""
        query_words = set(w.lower() for w in original_query.split())
        result_words = set(w.lower() for w in result['label'].split())
        
        # Check for word overlap - any shared words indicate relevance
        label_overlap = len(query_words.intersection(result_words))
        
        # Include if there's any word overlap
        return label_overlap > 0
    
    def _is_geographic_relevant(self, result: Dict[str, str], original_query: str) -> bool:
        """Check if a result is geographically relevant."""
        query_words = set(w.lower() for w in original_query.split())
        result_words = set(w.lower() for w in result['label'].split())
        
        # Check for word overlap - any shared words indicate relevance
        label_overlap = len(query_words.intersection(result_words))
        
        # Also check if the type field indicates it's geographic
        type_field = result.get('type', '').lower()
        is_geographic_type = 'geographic' in type_field
        
        # Include if there's word overlap OR if it's explicitly marked as geographic
        return label_overlap > 0 or is_geographic_type
    
    def find_terms(self, subjects: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Find FAST terms for multiple subjects with the updated API."""
        if not subjects:
            return {}
            
        results = {}
        
        for subject in subjects:
            if not subject or subject.strip() == "":
                continue
                
            subject = subject.strip()
            
            # Skip if already processed
            if subject in results:
                continue
                
            # Search for terms - STRICT LIMIT TO 3
            fast_results = self.search(subject, subject)[:self.max_results]
            results[subject] = fast_results
            
            if fast_results:
                print(f"   Found {len(fast_results)} FAST terms for '{subject}'")
            else:
                print(f"   No FAST terms found for '{subject}'")
        
        return results

    def find_geographic_terms(self, geographic_entities: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Find FAST geographic terms for multiple entities."""
        if not geographic_entities:
            return {}
            
        results = {}
        
        for entity in geographic_entities:
            if not entity or entity.strip() == "":
                continue
                
            entity = entity.strip()
            
            # Skip if already processed
            if entity in results:
                continue
            
            # Extract the searchable part by removing the type in parentheses
            # e.g., "Baltimore--Maryland (City)" becomes "Baltimore--Maryland"
            search_term = entity
            if '(' in entity and entity.endswith(')'):
                # Find the last opening parenthesis and remove everything from there
                paren_index = entity.rfind('(')
                if paren_index > 0:
                    search_term = entity[:paren_index].strip()
                        
            # Search for geographic terms using the cleaned search term - LIMITED TO 1 TERM
            fast_results = self.search_geographic(search_term, entity)[:self.max_geo_results]  
            results[entity] = fast_results  # Store under the original entity name
            
            if fast_results:
                print(f"   Found FAST geographic term for '{entity}'")  
            else:
                print(f"   No FAST geographic term found for '{entity}'")

        return results
    
class GettyTermFinder:
    """Getty Vocabularies term finder (AAT, ULAN, TGN) with broader search strategy and logging."""
    
    def __init__(self, stats_tracker=None, logs_folder_path=None):
        self.base_urls = {
            'AAT': 'http://vocabsservices.getty.edu/AATService.asmx/AATGetTermMatch',
            'ULAN': 'http://vocabsservices.getty.edu/ULANService.asmx/ULANGetTermMatch',
            'TGN': 'http://vocabsservices.getty.edu/TGNService.asmx/TGNGetTermMatch'
        }
        self.headers = {
            'User-Agent': 'Python-Getty-Term-Finder/1.0 (Educational/Research Use)'
        }
        self.max_results = 3  # Strict limit to 3 terms
        self.request_delay = 0.5
        self.cache = {}
        self.stats_tracker = stats_tracker
        self.logs_folder_path = logs_folder_path
    
    def search_aat(self, query: str, subject: str = "") -> List[Dict[str, str]]:
        """Search AAT (Art & Architecture Thesaurus) for terms with broader matching and logging."""
        cache_key = f"AAT_{query}"
        from_cache = cache_key in self.cache
        
        start_time = time.time()
        
        if from_cache:
            results = self.cache[cache_key]
            processing_time = time.time() - start_time
            
            if self.stats_tracker:
                self.stats_tracker.record_api_call(
                    'Getty AAT', subject or query, query, True, processing_time, len(results), from_cache=True
                )
            
            if self.logs_folder_path:
                log_individual_vocab_response(
                    self.logs_folder_path, "dissertation_step2", subject or query, 
                    "Getty AAT", f"{query} (CACHED)", results, processing_time
                )
            
            return results
        
        all_results = []
        error_msg = ""
        
        try:
            # Strategy 1: Exact term search
            params = {
                'term': query,
                'logop': 'and',
                'notes': ''
            }
            
            resp = requests.get(self.base_urls['AAT'], params=params, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            root = ET.fromstring(resp.content)
            
            # Parse XML response
            for subjectElement in root.findall('.//Subject'):
                if len(all_results) >= self.max_results:
                    break
                    
                subject_id = subjectElement.find('Subject_ID')
                preferred_term = subjectElement.find('Preferred_Term')
                
                if subject_id is not None and preferred_term is not None:
                    all_results.append({
                        'label': preferred_term.text,
                        'uri': f"http://vocab.getty.edu/aat/{subject_id.text}",
                        'source': 'Getty AAT',
                        'subject_id': subject_id.text
                    })
            
            # Strategy 2: If no results and multi-word query, try key terms
            if not all_results and ' ' in query:
                words = query.split()
                for word in words:
                    if len(word) > 3 and len(all_results) < self.max_results:  # Skip short words
                        params_word = {
                            'term': word,
                            'logop': 'and', 
                            'notes': ''
                        }
                        
                        try:
                            resp_word = requests.get(self.base_urls['AAT'], params=params_word, headers=self.headers, timeout=10)
                            resp_word.raise_for_status()
                            root_word = ET.fromstring(resp_word.content)
                            
                            for subjectElement in root_word.findall('.//Subject'):
                                if len(all_results) >= self.max_results:
                                    break
                                    
                                subject_id = subjectElement.find('Subject_ID')
                                preferred_term = subjectElement.find('Preferred_Term')
                                
                                if subject_id is not None and preferred_term is not None and preferred_term.text is not None:
                                    # Check if this result is relevant to original query
                                    term_lower = preferred_term.text.lower()
                                    query_words = set(w.lower() for w in query.split())
                                    term_words = set(w.lower() for w in preferred_term.text.split())
                                    
                                    # Include if there's word overlap or architectural relevance
                                    if (query_words.intersection(term_words) or 
                                        any(arch_word in term_lower for arch_word in ['architecture', 'architectural', 'building', 'style'])):
                                        all_results.append({
                                            'label': preferred_term.text,
                                            'uri': f"http://vocab.getty.edu/aat/{subject_id.text}",
                                            'source': 'Getty AAT',
                                            'subject_id': subject_id.text
                                        })
                        except:
                            continue  # Skip word if it fails
            
            success = True
            
        except Exception as e:
            error_msg = str(e)
            success = False
        
        processing_time = time.time() - start_time
        
        # Remove duplicates and STRICT LIMIT TO 3
        seen_uris = set()
        unique_results = []
        for result in all_results:
            if result['uri'] not in seen_uris and len(unique_results) < self.max_results:
                unique_results.append(result)
                seen_uris.add(result['uri'])
        
        results = unique_results
        self.cache[cache_key] = results
        
        # Log the API call
        if self.stats_tracker:
            self.stats_tracker.record_api_call(
                'Getty AAT', subject or query, query, success, processing_time, len(results)
            )
        
        if self.logs_folder_path:
            log_individual_vocab_response(
                self.logs_folder_path, "dissertation_step2", subject or query, 
                "Getty AAT", query, results, processing_time, error_msg
            )
        
        time.sleep(self.request_delay)
        return results
    
    def search_tgn(self, query: str, entity: str = "") -> List[Dict[str, str]]:
        """Search TGN (Thesaurus of Geographic Names) for terms with broader matching and logging."""
        cache_key = f"TGN_{query}"
        from_cache = cache_key in self.cache
        
        start_time = time.time()
        
        if from_cache:
            results = self.cache[cache_key]
            processing_time = time.time() - start_time
            
            if self.stats_tracker:
                self.stats_tracker.record_api_call(
                    'Getty TGN', entity or query, query, True, processing_time, len(results), from_cache=True
                )
            
            if self.logs_folder_path:
                log_individual_vocab_response(
                    self.logs_folder_path, "dissertation_step2", entity or query, 
                    "Getty TGN", f"{query} (CACHED)", results, processing_time
                )
            
            return results
        
        all_results = []
        error_msg = ""
        
        try:
            # Strategy 1: Exact search
            params = {
                'name': query,
                'placetypeid': '',
                'nationid': ''
            }
            
            resp = requests.get(self.base_urls['TGN'], params=params, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            root = ET.fromstring(resp.content)
            
            # Parse XML response
            for subject in root.findall('.//Subject'):
                if len(all_results) >= self.max_results:
                    break
                    
                subject_id = subject.find('Subject_ID')
                preferred_term = subject.find('Preferred_Term')
                
                if subject_id is not None and preferred_term is not None:
                    all_results.append({
                        'label': preferred_term.text,
                        'uri': f"http://vocab.getty.edu/tgn/{subject_id.text}",
                        'source': 'Getty TGN',
                        'subject_id': subject_id.text
                    })
            
            # Strategy 2: If no results and contains geographic terms, try broader search
            if not all_results:
                geographic_words = ['american', 'southern', 'northern', 'eastern', 'western', 'city', 'state', 'county']
                query_words = query.lower().split()
                
                for word in query_words:
                    if len(all_results) >= self.max_results:
                        break
                        
                    if word in geographic_words or len(word) > 4:
                        params_word = {
                            'name': word,
                            'placetypeid': '',
                            'nationid': ''
                        }
                        
                        try:
                            resp_word = requests.get(self.base_urls['TGN'], params=params_word, headers=self.headers, timeout=10)
                            resp_word.raise_for_status()
                            root_word = ET.fromstring(resp_word.content)
                            
                            for subject in root_word.findall('.//Subject'):
                                if len(all_results) >= self.max_results:
                                    break
                                    
                                subject_id = subject.find('Subject_ID')
                                preferred_term = subject.find('Preferred_Term')
                                
                                if subject_id is not None and preferred_term is not None:
                                    all_results.append({
                                        'label': preferred_term.text,
                                        'uri': f"http://vocab.getty.edu/tgn/{subject_id.text}",
                                        'source': 'Getty TGN',
                                        'subject_id': subject_id.text
                                    })
                        except:
                            continue
                        
                        if all_results:  # Stop after first successful word search
                            break
            
            success = True
            
        except Exception as e:
            error_msg = str(e)
            success = False
        
        processing_time = time.time() - start_time
        
        # Remove duplicates and LIMIT TO 3
        seen_uris = set()
        unique_results = []
        for result in all_results:
            if result['uri'] not in seen_uris and len(unique_results) < self.max_results:
                unique_results.append(result)
                seen_uris.add(result['uri'])
        
        results = unique_results
        self.cache[cache_key] = results
        
        # Log the API call
        if self.stats_tracker:
            self.stats_tracker.record_api_call(
                'Getty TGN', entity or query, query, success, processing_time, len(results)
            )
        
        if self.logs_folder_path:
            log_individual_vocab_response(
                self.logs_folder_path, "dissertation_step2", entity or query, 
                "Getty TGN", query, results, processing_time, error_msg
            )
        
        time.sleep(self.request_delay)
        return results
    
    def find_terms(self, subjects: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Find Getty terms for multiple subjects."""
        if not subjects:
            return {}
            
        results = {}
        
        for subject in subjects:
            if not subject or subject.strip() == "":
                continue
                
            subject = subject.strip()
            
            # Skip if already processed
            if subject in results:
                continue
                
            # Search AAT and TGN
            all_results = []
            
            # Search AAT (Art & Architecture Thesaurus)
            aat_results = self.search_aat(subject, subject)
            all_results.extend(aat_results)
            
            # Search TGN (Thesaurus of Geographic Names) - if we have room
            if len(all_results) < self.max_results:
                tgn_results = self.search_tgn(subject, subject)
                # Add TGN results up to the limit
                remaining_slots = self.max_results - len(all_results)
                all_results.extend(tgn_results[:remaining_slots])
            
            # LIMIT TO 3 TOTAL
            results[subject] = all_results[:self.max_results]
            
            if all_results:
                print(f"   Found {len(all_results)} Getty terms for '{subject}'")
            else:
                print(f"   No Getty terms found for '{subject}'")
        
        return results

class LOCAuthorizedTermFinder:
    """Enhanced LOC term finder with rate limiting, error handling, and logging."""
    
    def __init__(self, stats_tracker=None, logs_folder_path=None):
        self.base_url = "https://id.loc.gov/authorities/subjects/suggest2"
        self.headers = {
            'User-Agent': 'Python-LOC-Term-Finder/1.0 (Educational/Research Use)'
        }
        self.lcsh_authorized_headings = "http://id.loc.gov/authorities/subjects/collection_LCSHAuthorizedHeadings"
        self.max_results = 3  # Limit to 3 terms
        self.request_delay = 0.5
        self.cache = {}
        self.stats_tracker = stats_tracker
        self.logs_folder_path = logs_folder_path
        
    def search(self, query: str, search_type: str, subject: str = "") -> List[Dict[str, str]]:
        """Search LOC for authorized terms with logging."""
        cache_key = f"{query}_{search_type}"
        from_cache = cache_key in self.cache
        
        start_time = time.time()
        
        if from_cache:
            results = self.cache[cache_key]
            processing_time = time.time() - start_time
            
            if self.stats_tracker:
                self.stats_tracker.record_api_call(
                    'LCSH', subject or query, f"{query} ({search_type})", True, processing_time, len(results), from_cache=True
                )
            
            if self.logs_folder_path:
                log_individual_vocab_response(
                    self.logs_folder_path, "dissertation_step2", subject or query, 
                    "LCSH", f"{query} ({search_type}) (CACHED)", results, processing_time
                )
            
            return results
        
        params = {
            'q': query,
            'searchtype': search_type,
            'count': self.max_results,
            'memberOf': self.lcsh_authorized_headings
        }
        
        results = []
        error_msg = ""
        success = False
        
        try:
            resp = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get('hits', [])
            
            for h in hits:
                if len(results) >= self.max_results:
                    break
                if h.get('aLabel') and h.get('uri'):
                    results.append({
                        'label': h['aLabel'], 
                        'uri': h['uri'],
                        'source': 'LCSH'
                    })
            
            success = True
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            success = False
        
        processing_time = time.time() - start_time
        
        self.cache[cache_key] = results
        
        # Log the API call
        if self.stats_tracker:
            self.stats_tracker.record_api_call(
                'LCSH', subject or query, f"{query} ({search_type})", success, processing_time, len(results)
            )
        
        if self.logs_folder_path:
            log_individual_vocab_response(
                self.logs_folder_path, "dissertation_step2", subject or query, 
                "LCSH", f"{query} ({search_type})", results, processing_time, error_msg
            )
        
        time.sleep(self.request_delay)
        return results
    
    def find_terms(self, subjects: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Find LCSH terms for multiple subjects with logging."""
        if not subjects:
            return {}
            
        results = {}
        
        for subject in subjects:
            if not subject or subject.strip() == "":
                continue
                
            subject = subject.strip()
            
            # Skip if already processed
            if subject in results:
                continue
                
            # Try keyword search first
            keyword_results = self.search(subject, "keyword", subject)
            
            # If we need more results, try left-anchored search
            if len(keyword_results) < self.max_results:
                leftanchored_results = self.search(subject, "leftanchored", subject)
                
                # Merge results, avoiding duplicates
                existing_uris = {r['uri'] for r in keyword_results}
                for result in leftanchored_results:
                    if len(keyword_results) >= self.max_results:
                        break
                    if result['uri'] not in existing_uris:
                        keyword_results.append(result)
            
            # LIMIT TO 3
            results[subject] = keyword_results[:self.max_results]
            
            if keyword_results:
                print(f"   Found {len(keyword_results)} LCSH terms for '{subject}'")
            else:
                print(f"   No LCSH terms found for '{subject}'")
        
        return results
    
class DissertationVocabEnhancer:
    """
    Main class for enhancing dissertation metadata with multi-vocabulary terms
    (LCSH, FAST, Getty AAT/TGN) based on extracted subjects and geographic entities.
    """
    
    def __init__(self, folder_path: str):
        """
        folder_path: path to a single dissertation metadata output folder, e.g.
        CODE/output_folders/Dissertation_Metadata_Created_YYYY-MM-DD_Time_HH-MM-SS
        """
        self.folder_path = folder_path
        
        # Create logs folder
        self.logs_folder_path = os.path.join(folder_path, "logs")
        if not os.path.exists(self.logs_folder_path):
            os.makedirs(self.logs_folder_path)
        
        # Initialize stats tracker
        self.stats_tracker = APIStatsTracker()
        
        # Initialize finders with stats tracking and logging
        self.lcsh_finder = LOCAuthorizedTermFinder(self.stats_tracker, self.logs_folder_path)
        self.fast_finder = FASTTermFinder(stats_tracker=self.stats_tracker, logs_folder_path=self.logs_folder_path)
        self.getty_finder = GettyTermFinder(self.stats_tracker, self.logs_folder_path)
        
        self.workflow_type = None
        self.json_data = None
        self.excel_path = None
        self.max_terms_per_vocabulary = 3      # For subjects
        self.max_geo_terms_per_vocabulary = 1  # For geographic entities
        self.max_total_terms = 12              # 3 terms × 4 vocabularies = 12 max total for subjects
    
    def detect_workflow_type(self) -> bool:
        """
        Detect whether this folder contains text workflow files for dissertations.
        For dissertations we expect only text workflow (no image workflow).
        """
        metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        text_files = ['text_workflow.xlsx', 'text_workflow.json']
        
        has_text_files = all(os.path.exists(os.path.join(metadata_dir, f)) for f in text_files)
        
        if has_text_files:
            self.workflow_type = 'text'
            self.excel_path = os.path.join(metadata_dir, "text_workflow.xlsx")
            return True
        else:
            logging.error("No text workflow files (text_workflow.xlsx/json) found in the folder.")
            return False

    def load_json_data(self) -> bool:
        """Load the JSON data from the appropriate workflow file."""
        # Save the enhanced JSON in the collection_metadata folder
        json_filename = f"{self.workflow_type}_workflow.json"
        collection_metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        json_path = os.path.join(collection_metadata_dir, json_filename)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
            print(f"Loaded JSON data from {json_filename}")
            return True
        except Exception as e:
            logging.error(f"Error loading JSON data: {e}")
            return False
    
    def extract_subject_headings(self) -> tuple[List[str], List[str]]:
        """
        Extract all unique subjects and geographic entities from the JSON data.
        Returns (subjects, geographic_entities), each as a sorted list of unique strings.
        """
        all_subjects = set[str]()
        all_geographic_entities = set[str]()
    
        # Skip the last item if it's API stats
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data or []

        for item in data_items:
            if 'analysis' in item:
                analysis = item['analysis']
                
                # Extract subjects
                if 'subjects' in analysis:
                    subjects = analysis['subjects']
                    if isinstance(subjects, list):
                        for subject in subjects:
                            if subject and subject.strip():
                                all_subjects.add(subject.strip())
                    elif isinstance(subjects, str) and subjects.strip():
                        # Handle comma-separated string format
                        for subject in subjects.split(','):
                            if subject.strip():
                                all_subjects.add(subject.strip())
                
                # Extract geographic entities
                if 'geographic_entities' in analysis:
                    geo_entities = analysis['geographic_entities']
                    if isinstance(geo_entities, list):
                        for entity in geo_entities:
                            if entity and entity.strip():
                                all_geographic_entities.add(entity.strip())
                    elif isinstance(geo_entities, str) and geo_entities.strip():
                        # Handle comma-separated string format
                        for entity in geo_entities.split(','):
                            if entity.strip():
                                all_geographic_entities.add(entity.strip())
        
        sorted_subjects = sorted(list(all_subjects))
        sorted_geographic_entities = sorted(list(all_geographic_entities))
        return sorted_subjects, sorted_geographic_entities
        
    def process_multi_vocabulary_lookup(
        self,
        subjects: List[str],
        geographic_entities: List[str]
    ) -> Tuple[
        Dict[str, str],               # subject_to_terms_excel
        Dict[str, List[Dict[str, str]]],  # subject_to_terms_json
        Dict[str, str],               # geographic_to_terms_excel
        Dict[str, List[Dict[str, str]]]   # geographic_to_terms_json
    ]:
        """
        Process multi-vocabulary lookup for dissertation subjects and geographic entities.

        Returns:
            subject_to_terms_excel:  subject -> semicolon-separated string for Excel
            subject_to_terms_json:   subject -> list of term dicts (label, uri, source, ...)
            geographic_to_terms_excel: geographic entity -> semicolon-separated string for Excel
            geographic_to_terms_json:  geographic entity -> list of term dicts
        """
        
        print(f"\nProcessing multi-vocabulary lookup...")
        print(f"API calls will be logged to: {self.logs_folder_path}")
        
        # ----- Process subjects -----
        subject_to_terms_excel: Dict[str, str] = {}
        subject_to_terms_json: Dict[str, List[Dict[str, str]]] = {}
        
        for i, subject in enumerate(subjects, 1):
            if not subject or not subject.strip():
                continue
            subject = subject.strip()
            
            print(f"Processing subject {i}/{len(subjects)}: '{subject}'")
            
            # Search all vocabularies for THIS SPECIFIC subject
            all_terms: List[Dict[str, str]] = []
            
            # Search LCSH FIRST - LIMIT TO max_terms_per_vocabulary
            lcsh_results = self.lcsh_finder.find_terms([subject])
            if subject in lcsh_results:
                lcsh_terms = lcsh_results[subject][:self.max_terms_per_vocabulary]
                all_terms.extend(lcsh_terms)
            
            # Search FAST - LIMIT TO max_terms_per_vocabulary
            fast_results = self.fast_finder.find_terms([subject])
            if subject in fast_results:
                fast_terms = fast_results[subject][:self.max_terms_per_vocabulary]
                all_terms.extend(fast_terms)
            
            # Search Getty - LIMIT TO max_terms_per_vocabulary
            getty_results = self.getty_finder.find_terms([subject])
            if subject in getty_results:
                getty_terms = getty_results[subject][:self.max_terms_per_vocabulary]
                all_terms.extend(getty_terms)
                        
            # Format results for this subject
            formatted_terms_excel = self.format_results_for_excel(all_terms)
            formatted_terms_json = self.format_results_for_json(all_terms)
            
            # Store results for this specific subject
            subject_to_terms_excel[subject] = formatted_terms_excel
            subject_to_terms_json[subject] = formatted_terms_json
        
        # ----- Process geographic entities -----
        geographic_to_terms_excel: Dict[str, str] = {}
        geographic_to_terms_json: Dict[str, List[Dict[str, str]]] = {}
        
        for i, entity in enumerate(geographic_entities, 1):
            if not entity or not entity.strip():
                continue
            entity = entity.strip()
            
            print(f"\nProcessing geographic entity {i}/{len(geographic_entities)}: '{entity}'")
            
            # Search FAST Geographic only - LIMITED TO max_geo_terms_per_vocabulary
            fast_geo_results = self.fast_finder.find_geographic_terms([entity])
            if entity in fast_geo_results:
                geo_terms = fast_geo_results[entity][:self.max_geo_terms_per_vocabulary]
            else:
                geo_terms = []
                print(f"     No FAST Geographic term found")
            
            # Format results for this geographic entity
            formatted_terms_excel = self.format_results_for_excel(geo_terms)
            formatted_terms_json = self.format_results_for_json(geo_terms)
            
            # Store results for this specific geographic entity
            geographic_to_terms_excel[entity] = formatted_terms_excel
            geographic_to_terms_json[entity] = formatted_terms_json
        
        return (
            subject_to_terms_excel,
            subject_to_terms_json,
            geographic_to_terms_excel,
            geographic_to_terms_json
        )
            
    def format_results_for_excel(self, terms: List[Dict[str, str]]) -> str:
        """Format results for spreadsheet display with labels, URIs, and sources."""
        if not terms:
            return ""
        
        formatted_terms = []
        for term in terms:
            source = term.get('source', 'Unknown')
            label = term.get('label', '')
            uri = term.get('uri', '')
            
            if label and uri:
                formatted_terms.append(f"{label} ({uri}) [{source}]")
            elif label:
                formatted_terms.append(f"{label} [{source}]")
        
        return "; ".join(formatted_terms)
    
    def format_results_for_json(self, terms: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Format results for JSON storage with full structure."""
        if not terms:
            return []
        
        formatted_terms = []
        seen_uris = set()
        
        for term in terms:
            uri = term.get('uri', '')
            if uri and uri not in seen_uris:
                formatted_terms.append({
                    'label': term.get('label', ''),
                    'uri': uri,
                    'source': term.get('source', 'Unknown'),
                    'description': term.get('description', ''),
                    'qid': term.get('qid', ''),
                    'subject_id': term.get('subject_id', ''),
                    'type': term.get('type', ''),
                    'tag': term.get('tag', '')
                })
                seen_uris.add(uri)
        
        return formatted_terms
    
    def enhance_excel_file(
        self,
        subject_to_terms: Dict[str, str],
        geographic_to_terms: Dict[str, str]
    ) -> bool:
        """
        Add vocabulary terms columns to the Excel file for subjects and geographic entities.
        
        subject_to_terms:    subject -> semicolon-separated string for Excel
        geographic_to_terms: geographic entity -> semicolon-separated string for Excel
        """
        if not self.excel_path:
            return False

        try:
            # Load the existing workbook
            wb = load_workbook(self.excel_path)
            analysis_sheet = wb['Analysis']
            
            # Column indices in the dissertation Analysis sheet
            # 1: Filename, 2: Title, 3: Creator, 4: Date, 5: Department, 6: Abstract,
            # 7: Subjects, 8: Type, 9: Access, 10: Publisher, 11: Sponsor, 12: Language,
            # 13: Named Entities, 14: Geographic Entities, 15: Content Warning
            subject_col = 7            # Subjects column
            geo_col = 14               # Geographic Entities column
            insert_col = 16            # Insert vocab columns after Content Warning (column 15)
            
            # Insert TWO new columns:
            # one for subject vocab terms, one for geographic vocab terms
            analysis_sheet.insert_cols(insert_col, 2)
            
            # Add headers
            subject_vocab_header = analysis_sheet.cell(row=1, column=insert_col)
            geo_vocab_header = analysis_sheet.cell(row=1, column=insert_col + 1)

            if not isinstance(subject_vocab_header, Cell) or not isinstance(geo_vocab_header, Cell):
                return False
            subject_vocab_header.value = "Subject Vocabulary Terms (Max 3 per vocab per subject)"
            subject_vocab_header.alignment = Alignment(vertical='top', wrap_text=True)
            
            geo_vocab_header.value = "Geographic Vocabulary Terms (FAST only)"
            geo_vocab_header.alignment = Alignment(vertical='top', wrap_text=True)
            
            # Set column widths
            subject_col_letter = subject_vocab_header.column_letter
            geo_col_letter = geo_vocab_header.column_letter
            analysis_sheet.column_dimensions[subject_col_letter].width = 50
            analysis_sheet.column_dimensions[geo_col_letter].width = 50
            
            # Process each data row
            processed_rows = 0
            for row_num in range(2, analysis_sheet.max_row + 1):
                # Get the subjects and geographic entities from the current row
                subject_cell = analysis_sheet.cell(row=row_num, column=subject_col)
                geo_cell = analysis_sheet.cell(row=row_num, column=geo_col)
                
                subjects_value = subject_cell.value or ""
                geo_entities_value = geo_cell.value or ""
                
                # Process subject vocabulary terms
                subject_vocab_terms: list[str] = []
                if subjects_value and str(subjects_value).strip():
                    subjects = [s.strip() for s in str(subjects_value).split(',') if s.strip()]
                    print(f"Row {row_num-1}: Processing {len(subjects)} subjects: {subjects}")
                    
                    for subject in subjects:
                        if subject in subject_to_terms and subject_to_terms[subject]:
                            terms = [t.strip() for t in subject_to_terms[subject].split(';') if t.strip()]
                            subject_vocab_terms.extend(terms)
                            print(f"  - '{subject}': {len(terms)} terms")
                        else:
                            print(f"  - '{subject}': No terms found")
                
                # Process geographic entities vocabulary terms
                geo_vocab_terms: list[str] = []
                if geo_entities_value and str(geo_entities_value).strip():
                    entities = [e.strip() for e in str(geo_entities_value).split(',') if e.strip()]
                    print(f"Row {row_num-1}: Processing {len(entities)} geographic entities: {entities}")
                    
                    for entity in entities:
                        if entity in geographic_to_terms and geographic_to_terms[entity]:
                            terms = [t.strip() for t in geographic_to_terms[entity].split(';') if t.strip()]
                            geo_vocab_terms.extend(terms)
                            print(f"  - '{entity}': {len(terms)} geographic terms")
                        else:
                            print(f"  - '{entity}': No geographic terms found")
                
                # Remove duplicates while preserving order
                unique_subject_terms = []
                seen_subject = set()
                for term in subject_vocab_terms:
                    if term not in seen_subject:
                        unique_subject_terms.append(term)
                        seen_subject.add(term)
                
                unique_geo_terms = []
                seen_geo = set()
                for term in geo_vocab_terms:
                    if term not in seen_geo:
                        unique_geo_terms.append(term)
                        seen_geo.add(term)
                
                print(f"  → Total unique subject terms: {len(unique_subject_terms)}")
                print(f"  → Total unique geographic terms: {len(unique_geo_terms)}")
                
                # Set the vocabulary terms cell values
                subject_vocab_cell = analysis_sheet.cell(row=row_num, column=insert_col)
                geo_vocab_cell = analysis_sheet.cell(row=row_num, column=insert_col + 1)

                # quick type guard to ensure subject / geo vocab cells are Cell and not MergedCell type
                if not isinstance(subject_vocab_cell, Cell) or not isinstance(geo_vocab_cell, Cell):
                    continue

                subject_vocab_cell.value = "; ".join(unique_subject_terms) if unique_subject_terms else ""
                subject_vocab_cell.alignment = Alignment(vertical='top', wrap_text=True)
                
                geo_vocab_cell.value = "; ".join(unique_geo_terms) if unique_geo_terms else ""
                geo_vocab_cell.alignment = Alignment(vertical='top', wrap_text=True)
                
                if unique_subject_terms or unique_geo_terms:
                    processed_rows += 1
            
            # Save the enhanced workbook
            wb.save(self.excel_path)
            print(f"Enhanced Excel file saved with vocabulary terms in {processed_rows} rows")
            return True
            
        except Exception as e:
            logging.error(f"Error enhancing Excel file: {e}")
            return False

    def enhance_json_file(
        self,
        subject_to_terms_json: Dict[str, List[Dict[str, str]]], 
        geographic_to_terms_json: Dict[str, List[Dict[str, str]]]
    ) -> bool:
        """
        Add vocabulary search results to JSON file with subject-to-terms and geographic-to-terms mappings.

        subject_to_terms_json:    subject -> list of term dicts
        geographic_to_terms_json: geographic entity -> list of term dicts
        """
        try:
            # Skip the last item if it's API stats
            data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data or []
            api_stats = self.json_data[-1] if self.json_data and 'api_stats' in self.json_data[-1] else None
            
            enhanced_items = []
            processed_items = 0
            
            for item in data_items:
                if 'analysis' in item:
                    analysis = item['analysis']
                    
                    # Get subjects and geographic entities for this item
                    subjects_value = analysis.get('subjects', [])
                    geographic_entities_value = analysis.get('geographic_entities', [])
                    
                    # Normalize subjects to list format
                    if isinstance(subjects_value, str):
                        subjects = [s.strip() for s in subjects_value.split(',') if s.strip()]
                    else:
                        subjects = subjects_value if isinstance(subjects_value, list) else []
                    
                    # Normalize geographic entities to list format
                    if isinstance(geographic_entities_value, str):
                        geo_entities = [e.strip() for e in geographic_entities_value.split(',') if e.strip()]
                    else:
                        geo_entities = geographic_entities_value if isinstance(geographic_entities_value, list) else []
                    
                    # Create subject-to-terms mapping for this item
                    subject_to_terms = {}
                    for subject in subjects:
                        if subject in subject_to_terms_json and subject_to_terms_json[subject]:
                            subject_to_terms[subject] = subject_to_terms_json[subject].copy()
                    
                    # Create geographic-entity-to-terms mapping for this item
                    geographic_to_terms = {}
                    for entity in geo_entities:
                        if entity in geographic_to_terms_json and geographic_to_terms_json[entity]:
                            geographic_to_terms[entity] = geographic_to_terms_json[entity].copy()
                    
                    # Add mappings to the analysis
                    analysis['vocabulary_search_results'] = subject_to_terms
                    analysis['geographic_vocabulary_search_results'] = geographic_to_terms
                    
                    if subject_to_terms or geographic_to_terms:
                        processed_items += 1
                
                enhanced_items.append(item)
            
            # Add API stats back if it existed
            if api_stats:
                enhanced_items.append(api_stats)
            
            # Save the enhanced JSON in the collection_metadata folder
            json_filename = f"{self.workflow_type}_workflow.json"
            collection_metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            json_path = os.path.join(collection_metadata_dir, json_filename)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(enhanced_items, f, indent=2, ensure_ascii=False)
            
            print(f"Enhanced JSON file saved with vocabulary mappings for {processed_items} items")
            return True
            
        except Exception as e:
            logging.error(f"Error enhancing JSON file: {e}")
            return False
        
    def create_vocabulary_report(
        self,
        subject_to_terms: Dict[str, str], 
        geographic_to_terms: Dict[str, str]
    ) -> bool:
        """
        Create a dissertation-level vocabulary mapping report for subjects and geographic entities.
        
        subject_to_terms:    subject -> semicolon-separated string of vocab terms
        geographic_to_terms: geographic entity -> semicolon-separated string of vocab terms
        """
        try:
            # Save vocabulary report in the collection_metadata folder
            collection_metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            report_path = os.path.join(collection_metadata_dir, "vocabulary_mapping_report.txt")
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("DISSERTATION VOCABULARY MAPPING REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Workflow Type: {self.workflow_type or 'Unknown'.upper()}\n")
                f.write(f"Total Subjects Processed: {len(subject_to_terms)}\n")
                f.write(f"Total Geographic Entities Processed: {len(geographic_to_terms)}\n")
                f.write(f"Terms Per Vocabulary Limit: {self.max_terms_per_vocabulary}\n")
                f.write(f"Max Total Terms Per Subject: {self.max_total_terms}\n\n")
                
                f.write("VOCABULARIES SEARCHED:\n")
                f.write("FOR SUBJECTS:\n")
                f.write("- LCSH (Library of Congress Subject Headings)\n")
                f.write("- FAST (Faceted Application of Subject Terminology)\n")
                f.write("- Getty AAT (Art & Architecture Thesaurus)\n")
                f.write("- Getty TGN (Thesaurus of Geographic Names)\n")
                f.write("FOR GEOGRAPHIC ENTITIES:\n")
                f.write("- FAST Geographic (Faceted Application of Subject Terminology - Geographic)\n\n")
                
                # Statistics
                subjects_with_terms = sum(1 for terms in subject_to_terms.values() if terms)
                subjects_without_terms = len(subject_to_terms) - subjects_with_terms
                geo_with_terms = sum(1 for terms in geographic_to_terms.values() if terms)
                geo_without_terms = len(geographic_to_terms) - geo_with_terms
                
                f.write("STATISTICS:\n")
                f.write(f"- Subjects with vocabulary terms: {subjects_with_terms}\n")
                f.write(f"- Subjects without vocabulary terms: {subjects_without_terms}\n")
                if len(subject_to_terms) > 0:
                    f.write(f"- Subject success rate: {(subjects_with_terms/len(subject_to_terms)*100):.1f}%\n")
                else:
                    f.write("- Subject success rate: 0%\n")
                
                f.write(f"- Geographic entities with vocabulary terms: {geo_with_terms}\n")
                f.write(f"- Geographic entities without vocabulary terms: {geo_without_terms}\n")
                if len(geographic_to_terms) > 0:
                    f.write(f"- Geographic success rate: {(geo_with_terms/len(geographic_to_terms)*100):.1f}%\n\n")
                else:
                    f.write("- Geographic success rate: 0%\n\n")
                
                # Count terms by source for subjects
                subject_source_counts = {'LCSH': 0, 'FAST': 0, 'Getty AAT': 0, 'Getty TGN': 0}
                for terms_str in subject_to_terms.values():
                    if terms_str:
                        for term in terms_str.split(';'):
                            term = term.strip()
                            if '[LCSH]' in term:
                                subject_source_counts['LCSH'] += 1
                            elif '[FAST]' in term:
                                subject_source_counts['FAST'] += 1
                            elif '[Getty AAT]' in term:
                                subject_source_counts['Getty AAT'] += 1
                            elif '[Getty TGN]' in term:
                                subject_source_counts['Getty TGN'] += 1
                
                # Count terms by source for geographic entities
                geo_source_counts = {'FAST Geographic': 0}
                for terms_str in geographic_to_terms.values():
                    if terms_str:
                        for term in terms_str.split(';'):
                            term = term.strip()
                            if '[FAST Geographic]' in term:
                                geo_source_counts['FAST Geographic'] += 1
                
                f.write("SUBJECT TERMS BY SOURCE:\n")
                for source, count in subject_source_counts.items():
                    f.write(f"- {source}: {count} terms\n")
                f.write("\nGEOGRAPHIC TERMS BY SOURCE:\n")
                for source, count in geo_source_counts.items():
                    f.write(f"- {source}: {count} terms\n")
                f.write("\n")
                
                # Alphabetical subject reference
                f.write("ALPHABETICAL SUBJECT REFERENCE:\n")
                f.write("-" * 40 + "\n\n")
                
                for subject, vocab_terms in sorted(subject_to_terms.items()):
                    f.write(f"Subject: {subject}\n")
                    if vocab_terms:
                        f.write(f"Vocabulary Terms: {vocab_terms}\n")
                    else:
                        f.write("Vocabulary Terms: No terms found\n")
                    f.write("\n")
                
                # Alphabetical geographic entity reference
                f.write("ALPHABETICAL GEOGRAPHIC ENTITY REFERENCE:\n")
                f.write("-" * 45 + "\n\n")
                
                for entity, vocab_terms in sorted(geographic_to_terms.items()):
                    f.write(f"Geographic Entity: {entity}\n")
                    if vocab_terms:
                        f.write(f"Vocabulary Terms: {vocab_terms}\n")
                        if '[FAST Geographic]' in vocab_terms:
                            f.write("Note: FAST Geographic terms may include additional metadata in detailed API logs.\n")
                    else:
                        f.write("Vocabulary Terms: No terms found\n")
                    f.write("\n")
            
            print(f"Vocabulary mapping report created: {report_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error creating vocabulary report: {e}")
            return False

    def run(self) -> bool:
        """
        Main execution method for multi-vocabulary enhancement of dissertation metadata.
        Looks up controlled vocabulary terms for subjects and geographic entities,
        enhances the Excel and JSON outputs, and generates logs and a text report.
        """
        print(f"\nSTEP 2 - MULTI-VOCABULARY ENHANCEMENT (DISSERTATIONS)")
        print(f"Processing folder: {self.folder_path}")
        print(f"Maximum {self.max_terms_per_vocabulary} terms per vocabulary")
        print(f"Maximum {self.max_total_terms} terms total per subject")
        print(f"API log: {self.logs_folder_path}")
        print("-" * 50)
        
        # Detect workflow type (should be 'text' for dissertations)
        if not self.detect_workflow_type():
            return False
        
        print(f"Detected workflow type: {self.workflow_type or 'Unknown'.upper()}")
        
        # Load JSON data
        if not self.load_json_data():
            return False
        
        # Extract subjects and geographic entities
        subjects, geographic_entities = self.extract_subject_headings()

        if not subjects and not geographic_entities:
            print("No subjects or geographic entities found in the data")
            return False

        print(f"Found {len(subjects)} unique subjects")
        print(f"Found {len(geographic_entities)} unique geographic entities")
        
        # Process multi-vocabulary lookup with comprehensive logging
        (
            subject_to_terms_excel,
            subject_to_terms_json, 
            geographic_to_terms_excel,
            geographic_to_terms_json
        ) = self.process_multi_vocabulary_lookup(subjects, geographic_entities)
        
        # Enhance Excel file
        if not self.enhance_excel_file(subject_to_terms_excel, geographic_to_terms_excel):
            return False

        # Enhance JSON file
        if not self.enhance_json_file(subject_to_terms_json, geographic_to_terms_json):
            return False

        # Create vocabulary report (optional but useful)
        self.create_vocabulary_report(subject_to_terms_excel, geographic_to_terms_excel)
        
        # Generate comprehensive API usage logs
        total_items = len(subjects) + len(geographic_entities)
        api_summary_stats = self.stats_tracker.get_summary_stats(total_items)
        create_vocab_api_usage_log(
            logs_folder_path=self.logs_folder_path,
            script_name="dissertation_step2",
            total_subjects=total_items,
            api_stats=api_summary_stats
        )
        
        # Final summary
        subjects_with_terms = sum(1 for terms in subject_to_terms_excel.values() if terms)
        geo_with_terms = sum(1 for terms in geographic_to_terms_excel.values() if terms)

        print(f"\n✅ STEP 2 COMPLETE: Enhanced with vocabulary terms in {os.path.basename(self.folder_path)}")
        print(f"Updated Excel/JSON files, vocabulary report, and API logs created")
        print(f"Subjects with vocabulary terms: {subjects_with_terms}/{len(subjects)}")
        print(f"Geographic entities with vocabulary terms: {geo_with_terms}/{len(geographic_entities)}")
        if subjects:
            print(f"Subject success rate: {(subjects_with_terms/len(subjects)*100):.1f}%")
        if geographic_entities:
            print(f"Geographic success rate: {(geo_with_terms/len(geographic_entities)*100):.1f}%")
        print(f"Limited to {self.max_terms_per_vocabulary} terms per vocabulary")
        print(f"Maximum {self.max_total_terms} terms total per subject")
        print(f"Total API requests made: {api_summary_stats['total_requests']}")
        print(f"Processing time: {api_summary_stats['total_time']:.1f}s")
       
        # Show API breakdown
        print(f"\nAPI BREAKDOWN:")
        for api_name, stats in api_summary_stats['api_breakdown'].items():
            requests = stats['requests']
            success_rate = stats['success_rate']
            terms_found = stats['terms_found']
            cache_hits = stats['cache_hits']
            print(f"   {api_name}: {requests} requests, {success_rate:.1f}% success, {terms_found} terms, {cache_hits} cache hits")
        
        return True

def main():
    
    # Default base directory for dissertation output folders (from Step 1)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_output_dir = os.path.join(script_dir, "output_folders")
    
    # Default folder path: pick the newest Step 1 output folder
    folder_path = find_newest_folder(base_output_dir)
    if not folder_path:
        print(f"No folders found in: {base_output_dir}")
        return 1
    print(f"Auto-selected newest folder: {os.path.basename(folder_path)}")

    # Create and run the enhancer with comprehensive API logging
    enhancer = DissertationVocabEnhancer(folder_path)
    success = enhancer.run()
    
    if not success:
        print("Multi-vocabulary enhancement failed")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())            