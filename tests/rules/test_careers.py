"""Canonical career endings preserve original resources without account inheritance."""

import json

import pytest
from pydantic import ValidationError
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_careers as rules
from girlframe.engine.m2 import Obligation, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime


def actor(state, owner=2):
    return ActorRef(
        kind="pilot", entity=str(owner), incarnation=state.sheets[str(owner)].character_id
    )


def end(state, **changes):
    values = dict(
        reason="death",
        source_event="actual-death-source",
        account="Actual chosen outcome",
        archive_id="actual-career-archive",
        profile_id=state.sheets["2"].character_id,
        profile_revision=state.sheets["2"].source_profile_revision,
    )
    values.update(changes)
    return rules.end(state, actor(state), **values)


@pytest.mark.parametrize("reason", ["death", "execution", "imprisonment", "retirement"])
def test_actual_ending_preserves_immutable_original_sheet_and_removes_active_authority(
    canon, reason
):
    before = canon.model_dump_json()
    original = actor(canon)
    sheet = canon.sheets["2"].model_dump_json()
    result = end(canon, reason=reason)
    assert canon.model_dump_json() == before
    assert "2" not in result.sheets and 2 not in result.order
    saved = rules.archive_for(result, original)
    assert saved.ending == reason and saved.sheet_json == sheet
    assert rules.original_sheet(result, original).model_dump_json() == sheet
    with pytest.raises(ValidationError):
        saved.account = "Cannot rewrite an original ending"
    with pytest.raises(ValueError, match="CAREER_ENDED"):
        rules.profile_character(result, 2, original.incarnation, 1)


def test_end_clears_numeric_relationship_privileges_but_preserves_original_links_and_npc_bonds(
    canon,
):
    sheet = canon.sheets["3"]
    sheet.mentor, sheet.pair, sheet.helpless_against = 2, 2, (2,)
    sheet.tags.append(
        TagState(id="old-setter-tag", label="Actual old Tag", giver=2, observers=(2, 3))
    )
    sheet.frame_runtime = FrameRuntime(
        id="actual-third-frame",
        generation=1,
        source_work="actual",
        court={"The Consort": 2},
        psych_strings=(2,),
    )
    npc = canon.world.npcs[0]
    canon.world = canon.world.model_copy(
        update={"npcs": (npc.model_copy(update={"bonds": {"pilot:2": 2}}), *canon.world.npcs[1:])}
    )
    original = actor(canon)
    result = end(canon)
    other = result.sheets["3"]
    assert other.mentor is None and other.pair is None and not other.helpless_against
    assert not other.frame_runtime.court and not other.frame_runtime.psych_strings
    assert other.tags[-1].giver_character == original.incarnation
    assert other.tags[-1].observers == (3,)
    assert not rules.tag_giver_is_current(result, other.tags[-1])
    assert not any("2" in key.split(":") for key in result.bonds)
    assert result.world.npcs[0].bonds == {}
    from girlframe.engine.m3_actor_bonds import depth

    assert depth(result, original, ActorRef(kind="npc", entity=npc.id)) == 2
    links = json.loads(result.career_archives[-1].links_json)
    assert links["npc_bonds"] == {npc.id: 2}
    assert links["incoming"][0]["mentor"] == 2


def test_replacement_needs_explicit_new_incarnation_and_handler_starting_status(canon):
    old = actor(canon)
    next_revision = canon.sheets["2"].source_profile_revision + 1
    result = end(canon)
    newer = rules.replacement(
        result,
        "actual-career-archive",
        owner=2,
        new_character="new-actual-incarnation",
        profile_id=old.incarnation,
        profile_revision=next_revision,
        source_event="actual-owned-replacement",
    )
    assert "2" not in newer.sheets and 2 not in newer.order
    assert (
        rules.profile_character(newer, 2, old.incarnation, next_revision)
        == "new-actual-incarnation"
    )
    assert rules.binding(newer, 2).status_position is None
    approved = rules.replacement_status(
        newer, 2, "new-actual-incarnation", 1, "actual-handler-starting-status"
    )
    assert rules.binding(approved, 2).status_position == 1
    assert (
        rules.original_sheet(approved, old).source_fingerprint
        == canon.sheets["2"].source_fingerprint
    )
    with pytest.raises(ValueError):
        rules.replacement(
            result,
            "actual-career-archive",
            owner=2,
            new_character=old.incarnation,
            profile_id=old.incarnation,
            profile_revision=next_revision,
            source_event="reuse",
        )
    with pytest.raises(ValueError):
        rules.replacement_status(newer, 2, "wrong-incarnation", 0, "wrong-source")


def test_death_does_not_forge_tag_consent_or_transfer_old_owned_debts(canon):
    canon.obligations.extend(
        [
            Obligation(
                id="old-punishment", kind="punishment", owner=2, target=1, action="actual-old"
            ),
            Obligation(
                id="consent",
                kind="tag_rejection_permission",
                owner=2,
                target=3,
                action="actual-old",
                details={"owner_character": actor(canon).incarnation},
            ),
        ]
    )
    result = end(canon)
    assert [x.id for x in result.obligations] == ["consent"]
    assert result.obligations[0].state == "pending"
    links = json.loads(result.career_archives[-1].links_json)
    assert {x["id"] for x in links["owned_obligations"]} == {"old-punishment", "consent"}


def test_other_incarnation_or_replayed_ending_cannot_remove_the_active_girl(canon):
    original = actor(canon)
    with pytest.raises(ValueError):
        rules.end(
            canon,
            ActorRef(kind="pilot", entity="2", incarnation="another-girl"),
            reason="death",
            source_event="source",
            account="Actual",
            archive_id="archive",
            profile_id=original.incarnation,
            profile_revision=1,
        )

    ended = end(canon)
    with pytest.raises(ValueError):
        rules.end(
            ended,
            original,
            reason="death",
            source_event="source-again",
            account="Actual",
            archive_id="another-archive",
            profile_id=original.incarnation,
            profile_revision=1,
        )


def test_link_reversal_preserves_the_girl_and_records_the_actual_lost_frame(canon):
    original = actor(canon)
    sheet = canon.sheets["2"]
    prior_girl = [x for x in sheet.assets if x.family == "girl"]
    prior_frame = [x.model_dump(mode="json") for x in sheet.assets if x.family == "frame"]
    result = rules.unlink(
        canon, original, source_event="actual-link-reversal", account="Handler surgery"
    )
    changed = result.sheets["2"]
    assert changed.assets == prior_girl and changed.identities == sheet.identities
    assert changed.permissions == sheet.permissions and changed.heat == sheet.heat
    assert changed.frame_scrapped and result.order == canon.order and result.bonds == canon.bonds
    assert not rules.can_pilot(result, original)
    assert json.loads(result.unlinked_careers[-1].frame_json)["assets"] == prior_frame
