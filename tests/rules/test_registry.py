import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from girlframe.engine.rules_registry import Registry

ROOT = Path(__file__).resolve().parents[2]


def data():
    return json.loads((ROOT / "rules/registry.json").read_text())


def test_inventory_is_not_certification_and_strain_columns_are_distinct():
    registry = Registry.model_validate_json(json.dumps(data()))
    assert registry.coverage == "RULES_SUBSET"
    assert registry.summary()["verified"] == 0
    cells = [x for x in registry.entries if x.kind == "table_event"]
    assert len(cells) == 72
    assert len({x.id for x in cells}) == 72
    assert len([x for x in registry.entries if x.kind == "endgame"]) == 22
    for track in ("void", "rebellion", "budget"):
        assert len([x for x in cells if x.id.startswith("strain." + track + ".")]) == 24


@pytest.mark.parametrize(
    "mutation", ["duplicate", "page", "dependency", "fake_implementation", "fake_review"]
)
def test_registry_rejects_invalid_sources_and_false_verification(mutation):
    value = data()
    entry = value["entries"][0]
    if mutation == "duplicate":
        value["entries"].append(entry.copy())
    elif mutation == "page":
        entry["source"]["pdf_page"] = 999
    elif mutation == "dependency":
        entry["dependencies"] = ["nonexistent.rule"]
    elif mutation == "fake_implementation":
        entry["implementation"] = "implemented"
    else:
        entry["independent_review"] = "approved"
        entry["reviewer"] = "unsubstantiated"
    with pytest.raises(ValidationError):
        Registry.model_validate_json(json.dumps(value))


def test_ancillary_module_disabled_and_not_executable_by_toggling_a_flag():
    registry = Registry.model_validate_json(json.dumps(data()))
    optional = next(x for x in registry.entries if x.scope == "ancillary")
    assert registry.enabled_modules == frozenset({"core"})
    with pytest.raises(ValueError, match="MODULE_DISABLED"):
        registry.require_available(optional.id)
    enabled = registry.model_copy(update={"enabled_modules": frozenset({"core", "ancillary"})})
    with pytest.raises(ValueError, match="UNSUPPORTED_RULE"):
        enabled.require_available(optional.id)
    assert enabled.coverage == "RULES_SUBSET"
    assert (
        next(x for x in registry.entries if x.id == "strain.rebellion.endgame.3").module
        == "ancillary"
    )


def test_owner_reprogramming_ruling_has_explicit_provenance():
    registry = Registry.model_validate_json(json.dumps(data()))
    ruling = next(
        x for x in registry.campaign_rulings if x.id == "void-observation-reprogramming-fallback"
    )
    assert ruling.provenance == "owner_approved_campaign_ruling"
