# entity_authority.py
# Create local authority file for dissertation named entities with fuzzy matching

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import re
from shared_utilities import find_newest_folder

# Fuzzy matching imports - try rapidfuzz first (faster), fallback to fuzzywuzzy
try:
    from rapidfuzz import fuzz, process
    FUZZY_LIB = "rapidfuzz"
except ImportError:
    print("Warning: Rapidfuzz not found. Install one for fuzzy matching:")
    print("pip install rapidfuzz  # recommended")
    FUZZY_LIB = None

class EntityAuthority:
    """
    Build local authority records for dissertation named entities with fuzzy matching.

    This can be used to cluster and normalize:
      - Person names (authors, advisors, committee members)
      - Institutions (departments, universities)
      - Organizations, datasets, etc.
    """
    
    def __init__(self, folder_path: str, similarity_threshold: int = 85):
        """
        folder_path: path to a single dissertation output folder (from Steps 1–3)
        similarity_threshold: fuzzy matching threshold (0–100) for clustering variants
        """
        self.folder_path = folder_path
        self.workflow_type = ''
        self.json_data = None
        self.similarity_threshold = similarity_threshold
        self.entity_clusters: Dict[str, Dict] = {}  # Maps normalized names to canonical records

    def detect_workflow_type(self) -> bool:
        """
        Detect workflow type for the authority-building step.

        For dissertations we expect only text workflow files:
          - metadata/collection_metadata/text_workflow.xlsx
          - metadata/collection_metadata/text_workflow.json
        """
        metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        text_files = ['text_workflow.xlsx', 'text_workflow.json']
        
        has_text_files = all(os.path.exists(os.path.join(metadata_dir, f)) for f in text_files)
        
        if has_text_files:
            self.workflow_type = 'text'
            return True
        else:
            logging.error("Could not find text workflow files (text_workflow.xlsx/json) in the metadata folder.")
            return False
        
    def load_json_data(self) -> bool:
        """Load JSON data for the detected workflow type."""
        json_filename = f"{self.workflow_type}_workflow.json"
        metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        json_path = os.path.join(metadata_dir, json_filename)
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
            return True
        except Exception as e:
            logging.error(f"Error loading JSON data: {e}")
            return False

    def normalize_entity_name(self, name: str) -> str:
        """Basic normalization for entity names."""
        # Remove extra whitespace and punctuation
        normalized = re.sub(r'\s+', ' ', name.strip())
        
        # Handle common abbreviations and variations for better matching
        normalized = normalized.replace('&', 'and')
        normalized = re.sub(r'\bCo\.\b', 'Company', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bInc\.\b', 'Incorporated', normalized, flags=re.IGNORECASE)
        
        return normalized

    def find_similar_entity(self, entity_name: str, existing_entities: List[str]) -> Optional[str]:
        """Find if entity is similar to existing ones using fuzzy matching."""
        if not FUZZY_LIB or not existing_entities:
            return None
        
        normalized_name = self.normalize_entity_name(entity_name)
        normalized_existing = [self.normalize_entity_name(e) for e in existing_entities]
        
        # Find best match
        match = process.extractOne(
            normalized_name, 
            normalized_existing, 
            scorer=fuzz.ratio,
            score_cutoff=self.similarity_threshold
        )
        
        if match:
            # Return the original entity name that corresponds to the match
            match_index = normalized_existing.index(match[0])
            return existing_entities[match_index]
        
        return None

    def parse_typed_entity(self, entity_str: str) -> Tuple[str, str]:
        """Parse entity string to extract name and type.
        
        Input: 'John F. Staub (architect)' or 'Atlanta, Ga. (location)'
        Output: ('John F. Staub', 'architect')
        """
        # Look for pattern: 'Name (type)'
        match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', entity_str.strip())
        
        if match:
            name = match.group(1).strip()
            entity_type = match.group(2).strip().lower()
            return name, entity_type
        else:
            # If no type indicator found, return original string and classify it
            name = entity_str.strip()
            entity_type = self.classify_entity_fallback(name)
            return name, entity_type

    def classify_entity_fallback(self, entity: str) -> str:
        """
        Fallback classification for entities without type indicators.

        This is a heuristic and should be used only when explicit types
        (e.g., '(Person)', '(Institution)') are not present.
        """
        entity_lower = entity.lower()
        
        # Organizations / institutions / companies
        if any(term in entity_lower for term in ['university', 'college', 'institute', 'school', 'department']):
            return 'institution'
        if any(term in entity_lower for term in ['company', 'co.', 'inc.', 'corp.', 'corporation', 'association', 'society', 'foundation', 'committee']):
            return 'organization'
        
        # Datasets / projects / programs (very rough)
        if any(term in entity_lower for term in ['study', 'project', 'program', 'trial', 'survey']):
            return 'project'
        
        # Personal names (has initials or multiple capitalized words)
        # e.g., "J. Smith", "E. R. Denmark", "Laurence H. Fowler"
        if re.match(r'^[A-Z]\. ?[A-Z]\.? [A-Z]', entity):  # J. Staub, E. R. Denmark
            return 'person'
        elif re.match(r'^[A-Z][a-z]+ [A-Z]\. [A-Z]', entity):  # Laurence H. Fowler
            return 'person'
        elif len(entity.split()) >= 2 and all(word and word[0].isupper() for word in entity.split()[:2]):
            return 'person'
        
        # Geographic locations (very rough; most should be typed explicitly)
        if any(term in entity_lower for term in ['city', 'state', 'province', 'county', 'region', 'country']):
            return 'location'
        
        return 'unknown'

    def cluster_similar_entities(self, raw_entities: List[str]) -> Dict[str, List[str]]:
        """Group similar entities using fuzzy matching."""
        if not FUZZY_LIB:
            # If no fuzzy matching library, treat each entity as unique
            return {entity: [entity] for entity in raw_entities}
        
        clusters = {}
        processed = set()
        
        print(f"Clustering {len(raw_entities)} entities with similarity threshold {self.similarity_threshold}%...")
        
        for entity in raw_entities:
            if entity in processed:
                continue
                
            # Find all similar entities
            similar_entities = [entity]
            processed.add(entity)
            
            for other_entity in raw_entities:
                if other_entity in processed:
                    continue
                    
                # Check similarity
                similarity = fuzz.ratio(
                    self.normalize_entity_name(entity),
                    self.normalize_entity_name(other_entity)
                )
                
                if similarity >= self.similarity_threshold:
                    similar_entities.append(other_entity)
                    processed.add(other_entity)
            
            # Use the most common or longest form as canonical
            canonical = max(similar_entities, key=lambda x: (raw_entities.count(x), len(x)))
            clusters[canonical] = similar_entities
        
        # Show clustering results
        merged_count = sum(len(cluster) - 1 for cluster in clusters.values() if len(cluster) > 1)
        if merged_count > 0:
            print(f"   Merged {merged_count} entity variations into {len(clusters)} unique entities")
            
            # Show some examples of merges
            merge_examples = [(canonical, cluster) for canonical, cluster in clusters.items() if len(cluster) > 1][:5]
            for canonical, cluster in merge_examples:
                print(f"   • '{canonical}' ← {cluster[1:]}")
        
        return clusters

    def extract_all_entities(self) -> Dict[str, Dict]:
        """
        Extract all named entities across dissertations and cluster them with fuzzy matching.

        Returns:
            A dict mapping canonical entity names to records with:
              - appearances: list of entry identifiers where the entity appears
              - contexts: list of text snippets (e.g., title + abstract)
              - entity_type: inferred or explicit type (person, institution, etc.)
              - original_forms: list of original entity strings
              - clustered_variants: list of variant forms grouped under this canonical name
              - frequency: number of appearances
        """
        raw_entity_data = []  # Store raw entities with their contexts
        
        # Skip API stats
        data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
        if data_items is None:
            logging.error("JSON data is not in expected format (missing list of items).")
            return {} # Return dummy data to prevent crashes
        
        # First pass: collect all raw entities
        for entry_index, item in enumerate(data_items):
            if 'analysis' not in item:
                continue
            
            analysis = item['analysis']
            filename = item.get('filename') or item.get('file_path') or f"entry_{entry_index}"
            
            # Extract entities
            entities = analysis.get('namedEntities', []) or analysis.get('named_entities', [])
            if isinstance(entities, str):
                entities = [e.strip() for e in entities.split(',') if e.strip()]
            
            if not entities:
                continue
            
            # Extract context for additional analysis (e.g., title + abstract)
            title = analysis.get('title', '').strip()
            abstract = analysis.get('abstract', '').strip()
            context_parts = []
            if title:
                context_parts.append(title)
            if abstract:
                context_parts.append(abstract)
            context = " ".join(context_parts).lower()
            
            for entity_str in entities:
                if not entity_str or len(entity_str.strip()) < 2:
                    continue
                
                entity_name, entity_type = self.parse_typed_entity(entity_str)
                if not entity_name:
                    continue
                
                raw_entity_data.append({
                    'original_str': entity_str.strip(),
                    'entity_name': entity_name,
                    'entity_type': entity_type,
                    'entry_index': entry_index,
                    'filename': filename,
                    'context': context
                })
        
        if not raw_entity_data:
            print("No named entities found in JSON data.")
            return {}
        
        # Get all unique entity names for clustering
        all_entity_names = [item['entity_name'] for item in raw_entity_data]
        entity_clusters = self.cluster_similar_entities(all_entity_names)
        
        # Second pass: group by canonical entity names
        entity_records = defaultdict(lambda: {
            'appearances': [],
            'contexts': [],
            'entity_type': 'unknown',
            'original_forms': set(),
            'clustered_variants': set()
        })
        
        for item in raw_entity_data:
            entity_name = item['entity_name']
            
            # Find canonical name for this entity
            canonical_name = None
            for canonical, cluster in entity_clusters.items():
                if entity_name in cluster:
                    canonical_name = canonical
                    break
            
            if not canonical_name:
                canonical_name = entity_name
            
            record = entity_records[canonical_name]
            # Use filename or entry index as appearance identifier
            record['appearances'].append(item['filename'])
            record['contexts'].append(item['context'])
            record['original_forms'].add(item['original_str'])
            record['clustered_variants'].add(entity_name)
            
            # Set entity type (use the parsed type or keep existing if already set)
            if record['entity_type'] == 'unknown' or item['entity_type'] != 'unknown':
                record['entity_type'] = item['entity_type']
        
        # Convert sets to lists for JSON serialization and calculate frequency
        for entity, record in entity_records.items():
            record['original_forms'] = list(record['original_forms'])
            record['clustered_variants'] = list(record['clustered_variants'])
            record['frequency'] = len(record['appearances'])
        
        return dict(entity_records)

    def create_authority_file(self, entity_records: Dict) -> bool:
        """Create comprehensive authority file for dissertation named entities."""
        try:
            metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            authority_path = os.path.join(metadata_dir, "dissertation_entity_authority.json")
            
            # Create structured authority data
            authority_data = {
                "metadata": {
                    "created": datetime.now().isoformat(),
                    "source": "Texas ScholarWorks dissertations",
                    "total_entities": len(entity_records),
                    "extraction_method": "Named Entities from Step 1 metadata (with type classification)",
                    "fuzzy_matching": {
                        "enabled": FUZZY_LIB is not None,
                        "library": FUZZY_LIB,
                        "similarity_threshold": self.similarity_threshold
                    },
                    "entity_types": list(set(record['entity_type'] for record in entity_records.values()))
                },
                "entities": entity_records,
                "statistics": self.generate_statistics(entity_records)
            }
            
            with open(authority_path, 'w', encoding='utf-8') as f:
                json.dump(authority_data, f, indent=2, ensure_ascii=False)
            
            print(f"📋 Created entity authority file: {authority_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error creating authority file: {e}")
            return False

    def generate_statistics(self, entity_records: Dict) -> Dict:
        """
        Generate statistics about entities across dissertations.

        Returns a dict with:
          - by_type: count of entities per inferred type
          - by_frequency: buckets of how often entities appear
          - type_examples: up to 3 example entities per type
          - clustering_stats: how many entities had variants merged
        """
        stats = {
            'by_type': defaultdict(int),
            'by_frequency': defaultdict(int),
            'type_examples': defaultdict(list),
            'clustering_stats': {
                'entities_with_variants': 0,
                'total_variants_merged': 0
            }
        }
        
        for entity, record in entity_records.items():
            entity_type = record.get('entity_type', 'unknown')
            frequency = record.get('frequency', 0)
            
            stats['by_type'][entity_type] += 1
            
            # Add examples for each type (up to 3)
            if len(stats['type_examples'][entity_type]) < 3:
                stats['type_examples'][entity_type].append(entity)
            
            # Clustering statistics
            variants = record.get('clustered_variants', [])
            if isinstance(variants, list) and len(variants) > 1:
                stats['clustering_stats']['entities_with_variants'] += 1
                stats['clustering_stats']['total_variants_merged'] += len(variants) - 1
            
            # Frequency buckets
            if frequency == 1:
                stats['by_frequency']['single_mention'] += 1
            elif 2 <= frequency <= 3:
                stats['by_frequency']['low_frequency'] += 1
            elif 4 <= frequency <= 10:
                stats['by_frequency']['medium_frequency'] += 1
            elif frequency > 10:
                stats['by_frequency']['high_frequency'] += 1
        
        # Convert defaultdicts to regular dicts
        return {
            'by_type': dict(stats['by_type']),
            'by_frequency': dict(stats['by_frequency']),
            'type_examples': dict(stats['type_examples']),
            'clustering_stats': stats['clustering_stats']
        }

    def create_human_readable_report(self, entity_records: Dict) -> bool:
        """Create human-readable authority report for dissertation named entities."""
        try:
            metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            report_path = os.path.join(metadata_dir, "entity_authority_report.txt")
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("DISSERTATION ENTITY AUTHORITY REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Entities: {len(entity_records)}\n")
                f.write(f"Fuzzy Matching: {'Enabled' if FUZZY_LIB else 'Disabled'}")
                if FUZZY_LIB:
                    f.write(f" ({FUZZY_LIB}, threshold: {self.similarity_threshold}%)")
                f.write("\n\n")
                
                # Show statistics summary
                stats = self.generate_statistics(entity_records)
                
                if FUZZY_LIB and stats['clustering_stats']['entities_with_variants'] > 0:
                    f.write("FUZZY MATCHING RESULTS:\n")
                    f.write("-" * 25 + "\n")
                    f.write(f"  Entities with variants: {stats['clustering_stats']['entities_with_variants']}\n")
                    f.write(f"  Total variants merged: {stats['clustering_stats']['total_variants_merged']}\n\n")
                
                f.write("ENTITY TYPE BREAKDOWN:\n")
                f.write("-" * 25 + "\n")
                for entity_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"  {entity_type.upper().replace('_', ' ')}: {count} entities\n")
                f.write("\n")
                
                # Group by type for detailed listing
                by_type = defaultdict(list)
                for entity, record in entity_records.items():
                    by_type[record.get('entity_type', 'unknown')].append((entity, record))
                
                for entity_type in sorted(by_type.keys()):
                    entities = by_type[entity_type]
                    f.write(f"{entity_type.upper().replace('_', ' ')} ({len(entities)} entities):\n")
                    f.write("-" * 40 + "\n")
                    
                    # Sort by frequency (most mentioned first)
                    entities.sort(key=lambda x: x[1].get('frequency', 0), reverse=True)
                    
                    for entity, record in entities:
                        f.write(f"  {entity}\n")
                        f.write(f"    Frequency: {record.get('frequency', 0)} appearances\n")
                        
                        # Show clustered variants if any
                        variants = record.get('clustered_variants', [])
                        if isinstance(variants, list) and len(variants) > 1:
                            other_variants = [v for v in variants if v != entity]
                            if other_variants:
                                f.write(f"    Variants: {', '.join(other_variants)}\n")
                        
                        # Show different forms if multiple
                        original_forms = record.get('original_forms', [])
                        if isinstance(original_forms, list) and len(original_forms) > 1:
                            f.write(f"    Forms: {', '.join(original_forms)}\n")
                        
                        # Show up to 5 appearances (filenames/entries)
                        appearances = record.get('appearances', [])
                        if appearances:
                            f.write(f"    Appearances: {', '.join(appearances[:5])}")
                            if len(appearances) > 5:
                                f.write(f" ... (+{len(appearances)-5} more)")
                            f.write("\n")
                        
                        f.write("\n")
                
            print(f"📄 Created human-readable report: {report_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error creating report: {e}")
            return False

    def run(self) -> bool:
        """Main execution method for building a dissertation entity authority file."""
        print(f"\nDISSERTATION ENTITY AUTHORITY BUILDER")
        print(f"Processing folder: {self.folder_path}")
        if FUZZY_LIB:
            print(f"Fuzzy matching: Enabled ({FUZZY_LIB}, threshold: {self.similarity_threshold}%)")
        else:
            print("Fuzzy matching: Disabled (install rapidfuzz)")
        print("-" * 50)
        
        # Detect workflow type (should be 'text' for dissertations)
        if not self.detect_workflow_type():
            print("Could not detect workflow type")
            return False
        
        print(f"🔍 Detected workflow type: {self.workflow_type.upper()}")
        
        # Load JSON data
        if not self.load_json_data():
            print("Could not load JSON data")
            return False
        
        # Extract all entities with fuzzy matching
        print("Extracting and analyzing typed named entities with fuzzy matching...")
        entity_records = self.extract_all_entities()
        
        if not entity_records:
            print("No named entities found")
            return False
        
        print(f"Found {len(entity_records)} unique entities after clustering")
        
        # Show type breakdown
        type_counts = defaultdict(int)
        for record in entity_records.values():
            entity_type = record.get('entity_type', 'unknown')
            type_counts[entity_type] += 1
        
        for entity_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {entity_type}: {count} entities")
        
        # Create authority files
        if not self.create_authority_file(entity_records):
            return False
        
        if not self.create_human_readable_report(entity_records):
            return False
        
        print(f"\n✅ ENTITY AUTHORITY COMPLETE: Built entity authority in {os.path.basename(self.folder_path)}")
        print(f"Entity authority JSON and human-readable report created with fuzzy matching")
        
        return True

def main():
    """
    Entry point for building a dissertation entity authority file.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_output_dir = os.path.join(script_dir, "output_folders")
    
    # Default folder path: pick the newest dissertation output folder
    folder_path = find_newest_folder(base_output_dir)
    if not folder_path:
        print(f"No folders found in: {base_output_dir}")
        return 1
    print(f"Auto-selected newest folder: {os.path.basename(folder_path)}")
    
    authority_builder = EntityAuthority(folder_path)
    success = authority_builder.run()
    
    if not success:
        print("Entity authority building failed")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())                                                                