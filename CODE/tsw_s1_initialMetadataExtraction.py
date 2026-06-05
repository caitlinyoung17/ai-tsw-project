import os
import json
import logging
from datetime import datetime
from urllib import response
from openai import OpenAI
import tenacity
import re
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Alignment
from openpyxl.cell import Cell
import time
from shared_utilities import APIStats, postprocess_api_response, parse_json_response_enhanced, preprocess_ocr_text

# Import custom modules
from model_pricing import calculate_cost, get_model_info
from token_logging import create_token_usage_log, log_individual_response
from batch_processor import BatchProcessor
from prompts import DissertationPrompts
from pdf_to_txt import collect_dissertation_files

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Suppress verbose HTTP logging
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
DEFAULT_MODEL = "gpt-4o"  # Default model name, change as needed

api_stats = APIStats()

def prepare_batch_requests(all_files, model_name):
    """
    Prepare all requests for batch processing (one request per dissertation).

    all_files: list of (filename, file_path, content) tuples
    """
    batch_requests = []
    custom_id_mapping = {}
    
    # Get the shared metadata prompt once
    base_prompt = DissertationPrompts.get_dissertation_metadata_prompt()
    
    for i, (filename, file_path, content) in enumerate(all_files):
        # Preprocess the text (currently minimal; mostly whitespace normalization)
        content = preprocess_ocr_text(content)
        
        # Skip empty content
        if not content.strip():
            continue
        
        # Build the user message: prompt + full dissertation text
        user_content = (
            base_prompt
            + "\n\nHere is the full dissertation text:\n\n"
            + content.strip()
        )
        
        # Create request data for this dissertation
        request_data = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an AI archival expert tasked with extracting metadata from full dissertation text."
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "max_tokens": 8000
        }
        
        batch_requests.append(request_data)
        
        # Map a custom ID to this dissertation so we can match results later
        custom_id_mapping[f"dissertation_text_{i}"] = {
            "filename": filename,
            "file_path": file_path,
            "row_number": i + 2  # +2 for header row in Excel
        }
    
    return batch_requests, custom_id_mapping


def parse_json_response(raw_response):
    """Enhanced JSON parsing with trailing comma handling."""
    return parse_json_response_enhanced(raw_response)


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(Exception)
)
def process_single_file(filename, file_path, content, model_name=DEFAULT_MODEL):
    """Process a single dissertation text file (for individual processing).
    Expects 'content' to be the full text of one dissertation."""
    # # Preprocess the OCR text
    # content = preprocess_ocr_text(content)
    
    # Check if the content is empty or only whitespace
    if not content.strip():
        return {
            "title": "",
            "creator": "",
            "date": "",
            "department": "",
            "abstract": "",
            "subjects": [],
            "type": "",
            "access": "",
            "publisher": "",
            "sponsor": "",
            "language": "",
            "namedEntities": [],
            "geographicEntities": [],
            "contentWarning": "None"
        }, "", None, 0
    
    # Use prompts module
    base_prompt = DissertationPrompts.get_dissertation_metadata_prompt()
    user_content = base_prompt + "\n\nHere is the full dissertation text:\n\n" + content.strip()
    
    api_stats.total_requests += 1
    start_time = time.time()
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[{
            "role": "system", 
            "content": "You are an AI archival expert tasked with extracting metadata from a full dissertation text."
        }, {
            "role": "user",
            "content": user_content
        }],
        max_tokens=3000, 
        temperature=0.3 # Lower temperature for more focused responses, but still creative
    )
    
    processing_time = time.time() - start_time
    api_stats.processing_times.append(processing_time)
    
    usage = response.usage or {}
    prompt_tokens = getattr(usage, "prompt_tokens", 0)
    completion_tokens = getattr(usage, "completion_tokens", 0)

    api_stats.total_input_tokens += prompt_tokens
    api_stats.total_output_tokens += completion_tokens

    # Safely get the first choice's content
    if not response.choices:
        raise Exception("No choices returned from OpenAI API")

    message_content = response.choices[0].message.content or ""
    raw_response = message_content.strip()
    
    # Parse JSON from the model output
    parsed_json, error = parse_json_response(raw_response)
    if not parsed_json:
        logging.error(f"JSON parsing failed for {file_path}: {error}\nRaw response: {raw_response}")
        # Raise exception to trigger retry
        raise Exception(f"JSON parsing failed: {error}")
    
    # Post-process the response: normalize subjects, entities, contentWarning, trim strings
    response_data = postprocess_api_response(parsed_json)
    
    return response_data, raw_response, response.usage, processing_time


