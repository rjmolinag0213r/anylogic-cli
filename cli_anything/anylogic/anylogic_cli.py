#!/usr/bin/env python3
"""AnyLogic CLI - a stateful command-line interface for AnyLogic models.

Edits real AnyLogic project files (.alp) and drives the real AnyLogic IDE
(Personal Learning and University editions) through its Design-Time Python API.

Usage:
    # One-shot commands
    cli-anything-anylogic project open "C:/Models/SIR/SIR.alp"
    cli-anything-anylogic var list
    cli-anything-anylogic var set ContactRate 2.5
    cli-anything-anylogic experiment stop --time 365
    cli-anything-anylogic live run --experiment Simulation

    # Interactive REPL (default when no command is given)
    cli-anything-anylogic
"""

import csv
import functools
import json
import os
import shlex
import sys
from contextlib import contextmanager

import click

from cli_anything.anylogic import __version__
from cli_anything.anylogic.core import elements as el_mod
from cli_anything.anylogic.core import experiments as exp_mod
from cli_anything.anylogic.core import project as proj_mod
from cli_anything.anylogic.core.session import Session
from cli_anything.anylogic.utils import anylogic_backend as backend

_json_output = False
_repl_mode = False
_project_override = None


# ── Output helpers ───────────────────────────────────────────────────

def output(data, message: str = ""):
    if _json_output:
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if message:
        click.echo(message)
    if isinstance(data, dict):
        _print_dict(data)
    elif isinstance(data, list):
        _print_list(data)
    elif data is not None:
        click.echo(str(data))


def _print_dict(d: dict, indent: int = 0):
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict) and v:
            click.echo(f"{prefix}{k}:")
            _print_dict(v, indent + 1)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            click.echo(f"{prefix}{k}:")
            _print_list(v, indent + 1)
        else:
            click.echo(f"{prefix}{k}: {v}")


def _print_list(items: list, indent: int = 0):
    prefix = "  " * indent
    if not items:
        click.echo(f"{prefix}(none)")
        return
    if all(isinstance(i, dict) for i in items):
        keys = [k for k in items[0] if not isinstance(items[0][k], (dict, list))]
        widths = {k: max(len(str(k)), *(len(_cell(i.get(k))) for i in items)) for k in keys}
        click.echo(prefix + "  ".join(str(k).ljust(widths[k]) for k in keys))
        click.echo(prefix + "  ".join("-" * widths[k] for k in keys))
        for i in items:
            click.echo(prefix + "  ".join(_cell(i.get(k)).ljust(widths[k]) for k in keys))
    else:
        for i in items:
            click.echo(f"{prefix}- {i}")


def _cell(v, limit=60):
    s = "" if v is None else str(v).replace("\r", " ").replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 1] + "..."


def handle_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (proj_mod.AlpError, backend.LiveApiError, backend.AnyLogicNotFound,
                FileNotFoundError, RuntimeError, ValueError) as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": type(e).__name__}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
    return wrapper


# ── Project resolution ───────────────────────────────────────────────

def _has_project() -> bool:
    return bool(_project_override or Session().project_path)


def _project_path() -> str:
    path = _project_override or Session().project_path
    if not path:
        raise RuntimeError("No model selected. Run 'project open <file.alp>' or pass --project <file.alp>")
    return path


def load() -> proj_mod.AlpProject:
    return proj_mod.open_project(_project_path())


@contextmanager
def mutate(label: str):
    """Load the model, snapshot it for undo, yield it, then save."""
    proj = load()
    sess = Session()
    if sess.project_path != proj.path:
        sess.set_project(proj.path)
    sess.snapshot(proj.path, label)
    yield proj
    proj.save()


def _agent(proj, agent):
    """Default agent = the top-level agent of the first experiment (usually Main)."""
    if agent:
        return agent
    for e in proj.experiments():
        aoc = proj.agent_class_by_id(e.get("ActiveObjectClassId"))
        if aoc is not None:
            return proj_mod.text(aoc, "Name")
    classes = proj.agent_classes()
    if not classes:
        raise proj_mod.AlpError("Model has no agent types")
    return proj_mod.text(classes[0], "Name")


