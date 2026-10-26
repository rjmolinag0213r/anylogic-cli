# AnyLogic: analysis and SOP for the CLI harness

## Backend engine (Phase 1 findings, AnyLogic 8.9.10 PLE)
- **IDE**: Eclipse RCP product `com.anylogic.ui.ple.AnyLogicPLE` with a bundled JRE. Models are
  built and run only inside the IDE; PLE has no standalone export.
- **Design-Time Python API** (undocumented, shipped in 8.9): `anylogic_design_time_api/` plus
  py4j 0.10.9.7 in `plugins/com.anylogic.core8_*/lib`. The IDE action
  `com.anylogic.commands.EnablePythonConnectionAction` ("Enable Python connection") calls
  `PythonConnector.startStaticInstance`, which starts a py4j `GatewayServer` on preference
  `AnyLogic.PythonAPIPort` (Python default 25333) with a random UUID auth token shown to the user.
  The entry point is `com.anylogic.python.PythonWorkspace`, which exposes:
  - `ModelManager`: openModel, runModel(model, experiment), stopModel, getModels, getAgents,
    getExperiments, executeDbQuery, getDbStructure
  - `ElementManager`: getModelStructure, getModelRunErrors, getBlocks, getPorts,
    connectBlocks, createElement, deleteElement
  - `PropertyManager`: getPropertyValue / setProperty
- **Data model**: `.alp` = XML `<AnyLogicWorkspace><Model>`, with `ActiveObjectClasses` (agent
  types: `Variables/Variable[@Class=Parameter|PlainVariable|StockVariable|Flow|AuxVariable]`,
  `EmbeddedObjects` (library blocks / populations), `Connectors`, `StatechartElements`),
  `RunConfiguration`, and `Experiments`. Element ids are integers (some are intentionally
  repeated as references). Values are `CodeValue` or `CodeUnitValue` (`<Code>` plus `<Unit Class=...>`).
- AnyLogic also ships an AI assistant (`ProgramData/.../ai/com.anylogic.ai_connector-*.jar`,
  langchain4j); it isn't used here.

## Design decisions
- Lossless lxml parsing (CDATA, comments, prolog, CRLF, `<x></x>` vs `<x/>`): 523/525 bundled
  examples and all tested user models re-serialise byte-identically.
- In-place value updates keep the original indentation, so diffs stay minimal.
- Every mutation snapshots the file, which gives undo/redo (`~/.cli-anything-anylogic/history`).
- Structural creation (new blocks/connectors) is deliberately left to the IDE / live API.
