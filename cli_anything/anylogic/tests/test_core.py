"""Unit tests for the .alp data layer (synthetic models, no AnyLogic needed)."""

import os

import pytest

from cli_anything.anylogic.core import elements as el
from cli_anything.anylogic.core import experiments as ex
from cli_anything.anylogic.core import project as pr
from cli_anything.anylogic.core.session import Session

MINI = """<?xml version="1.0" encoding="UTF-8"?>
<!-- AnyLogic Project File -->
<AnyLogicWorkspace WorkspaceVersion="1.9" AnyLogicVersion="8.9.10" AlpVersion="8.9.10">
<Model>
	<Id>100</Id>
	<Name><![CDATA[Mini]]></Name>
	<JavaPackageName><![CDATA[mini]]></JavaPackageName>
	<ModelTimeUnit><![CDATA[Day]]></ModelTimeUnit>
	<ActiveObjectClasses>
		<!-- comment -->
		<ActiveObjectClass>
			<Id>101</Id>
			<Name><![CDATA[Main]]></Name>
			<CurrentLevel>1</CurrentLevel>
			<Variables>
				<Variable Class="Parameter">
					<Id>110</Id>
					<Name><![CDATA[Rate]]></Name>
					<X>50</X><Y>100</Y>
					<Properties>
						<Type><![CDATA[double]]></Type>
						<UnitType><![CDATA[NONE]]></UnitType>
						<DefaultValue Class="CodeValue">
							<Code><![CDATA[1]]></Code>
						</DefaultValue>
						<ParameterEditor><Id>111</Id></ParameterEditor>
					</Properties>
				</Variable>
				<Variable Class="StockVariable">
					<Id>120</Id>
					<Name><![CDATA[S]]></Name>
					<Properties><InitialValue>99</InitialValue></Properties>
				</Variable>
				<Variable Class="Flow">
					<Id>121</Id>
					<Name><![CDATA[f]]></Name>
					<Properties><Formula>S*Rate</Formula></Properties>
				</Variable>
			</Variables>
			<EmbeddedObjects>
				<EmbeddedObject>
					<Id>130</Id>
					<Name>source</Name>
					<ActiveObjectClass>
						<PackageName>com.anylogic.libraries.processmodeling</PackageName>
						<ClassName>Source</ClassName>
					</ActiveObjectClass>
					<Parameters>
						<Parameter><Name>arrivalType</Name></Parameter>
						<Parameter>
							<Name>rate</Name>
							<Value Class="CodeUnitValue">
								<Code>1</Code>
								<Unit Class="RateUnits">PER_MINUTE</Unit>
							</Value>
						</Parameter>
					</Parameters>
				</EmbeddedObject>
				<EmbeddedObject>
					<Id>131</Id>
					<Name>people</Name>
					<ActiveObjectClass><PackageName>mini</PackageName><ClassName>Person</ClassName></ActiveObjectClass>
					<Parameters></Parameters>
					<ReplicationFlag>true</ReplicationFlag>
					<Replication Class="CodeValue"><Code>100</Code></Replication>
				</EmbeddedObject>
			</EmbeddedObjects>
		</ActiveObjectClass>
		<ActiveObjectClass>
			<Id>102</Id>
			<Name><![CDATA[Person]]></Name>
			<StatechartElements>
				<StatechartElement Class="State"><Id>140</Id><Name>A</Name></StatechartElement>
				<StatechartElement Class="State"><Id>141</Id><Name>B</Name></StatechartElement>
				<StatechartElement Class="Transition">
					<Id>142</Id><Name>go</Name>
					<Properties Source="140" Target="141" Trigger="rate">
						<Rate Class="CodeUnitValue"><Code>1</Code><Unit Class="RateUnits">PER_DAY</Unit></Rate>
					</Properties>
				</StatechartElement>
			</StatechartElements>
		</ActiveObjectClass>
	</ActiveObjectClasses>
	<RunConfiguration ActiveObjectClassId="101">
		<Id>150</Id>
		<Name>RunConfiguration</Name>
		<ModelTimeProperties>
			<StopOption>Stop at specified time</StopOption>
			<InitialDate>0</InitialDate>
			<InitialTime>0.0</InitialTime>
			<FinalDate>8640000000</FinalDate>
			<FinalTime>100.0</FinalTime>
		</ModelTimeProperties>
	</RunConfiguration>
	<Experiments>
		<!-- exp -->
		<SimulationExperiment ActiveObjectClassId="101">
			<Id>160</Id>
			<Name><![CDATA[Simulation]]></Name>
			<RandomNumberGenerationType>randomSeed</RandomNumberGenerationType>
			<SeedValue>1</SeedValue>
			<Parameters>
				<Parameter><ParameterName><![CDATA[Rate]]></ParameterName></Parameter>
			</Parameters>
			<ModelTimeProperties>
				<StopOption>Stop at specified time</StopOption>
				<InitialDate>0</InitialDate>
				<InitialTime>0.0</InitialTime>
				<FinalDate>8640000000</FinalDate>
				<FinalTime>100.0</FinalTime>
			</ModelTimeProperties>
		</SimulationExperiment>
	</Experiments>
</Model>
</AnyLogicWorkspace>"""