def _first_exp(proj):
    exps = proj.experiments()
    if not exps:
        raise proj_mod.AlpError("Model has no experiments")
    return proj_mod.text(exps[0], "Name")


agent_option = click.option("--agent", "-a", default=None,
                            help="Agent type (default: the top-level agent, usually Main)")


# ── Root group ───────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--project", "-p", "project_path", type=click.Path(), default=None,
              help="Model file (.alp) to operate on; defaults to the session's model")
@click.option("--edition", type=click.Choice(backend.EDITIONS), envvar="ANYLOGIC_EDITION", default=None,
              help="AnyLogic edition to use; defaults to 'system use', then the running IDE")
@click.version_option(__version__, prog_name="cli-anything-anylogic")
@click.pass_context
def cli(ctx, use_json, project_path, edition):
    """AnyLogic CLI - edit .alp models and drive the AnyLogic IDE from the terminal."""
    global _json_output, _project_override
    _json_output = use_json
    _project_override = os.path.abspath(project_path) if project_path else None
    backend.set_preferred_edition(edition or Session().edition)
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl, project_path=project_path)


# ── system ───────────────────────────────────────────────────────────

@cli.group()
def system():
    """AnyLogic installation details."""


@system.command("info")
@handle_errors
def system_info():
    """Show the AnyLogic install this CLI drives."""
    info = backend.install_info()
    info["all_installs"] = backend.find_installs()
    output(info)


@system.command("editions")
@handle_errors
def system_editions():
    """List installed AnyLogic editions and which one this CLI is using."""
    output(backend.list_editions())


@system.command("use")
@click.argument("edition", type=click.Choice(backend.EDITIONS + ("auto",)))
@handle_errors
def system_use(edition):
    """Remember which edition to use ('auto' follows the running IDE)."""
    choice = None if edition == "auto" else edition
    backend.set_preferred_edition(choice)
    home = backend.find_anylogic()
    Session().set_edition(choice)
    output({"edition": edition, "home": home}, f"Using AnyLogic edition: {edition}")


@system.command("examples")
@click.option("--filter", "-f", "pattern", default="", help="Substring to match in the model name")
@click.option("--limit", default=50, show_default=True)
@handle_errors
def system_examples(pattern, limit):
    """List AnyLogic's bundled example models (good starting points)."""
    root = backend.examples_dir()
    if not root:
        raise RuntimeError("Example models folder not found")
    hits = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".alp") and pattern.lower() in f.lower():
                hits.append({"name": f[:-4], "path": os.path.join(dirpath, f)})
    hits.sort(key=lambda h: h["name"].lower())
    more = f" (showing {limit})" if len(hits) > limit else ""
    output(hits[:limit], f"{len(hits)} example model(s){more}")


# ── project ──────────────────────────────────────────────────────────

@cli.group()
def project():
    """Open, inspect, validate and copy .alp models."""


@project.command("open")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@handle_errors
def project_open(path):
    """Select a model for subsequent commands."""
    proj = proj_mod.open_project(path)
    Session().set_project(proj.path)
    output(proj.info(), f"Opened {proj.name}")


@project.command("info")
@handle_errors
def project_info():
    """Summary of the current model."""
    output(load().info())


@project.command("close")
@handle_errors
def project_close():
    """Forget the current model (clears undo history)."""
    Session().set_project(None)
    output({"closed": True})


@project.command("save-as")
@click.argument("dest", type=click.Path())
@click.option("--name", default=None, help="Rename the model (also renames its Java package)")
@click.option("--switch/--no-switch", default=True, help="Make the copy the current model")
@handle_errors
def project_save_as(dest, name, switch):
    """Copy the model to a new .alp file (a safe sandbox for experiments).

    DEST may be a .alp path or a folder (the file is then named after the model).
    """
    proj = load()
    if not dest.lower().endswith(".alp"):
        dest = os.path.join(dest, (name or proj.name) + ".alp")
    result = proj_mod.save_as(proj, dest, name)
    if switch:
        Session().set_project(result["output"])
    output(result, f"Saved copy to {result['output']}")


