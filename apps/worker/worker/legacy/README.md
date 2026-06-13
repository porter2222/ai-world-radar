# Legacy Worker Notes

This folder records old HN event pipeline materials kept only for reference.

The current P1 architecture is based on:

SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent

Old names such as EvidenceCard, EventCluster, ContentArtifact, QualityGateResult,
Brief, and BriefItem are no longer implementation contracts.

The legacy runtime files below are not P1-1 entrypoints. In P1-2 they are also
not active event dossier workflow entrypoints:

- worker/pipelines/hn_event_pipeline.py
- scripts/run_hn_pipeline.py: now fails fast with a legacy message and points to
  scripts/run_event_pipeline.py.

For P1-1 and P1-2 acceptance, use the new schemas, ORM models, Alembic
migration, service-layer tests, EventPipelineTools, and
scripts/run_event_pipeline.py instead of the old HN closed-loop pipeline.
