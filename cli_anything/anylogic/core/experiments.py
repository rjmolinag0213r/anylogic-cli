"""Experiments: parameter overrides, stop time, random seed."""

import calendar
import datetime as _dt

from lxml import etree

from cli_anything.anylogic.core.project import AlpError, AlpProject, set_el_text, text

STOP_OPTIONS = {
    "time": "Stop at specified time",
    "date": "Stop at specified date",
    "never": "Never",
}

_UNIT_MS = {
    "Millisecond": 1, "Second": 1000, "Minute": 60_000, "Hour": 3_600_000,
    "Day": 86_400_000, "Week": 7 * 86_400_000,
}


def _find(proj: AlpProject, name: str = None):
    exps = proj.experiments()
    if not exps:
        raise AlpError("This model has no experiments")
    if name is None:
        return exps[0]
    for e in exps:
        if text(e, "Name") == name:
            return e
    raise AlpError(f"No experiment '{name}'. Available: {[text(e, 'Name') for e in exps]}")


def describe(proj: AlpProject, exp) -> dict:
    root = proj.agent_class_by_id(exp.get("ActiveObjectClassId"))
    defaults = {}
    if root is not None:
        for v in root.findall("Variables/Variable[@Class='Parameter']"):
            defaults[text(v, "Name")] = text(v, "Properties/DefaultValue/Code")
    params = []
    for p in exp.findall("Parameters/Parameter"):
        name = text(p, "ParameterName")
        override = text(p, "ParameterValue/Code")
        params.append({"name": name, "value": override if override is not None else defaults.get(name),
                       "overridden": override is not None, "default": defaults.get(name)})
    mtp = exp.find("ModelTimeProperties")
    return {
        "name": text(exp, "Name"),
        "type": exp.tag,
        "top_level_agent": text(root, "Name") if root is not None else None,
        "stop": text(mtp, "StopOption"),
        "start_time": text(mtp, "InitialTime"),
        "stop_time": text(mtp, "FinalTime"),
        "time_unit": proj.time_unit,
        "random": text(exp, "RandomNumberGenerationType"),
        "seed": text(exp, "SeedValue"),
        "max_memory_mb": text(exp, "MaximumMemory"),
        "parameters": params,
    }


def list_experiments(proj: AlpProject) -> list:
    return [describe(proj, e) for e in proj.experiments()]


def show(proj: AlpProject, name: str = None) -> dict:
    return describe(proj, _find(proj, name))


def set_parameter(proj: AlpProject, exp_name: str, param: str, value: str) -> dict:
    exp = _find(proj, exp_name)
    entry = next((p for p in exp.findall("Parameters/Parameter")
                  if text(p, "ParameterName") == param), None)
    if entry is None:
        names = [text(p, "ParameterName") for p in exp.findall("Parameters/Parameter")]
        raise AlpError(f"Experiment '{text(exp, 'Name')}' has no parameter '{param}'. Available: {names}")
    pv = entry.find("ParameterValue")
    if pv is None:
        pv = etree.SubElement(entry, "ParameterValue")
        pv.set("Class", "CodeValue")
        etree.SubElement(pv, "Code")
    code = pv.find("Code")
    old = code.text.strip() if code.text else None
    code.text = etree.CDATA(str(value))
    return {"experiment": text(exp, "Name"), "parameter": param, "old": old, "new": str(value)}


def reset_parameter(proj: AlpProject, exp_name: str, param: str) -> dict:
    exp = _find(proj, exp_name)
    for p in exp.findall("Parameters/Parameter"):
        if text(p, "ParameterName") == param:
            pv = p.find("ParameterValue")
            if pv is not None:
                p.remove(pv)
            return {"experiment": text(exp, "Name"), "parameter": param, "reset": True}
    raise AlpError(f"No parameter '{param}' in experiment '{text(exp, 'Name')}'")


def add_units(start_ms: int, amount: float, unit: str) -> int:
    """Epoch-ms date that is ``amount`` model-time units after ``start_ms``."""
    if unit in _UNIT_MS:
        return int(round(start_ms + amount * _UNIT_MS[unit]))
    months = {"Month": 1, "Year": 12}.get(unit)
    if months is None:
        raise AlpError(f"Unsupported model time unit '{unit}'")
    start = _dt.datetime.fromtimestamp(start_ms / 1000, tz=_dt.timezone.utc)
    y, m = divmod(start.month - 1 + int(round(amount * months)), 12)
    y, m = start.year + y, m + 1
    d = min(start.day, calendar.monthrange(y, m)[1])
    return int(start.replace(year=y, month=m, day=d).timestamp() * 1000)


def set_stop(proj: AlpProject, exp_name: str = None, stop_time: float = None, never: bool = False,
             include_run_config: bool = True) -> dict:
    """Set when the experiment stops (in model time units), or make it run forever.

    The model's RunConfiguration carries its own copy of the time settings,
    so it is updated too unless ``include_run_config`` is False.
    """
    if not never and stop_time is None:
        raise AlpError("Give a stop time or --never")
    targets = [_find(proj, exp_name)]
    rc = proj.model.find("RunConfiguration")
    if include_run_config and rc is not None:
        targets.append(rc)
    changed = []
    for el in targets:
        mtp = el.find("ModelTimeProperties")
        if mtp is None:
            continue
        if never:
            set_el_text(mtp.find("StopOption"), STOP_OPTIONS["never"])
        else:
            start = float(text(mtp, "InitialTime", "0") or 0)
            if stop_time <= start:
                raise AlpError(f"Stop time {stop_time} must be after start time {start}")
            set_el_text(mtp.find("StopOption"), STOP_OPTIONS["time"])
            set_el_text(mtp.find("FinalTime"), repr(float(stop_time)))
            init_date = text(mtp, "InitialDate")
            if init_date and init_date.lstrip("-").isdigit() and mtp.find("FinalDate") is not None:
                set_el_text(mtp.find("FinalDate"),
                            str(add_units(int(init_date), stop_time - start, proj.time_unit)))
        changed.append(text(el, "Name"))
    return {"updated": changed, "stop": "never" if never else stop_time, "time_unit": proj.time_unit}


def set_seed(proj: AlpProject, exp_name: str = None, seed: int = None, random: bool = False) -> dict:
    exp = _find(proj, exp_name)
    rng = exp.find("RandomNumberGenerationType")
    if rng is None:
        raise AlpError(f"Experiment '{text(exp, 'Name')}' has no random-number settings")
    if random:
        set_el_text(rng, "randomSeed")
    else:
        if seed is None:
            raise AlpError("Give --seed N or --random")
        set_el_text(rng, "fixedSeed")
        set_el_text(exp.find("SeedValue"), str(int(seed)))
    return {"experiment": text(exp, "Name"), "random": text(exp, "RandomNumberGenerationType"),
            "seed": text(exp, "SeedValue")}
