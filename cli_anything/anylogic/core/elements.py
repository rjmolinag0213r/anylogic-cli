"""Agent-type contents: variables, embedded objects (blocks / populations),
connectors and statecharts - read and edit them in the .alp XML."""

from lxml import etree

from cli_anything.anylogic.core.project import (
    LIBRARY_PREFIX, AlpError, AlpProject, set_el_text, text,
)

VARIABLE_KINDS = {
    "parameter": "Parameter",
    "variable": "PlainVariable",
    "stock": "StockVariable",
    "flow": "Flow",
    "dynamic": "AuxVariable",
    "collection": "CollectionVariable",
}

_UNIT_CLASSES = {
    "TimeUnits": {"MILLISECOND", "SECOND", "MINUTE", "HOUR", "DAY", "WEEK", "MONTH", "YEAR"},
    "LengthUnits": {"MILLIMETER", "CENTIMETER", "METER", "KILOMETER", "INCH", "FOOT", "YARD", "MILE",
                    "NAUTICAL_MILE"},
    "SpeedUnits": {"MPS", "KPH", "FPS", "FPM", "MPH", "KN", "MPM"},
}


def unit_class(unit: str) -> str:
    u = unit.upper()
    if u.startswith("PER_"):
        return "RateUnits"
    for cls, members in _UNIT_CLASSES.items():
        if u in members:
            return cls
    raise AlpError(f"Unknown unit '{unit}'. Use e.g. SECOND/MINUTE/HOUR/DAY, PER_MINUTE/PER_HOUR, METER, MPS")


# ── Generic value helpers ────────────────────────────────────────────

def _value_of(el):
    """Read a CodeValue / CodeUnitValue / plain-text value element."""
    if el is None:
        return None, None
    code = el.find("Code")
    if code is not None:
        return (code.text or "").strip(), text(el, "Unit")
    return (el.text or "").strip(), None


def _write_value(parent, tag: str, value: str, unit: str = None, before: str = None):
    """Create or update ``<tag Class=CodeValue|CodeUnitValue>`` under parent."""
    if unit is not None:
        unit_class(unit)  # validate before mutating anything
    el = parent.find(tag)
    if el is not None and el.find("Code") is None and unit is None and el.get("Class") is None:
        set_el_text(el, value)  # plain-text style value (e.g. stock InitialValue)
        return el
    if el is None:
        el = etree.Element(tag)
        anchor = parent.find(before) if before else None
        if anchor is not None:
            anchor.addprevious(el)
        else:
            parent.append(el)
    # Update <Code>/<Unit> in place so the file's indentation is kept.
    code = el.find("Code")
    if code is None:
        code = etree.SubElement(el, "Code")
    u = el.find("Unit")
    if unit is None and u is not None:
        unit = (u.text or "").strip()
    el.set("Class", "CodeUnitValue" if unit else "CodeValue")
    code.text = etree.CDATA(str(value)) if value != "" else ""
    if unit:
        if u is None:
            u = etree.SubElement(el, "Unit")
            # <Unit> takes the closing indentation; <Code> gets the child indentation.
            u.tail, code.tail = code.tail, el.text
        u.set("Class", unit_class(unit))
        u.text = etree.CDATA(unit.upper())
    return el


# ── Agents ───────────────────────────────────────────────────────────

def list_agents(proj: AlpProject) -> list:
    out = []
    root_ids = {e.get("ActiveObjectClassId") for e in proj.experiments()}
    for aoc in proj.agent_classes():
        embedded = _embedded(aoc)
        out.append({
            "name": text(aoc, "Name"),
            "id": text(aoc, "Id"),
            "is_top_level": text(aoc, "Id") in root_ids,
            "variables": len(_variables(aoc)),
            "blocks": sum(1 for e in embedded if _is_block(e)),
            "embedded_agents": sum(1 for e in embedded if not _is_block(e)),
            "statechart_elements": len(aoc.findall("StatechartElements/StatechartElement")),
            "connectors": len(aoc.findall("Connectors/Connector")),
            "startup_code": text(aoc, "StartupCode") or "",
        })
    return out


def set_startup_code(proj: AlpProject, agent: str, code: str) -> dict:
    aoc = proj.agent_class(agent)
    el = aoc.find("StartupCode")
    if el is None:
        el = etree.Element("StartupCode")
        aoc.find("Name").addnext(el)
    set_el_text(el, code)
    return {"agent": agent, "startup_code": code}


# ── Variables (parameters, variables, stocks, flows, dynamic vars) ──

def _variables(aoc):
    return aoc.findall("Variables/Variable")


