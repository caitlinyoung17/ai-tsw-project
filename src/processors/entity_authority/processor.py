"""Step 4 processor: owns I/O; all logic lives in pure modules."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Callable, Optional

from processors.entity_authority.authority_file import (
    build_authority_file, generate_statistics, render_report)
from processors.entity_authority.clustering import (
    Similarity, build_entities, default_similarity)
from processors.entity_authority.extraction import extract_all_entities
from processors.base import ProcessorStep
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

logger = logging.getLogger(__name__)

AUTHORITY_NAME = "dissertation_entity_authority.json"
REPORT_NAME = "entity_authority_report.txt"


class EntityAuthorityProcessor(ProcessorStep):
    name = "entity_authority"

    def __init__(self, run_folder: RunFolder, *, store: Optional[WorkflowStore] = None,
                 similarity: Optional[Similarity] = None,
                 library: Optional[str] = None, threshold: float = 85,
                 require_rapidfuzz: bool = False,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.run_folder = run_folder
        self.store = store or WorkflowStore(run_folder)
        if similarity is None:
            similarity, library = default_similarity(require_rapidfuzz)
        self.similarity = similarity
        self.library = library
        self.threshold = threshold
        self.clock = clock

    def run(self) -> dict:
        """Write authority JSON + report; raises WorkflowFilesNotFound if inputs missing."""
        self.run_folder.require_workflow_files()
        logger.info("Sub-step 1/3: loading workflow and extracting entities")
        workflow = self.store.load()
        raws = extract_all_entities(workflow.items)
        logger.info("Sub-step 2/3: clustering %d raw entit(ies) (threshold %s)",
                    len(raws), self.threshold)
        entities = build_entities(raws, self.similarity, self.threshold)
        if not entities:
            logger.info("No named entities found; writing empty authority file")
        logger.info("Sub-step 3/3: writing authority file and report")
        now = self.clock()
        data = build_authority_file(entities, created=now.isoformat(),
                                    library=self.library, threshold=self.threshold)
        report = render_report(generate_statistics(entities), entities,
                               generated=now.strftime("%Y-%m-%d %H:%M:%S"),
                               library=self.library, threshold=self.threshold)
        meta = self.run_folder.metadata_dir
        (meta / AUTHORITY_NAME).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        (meta / REPORT_NAME).write_text(report, encoding="utf-8")
        logger.info("Complete: %d entities", len(entities))
        return data