@pytest.fixture
def alp(tmp_path):
    p = tmp_path / "Mini.alp"
    p.write_bytes(MINI.replace("\n", "\r\n").encode("utf-8"))  # AnyLogic writes CRLF on Windows
    return str(p)


@pytest.fixture
def proj(alp):
    return pr.open_project(alp)


def reload(proj):
    proj.save()
    return pr.open_project(proj.path)


class TestProject:
    def test_roundtrip_is_byte_identical(self, alp, proj):
        assert proj.to_bytes() == open(alp, "rb").read()

    def test_info(self, proj):
        info = proj.info()
        assert info["name"] == "Mini" and info["time_unit"] == "Day"
        assert info["agent_types"] == ["Main", "Person"]
        assert info["experiments"] == [{"name": "Simulation", "type": "SimulationExperiment"}]

    def test_rejects_non_alp(self, tmp_path):
        p = tmp_path / "x.xml"
        p.write_text("<a/>")
        with pytest.raises(pr.AlpError):
            pr.open_project(str(p))

    def test_rejects_wrong_root(self, tmp_path):
        p = tmp_path / "x.alp"
        p.write_text("<Other/>")
        with pytest.raises(pr.AlpError):
            pr.open_project(str(p))

    def test_rejects_broken_xml(self, tmp_path):
        p = tmp_path / "x.alp"
        p.write_text("<AnyLogicWorkspace><Model>")
        with pytest.raises(pr.AlpError):
            pr.open_project(str(p))

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            pr.open_project("nope.alp")

    def test_new_ids_unique(self, proj):
        a, b = proj.new_id(), proj.new_id()
        assert a != b and min(a, b) > max(proj.all_ids()) - 2

    def test_save_as_renames_package(self, proj, tmp_path):
        res = pr.save_as(proj, str(tmp_path / "out" / "Copy.alp"), "What If 2")
        copy = pr.open_project(res["output"])
        assert copy.name == "What If 2" and copy.package == "whatif2"
        assert res["renamed"]["package_refs_updated"] == 1

    def test_save_as_refuses_overwrite(self, proj, alp):
        with pytest.raises(pr.AlpError):
            pr.save_as(proj, alp)

    def test_java_package(self):
        assert pr.java_package("9 Lives") == "model9lives"