@project.command("validate")
@handle_errors
def project_validate():
    """Check the model file for structural problems."""
    proj = load()
    problems = []
    names = {proj_mod.text(a, "Name") for a in proj.agent_classes()}
    for aoc in proj.agent_classes():
        agent_name = proj_mod.text(aoc, "Name")
        embedded = aoc.findall("EmbeddedObjects/EmbeddedObject")
        blocks = {proj_mod.text(e, "Name") for e in embedded}
        for c in el_mod.list_connectors(proj, agent_name):
            for end in (c["from"], c["to"]):
                owner = end.split(".")[0] if "." in end else None
                if owner and owner not in blocks:
                    problems.append(f"{agent_name}: connector {c['name']} references missing block '{owner}'")
        for eo in embedded:
            pkg = proj_mod.text(eo, "ActiveObjectClass/PackageName")
            cls = proj_mod.text(eo, "ActiveObjectClass/ClassName")
            if pkg == proj.package and cls not in names:
                problems.append(f"{agent_name}: '{proj_mod.text(eo, 'Name')}' uses unknown agent type '{cls}'")
    for e in proj.experiments():
        if proj.agent_class_by_id(e.get("ActiveObjectClassId")) is None:
            problems.append(f"experiment '{proj_mod.text(e, 'Name')}' points at a missing agent type")
    output({"valid": not problems, "problems": problems,
            "note": "Java compile errors are only detectable by AnyLogic: run it, then 'live errors'."})


# ── agent ────────────────────────────────────────────────────────────

@cli.group()
def agent():
    """Agent types in the model."""


@agent.command("list")
@handle_errors
def agent_list():
    """List agent types."""
    output(el_mod.list_agents(load()))


@agent.command("show")
@click.argument("name", required=False)
@handle_errors
def agent_show(name):
    """Everything inside one agent type."""
    proj = load()
    name = _agent(proj, name)
    output({
        "agent": name,
        "variables": el_mod.list_variables(proj, name),
        "embedded": el_mod.list_embedded(proj, name),
        "connectors": el_mod.list_connectors(proj, name),
        "statechart": el_mod.statechart(proj, name),
    })


@agent.command("set-startup")
@click.argument("code")
@agent_option
@handle_errors
def agent_set_startup(code, agent):
    """Replace an agent's 'On startup' Java code."""
    with mutate("agent set-startup") as proj:
        output(el_mod.set_startup_code(proj, _agent(proj, agent), code))


# ── var (parameters, variables, stocks, flows, dynamic variables) ────

@cli.group("var")
def var():
    """Parameters, variables, stocks, flows and dynamic variables."""


@var.command("list")
@agent_option
@click.option("--kind", "-k", type=click.Choice(sorted(el_mod.VARIABLE_KINDS)), default=None)
@handle_errors
def var_list(agent, kind):
    """List variables of an agent type."""
    proj = load()
    output(el_mod.list_variables(proj, _agent(proj, agent), kind))


@var.command("get")
@click.argument("name")
@agent_option
@handle_errors
def var_get(name, agent):
    """Show one variable/parameter."""
    proj = load()
    hits = [v for v in el_mod.list_variables(proj, _agent(proj, agent)) if v["name"] == name]
    if not hits:
        raise proj_mod.AlpError(f"No variable '{name}'")
    output(hits[0])


@var.command("set")
@click.argument("name")
@click.argument("value")
@agent_option
@click.option("--unit", default=None, help="Unit for unit-aware values (e.g. DAY, PER_HOUR)")
@handle_errors
def var_set(name, value, agent, unit):
    """Set a parameter default, initial value (variable/stock) or formula (flow/dynamic)."""
    with mutate(f"var set {name}") as proj:
        output(el_mod.set_variable(proj, _agent(proj, agent), name, value, unit))


