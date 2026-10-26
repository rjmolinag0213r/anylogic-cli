# TEST.md: cli-anything-anylogic

## Part 1: Test plan

| File | Planned | Scope |
|---|---|---|
| test_core.py | 45 | data layer on a synthetic CRLF `.alp` (no AnyLogic needed) |
| test_full_e2e.py | 12 | real AnyLogic install, real bundled models, installed CLI via subprocess, live engine |

**Unit (test_core.py)**: project (lossless round-trip, info, invalid/missing files, id
allocation, save-as with package rename), variables (parameter/stock/flow edits, CDATA and
line-layout preservation, unit validation, add/remove parameter with experiment sync),
blocks (list, params, unit handling, rollback on a bad unit, reset, population size),
statecharts (show, rate, trigger switch), experiments (comment nodes ignored, overrides,
stop time with FinalDate recalculation, seeds, month arithmetic), session (undo/redo,
token masking, history reset).

**E2E (test_full_e2e.py)**
- *Installation*: AnyLogic PLE detected, design-time API present.
- *Real model files*: every bundled example (525) parses; >99% re-serialise byte-identically;
  edit the "Bass Diffusion" SD model (parameter + stock + stop time) and the "Call Center"
  process model (Source.rate with unit), then reload and verify.
- *CLI subprocess*: --help, system info, the full open → var set → stop → seed → history →
  undo → validate workflow, save-as copy, JSON errors with exit code 1, no-model error.
- *Live engine* (`-m live`, needs ANYLOGIC_API_TOKEN): open an edited copy in the IDE, list
  agents/experiments, run the experiment with the real AnyLogic engine, assert no run errors, stop.

## Part 2: Results (`-m "not live"`, AnyLogic 8.9.10 PLE, Python 3.13, Windows 11)

```
cli_anything/anylogic/tests/test_core.py::TestProject::test_roundtrip_is_byte_identical PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_info PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_rejects_non_alp PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_rejects_wrong_root PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_rejects_broken_xml PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_missing_file PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_new_ids_unique PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_save_as_renames_package PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_save_as_refuses_overwrite PASSED
cli_anything/anylogic/tests/test_core.py::TestProject::test_java_package PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_list_and_kinds PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_set_parameter_keeps_cdata PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_set_keeps_line_layout PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_set_stock_and_flow PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_unit_on_unitless_param_rejected PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_unknown_variable PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_add_parameter_syncs_experiment PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_add_parameter_validation PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_remove_parameter PASSED
cli_anything/anylogic/tests/test_core.py::TestVariables::test_unknown_agent PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_list_embedded PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_block_params_only_set PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_set_keeps_existing_unit PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_set_new_value_with_unit PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_bad_unit_leaves_file_unchanged PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_unknown_block_param PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_reset PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_population PASSED
cli_anything/anylogic/tests/test_core.py::TestBlocks::test_unit_class PASSED
cli_anything/anylogic/tests/test_core.py::TestStatechart::test_show PASSED
cli_anything/anylogic/tests/test_core.py::TestStatechart::test_set_rate PASSED
cli_anything/anylogic/tests/test_core.py::TestStatechart::test_switch_to_timeout PASSED
cli_anything/anylogic/tests/test_core.py::TestStatechart::test_missing_transition PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_comments_ignored PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_set_and_reset_param PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_unknown_param PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_stop_time_updates_dates PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_stop_never PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_stop_before_start PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_seed PASSED
cli_anything/anylogic/tests/test_core.py::TestExperiments::test_month_arithmetic PASSED
cli_anything/anylogic/tests/test_core.py::TestSession::test_undo_redo PASSED
cli_anything/anylogic/tests/test_core.py::TestSession::test_undo_empty PASSED
cli_anything/anylogic/tests/test_core.py::TestSession::test_status_masks_token PASSED
cli_anything/anylogic/tests/test_core.py::TestSession::test_switching_project_clears_history PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestInstallation::test_anylogic_found PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestInstallation::test_design_time_api_shipped PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestRealModelFiles::test_all_examples_roundtrip PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestRealModelFiles::test_edit_system_dynamics_model PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestRealModelFiles::test_edit_process_model_blocks PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_help PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_system_info PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_full_workflow PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_save_as_copy PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_error_is_json_and_nonzero PASSED
cli_anything/anylogic/tests/test_full_e2e.py::TestCLISubprocess::test_no_project_selected PASSED
====================== 56 passed, 1 deselected in 7.25s =======================
```

Additional manual check: copies of the user's own course models (SIR, CallCenterPhase5) were
edited through the installed CLI and diffed against the originals. Only the intended lines changed.

### Coverage notes
- The live-engine test **could not be run**: AnyLogic 8.9.10 PLE does not show the
  "Enable Python connection" button (confirmed from a screenshot of the real install; the
  button is gated by a license-type check in AnyLogic's code). It applies to editions that have it.
- Opening an edited model in the AnyLogic GUI to confirm it loads is part of the live test.