def process_folder_individual(all_files, wb, analysis_sheet, raw_sheet, issues_sheet, logs_folder_path, model_name, all_results, output_dir):
    """Process dissertations using individual API calls."""
    items_with_issues = 0
    total_processing_time = 0
    
    for i, (filename, file_path, content) in enumerate(all_files):
        row_number = i + 2  # +2 for header row
        
        print(f"\n Processing file {i+1}/{len(all_files)}")
        print(f"   File: {filename}")
        print(f"   Progress: {((i+1)/len(all_files))*100:.1f}%")
        
        try:
            response_data, raw_response, usage, processing_time = process_single_file(
                filename, file_path, content, model_name
            )
            total_processing_time += processing_time
            
            # Log individual response
            log_individual_response(
                logs_folder_path=logs_folder_path,
                script_name="dissertation_text_metadata",
                row_number=row_number,
                barcode=filename,
                response_text=raw_response,
                model_name=model_name,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                processing_time=processing_time
            )
            if usage:
                print(f"   Processed successfully! Tokens: {(usage.prompt_tokens + usage.completion_tokens):,}") 
            else:
                 print(f"   Processed successfully! (no usage info)")
            
        except Exception as e:
            logging.error(f"Error processing {file_path}: {str(e)}")
            items_with_issues += 1
            raw_response = f"Processing error: {str(e)}"

           # Empty but well-formed dissertation record on error
            response_data = {
                "title": "",
                "creator": "",
                "date": "",
                "department": "",
                "abstract": "",
                "subjects": [],
                "type": "",
                "access": "",
                "publisher": "",
                "sponsor": "",
                "language": "",
                "namedEntities": [],
                "geographicEntities": [],
                "contentWarning": "None"
            }
            usage = None
            
            # Add to issues sheet
            issues_sheet.append([filename, str(e)])
            
            # Log error
            log_individual_response(
                logs_folder_path=logs_folder_path,
                script_name="dissertation_text_metadata",
                row_number=row_number,
                barcode=filename,
                response_text=raw_response,
                model_name=model_name,
                prompt_tokens=0,
                completion_tokens=0,
                processing_time=0
            )
            
            print(f"  Processing failed: {str(e)}")

        # Build analysis sheet row with dissertation fields
        analysis_row = [
            filename,
            response_data.get('title', ''),
            response_data.get('creator', ''),
            response_data.get('date', ''),
            response_data.get('department', ''),
            response_data.get('abstract', ''),
            ', '.join(response_data.get('subjects', [])),
            response_data.get('type', ''),
            response_data.get('access', ''),
            response_data.get('publisher', ''),
            response_data.get('sponsor', ''),
            response_data.get('language', ''),
            ', '.join(response_data.get('namedEntities', [])),
            ', '.join(response_data.get('geographicEntities', [])),
            response_data.get('contentWarning', 'None')
        ]
        analysis_sheet.append(analysis_row)

        # Set alignment
        current_row = analysis_sheet.max_row
        for cell in analysis_sheet[current_row]:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        
        # Add to raw responses sheet
        raw_row = [filename, raw_response]
        raw_sheet.append(raw_row)
        for cell in raw_sheet[raw_sheet.max_row]:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        
        #Add to JSON results
        entry_result = {
            'filename': filename,
            'file_path': file_path,
            'analysis': {
                'title': response_data.get('title', ''),
                'creator': response_data.get('creator', ''),
                'date': response_data.get('date', ''),
                'department': response_data.get('department', ''),
                'abstract': response_data.get('abstract', ''),
                'subjects': response_data.get('subjects', []),
                'type': response_data.get('type', ''),
                'access': response_data.get('access', ''),
                'publisher': response_data.get('publisher', ''),
                'sponsor': response_data.get('sponsor', ''),
                'language': response_data.get('language', ''),
                'named_entities': response_data.get('namedEntities', []),
                'geographic_entities': response_data.get('geographicEntities', []),
                'content_warning': response_data.get('contentWarning', 'None'),
                'raw_response': raw_response
            }
        }
        all_results.append(entry_result)
        
        # Add delay between requests
        time.sleep(1)
    
    return (wb, all_results, api_stats, len(all_files), items_with_issues, total_processing_time,
           api_stats.total_input_tokens, api_stats.total_output_tokens, False)  # False for was_batch_processed