@var.command("add-param")
@click.argument("name")
@agent_option
@click.option("--type", "ptype", default="double", show_default=True)
@click.option("--default", "default", default="0", show_default=True)
@handle_errors
def var_add_param(name, agent, ptype, default):
    """Add a new parameter to an agent type."""
    with mutate(f"var add-param {name}") as proj:
        output(el_mod.add_parameter(proj, _agent(proj, agent), name, ptype, default))


@var.command("remove")
@click.argument("name")
@agent_option
@handle_errors
def var_remove(name, agent):
    """Delete a variable/parameter (references in code are not rewritten)."""
    with mutate(f"var remove {name}") as proj:
        output(el_mod.remove_variable(proj, _agent(proj, agent), name))


# ── block (library blocks, agent populations) ────────────────────────

@cli.group()
def block():
    """Process-library blocks (Source, Delay, Service...) and agent populations."""


@block.command("list")
@agent_option
@click.option("--kind", type=click.Choice(["block", "population", "agent"]), default=None)
@handle_errors
def block_list(agent, kind):
    """List blocks and embedded agents."""
    proj = load()
    output(el_mod.list_embedded(proj, _agent(proj, agent), kind))


@block.command("params")
@click.argument("block_name")
@agent_option
@click.option("--all", "show_all", is_flag=True, help="Include parameters left at their defaults")
@handle_errors
def block_params(block_name, agent, show_all):
    """Show a block's parameters (only explicitly set ones unless --all)."""
    proj = load()
    output(el_mod.block_parameters(proj, _agent(proj, agent), block_name, only_set=not show_all))


@block.command("set")
@click.argument("block_name")
@click.argument("param")
@click.argument("value")
@agent_option
@click.option("--unit", default=None, help="e.g. MINUTE, PER_HOUR, METER")
@handle_errors
def block_set(block_name, param, value, agent, unit):
    """Set a block parameter, e.g.: block set source rate 2 --unit PER_MINUTE"""
    with mutate(f"block set {block_name}.{param}") as proj:
        output(el_mod.set_block_parameter(proj, _agent(proj, agent), block_name, param, value, unit))


@block.command("reset")
@click.argument("block_name")
@click.argument("param")
@agent_option
@handle_errors
def block_reset(block_name, param, agent):
    """Return a block parameter to its library default."""
    with mutate(f"block reset {block_name}.{param}") as proj:
        output(el_mod.reset_block_parameter(proj, _agent(proj, agent), block_name, param))


@block.command("population")
@click.argument("name")
@click.argument("size")
@agent_option
@handle_errors
def block_population(name, size, agent):
    """Set the initial number of agents in a population."""
    with mutate(f"block population {name}") as proj:
        output(el_mod.set_population_size(proj, _agent(proj, agent), name, size))


@block.command("connectors")
@agent_option
@handle_errors
def block_connectors(agent):
    """Show how blocks are wired together."""
    proj = load()
    output(el_mod.list_connectors(proj, _agent(proj, agent)))


# ── statechart ───────────────────────────────────────────────────────

@cli.group()
def statechart():
    """States and transitions of an agent's statechart."""


@statechart.command("show")
@agent_option
@handle_errors
def statechart_show(agent):
    """List states and transitions."""
    proj = load()
    output(el_mod.statechart(proj, _agent(proj, agent)))


@statechart.command("set")
@click.argument("transition")
@click.argument("value")
@agent_option
@click.option("--unit", default=None, help="e.g. PER_DAY for rates, DAY for timeouts")
@click.option("--trigger", type=click.Choice(["rate", "timeout", "condition"]), default=None)
@handle_errors
def statechart_set(transition, value, agent, unit, trigger):
    """Change a transition's rate, timeout or condition."""
    with mutate(f"statechart set {transition}") as proj:
        output(el_mod.set_transition(proj, _agent(proj, agent), transition, value, unit, trigger))


# ── experiment ───────────────────────────────────────────────────────

@cli.group()
def experiment():
    """Experiments: parameter values, stop time, random seed."""


