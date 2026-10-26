---
name: "cli-anything-anylogic"
description: "Inspect, edit and run AnyLogic simulation models (.alp) from the command line: parameters, stocks/flows, process blocks, statecharts, experiments, plus running models in the real AnyLogic IDE via its Design-Time Python API. Works with AnyLogic 8.9 Personal Learning Edition."
---

# cli-anything-anylogic

Command: `cli-anything-anylogic` (or `python -m cli_anything.anylogic`).
Always put `--json` first when you parse output: `cli-anything-anylogic --json var list`.
Errors print `{"error": ..., "type": ...}` and exit 1.

## Prerequisites
- AnyLogic 8.9+ installed (auto-detected; else set `ANYLOGIC_HOME`).
- For running models: AnyLogic open, with **Enable Python connection** clicked; the user gives you the token.
  This button is NOT available in AnyLogic 8.9.10 PLE; there, edit files and ask the user to press Run in the IDE (`ide open` opens the model).

## Workflow for agents
1. `project open <file.alp>`. Prefer `project save-as <dir> --name <NewName>` first, so you edit a copy.
2. Inspect before editing: `project info`, `agent list`, `agent show [Agent]`, `var list`,
   `block list`, `block params <block> [--all]`, `statechart show -a <Agent>`, `experiment show`.
3. Edit (each edit is saved immediately and is undoable with `session undo`):
   - `var set <name> <value> [-a Agent] [--unit U]` sets a parameter default, variable/stock
     initial value, or flow/dynamic-variable formula (Java expressions allowed).
   - `var add-param <name> --type double --default 0 [-a Agent]`, `var remove <name>`
   - `block set <block> <param> <value> [--unit PER_MINUTE|MINUTE|...]`, `block reset`,
     `block population <name> <count>`
   - `statechart set <transition> <value> -a <Agent> [--unit PER_DAY] [--trigger rate|timeout|condition]`
   - `experiment set-param <param> <value> [-e Exp]`, `experiment stop --time T | --never`,
     `experiment seed --seed N | --random`
4. Run with the real engine:
   `live connect --token T` → `live open` → `live run [-e Exp]` → `live errors` →
   `live query "SQL" [--csv out.csv]` → `live stop`.
5. `project validate` checks structure (not Java compilation; AnyLogic reports that on run).

## Defaults
- `-a/--agent` defaults to the top-level agent of the first experiment (usually `Main`).
- `-e/--experiment` defaults to the first experiment.
- `--project/-p <file.alp>` overrides the session's current model for one command.
- Units: time `SECOND MINUTE HOUR DAY WEEK MONTH YEAR`, rates `PER_SECOND ... PER_YEAR`,
  length `METER ...`, speed `MPS KPH ...`. Stop times use the model time unit (`project info`).

## Cautions
- If the model is open in the IDE, file edits are not seen there until it is reopened; tell the
  user to close it without saving, or use `live open`.
- Never edit the user's original model without asking; work on a `save-as` copy.
- Don't add blocks or connectors by hand; ask the user to do that in the IDE.

## Examples
```bash
cli-anything-anylogic --json system examples -f "call center"
cli-anything-anylogic project open "C:/Models/CallCenter/CallCenter.alp"
cli-anything-anylogic block set source rate 3 --unit PER_MINUTE
cli-anything-anylogic block set Operators capacity 6
cli-anything-anylogic experiment stop --time 480
cli-anything-anylogic live run
```