def _find_variable(aoc, name):
    for v in _variables(aoc):
        if text(v, "Name") == name:
            return v
    raise AlpError(f"No variable/parameter named '{name}' in agent '{text(aoc, 'Name')}'. "
                   f"Available: {[text(v, 'Name') for v in _variables(aoc)]}")


def _variable_value(v):
    cls = v.get("Class")
    props = v.find("Properties")
    if props is None:
        return None, None
    if cls == "Parameter":
        return _value_of(props.find("DefaultValue"))
    if cls in ("PlainVariable", "StockVariable"):
        return _value_of(props.find("InitialValue"))
    if cls in ("Flow", "AuxVariable"):
        return _value_of(props.find("Formula"))
    return None, None


def describe_variable(v) -> dict:
    value, unit = _variable_value(v)
    kind = next((k for k, c in VARIABLE_KINDS.items() if c == v.get("Class")), v.get("Class"))
    return {"name": text(v, "Name"), "kind": kind, "type": text(v, "Properties/Type"),
            "value": value, "unit": unit, "id": text(v, "Id")}


def list_variables(proj: AlpProject, agent: str, kind: str = None) -> list:
    aoc = proj.agent_class(agent)
    cls = VARIABLE_KINDS.get(kind) if kind else None
    if kind and cls is None:
        raise AlpError(f"Unknown kind '{kind}'. Choose from {sorted(VARIABLE_KINDS)}")
    return [describe_variable(v) for v in _variables(aoc) if cls is None or v.get("Class") == cls]


def set_variable(proj: AlpProject, agent: str, name: str, value: str, unit: str = None) -> dict:
    """Set a parameter default, variable/stock initial value or flow/dynamic formula."""
    aoc = proj.agent_class(agent)
    v = _find_variable(aoc, name)
    cls = v.get("Class")
    props = v.find("Properties")
    old = describe_variable(v)["value"]
    if cls == "Parameter":
        if unit and (text(props, "UnitType") or "NONE") == "NONE":
            raise AlpError(f"Parameter '{name}' has no unit type; give a plain value or set its unit "
                           "type in AnyLogic first")
        _write_value(props, "DefaultValue", value, unit, before="ParameterEditor")
    elif cls == "PlainVariable":
        _write_value(props, "InitialValue", value, unit)
    elif cls in ("StockVariable", "Flow", "AuxVariable"):
        tag = "InitialValue" if cls == "StockVariable" else "Formula"
        el = props.find(tag)
        if el is None:
            el = etree.SubElement(props, tag)
        set_el_text(el, value)
    else:
        raise AlpError(f"'{name}' is a {cls}; its value cannot be set from the CLI")
    new = describe_variable(v)
    return {"agent": agent, "name": name, "kind": new["kind"], "old": old, "new": new["value"],
            "unit": new["unit"]}


_PARAM_TEMPLATE = """<Variable Class="Parameter">
	<Id>{id}</Id>
	<Name><![CDATA[{name}]]></Name>
	<X>{x}</X><Y>{y}</Y>
	<Label><X>10</X><Y>0</Y></Label>
	<PublicFlag>false</PublicFlag>
	<PresentationFlag>true</PresentationFlag>
	<ShowLabel>true</ShowLabel>
	<Properties SaveInSnapshot="true" ModificatorType="STATIC">
		<Type><![CDATA[{type}]]></Type>
		<UnitType><![CDATA[NONE]]></UnitType>
		<SdArray>false</SdArray>
		<DefaultValue Class="CodeValue">
			<Code><![CDATA[{default}]]></Code>
		</DefaultValue>
		<ParameterEditor>
			<Id>{editor_id}</Id>
			<EditorContolType>TEXT_BOX</EditorContolType>
			<MinSliderValue><![CDATA[0]]></MinSliderValue>
			<MaxSliderValue><![CDATA[100]]></MaxSliderValue>
			<DelimeterType>NO_DELIMETER</DelimeterType>
		</ParameterEditor>
	</Properties>
</Variable>"""

_JAVA_TYPES = {"double", "int", "boolean", "String", "long"}