@experiment.command("list")
@handle_errors
def experiment_list():
    """List experiments."""
    output([{k: v for k, v in e.items() if k != "parameters"} for e in exp_mod.list_experiments(load())])


@experiment.command("show")
@click.argument("name", required=False)
@handle_errors
def experiment_show(name):
    """Show an experiment (default: the first one)."""
    output(exp_mod.show(load(), name))


@experiment.command("set-param")
@click.argument("param")
@click.argument("value")
@click.option("--experiment", "-e", "exp_name", default=None)
@handle_errors
def experiment_set_param(param, value, exp_name):
    """Override a top-level parameter's value in an experiment."""
    with mutate(f"experiment set-param {param}") as proj:
        output(exp_mod.set_parameter(proj, exp_name or _first_exp(proj), param, value))


@experiment.command("reset-param")
@click.argument("param")
@click.option("--experiment", "-e", "exp_name", default=None)
@handle_errors
def experiment_reset_param(param, exp_name):
    """Drop an experiment override so the parameter's default is used."""
    with mutate(f"experiment reset-param {param}") as proj:
        output(exp_mod.reset_parameter(proj, exp_name or _first_exp(proj), param))


@experiment.command("stop")
@click.option("--time", "stop_time", type=float, default=None, help="Stop time in model time units")
@click.option("--never", is_flag=True, help="Run until stopped manually")
@click.option("--experiment", "-e", "exp_name", default=None)
@handle_errors
def experiment_stop(stop_time, never, exp_name):
    """Set when the experiment stops."""
    with mutate("experiment stop") as proj:
        output(exp_mod.set_stop(proj, exp_name, stop_time, never))


@experiment.command("seed")
@click.option("--seed", type=int, default=None, help="Fixed seed (reproducible runs)")
@click.option("--random", "use_random", is_flag=True, help="Random seed each run")
@click.option("--experiment", "-e", "exp_name", default=None)
@handle_errors
def experiment_seed(seed, use_random, exp_name):
    """Configure random number generation."""
    with mutate("experiment seed") as proj:
        output(exp_mod.set_seed(proj, exp_name, seed, use_random))


# ── ide (the real AnyLogic application) ──────────────────────────────

@cli.group()
def ide():
    """Launch the real AnyLogic IDE."""


@ide.command("open")
@click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False))
@handle_errors
def ide_open(path):
    """Open the model in AnyLogic (starts the IDE if it is not running)."""
    output(backend.open_in_ide(path or _project_path()), "Opening in AnyLogic...")


@ide.command("status")
@handle_errors
def ide_status():
    """Is the AnyLogic IDE running?"""
    output({"running": backend.is_ide_running(), "running_edition": backend.running_edition(),
            "home": backend.find_anylogic()})


# ── live (Design-Time Python API inside the running IDE) ─────────────

@cli.group()
def live():
    """Drive the running AnyLogic IDE: open, run, stop, inspect, query results.

    First, in AnyLogic click 'Enable Python connection' and copy the token.
    """


def _conn(token=None, port=None):
    sess = Session()
    tok = backend.resolve_token(token, sess.live.get("token"))
    return backend.LiveConnection(tok, backend.resolve_port(port, sess.live.get("port")))


def _live_model(model):
    if model:
        return model
    if _has_project():
        return load().name
    stored = Session().live.get("model")
    if stored:
        return stored
    raise RuntimeError("Which model? Pass --model NAME or select one with 'project open'")


def _live_agent(agent):
    if agent:
        return agent
    return _agent(load(), None) if _has_project() else "Main"


model_option = click.option("--model", "-m", default=None,
                            help="Model name as shown in the IDE (default: the current .alp's model)")


@live.command("connect")
@click.option("--token", default=None, help="Token shown by 'Enable Python connection'")
@click.option("--port", type=int, default=None, help=f"Gateway port (default {backend.DEFAULT_PORT})")
@handle_errors
def live_connect(token, port):
    """Verify and remember the IDE connection."""
    tok = backend.resolve_token(token, Session().live.get("token"))
    with _conn(tok, port) as c:
        models = c.list_models()
        port_used = c.port
    Session().set_live(token=tok, port=port_used)
    output({"connected": True, "port": port_used, "ide_edition": backend.gateway_edition(port_used),
            "open_models": models}, "Connected to AnyLogic")


