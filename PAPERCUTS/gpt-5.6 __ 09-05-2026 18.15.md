# Papercuts

- `tests/processing/test_searchable_projection.py` fixture omitted the currently non-null `Photo.admission_pipeline_revision_id`, so its listed task regression gate failed before exercising search behavior. TASK-107 restores the fixture's valid admission lineage without changing production behavior.
