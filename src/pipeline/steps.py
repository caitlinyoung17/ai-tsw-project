"""ProcessorStep adapters: wire each processor from a PipelineContext."""
from __future__ import annotations

from api.llm_core.types import Usage
from processors.base import ProcessorStep
from processors.batch_cleanup.processor import BatchCleanupProcessor, CleanupStatus
from processors.batch_cleanup.reprocessor import ItemReprocessor
from processors.entity_authority.processor import EntityAuthorityProcessor
from processors.metadata_extraction.extractor import MetadataExtractor
from processors.metadata_extraction.processor import MetadataExtractionProcessor
from processors.vocab_enhancement.processor import VocabEnhancementProcessor
from processors.vocab_selection.processor import VocabSelectionProcessor
from utils.exceptions import ConfigError
from utils.run_folder import RunFolder

from .context import PipelineContext
from .report import OK, SKIPPED, StepSummary


def _cost(ctx: PipelineContext, usage: Usage, batch: bool = False) -> float:
    try:
        return ctx.provider.pricing.cost(usage, ctx.config.model, batch)
    except Exception:  # pricing is informational; never fail a step over it
        return 0.0


class ExtractionStep(ProcessorStep):
    name = "1"
    depends_on = ()

    def run(self, ctx: PipelineContext) -> StepSummary:
        cfg = ctx.config
        if ctx.run_folder is None:
            if cfg.input_folder is None:
                raise ConfigError("--input is required to run step 1")
            ctx.run_folder = RunFolder.create(cfg.output_root, ctx.clock)
        chunking = None
        if cfg.chunking is not None:
            from processors.metadata_extraction.chunking import ChunkingStrategyImpl
            chunking = ChunkingStrategyImpl(ctx.provider, cfg.model, cfg.chunking)
        extractor = MetadataExtractor(ctx.provider, cfg.model, chunking=chunking)
        s = MetadataExtractionProcessor(ctx.provider, extractor, use_batch=cfg.use_batch,
                                        sleep=ctx.sleep).run(cfg.input_folder, ctx.run_folder)
        return StepSummary(OK, s.usage, _cost(ctx, s.usage, s.mode == "BATCH"),
                           s.failed, f"{s.succeeded}/{s.total} {s.mode}")


class CleanupStep(ProcessorStep):
    name = "1.5"
    depends_on = ("1",)

    def run(self, ctx: PipelineContext) -> StepSummary:
        extractor = MetadataExtractor(ctx.provider, ctx.config.model)
        s = BatchCleanupProcessor(ItemReprocessor(extractor)).run(ctx.run_folder)
        if s.status is CleanupStatus.NOT_A_BATCH_RUN:
            return StepSummary(SKIPPED, detail="not a batch run")
        return StepSummary(OK, issues=s.n_still_failed,
                           detail=f"fixed={s.n_fixed} still_failed={s.n_still_failed}")


class VocabEnhancementStep(ProcessorStep):
    name = "2"
    depends_on = ("1",)

    def run(self, ctx: PipelineContext) -> StepSummary:
        lookup = ctx.standard_factory(ctx.run_folder)
        s = VocabEnhancementProcessor(ctx.run_folder, lookup, clock=ctx.clock).run()
        return StepSummary(OK, issues=len(s.errors),
                           detail=f"{s.subjects_with_terms}/{s.n_subjects} subjects with terms")


class VocabSelectionStep(ProcessorStep):
    name = "3"
    depends_on = ("2",)

    def run(self, ctx: PipelineContext) -> StepSummary:
        p = VocabSelectionProcessor(ctx.run_folder, ctx.provider, ctx.config.model,
                                    use_batch=ctx.config.use_batch, sleep=ctx.sleep)
        p.run()
        u = p.usage.usage
        return StepSummary(OK, u, _cost(ctx, u))


class EntityAuthorityStep(ProcessorStep):
    name = "4"
    depends_on = ("1",)

    def run(self, ctx: PipelineContext) -> StepSummary:
        data = EntityAuthorityProcessor(ctx.run_folder, threshold=ctx.config.threshold,
                                        clock=ctx.clock).run()
        return StepSummary(OK, detail=f"{len(data.get('entities', data))} entities")


def default_steps():
    return [ExtractionStep(), CleanupStep(), VocabEnhancementStep(),
            VocabSelectionStep(), EntityAuthorityStep()]
