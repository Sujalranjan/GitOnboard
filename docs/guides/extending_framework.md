# Extending the Analysis Framework

The Repository Intelligence Platform is designed around modular, extensible analysis providers and pipeline stages.

---

## 1. Modular Analyzers (`backend/intelligence/engine/analyzers/`)

Analyzers inspect the extracted Concrete Syntax Tree (CST/AST) and populate entities and relationships into the Repository Intelligence Model (RIM).

### Adding a New AST Analyzer
1. Create a new analyzer module in `backend/intelligence/engine/analyzers/`.
2. Inherit from the base analyzer protocol/class.
3. Register the analyzer in `get_default_registry()` (`backend/intelligence/engine/analyzers/__init__.py`).

---

## 2. Modular Analysis Stages (`backend/intelligence/stages/`)

Stages run after initial RIM graph construction to compute higher-level metrics or metadata:
- `RepositoryMetadataStage` (`backend/intelligence/stages/metadata_stage.py`): Extracts frameworks, entrypoints, and architectural layers.
- `MetricsStage` (`backend/intelligence/stages/metrics_stage.py`): Computes lines of code, symbol counts, and complexity metrics.

### Adding a New Analysis Stage
1. Create a stage class implementing the `AnalysisStage` protocol (`run(model: RepositoryModel) -> None`).
2. Add the stage to `AnalysisPipeline` in `backend/intelligence/pipeline.py` or `AnalysisWorker` in `backend/services/worker.py`.

---

## 3. Capability Detectors (`backend/intelligence/capabilities/detectors/`)

Layer 6 capability detectors match multi-fact patterns across routes, handlers, services, and models to classify architectural capabilities.

### Adding a New Capability Detector
1. Create a detector class in `backend/intelligence/capabilities/detectors/` (e.g. `WebSocketDetector`, `PaymentDetector`).
2. Implement detection rules scanning RIM entities and relationships.
3. Register the detector in `CapabilityBuilderEngine` (`backend/intelligence/capabilities/engine.py`).
4. Add automated positive and negative test cases in `backend/tests/test_capabilities.py`.
