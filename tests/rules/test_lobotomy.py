"""Only source-owned surgery and the actual patient's responses change her sheet."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_lobotomy as rules
from girlframe.engine.m2 import IdentityState, pair_key
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_lobotomy_state import Plan, Surgery


def begun(canon):
    canon.lobotomies.append(
        Surgery(
            id="actual-surgery",
            subject=current_ref(canon, 2),
            inflictor=current_ref(canon, 1),
            work_ids=("actual-severe-work",),
            source_event="actual-severe-choice",
        )
    )
    return canon


def plan(**kwargs):
    return Plan(room="Actual room", restraints="Actual restraints", tools="Actual tools", **kwargs)


def apply(canon, selected):
    prepared = rules.prepare(begun(canon), "actual-surgery", selected, "actual-plan")
    assert not prepared.lobotomies[0].responses
    with pytest.raises(ValueError, match="patient"):
        rules.apply(prepared, "actual-surgery", "too-early", allow_duplicate_labels=False)
    described = rules.respond(
        prepared,
        "actual-surgery",
        {option: "The original patient's actual description" for option in selected.options},
        "actual-patient-responses",
    )
    return rules.apply(
        described, "actual-surgery", "actual-application", allow_duplicate_labels=False
    )


def test_reset_erase_and_implant_preserve_protected_extras_and_source_ordinary_slots(canon):
    canon.sheets["2"].identities.append(
        IdentityState(id="protected", name="Protected extra", protected=True, marked=True)
    )
    before = canon.sheets["2"].model_dump_json()
    result = apply(
        canon,
        plan(
            options=("memories", "memory"),
            erase_slots=(0, 2),
            memory="The inflictor's implanted memory",
            identity="Implanted Identity",
        ),
    )
    assert canon.sheets["2"].model_dump_json() == before
    identities = result.sheets["2"].identities
    assert len([x for x in identities if not x.protected]) == 3
    assert next(x for x in identities if x.id == "protected").marked
    assert {x.slot for x in identities if not x.protected} == {0, 1, 3}


def test_forbidden_mandatory_play_remains_forbidden_without_an_invented_exception(canon):
    result = apply(canon, plan(options=("play",), forbidden_play="defeat"))
    actual = rules.blocked_play(result.sheets["2"], "defeat")
    assert actual.surgery == "actual-surgery" and actual.source_event == "actual-application"
    assert rules.blocked_play(result.sheets["3"], "defeat") is None
    assert not canon.sheets["2"].blocked_plays


def test_remove_all_bonds_then_inflictor_selected_bonds_have_single_actor_authority(canon):
    canon.bonds[pair_key(2, 3)] = 2
    first, handler = current_ref(canon, 2), current_ref(canon, 1)
    result = apply(canon, plan(options=("bonds", "name"), inflictor_depth=2, new_name=""))
    assert not result.sheets["2"].callsign
    assert depth(result, first, current_ref(result, 3)) == 0
    assert depth(result, first, handler) == 2
    assert all("2" not in key.split(":") for key in result.bonds)


def test_identity_implant_requires_real_four_slot_replacement_and_never_protected(canon):
    with pytest.raises(ValueError, match="four-slot"):
        rules.prepare(
            begun(canon),
            "actual-surgery",
            plan(options=("memory",), memory="Actual memory", identity="New Identity"),
            "actual-plan",
        )


def test_surgery_cannot_follow_replacement_of_same_human_account(canon):
    result = rules.prepare(
        begun(canon), "actual-surgery", plan(options=("name",), new_name="Changed"), "actual-plan"
    )
    result.sheets["2"].character_id = "replacement-character"
    with pytest.raises(ValueError, match="original patient"):
        rules.respond(result, "actual-surgery", {"name": "Replacement cannot respond"}, "forged")