def process_folder_with_batch(input_folder, output_dir, model_name=DEFAULT_MODEL):
    """Process a folder of dissertations using batch processing when appropriate."""
    
    # Create logs folder
    logs_folder_path = os.path.join(output_dir, "logs")
    if not os.path.exists(logs_folder_path):
        os.makedirs(logs_folder_path)
    
    # Collect all dissertationfiles
    all_files = collect_dissertation_files(input_folder) # (filename, file_path, content)
    total_items = len(all_files)
    
    print(f"\nDISSERTATION METADATA EXTRACTION")
    print(f"Found {total_items} text files to process")
    print(f"Starting metadata extraction using {model_name}...")
    print("-" * 50)
    
    # Initialize batch processor and check if we should use batch processing
    processor = BatchProcessor()
    use_batch = processor.should_use_batch(total_items)
    
    print(f"Processing mode: {'BATCH' if use_batch else 'INDIVIDUAL'}")
    
    # Show model pricing info
    model_info = get_model_info(model_name)
    if model_info:
        print(f"Model: {model_name}")
        print(f"Pricing: ${model_info['input_per_1k']:.5f}/1K input, ${model_info['output_per_1k']:.5f}/1K output")
        print(f"Batch discount: {model_info['batch_discount']*100:.0f}%")
    
    # Create new workbook
    wb = Workbook()
    analysis_sheet = wb.active
    if analysis_sheet == None:
        return
    analysis_sheet.title = "Analysis"
    
    # Dissertation-level analysis headers
    analysis_headers = [
        'Filename',
        'Title',
        'Creator',
        'Date',
        'Department',
        'Abstract',
        'Subjects',
        'Type',
        'Access',
        'Publisher',
        'Sponsor',
        'Language',
        'Named Entities',
        'Geographic Entities',
        'Content Warning'
    ]
    analysis_sheet.append(analysis_headers)
    analysis_sheet.freeze_panes = 'A2'
    
    # Column widths (adjust as needed for better display)
    column_widths = [30, 50, 30, 12, 30, 60, 40, 15, 15, 25, 25, 15, 40, 40, 30]
    for i, width in enumerate(column_widths):
        cell = analysis_sheet.cell(row=1, column=i+1)
        # double-check that this is a Cell and not a MergedCell
        if not isinstance(cell, Cell):
            continue
        cell_column_letter = cell.column_letter
        analysis_sheet.column_dimensions[cell_column_letter].width = width
    
    # Create raw responses sheet
    raw_sheet = wb.create_sheet("Raw Responses")
    raw_headers = ['Filename', 'API Response']
    raw_sheet.append(raw_headers)
    raw_sheet.freeze_panes = 'A2'
    
    for i, width in enumerate([15, 10, 120]):
        raw_sheet.column_dimensions[raw_sheet.cell(row=1, column=i+1).column_letter].width = width
    
    # Create issues sheet
    issues_sheet = wb.create_sheet("Issues")
    issues_sheet.append(["Filename", "Error"])
    
    all_results = []
    items_with_issues = 0
    
    if use_batch:
        # Batch processing
        print(f"Preparing {total_items} requests for batch processing...")
        
        # Build request bodies and ID mapping for batch processing
        batch_requests, custom_id_mapping = prepare_batch_requests(all_files, model_name)        
        
        # Estimate costs
        cost_estimate = processor.estimate_batch_cost(batch_requests, model_name)
        
        # Simplified cost display
        print(f"Estimated cost: ${cost_estimate['batch_cost']:.4f} (${cost_estimate['savings']:.4f} savings)")
        
        # Convert to batch format
        formatted_requests = processor.create_batch_requests(batch_requests, "dissertation_text")
        
        # Submit batch
        batch_id = processor.submit_batch(
            formatted_requests, 
            f"Dissertation Text Metadata - {total_items} files - {datetime.now().strftime('%Y-%m-%d')}"
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
            
            # Add results to spreadsheet and JSON
            for custom_id, result_data in processed_results["results"].items():
                if custom_id.startswith("dissertation_text_"):
                    # Extract the index from custom_id: "dissertation_text_{i}_xxxx"
                    parts = custom_id.split("_")
                    if len(parts) >= 3:
                        try:
                            index = int(parts[2]) # "dissertation_text_{index}""
                            mapping_key = f"dissertation_text_{index}"
                            
                            if mapping_key in custom_id_mapping:
                                filename = custom_id_mapping[mapping_key]["filename"]
                                file_path = custom_id_mapping[mapping_key]["file_path"]
                                row_number = custom_id_mapping[mapping_key]["row_number"]
                                
                                if result_data["success"]:
                                    raw_response = result_data["content"]
                                    usage = result_data["usage"]
                                    
                                     # Parse JSON response
                                    parsed_json, error = parse_json_response(raw_response)
                                    if parsed_json:
                                        response_data = postprocess_api_response(parsed_json)
                                    else:
                                        items_with_issues += 1
                                        response_data = {
                                            "title": "",
                                            "creator": "",
                                            "date": "",
                                            "department": "",
                                            "abstract": "",
                                            "subjects": [],
                                            "type": "",
                                            "access": "",
                                            "publisher": "",
                                            "sponsor": "",
                                            "language": "",
                                            "namedEntities": [],
                                            "geographicEntities": [],
                                            "contentWarning": "None"
                                        }
                                    
                                    # Log individual response
                                    log_individual_response(
                                        logs_folder_path=logs_folder_path,
                                        script_name="dissertation_text_metadata",
                                        row_number=row_number,
                                        barcode=filename,
                                        response_text=raw_response,
                                        model_name=model_name,
                                        prompt_tokens=usage.get("prompt_tokens", 0),
                                        completion_tokens=usage.get("completion_tokens", 0),
                                        processing_time=0  # Batch processing doesn't track individual timing
                                    )
                                    
                                else:
                                    # Handle error case
                                    raw_response = f"Error: {result_data['error']}"
                                    items_with_issues += 1
                                    response_data = {
                                        "title": "",
                                        "creator": "",
                                        "date": "",
                                        "department": "",
                                        "abstract": "",
                                        "subjects": [],
                                        "type": "",
                                        "access": "",
                                        "publisher": "",
                                        "sponsor": "",
                                        "language": "",
                                        "namedEntities": [],
                                        "geographicEntities": [],
                                        "contentWarning": "None"
                                    }
                                    
                                    # Add to issues sheet
                                    issues_sheet.append([filename, result_data['error']])
                                    
                                    # Log error
                                    log_individual_response(
                                        logs_folder_path=logs_folder_path,
                                        script_name="dissertation_text_metadata",
                                        row_number=row_number,
                                        barcode=filename,
                                        response_text=raw_response,
                                        model_name=model_name,
                                        prompt_tokens=0,
                                        completion_tokens=0,
                                        processing_time=0
                                    )
                                
                                analysis_row = [
                                    filename,
                                    response_data.get('title', ''),
                                    response_data.get('creator', ''),
                                    response_data.get('date', ''),
                                    response_data.get('department', ''),
                                    response_data.get('abstract', ''),
                                    ', '.join(response_data.get('subjects', [])),
                                    response_data.get('type', ''),
                                    response_data.get('access', ''),
                                    response_data.get('publisher', ''),
                                    response_data.get('sponsor', ''),
                                    response_data.get('language', ''),
                                    ', '.join(response_data.get('namedEntities', [])),
                                    ', '.join(response_data.get('geographicEntities', [])),
                                    response_data.get('contentWarning', 'None')
                                ]
                                analysis_sheet.append(analysis_row)
                                
                                # Wrap text
                                current_row = analysis_sheet.max_row
                                for cell in analysis_sheet[current_row]:
                                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                                
                                # Add to raw sheet
                                raw_row = [filename, raw_response]
                                raw_sheet.append(raw_row)
                                
                                for cell in raw_sheet[raw_sheet.max_row]:
                                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                                
                                entry_result = {
                                    'filename': filename,
                                    'file_path': file_path,
                                    'analysis': {
                                        'title': response_data.get('title', ''),
                                        'creator': response_data.get('creator', ''),
                                        'date': response_data.get('date', ''),
                                        'department': response_data.get('department', ''),
                                        'abstract': response_data.get('abstract', ''),
                                        'subjects': response_data.get('subjects', []),
                                        'type': response_data.get('type', ''),
                                        'access': response_data.get('access', ''),
                                        'publisher': response_data.get('publisher', ''),
                                        'sponsor': response_data.get('sponsor', ''),
                                        'language': response_data.get('language', ''),
                                        'named_entities': response_data.get('namedEntities', []),
                                        'geographic_entities': response_data.get('geographicEntities', []),
                                        'content_warning': response_data.get('contentWarning', 'None'),
                                        'raw_response': raw_response
                                    }
                                }
                                all_results.append(entry_result)
                                
                        except (ValueError, IndexError) as e:
                            logging.error(f"Error processing custom_id {custom_id}: {e}")
                            continue
            
            # Return batch processing metrics
            summary = processed_results["summary"]
            return (wb, all_results, api_stats, total_items, items_with_issues, 0,  # 0 for total_time since batch doesn't track individual timing
                   summary["total_prompt_tokens"], summary["total_completion_tokens"], True)  # True for was_batch_processed
    
    # Fall back to individual processing
    print(f"Using individual processing:")
    return process_folder_individual(all_files, wb, analysis_sheet, raw_sheet, issues_sheet, logs_folder_path, model_name, all_results, output_dir)


def main():

    print("DEBUG: main() started") 

    model_name = DEFAULT_MODEL

    # Start timing the entire script execution
    script_start_time = time.time()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))

   # Folder containing one .txt file (output from your pdf-to-txt script)
    input_folder_name = "DigitizedDissertationTest"  # adjust to your actual folder name
    input_folder = os.path.join(script_dir, input_folder_name)
    
    # Create dynamic output folder name
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H-%M-%S")
    
    # Create folder name
    folder_name = f"Dissertation_Metadata_Created_{current_date}_Time_{current_time}"

    # Create the full output directory path
    base_output_dir = os.path.join(script_dir, "output_folders")
    output_dir = os.path.join(base_output_dir, folder_name)
    
    # Create the directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Create metadata folder structure
    metadata_folder = os.path.join(output_dir, "metadata", "collection_metadata")
    os.makedirs(metadata_folder, exist_ok=True)

    print(f"Output directory: {output_dir}")
    
    # Process folder
    (wb, all_results, api_stats, total_items, items_with_issues, total_processing_time,
     total_prompt_tokens, total_completion_tokens, was_batch_processed) = process_folder_with_batch(
        input_folder, output_dir, model_name
    )
    
    # Add API Stats sheet
    api_summary = {
        "total_requests": api_stats.total_requests,
        "total_input_tokens": total_prompt_tokens,
        "total_output_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "processing_mode": "BATCH" if was_batch_processed else "INDIVIDUAL"
    }
    
    all_results.append({"api_stats": api_summary})
    
    stats_sheet = wb.create_sheet("API Stats")
    stats_sheet.append(["Metric", "Value"])
    for key, value in api_summary.items():
        stats_sheet.append([key, value])
    
    # Save files
    excel_path = os.path.join(metadata_folder, "text_workflow.xlsx")
    json_path = os.path.join(metadata_folder, "text_workflow.json")
    
    wb.save(excel_path)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    # Calculate script metrics
    script_duration = time.time() - script_start_time
    
    # Calculate actual cost
    estimated_cost = calculate_cost(
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        is_batch=was_batch_processed
    )
    
    # Create logs folder
    logs_folder_path = os.path.join(output_dir, "logs")
    if not os.path.exists(logs_folder_path):
        os.makedirs(logs_folder_path)
    
    # Create standardized token usage log
    create_token_usage_log(
        logs_folder_path=logs_folder_path,
        script_name="dissertation_text_metadata",
        model_name=model_name,
        total_items=total_items,
        items_with_issues=items_with_issues,
        total_time=total_processing_time,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        additional_metrics={
            "Total script execution time": f"{script_duration:.2f}s",
            "Processing time percentage": f"{(total_processing_time/script_duration)*100:.1f}%" if script_duration > 0 else "0%",
            "Items successfully processed": total_items - items_with_issues,
            "Processing mode": "BATCH" if was_batch_processed else "INDIVIDUAL",
            "Actual cost": f"${estimated_cost:.4f}",
            "Average tokens per item": f"{(total_prompt_tokens + total_completion_tokens)/total_items:.0f}" if total_items > 0 else "0"
        }
    )
    
    # Final summary
    print(f"\n STEP 1 COMPLETE: Generated text metadata in {os.path.basename(output_dir)}")
    print(f"Excel file, JSON data, and processing logs created")
    print(f"Successfully processed: {total_items - items_with_issues}/{total_items} files")
    print(f"Items with issues: {items_with_issues}")
    print(f"Total script time: {script_duration:.1f}s ({script_duration/60:.1f} minutes)")
    print(f"Tokens: {total_prompt_tokens + total_completion_tokens:,} (Input: {total_prompt_tokens:,}, Output: {total_completion_tokens:,})")
    print(f"Processing mode: {'BATCH' if was_batch_processed else 'INDIVIDUAL'}")
    print(f"Cost estimate: ${estimated_cost:.4f}")

if __name__ == "__main__":
    main()