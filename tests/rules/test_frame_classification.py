"""Printed Frame/class eligibility and stable historical rule references."""

import json
from collections import Counter

import pytest
from pydantic import ValidationError
from test_registry import data

from girlframe.engine.frame_classes import FRAME_CLASSES, frame_class, official_frame
from girlframe.engine.rules_registry import Registry


def registry():
    return Registry.model_validate_json(json.dumps(data()))


def test_nine_actual_frame_playbooks_and_three_printed_classes_are_distinct():
    rules = registry()
    books = [x for x in rules.entries if x.scope == "frame" and x.kind == "playbook"]
    assert len(books) == 9 and {x.frame_playbook for x in books} == set(FRAME_CLASSES)
    assert Counter(x.frame_class for x in books) == {"autocrat": 3, "priestess": 3, "legion": 3}
    assert all(x.frame_rule == "playbook" for x in books)
    assert rules.entry("frame.ankou.project-ankou").source.pdf_page == 84
    assert rules.entry("frame.prince.the-prince").source.pdf_page == 61


def test_janus_server_label_uses_its_actual_printed_class_without_creating_a_tenth_playbook():
    assert official_frame("JANUS-B") == official_frame("JANUS") == "JANUS"
    assert frame_class("janus-b") == "priestess"
    assert len(FRAME_CLASSES) == 9
    with pytest.raises(ValueError):
        frame_class("invented Frame")


@pytest.mark.parametrize(
    "cls,names",
    (
        (
            "autocrat",
            {
                "clone-am",
                "handlers-special-girl",
                "martyr",
                "succubus-protocol",
                "untouchable-frame",
            },
        ),
        (
            "priestess",
            {
                "appearance-matrix",
                "nightmare-core",
                "sup-of-primordial-flesh",
                "void-physiotherapist",
            },
        ),
        ("legion", {"dampener-link", "home-of-a-sort", "kicked-puppy", "modular-build"}),
    ),
)
def test_class_requisitions_belong_to_their_source_class_instead_of_red_queen(cls, names):
    rules = registry()
    entries = [
        x for x in rules.entries if x.frame_rule == "class_requisition" and x.frame_class == cls
    ]
    assert {x.id.rsplit(".", 1)[-1] for x in entries} == names
    assert all(x.frame_playbook is None and x.scope == "frame" for x in entries)
    assert {x.source.pdf_page for x in entries} == {dict(autocrat=92, priestess=93, legion=94)[cls]}
    for entry in entries:
        previous = "frame.red-queen." + entry.id.rsplit(".", 1)[-1]
        assert rules.entry(previous) == entry and previous in entry.aliases
        with pytest.raises(ValueError, match="implementation and review are incomplete"):
            rules.require_available(previous)


@pytest.mark.parametrize(
    "identity,category",
    (
        ("frame.consume.eat", "base"),
        ("frame.consume.human-hound", "requisition"),
        ("frame.janus.living-battery", "base"),
        ("frame.janus.pandora", "requisition"),
        ("frame.doctordoctor.nanobot-injection", "base"),
        ("frame.doctordoctor.borrowed-wings", "requisition"),
        ("frame.enforcer.enforcement-initiative", "base"),
        ("frame.enforcer.masters-dog", "requisition"),
        ("frame.changeling.psych-strings", "base"),
        ("frame.changeling.fingers-in-the-brain", "base"),
        ("frame.changeling.mindfuck", "requisition"),
        ("frame.ankou.emotional-relay", "base"),
        ("frame.ankou.fight-fawn-procedure", "requisition"),
    ),
)
def test_rules_on_pages_with_a_requisition_boundary_keep_their_actual_category(identity, category):
    entry = registry().entry(identity)
    assert entry.frame_rule == category and entry.frame_playbook in FRAME_CLASSES


def test_complete_frame_classification_is_not_runtime_implementation_or_certification():
    rules = registry()
    frame_entries = [x for x in rules.entries if x.scope == "frame"]
    assert len(frame_entries) == 104
    assert Counter(x.frame_rule for x in frame_entries) == {
        "playbook": 9,
        "base": 30,
        "requisition": 52,
        "class_requisition": 13,
    }
    assert len({x for entry in frame_entries for x in entry.aliases}) == 13
    assert rules.coverage == "RULES_SUBSET" and rules.summary()["verified"] == 0


@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate_alias",
        "canonical_collision",
        "self_alias",
        "bad_alias",
        "wrong_class",
        "wrong_scope",
        "class_owned_by_frame",
        "missing_category",
        "header_as_rule",
    ),
)
def test_registry_rejects_ambiguous_aliases_and_false_frame_classification(mutation):
    value = data()
    entry = next(x for x in value["entries"] if x["id"] == "frame.class.legion.modular-build")
    other = next(x for x in value["entries"] if x["id"] == "frame.class.legion.kicked-puppy")
    if mutation == "duplicate_alias":
        other["aliases"] = list(entry["aliases"])
    elif mutation == "canonical_collision":
        entry["aliases"] = [other["id"]]
    elif mutation == "self_alias":
        entry["aliases"] = [entry["id"]]
    elif mutation == "bad_alias":
        entry["aliases"] = ["Not a rule reference"]
    elif mutation == "wrong_class":
        target = next(x for x in value["entries"] if x["id"] == "frame.prince.performer")
        target["frame_class"] = "legion"
    elif mutation == "wrong_scope":
        entry["scope"] = "girl"
    elif mutation == "class_owned_by_frame":
        entry["frame_playbook"] = "THE RED QUEEN"
    elif mutation == "missing_category":
        entry["frame_rule"] = None
    else:
        target = next(x for x in value["entries"] if x["id"] == "frame.ankou.project-ankou")
        target["frame_rule"] = "base"
    with pytest.raises(ValidationError):
        Registry.model_validate_json(json.dumps(value))


def test_older_registry_records_without_class_metadata_still_load_without_inventing_eligibility():
    value = data()
    for entry in value["entries"]:
        for field in ("aliases", "frame_playbook", "frame_class", "frame_rule"):
            entry.pop(field, None)
    older = Registry.model_validate_json(json.dumps(value))
    assert all(x.frame_rule is None and not x.aliases for x in older.entries)
    assert older.coverage == "RULES_SUBSET"