class TestVariables:
    def test_list_and_kinds(self, proj):
        assert [v["kind"] for v in el.list_variables(proj, "Main")] == ["parameter", "stock", "flow"]
        assert el.list_variables(proj, "Main", "stock")[0]["value"] == "99"

    def test_set_parameter_keeps_cdata(self, proj):
        el.set_variable(proj, "Main", "Rate", "2.5")
        assert b"<![CDATA[2.5]]>" in proj.to_bytes()
        assert el.list_variables(reload(proj), "Main", "parameter")[0]["value"] == "2.5"

    def test_set_keeps_line_layout(self, alp, proj):
        el.set_variable(proj, "Main", "Rate", "2.5")
        assert proj.to_bytes().count(b"\n") == open(alp, "rb").read().count(b"\n")

    def test_set_stock_and_flow(self, proj):
        el.set_variable(proj, "Main", "S", "500")
        el.set_variable(proj, "Main", "f", "S*Rate/2")
        vals = {v["name"]: v["value"] for v in el.list_variables(reload(proj), "Main")}
        assert vals["S"] == "500" and vals["f"] == "S*Rate/2"

    def test_unit_on_unitless_param_rejected(self, proj):
        with pytest.raises(pr.AlpError):
            el.set_variable(proj, "Main", "Rate", "2", unit="DAY")

    def test_unknown_variable(self, proj):
        with pytest.raises(pr.AlpError, match="Available"):
            el.set_variable(proj, "Main", "nope", "1")

    def test_add_parameter_syncs_experiment(self, proj):
        el.add_parameter(proj, "Main", "Beta", "int", "3")
        p = reload(proj)
        assert any(v["name"] == "Beta" and v["type"] == "int" for v in el.list_variables(p, "Main"))
        assert "Beta" in [x["name"] for x in ex.show(p)["parameters"]]

    def test_add_parameter_validation(self, proj):
        with pytest.raises(pr.AlpError):
            el.add_parameter(proj, "Main", "Rate")
        with pytest.raises(pr.AlpError):
            el.add_parameter(proj, "Main", "bad name")
        with pytest.raises(pr.AlpError):
            el.add_parameter(proj, "Main", "x", "Widget")

    def test_remove_parameter(self, proj):
        el.remove_variable(proj, "Main", "Rate")
        p = reload(proj)
        assert "Rate" not in [v["name"] for v in el.list_variables(p, "Main")]
        assert ex.show(p)["parameters"] == []

    def test_unknown_agent(self, proj):
        with pytest.raises(pr.AlpError):
            el.list_variables(proj, "Ghost")


class TestBlocks:
    def test_list_embedded(self, proj):
        items = {i["name"]: i for i in el.list_embedded(proj, "Main")}
        assert items["source"]["kind"] == "block" and items["source"]["library"] == "processmodeling"
        assert items["people"]["kind"] == "population" and items["people"]["population_size"] == "100"

    def test_block_params_only_set(self, proj):
        ps = el.block_parameters(proj, "Main", "source", only_set=True)
        assert ps == [{"name": "rate", "value": "1", "unit": "PER_MINUTE", "is_default": False}]
        assert len(el.block_parameters(proj, "Main", "source")) == 2

    def test_set_keeps_existing_unit(self, proj):
        assert el.set_block_parameter(proj, "Main", "source", "rate", "3")["unit"] == "PER_MINUTE"

    def test_set_new_value_with_unit(self, proj):
        el.set_block_parameter(proj, "Main", "source", "arrivalType", "4", unit="PER_HOUR")
        ps = {x["name"]: x for x in el.block_parameters(reload(proj), "Main", "source")}
        assert ps["arrivalType"]["value"] == "4" and ps["arrivalType"]["unit"] == "PER_HOUR"

    def test_bad_unit_leaves_file_unchanged(self, proj):
        before = proj.to_bytes()
        with pytest.raises(pr.AlpError):
            el.set_block_parameter(proj, "Main", "source", "rate", "3", unit="FURLONG")
        assert proj.to_bytes() == before

    def test_unknown_block_param(self, proj):
        with pytest.raises(pr.AlpError, match="Available"):
            el.set_block_parameter(proj, "Main", "source", "nope", "1")

    def test_reset(self, proj):
        el.reset_block_parameter(proj, "Main", "source", "rate")
        assert el.block_parameters(proj, "Main", "source", only_set=True) == []

    def test_population(self, proj):
        el.set_population_size(proj, "Main", "people", "5000")
        assert el.list_embedded(reload(proj), "Main", "population")[0]["population_size"] == "5000"
        with pytest.raises(pr.AlpError):
            el.set_population_size(proj, "Main", "source", "3")

    def test_unit_class(self):
        assert el.unit_class("per_day") == "RateUnits"
        assert el.unit_class("MINUTE") == "TimeUnits"
        assert el.unit_class("METER") == "LengthUnits"


