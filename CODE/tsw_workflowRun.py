"""
Texas ScholarWorks Workflow Runner
=========================================

This script runs the complete Texas ScholarWorks workflow pipeline:
Step 1: Initial Metadata Extraction & Normalization (including PDF text extraction)
Step 1.5: Batch Cleanup (automatic if batch processing was used)
Step 2: Multi-Vocabulary Enhancement (LCSH, FAST, Getty)
Step 3: AI-Powered Vocabulary Selection & Clean Output Generation
Step 4: Entity Authority File Creation

Author: Texas ScholarWorks Processing Team
"""

import os
import sys
import subprocess
import logging
import argparse
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TexasScholarWorksWorkflowRunner:
    """Workflow runner for the Texas ScholarWorks processing pipeline."""
    
    def __init__(self):
        self.workflow_type = None
        self.output_folder = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Define script paths
        self.scripts = {
            'text_step1': os.path.join(self.script_dir, 'tsw_s1_initialMetadataExtraction.py'),
            'step1_5': os.path.join(self.script_dir, 'tsw_s1.5_batchCleanup.py'),  # NEW
            'step2': os.path.join(self.script_dir, 'tsw_s2_vocabQuerying.py'),
            'step3': os.path.join(self.script_dir, 'tsw_s3_termsSelection.py'),
            'step4': os.path.join(self.script_dir, 'tsw_s4_entityAuthority.py'),
        }

    def print_banner(self):
        """Print the workflow banner."""
        print("\n" + "="*70)
        print("  TEXAS SCHOLARWORKS COMPLETE WORKFLOW PIPELINE")
        print("="*70)
        print("Processing digitized dissertations")
        print("University of Texas at Austin Digital Collections")
        print("Open & Digital Scholarship Services Team, Research & Scholarship Department")
        print("="*70 + "\n")
        
            