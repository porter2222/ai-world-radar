# Legacy Worker Notes

This folder records old HN event pipeline materials kept only for reference.

The current P1 architecture is based on:

SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent

Old names such as EvidenceCard, EventCluster, ContentArtifact, QualityGateResult,
Brief, and BriefItem are no longer implementation contracts.

The legacy runtime files below are not P1-1 entrypoints:

- worker/pipelines/hn_event_pipeline.py
- scripts/run_hn_pipeline.py

For P1-1 acceptance, use the new schemas, ORM models, Alembic migration, and
service-layer tests instead of the old HN closed-loop pipeline.