class TestStatechart:
    def test_show(self, proj):
        sc = el.statechart(proj, "Person")
        assert [s["name"] for s in sc["states"]] == ["A", "B"]
        t = sc["transitions"][0]
        assert (t["from"], t["to"], t["trigger"], t["value"], t["unit"]) == ("A", "B", "rate", "1", "PER_DAY")

    def test_set_rate(self, proj):
        el.set_transition(proj, "Person", "go", "0.5", unit="PER_WEEK")
        t = el.statechart(reload(proj), "Person")["transitions"][0]
        assert (t["value"], t["unit"]) == ("0.5", "PER_WEEK")

    def test_switch_to_timeout(self, proj):
        el.set_transition(proj, "Person", "go", "7", unit="DAY", trigger="timeout")
        t = el.statechart(reload(proj), "Person")["transitions"][0]
        assert (t["trigger"], t["value"], t["unit"]) == ("timeout", "7", "DAY")

    def test_missing_transition(self, proj):
        with pytest.raises(pr.AlpError):
            el.set_transition(proj, "Person", "nope", "1")


class TestExperiments:
    def test_comments_ignored(self, proj):
        assert [e["name"] for e in ex.list_experiments(proj)] == ["Simulation"]

    def test_set_and_reset_param(self, proj):
        ex.set_parameter(proj, "Simulation", "Rate", "9")
        p = reload(proj)
        par = ex.show(p)["parameters"][0]
        assert par["value"] == "9" and par["overridden"] and par["default"] == "1"
        ex.reset_parameter(p, "Simulation", "Rate")
        assert not ex.show(p)["parameters"][0]["overridden"]

    def test_unknown_param(self, proj):
        with pytest.raises(pr.AlpError):
            ex.set_parameter(proj, "Simulation", "Ghost", "1")

    def test_stop_time_updates_dates(self, proj):
        assert ex.set_stop(proj, stop_time=365)["updated"] == ["Simulation", "RunConfiguration"]
        p = reload(proj)
        assert ex.show(p)["stop_time"] == "365.0"
        assert pr.text(p.experiments()[0], "ModelTimeProperties/FinalDate") == str(365 * 86_400_000)

    def test_stop_never(self, proj):
        ex.set_stop(proj, never=True)
        assert ex.show(proj)["stop"] == "Never"

    def test_stop_before_start(self, proj):
        with pytest.raises(pr.AlpError):
            ex.set_stop(proj, stop_time=0)

    def test_seed(self, proj):
        ex.set_seed(proj, seed=42)
        e = ex.show(reload(proj))
        assert (e["random"], e["seed"]) == ("fixedSeed", "42")
        ex.set_seed(proj, random=True)
        assert ex.show(proj)["random"] == "randomSeed"

    def test_month_arithmetic(self):
        jan31 = 1706659200000  # 2024-01-31 UTC
        assert ex.add_units(jan31, 1, "Month") == 1709164800000  # 2024-02-29


class TestSession:
    def test_undo_redo(self, alp, tmp_path, monkeypatch):
        monkeypatch.setenv("CLI_ANYTHING_ANYLOGIC_HOME", str(tmp_path / "state"))
        s = Session()
        s.set_project(alp)
        original = open(alp, "rb").read()
        s.snapshot(alp, "edit")
        p = pr.open_project(alp)
        el.set_variable(p, "Main", "Rate", "7")
        p.save()
        edited = open(alp, "rb").read()
        assert Session().undo()["label"] == "edit"
        assert open(alp, "rb").read() == original
        Session().redo()
        assert open(alp, "rb").read() == edited

    def test_undo_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLI_ANYTHING_ANYLOGIC_HOME", str(tmp_path / "state2"))
        with pytest.raises(RuntimeError):
            Session().undo()

    def test_status_masks_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLI_ANYTHING_ANYLOGIC_HOME", str(tmp_path / "state3"))
        Session().set_live(token="abcdef-123456", port=25333)
        tok = Session().status()["live"]["token"]
        assert tok.startswith("abcd") and "123456" not in tok

    def test_switching_project_clears_history(self, alp, tmp_path, monkeypatch):
        monkeypatch.setenv("CLI_ANYTHING_ANYLOGIC_HOME", str(tmp_path / "state4"))
        s = Session()
        s.set_project(alp)
        s.snapshot(alp, "x")
        s.set_project(str(tmp_path / "other.alp"))
        assert Session().history() == []
        assert os.listdir(str(tmp_path / "state4" / "snapshots")) == []