@live.command("disconnect")
@handle_errors
def live_disconnect():
    """Forget the stored token."""
    Session().clear_live()
    output({"disconnected": True})


@live.command("status")
@handle_errors
def live_status():
    """Check the connection and list open models."""
    try:
        with _conn() as c:
            output({"connected": True, "port": c.port, "ide_edition": backend.gateway_edition(c.port),
                    "open_models": c.list_models()})
    except backend.LiveApiError as e:
        output({"connected": False, "reason": str(e).splitlines()[0],
                "ide_running": backend.is_ide_running(), "ide_edition": backend.running_edition()})


@live.command("models")
@handle_errors
def live_models():
    """Models currently open in the IDE."""
    with _conn() as c:
        output(c.list_models())


@live.command("open")
@click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False))
@handle_errors
def live_open(path):
    """Open a model inside the connected IDE."""
    path = os.path.abspath(path or _project_path())
    with _conn() as c:
        res = c.open_model(path)
    if res:
        Session().set_live(model=res["name"])
    output(res or {"opened": path}, f"Opened {path} in AnyLogic")


@live.command("agents")
@model_option
@handle_errors
def live_agents(model):
    """Agent types as seen by the IDE."""
    with _conn() as c:
        output(c.list_agents(_live_model(model)))


@live.command("experiments")
@model_option
@handle_errors
def live_experiments(model):
    """Experiments as seen by the IDE."""
    with _conn() as c:
        output(c.list_experiments(_live_model(model)))


@live.command("structure")
@click.argument("agent_name", required=False)
@model_option
@handle_errors
def live_structure(agent_name, model):
    """The IDE's own description of an agent's structure."""
    with _conn() as c:
        output(c.structure(_live_model(model), _live_agent(agent_name)))


@live.command("blocks")
@agent_option
@model_option
@handle_errors
def live_blocks(agent, model):
    """Process-library blocks in an agent, as seen by the IDE."""
    with _conn() as c:
        output(c.blocks(_live_model(model), _live_agent(agent)))


@live.command("children")
@agent_option
@model_option
@handle_errors
def live_children(agent, model):
    """All elements directly inside an agent, as seen by the IDE."""
    with _conn() as c:
        output(c.children(_live_model(model), _live_agent(agent)))


@live.command("run")
@click.option("--experiment", "-e", "exp_name", default=None, help="Experiment name (default: first)")
@model_option
@handle_errors
def live_run(exp_name, model):
    """Build and run an experiment in the IDE (the real AnyLogic engine)."""
    m = _live_model(model)
    with _conn() as c:
        if not exp_name:
            exps = c.list_experiments(m)
            if not exps:
                raise RuntimeError(f"Model '{m}' has no experiments")
            exp_name = exps[0]["name"]
        output(c.run(m, exp_name), f"Running {m}/{exp_name} in AnyLogic")


@live.command("stop")
@handle_errors
def live_stop():
    """Stop the running model."""
    with _conn() as c:
        output(c.stop())


@live.command("errors")
@model_option
@handle_errors
def live_errors(model):
    """Build / runtime errors reported by the IDE for a model."""
    m = _live_model(model)
    with _conn() as c:
        output({"model": m, "errors": c.run_errors(m)})


@live.command("get")
@click.argument("element")
@click.argument("prop")
@agent_option
@model_option
@handle_errors
def live_get(element, prop, agent, model):
    """Read an element property from the IDE's in-memory model."""
    with _conn() as c:
        value = c.get_property(_live_model(model), _live_agent(agent), element, prop)
        output({"element": element, "property": prop, "value": value})


