# cli-anything-anylogic

A command-line interface for **AnyLogic 8.9+** (including the free Personal Learning
Edition), built with the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology.
It lets you, or an AI agent, inspect and edit AnyLogic simulation models (`.alp`) and drive the
real AnyLogic IDE from the terminal.

## What it talks to

| Layer | Used for | Needs |
|---|---|---|
| `.alp` XML (lxml, lossless) | inspect/edit parameters, stocks, flows, blocks, statecharts, experiments | nothing else |
| `AnyLogic.exe` | open a model in the IDE | AnyLogic installed |
| AnyLogic **Design-Time Python API** (py4j, inside the IDE) | open, **run**, stop, read run errors, query the model database | IDE running + *Enable Python connection* |

AnyLogic PLE cannot export standalone Java apps, so **the IDE is the only engine that runs
models**. This CLI never imitates the simulation engine; it hands the model to AnyLogic.

## Install

```bash
pip install -e .            # from the agent-harness folder
cli-anything-anylogic --help
```

Requirements: Python 3.10+, AnyLogic 8.9+. The CLI auto-detects
`C:\Program Files\AnyLogic 8.9 Personal Learning Edition`; set `ANYLOGIC_HOME` to override.

## Quick start

```bash
cli-anything-anylogic project open "C:/Users/me/Models/SIR/SIR.alp"
cli-anything-anylogic project save-as "C:/Users/me/Models/SIR_whatif" --name SIR_whatif   # work on a copy
cli-anything-anylogic var list                       # parameters of Main
cli-anything-anylogic var set ContactRate 2.5
cli-anything-anylogic statechart show -a Person
cli-anything-anylogic statechart set Recovery "1.0/main.AverageIllnessDuration" -a Person --unit PER_DAY
cli-anything-anylogic experiment stop --time 365
cli-anything-anylogic experiment seed --seed 42
cli-anything-anylogic session undo                   # every edit is undoable
```

Process models:

```bash
cli-anything-anylogic block list
cli-anything-anylogic block params service
cli-anything-anylogic block set source rate 2 --unit PER_MINUTE
cli-anything-anylogic block set Operators capacity 8
cli-anything-anylogic block connectors
```

Add `--json` before the command for machine-readable output. Run with no arguments to get the REPL.

## Running models in the real AnyLogic

> **License note:** the *Enable Python connection* toolbar button (Python logo) only appears for
> some AnyLogic license types. It is **not present in AnyLogic 8.9.10 Personal Learning Edition**
> (checked on a real install). With PLE, use the file-editing commands, then `ide open` and press
> AnyLogic's Run button yourself. The `live` commands work on editions that show the button.

1. Open AnyLogic and click **Enable Python connection** (API icon). Copy the token it shows.
2. Then:

```bash
cli-anything-anylogic live connect --token <TOKEN>
cli-anything-anylogic live open                   # opens the current .alp in the IDE
cli-anything-anylogic live run -e Simulation      # builds & runs with the real engine
cli-anything-anylogic live errors                 # build/runtime errors reported by AnyLogic
cli-anything-anylogic live db-tables
cli-anything-anylogic live query "SELECT * FROM my_log" --csv results.csv
cli-anything-anylogic live stop
```

The token changes every time you toggle the connection; `ANYLOGIC_API_TOKEN` and
`ANYLOGIC_API_PORT` (default 25333) also work.

**Important:** file edits (`var set`, `block set`, ...) change the `.alp` on disk. If the model is
already open in AnyLogic, close it there *without saving* and reopen it (or use `live open`),
otherwise AnyLogic keeps showing, and may save over, its in-memory copy.

## Command groups

`system` (info, examples) · `project` (open, info, validate, save-as, close) ·
`agent` (list, show, set-startup) · `var` (list, get, set, add-param, remove) ·
`block` (list, params, set, reset, population, connectors) · `statechart` (show, set) ·
`experiment` (list, show, set-param, reset-param, stop, seed) · `ide` (open, status) ·
`live` (connect, status, models, open, agents, experiments, structure, run, stop, errors,
get, set, db-tables, query) · `session` (status, undo, redo, history)

## Tests

```bash
pip install pytest
pytest cli_anything/anylogic/tests -m "not live" -v       # file + subprocess tests
ANYLOGIC_API_TOKEN=<token> pytest cli_anything/anylogic/tests -m live -v -s   # real engine
```

## Limitations

* Creating new blocks/agents and wiring connectors is not done through file edits (too
  easy to produce a model AnyLogic rejects); use the IDE, or `live set` for properties.
* Java compile errors are only detectable by AnyLogic itself (`live run` and then `live errors`).
* Changes made with `live set` live in the IDE's memory until you save in AnyLogic.