def add_parameter(proj: AlpProject, agent: str, name: str, ptype: str = "double",
                  default: str = "0", x: int = None, y: int = None) -> dict:
    if not name.isidentifier():
        raise AlpError(f"'{name}' is not a valid Java identifier")
    if ptype not in _JAVA_TYPES:
        raise AlpError(f"Unsupported type '{ptype}'. Choose from {sorted(_JAVA_TYPES)}")
    aoc = proj.agent_class(agent)
    if any(text(v, "Name") == name for v in _variables(aoc)):
        raise AlpError(f"'{name}' already exists in agent '{agent}'")
    variables = aoc.find("Variables")
    if variables is None:
        variables = etree.Element("Variables")
        anchor = aoc.find("CurrentLevel")
        if anchor is not None:
            anchor.addnext(variables)
        else:
            aoc.append(variables)
    if y is None:
        ys = [int(text(v, "Y")) for v in _variables(aoc)
              if (text(v, "Y") or "").lstrip("-").isdigit()]
        y = max(ys) + 40 if ys else 100
    x = 50 if x is None else x
    xml = _PARAM_TEMPLATE.format(id=proj.new_id(), editor_id=proj.new_id(), name=name, type=ptype,
                                 default=default, x=x, y=y)
    variables.append(etree.fromstring(xml, etree.XMLParser(strip_cdata=False)))
    _sync_experiment_parameter(proj, aoc, name, add=True)
    return {"agent": agent, "added": name, "type": ptype, "default": default}


def remove_variable(proj: AlpProject, agent: str, name: str) -> dict:
    aoc = proj.agent_class(agent)
    v = _find_variable(aoc, name)
    kind = v.get("Class")
    v.getparent().remove(v)
    if kind == "Parameter":
        _sync_experiment_parameter(proj, aoc, name, add=False)
    return {"agent": agent, "removed": name, "kind": kind}


def _sync_experiment_parameter(proj, aoc, name, add):
    """Experiments list the top-level agent's parameters; keep them in step."""
    aoc_id = text(aoc, "Id")
    for exp in proj.experiments():
        if exp.get("ActiveObjectClassId") != aoc_id:
            continue
        params = exp.find("Parameters")
        if params is None:
            continue
        hits = [p for p in params.findall("Parameter") if text(p, "ParameterName") == name]
        if add and not hits:
            p = etree.SubElement(params, "Parameter")
            n = etree.SubElement(p, "ParameterName")
            n.text = etree.CDATA(name)
        elif not add:
            for p in hits:
                params.remove(p)


# ── Embedded objects: library blocks and agent populations ───────────

def _is_block(eo) -> bool:
    return (text(eo, "ActiveObjectClass/PackageName") or "").startswith(LIBRARY_PREFIX)


def _embedded(aoc):
    return aoc.findall("EmbeddedObjects/EmbeddedObject")


def _find_embedded(aoc, name):
    for eo in _embedded(aoc):
        if text(eo, "Name") == name:
            return eo
    raise AlpError(f"No block/embedded object '{name}' in agent '{text(aoc, 'Name')}'. "
                   f"Available: {[text(e, 'Name') for e in _embedded(aoc)]}")


def describe_embedded(eo) -> dict:
    pkg = text(eo, "ActiveObjectClass/PackageName") or ""
    is_lib = pkg.startswith(LIBRARY_PREFIX)
    replicated = text(eo, "ReplicationFlag") == "true"
    size = _value_of(eo.find("Replication"))[0] if replicated else None
    set_params = {}
    for p in eo.findall("Parameters/Parameter"):
        if p.find("Value") is not None:
            val, unit = _value_of(p.find("Value"))
            set_params[text(p, "Name")] = f"{val} {unit}" if unit else val
    return {
        "name": text(eo, "Name"),
        "type": text(eo, "ActiveObjectClass/ClassName"),
        "library": pkg[len(LIBRARY_PREFIX):] if is_lib else None,
        "kind": "block" if is_lib else ("population" if replicated else "agent"),
        "population_size": size,
        "x": text(eo, "X"), "y": text(eo, "Y"),
        "parameters_set": set_params,
    }


def list_embedded(proj: AlpProject, agent: str, kind: str = None) -> list:
    items = [describe_embedded(e) for e in _embedded(proj.agent_class(agent))]
    return [i for i in items if kind is None or i["kind"] == kind]


def block_parameters(proj: AlpProject, agent: str, block: str, only_set: bool = False) -> list:
    eo = _find_embedded(proj.agent_class(agent), block)
    out = []
    for p in eo.findall("Parameters/Parameter"):
        val_el = p.find("Value")
        if only_set and val_el is None:
            continue
        val, unit = _value_of(val_el)
        out.append({"name": text(p, "Name"), "value": val, "unit": unit, "is_default": val_el is None})
    return out


def set_block_parameter(proj: AlpProject, agent: str, block: str, param: str, value: str,
                        unit: str = None) -> dict:
    eo = _find_embedded(proj.agent_class(agent), block)
    params = eo.find("Parameters")
    target = None
    if params is not None:
        target = next((p for p in params.findall("Parameter") if text(p, "Name") == param), None)
    if target is None:
        if _is_block(eo):
            names = [text(p, "Name") for p in eo.findall("Parameters/Parameter")]
            raise AlpError(f"Block '{block}' has no parameter '{param}'. Available: {names}")
        # Embedded agent: parameters of its agent type may be overridden here.
        if params is None:
            params = etree.SubElement(eo, "Parameters")
        target = etree.SubElement(params, "Parameter")
        etree.SubElement(target, "Name").text = etree.CDATA(param)
    old, old_unit = _value_of(target.find("Value"))
    _write_value(target, "Value", value, unit)
    new, new_unit = _value_of(target.find("Value"))
    return {"agent": agent, "block": block, "parameter": param, "old": old, "old_unit": old_unit,
            "new": new, "unit": new_unit}