@live.command("set")
@click.argument("element")
@click.argument("prop")
@click.argument("value")
@agent_option
@model_option
@handle_errors
def live_set(element, prop, value, agent, model):
    """Set an element property in the IDE (unsaved until you save in AnyLogic)."""
    with _conn() as c:
        output(c.set_property(_live_model(model), _live_agent(agent), element, prop, value))


@live.command("db-tables")
@model_option
@handle_errors
def live_db_tables(model):
    """Tables and columns in the model's built-in database."""
    with _conn() as c:
        output(c.db_structure(_live_model(model)))


@live.command("query")
@click.argument("sql")
@model_option
@click.option("--csv", "csv_path", type=click.Path(dir_okay=False), default=None,
              help="Also write the rows to a CSV file")
@handle_errors
def live_query(sql, model, csv_path):
    """Run SQL against the model database (results/logs after a run)."""
    with _conn() as c:
        rows = c.db_query(_live_model(model), sql)
    if csv_path:
        if not isinstance(rows, list):
            raise RuntimeError(f"Query did not return rows: {rows}")
        _write_csv(rows, csv_path)
        output({"rows": len(rows), "csv": os.path.abspath(csv_path)})
    else:
        output(rows)


def _write_csv(rows, path):
    keys = []
    for r in rows:
        for k in (r if isinstance(r, dict) else {}):
            if k not in keys:
                keys.append(k)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ── session ──────────────────────────────────────────────────────────

@cli.group()
def session():
    """Session state, undo and redo."""


@session.command("status")
@handle_errors
def session_status():
    """Current model, undo depth, live connection."""
    output(Session().status())


@session.command("undo")
@handle_errors
def session_undo():
    """Undo the last change to the model file."""
    output(Session().undo())


@session.command("redo")
@handle_errors
def session_redo():
    """Redo the last undone change."""
    output(Session().redo())


@session.command("history")
@handle_errors
def session_history():
    """Changes that can be undone."""
    output(Session().history())


# ── REPL ─────────────────────────────────────────────────────────────

_REPL_COMMANDS = {
    "system": "info|examples",
    "project": "open|info|validate|save-as|close",
    "agent": "list|show|set-startup",
    "var": "list|get|set|add-param|remove",
    "block": "list|params|set|reset|population|connectors",
    "statechart": "show|set",
    "experiment": "list|show|set-param|reset-param|stop|seed",
    "ide": "open|status",
    "live": "connect|status|models|open|agents|experiments|structure|run|stop|errors|get|set|db-tables|query",
    "session": "status|undo|redo|history",
    "help": "show this help",
    "quit": "exit REPL",
}


@cli.command()
@click.argument("project_path", required=False)
def repl(project_path):
    """Interactive REPL."""
    from cli_anything.anylogic.utils.repl_skin import ReplSkin

    # Point the banner's "npx skills add" hint at this harness's own repo.
    os.environ.setdefault("CLI_ANYTHING_SKILL_REPO", "rjmolinag0213r/anylogic-cli")

    global _repl_mode
    _repl_mode = True
    skin = ReplSkin("anylogic", version=__version__)
    if project_path:
        Session().set_project(os.path.abspath(project_path))
    skin.print_banner()
    pt_session = skin.create_prompt_session()
    while True:
        try:
            path = Session().project_path
            line = skin.get_input(pt_session, project_name=os.path.basename(path) if path else "",
                                  modified=False).strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                skin.print_goodbye()
                break
            if line.lower() == "help":
                skin.help(_REPL_COMMANDS)
                continue
            try:
                # posix=False keeps Windows backslashes; strip the quotes it leaves behind.
                args = [a[1:-1] if len(a) > 1 and a[0] == a[-1] and a[0] in "\"'" else a
                        for a in shlex.split(line, posix=False)]
            except ValueError:
                args = line.split()
            try:
                cli.main(args, standalone_mode=False)
            except SystemExit:
                pass
            except click.exceptions.UsageError as e:
                skin.warning(f"Usage error: {e}")
            except Exception as e:
                skin.error(str(e))
        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break
    _repl_mode = False


def main():
    cli()


if __name__ == "__main__":
    main()
