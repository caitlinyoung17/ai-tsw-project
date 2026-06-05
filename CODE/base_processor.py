class BaseProcessorStep:
    def __init__(self, json_data):
        self.json_data = None

    def process(self):
        raise NotImplementedError("Subclasses should implement this method.")
    

# !! could potentially write processor steps for the following: 
#         def detect_workflow_type(self) -> bool:
            # """
            # Detect workflow type and check that vocabulary enhancement (Step 2) has been run.

            # For dissertations we expect only text workflow files:
            # - metadata/collection_metadata/text_workflow.xlsx
            # - metadata/collection_metadata/text_workflow.json
            # and a vocabulary_mapping_report.txt from Step 2.
            # """
            # metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
            # text_files = ['text_workflow.xlsx', 'text_workflow.json']
            
            # has_text_files = all(os.path.exists(os.path.join(metadata_dir, f)) for f in text_files)
            
            # if has_text_files:
            #     self.workflow_type = 'text'
            #     self.excel_path = os.path.join(metadata_dir, 'text_workflow.xlsx')
            # else:
            #     logging.error("Could not find text workflow files (text_workflow.xlsx/json) in the metadata folder.")
            #     return False
            
            # # Check if vocabulary enhancement has been run (Step 2)
            # vocab_report_path = os.path.join(metadata_dir, 'vocabulary_mapping_report.txt')
            # if not os.path.exists(vocab_report_path):
            #     logging.error("Vocabulary enhancement (step 2) must be run before step 3.")
            #     return False

            # return True

#     def load_json_data(self) -> bool:
        # """
        # Load JSON data for the detected workflow type and verify that vocabulary terms exist.

        # Expects that Step 2 has populated analysis['vocabulary_search_results'] for at least one item.
        # """
        # json_filename = f"{self.workflow_type}_workflow.json"
        # metadata_dir = os.path.join(self.folder_path, "metadata", "collection_metadata")
        # json_path = os.path.join(metadata_dir, json_filename)
        
        # try:
        #     with open(json_path, 'r', encoding='utf-8') as f:
        #         self.json_data = json.load(f)
            
        #     # Check if vocabulary terms exist in the data
        #     data_items = self.json_data[:-1] if self.json_data and 'api_stats' in self.json_data[-1] else self.json_data
            
        #     has_vocab_terms = False
        #     for item in data_items:
        #         if 'analysis' in item and 'vocabulary_search_results' in item['analysis']:
        #             vocab_terms = item['analysis']['vocabulary_search_results']
        #             if vocab_terms:  # Check if there are any vocabulary terms
        #                 has_vocab_terms = True
        #                 break
            
        #     if not has_vocab_terms:
        #         logging.error("No vocabulary terms found in JSON. Please run Step 2 (vocab querying) first.")
        #         return False
            
        #     print(f"Loaded JSON data from {json_filename}")
        #     return True
            
        # except Exception as e:
        #     logging.error(f"Error loading JSON data: {e}")
        #     return False      