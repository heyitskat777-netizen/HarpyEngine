"""Handler Assets replace actual triggers with owned effects, never imaginary damage tracks."""

import json

import pytest
from pydantic import ValidationError
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_handler_consequences as rules
from girlframe.engine.m2 import DirectorContext, IdentityState, TagState, pair_key
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_handler_state import Draft, HandlerPersona


def required(canon, *, occurrence="actual-damage"):
    target = rules.active_handler(canon)
    return rules.require(
        canon,
        target,
        trigger="asset_damage",
        source_action="actual-source-play",
        source_event="actual-damage-event",
        opponent=current_ref(canon, 2),
        appointment="actual-appointment",
        occurrence=occurrence,
    )


@pytest.mark.parametrize("choice", ["opportunity", "chance_to_act", "weakness", "injury"])
def test_actual_surviving_choices_preserve_body_and_create_exact_persistent_source_effect(
    canon, choice
):
    before = canon.model_dump_json()
    prepared, identity = required(canon)
    result = rules.apply(
        prepared, identity, choice, "Actual human-described effect", "effect-event"
    )
    assert canon.model_dump_json() == before
    assert rules.active_handler(result) == rules.active_handler(canon)
    assert not result.handler_archives
    assert result.handler_consequences[-1].choice == choice
    if choice == "injury":
        assert result.handler_injuries[-1].description == "Actual human-described effect"
        assert result.handler_injuries[-1].recovery_event is None
    else:
        assert result.handler_opportunities[-1].beneficiary == current_ref(canon, 2)
        assert result.handler_opportunities[-1].kind == choice
    assert not result.helpless_conditions


def test_legacy_handler_death_preserves_actual_original_resources_and_ends_live_body_not_gm(canon):
    canon.handler_heat = 7
    canon.handler_tags = [TagState(id="actual-handler-tag", label="Actual Tag", giver=2)]
    canon.bonds[pair_key(1, 2)] = 2
    canon.director_contexts.append(
        DirectorContext(
            id="actual-director-context",
            handler=1,
            directors=("actual-director",),
            source_works=("actual-presence-source",),
            identities=[IdentityState(id="actual-context-identity", name="Actual context self")],
            source_event="actual-director-presence",
        )
    )
    target = rules.active_handler(canon)
    prepared, identity = required(canon)
    result = rules.apply(
        prepared, identity, "death", "Actual original body's death", "actual-death"
    )
    assert result.handler == 1 and rules.active_handler(result) is None
    assert not result.handler_tags and result.handler_heat == 0 and result.handler_persona is None
    saved = result.handler_archives[-1]
    assert saved.actor == target and saved.body.heat == 7
    assert json.loads(saved.body.tags_json)[0]["id"] == "actual-handler-tag"
    assert rules.body_original(result, target) == saved.body
    assert depth(result, target, current_ref(result, 2)) == 2
    assert pair_key(1, 2) not in result.bonds
    context = result.director_contexts[-1]
    assert not context.active and context.directors == ("actual-director",)
    assert context.identities == canon.director_contexts[-1].identities
    assert (
        context.termination_event == "actual-death"
        and context.termination_reason == "handler_death"
    )
    with pytest.raises(ValidationError):
        saved.account = "Cannot erase an original death"
    with pytest.raises(ValueError, match="body ended"):
        current_ref(result, 1)


def test_fresh_persona_does_not_reuse_legacy_body_bonds_heat_tags_or_injury(canon):
    canon.bonds[pair_key(1, 2)] = 2
    prepared, identity = required(canon)
    result = rules.apply(prepared, identity, "death", "Actual death", "actual-source-death")
    # This synthetic birth isolates the actual runtime identity-port guarantee.
    result.handler_persona = HandlerPersona(
        id="actual-fresh-persona",
        owner=1,
        appointment="actual-appointment",
        draft=Draft(name="New actual Handler"),
        source_event="actual-new-persona-source",
    )
    new = rules.active_handler(result)
    old = result.handler_archives[-1].actor
    assert old != new and new.incarnation == "actual-fresh-persona"
    assert depth(result, new, current_ref(result, 2)) == 0
    assert depth(result, old, current_ref(result, 2)) == 2


def test_actual_body_death_ends_other_pending_triggers_without_a_forged_second_human_choice(canon):
    prepared, first = required(canon, occurrence="first-actual-trigger")
    prepared, second = required(prepared, occurrence="second-actual-trigger")
    result = rules.apply(prepared, first, "death", "One actual original body dies", "actual-death")
    ending = next(x for x in result.handler_consequences if x.id == second)
    assert ending.state == "ended" and ending.choice is None and not ending.account
    assert ending.ended_by == first and ending.effect_event == "actual-death"
    assert len(result.handler_archives) == 1
    with pytest.raises(ValueError, match="pending source"):
        rules.apply(result, second, "injury", "No new body may inherit this", "fake-effect")
