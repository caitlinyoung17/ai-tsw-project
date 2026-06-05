import os
import logging
from pdfminer.high_level import extract_text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Suppress verbose HTTP logging
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Utility functions for handling dissertation PDFs and text files. 
# Works by looking for .txt files first, and if not found, extracting text from PDFs directly (extract_text).

def collect_dissertation_files(input_folder):
    all_files = []
    for filename in sorted(os.listdir(input_folder)):
        if not (filename.endswith('.txt') or filename.endswith('.pdf')):
            continue

        file_path = os.path.join(input_folder, filename)
        if not os.path.isfile(file_path):
            continue

        try:
            if filename.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:  # PDF
                content = extract_text(file_path)

            all_files.append((filename, file_path, content))
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {e}")
            continue

    return all_files

# When testing, you can use this step (instead of step before) 
# to generate and extract .txt files from PDFs to be stored locally, 
# rather than relying on extracted txt file from PDF to be stored in memory. 
#
# def convert_pdfs_to_txt(input_folder, output_folder=None):
#     """
#     Convert all PDFs in input_folder to .txt files.
#     If output_folder is None, write the .txt files back into input_folder.
#     """
#     if output_folder is None:
#         output_folder = input_folder
    
#     os.makedirs(output_folder, exist_ok=True)
    
#     for filename in sorted(os.listdir(input_folder)):
#         if not filename.lower().endswith('.pdf'):
#             continue
        
#         pdf_path = os.path.join(input_folder, filename)
#         if not os.path.isfile(pdf_path):
#             continue
        
#         try:
#             print(f"Extracting text from {filename}...")
#             text = extract_text(pdf_path)
            
#             txt_name = os.path.splitext(filename)[0] + ".txt"
#             txt_path = os.path.join(output_folder, txt_name)
            
#             with open(txt_path, 'w', encoding='utf-8') as f:
#                 f.write(text)
            
#             print(f"  → Wrote {txt_name} ({len(text)} characters)")
        
#         except Exception as e:
#             logging.error(f"Error converting {pdf_path} to text: {e}")

def main():
    # Figure out where this script lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Folder that contains your test PDFs / TXTs
    input_folder = os.path.join(script_dir, "DigitizedDissertationTest")
    
    print(f"Looking in: {input_folder}")
    
    all_files = collect_dissertation_files(input_folder)
    print(f"Found {len(all_files)} files")

    for filename, file_path, content in all_files:
        print(f"- {filename}")
        print(f"  Path: {file_path}")
        print(f"  Characters of text: {len(content)}")
        # Optional: print a small snippet to verify extraction
        print(f"  Preview: {content[:300].replace('\\n', ' ')}")
        print()

if __name__ == "__main__":
    main()