def reset_block_parameter(proj: AlpProject, agent: str, block: str, param: str) -> dict:
    eo = _find_embedded(proj.agent_class(agent), block)
    for p in eo.findall("Parameters/Parameter"):
        if text(p, "Name") == param:
            v = p.find("Value")
            if v is not None:
                p.remove(v)
            return {"agent": agent, "block": block, "parameter": param, "reset": True}
    raise AlpError(f"'{block}' has no parameter '{param}'")


def set_population_size(proj: AlpProject, agent: str, name: str, size: str) -> dict:
    eo = _find_embedded(proj.agent_class(agent), name)
    if text(eo, "ReplicationFlag") != "true":
        raise AlpError(f"'{name}' is not an agent population")
    old = _value_of(eo.find("Replication"))[0]
    _write_value(eo, "Replication", str(size))
    return {"agent": agent, "population": name, "old": old, "new": str(size)}


# ── Connectors ───────────────────────────────────────────────────────

def list_connectors(proj: AlpProject, agent: str) -> list:
    out = []
    for c in proj.agent_class(agent).findall("Connectors/Connector"):
        src = (text(c, "SourceEmbeddedObjectReference/ItemName"), text(c, "SourceConnectableItemReference/ItemName"))
        dst = (text(c, "TargetEmbeddedObjectReference/ItemName"), text(c, "TargetConnectableItemReference/ItemName"))
        out.append({"name": text(c, "Name"), "from": ".".join(filter(None, src)),
                    "to": ".".join(filter(None, dst))})
    return out


# ── Statecharts ──────────────────────────────────────────────────────

_TRIGGER_TAGS = {"rate": "Rate", "timeout": "Timeout", "condition": "Condition"}


def statechart(proj: AlpProject, agent: str) -> dict:
    elements = proj.agent_class(agent).findall("StatechartElements/StatechartElement")
    by_id = {text(e, "Id"): text(e, "Name") for e in elements}
    states, transitions, entries = [], [], []
    for e in elements:
        cls = e.get("Class")
        if cls == "Transition":
            props = e.find("Properties")
            props = props if props is not None else etree.Element("Properties")
            trig = props.get("Trigger")
            tag = _TRIGGER_TAGS.get(trig)
            val, unit = _value_of(props.find(tag)) if tag else (None, None)
            transitions.append({
                "name": text(e, "Name"), "trigger": trig,
                "from": by_id.get(props.get("Source")), "to": by_id.get(props.get("Target")),
                "value": val, "unit": unit,
                "guard": text(props, "Guard"), "action": text(props, "Action"),
            })
        elif cls == "EntryPoint":
            entries.append(text(e, "Name"))
        else:
            states.append({"name": text(e, "Name"), "kind": cls,
                           "entry_action": text(e, "Properties/EntryAction")})
    return {"agent": agent, "entry_points": entries, "states": states, "transitions": transitions}


def set_transition(proj: AlpProject, agent: str, name: str, value: str, unit: str = None,
                   trigger: str = None) -> dict:
    """Change a transition's rate / timeout / condition (optionally switching trigger)."""
    for e in proj.agent_class(agent).findall("StatechartElements/StatechartElement"):
        if e.get("Class") != "Transition" or text(e, "Name") != name:
            continue
        props = e.find("Properties")
        if trigger:
            if trigger not in _TRIGGER_TAGS:
                raise AlpError(f"Trigger must be one of {sorted(_TRIGGER_TAGS)}")
            props.set("Trigger", trigger)
        trig = props.get("Trigger")
        tag = _TRIGGER_TAGS.get(trig)
        if tag is None:
            raise AlpError(f"Transition '{name}' is triggered by '{trig}'; "
                           "only rate/timeout/condition values can be set (use --trigger to switch)")
        if tag == "Condition":
            el = props.find("Condition")
            if el is None:
                el = etree.SubElement(props, "Condition")
            set_el_text(el, value)
        else:
            _write_value(props, tag, value, unit)
        val, unit_now = _value_of(props.find(tag))
        return {"agent": agent, "transition": name, "trigger": trig, "value": val, "unit": unit_now}
    raise AlpError(f"No transition '{name}' in agent '{agent}'")
