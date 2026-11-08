import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_director import enter

canon = canon_fixture
ledger = ledger_fixture


def handler(canon):
    state = enter(canon, 1, "director", "actual-presence", ("Afraid", "Defiant"), "actual-source")
    return state, ActorRef(kind="handler", entity="1", incarnation=state.director_contexts[-1].id)


def test_handler_girl_port_marks_and_spends_actual_context_without_a_proxy_pilot_or_borrowed_traits(
    canon,
):
    state, ref = handler(canon)
    actual = resolve(state, ref, bindings(state))
    identity = actual.identities[0].id
    result = commit(
        state,
        ref,
        bindings(state),
        Commitment(heat=2, identity=identity, gain=3),
        actual.source_sha256,
    )
    assert (
        result.state.handler_heat == 1 and result.state.director_contexts[-1].identities[0].marked
    )
    assert (
        result.state.sheets == state.sheets
        and result.state.order == state.order
        and "1" not in result.state.sheets
    )
    assert (
        not result.followups
        and state.handler_heat == 0
        and not state.director_contexts[-1].identities[0].marked
    )
    assert actual.girl is actual.frame is None


@pytest.mark.parametrize(
    "held,gain,spend,allowed",
    [
        (0, 0, 1, False),
        (2, 0, 2, True),
        (5, 0, 4, False),
        (5, 0, 5, True),
        (2, 3, 4, False),
        (2, 3, 5, True),
    ],
)
def test_actual_handler_context_obeys_standard_heat_and_forced_spending(
    canon, held, gain, spend, allowed
):
    state, ref = handler(canon)
    state.handler_heat = held
    actual = resolve(state, ref, bindings(state))
    prepared = Commitment(heat=spend, gain=gain, identity=actual.identities[0].id if gain else None)
    if allowed:
        result = commit(state, ref, bindings(state), prepared, actual.source_sha256)
        assert result.state.handler_heat == held + gain - spend
    else:
        with pytest.raises(ValueError):
            commit(state, ref, bindings(state), prepared, actual.source_sha256)
    assert state.handler_heat == held


def test_stale_scope_foreign_identity_pair_share_and_non_girl_roles_cannot_borrow_resources(canon):
    state, ref = handler(canon)
    actual = resolve(state, ref, bindings(state))
    for prepared, expected in (
        (Commitment(heat=0), "a" * 64),
        (
            Commitment(heat=0, identity=state.sheets["2"].identities[0].id, gain=1),
            actual.source_sha256,
        ),
        (Commitment(heat=0, pair_share=1), actual.source_sha256),
    ):
        with pytest.raises(ValueError):
            commit(state, ref, bindings(state), prepared, expected)
    for other in (ActorRef(kind="npc", entity="2"), ActorRef(kind="gorgon", entity="secret")):
        current = resolve(state, other, bindings(state))
        with pytest.raises(ValueError, match="no supported Girl"):
            commit(state, other, bindings(state), Commitment(heat=0), current.source_sha256)
    assert state.sheets == canon.sheets and state.handler_heat == 0


def test_pilot_port_retains_real_paired_heat_and_emits_required_ankou_feedback(canon):
    sheet = canon.sheets["2"]
    sheet.girl, sheet.pair = "BONDED", 3
    sheet.identities[0].paired = True
    ref = ActorRef(kind="pilot", entity="2", incarnation=sheet.character_id)
    actual = resolve(canon, ref, bindings(canon))
    result = commit(
        canon,
        ref,
        bindings(canon),
        Commitment(heat=1, identity=sheet.identities[0].id, gain=5, pair_share=3),
        actual.source_sha256,
    )
    assert result.state.sheets["2"].heat == 1 and result.state.sheets["3"].heat == 3
    assert canon.sheets["2"].heat == canon.sheets["3"].heat == 0
    sheet.girl, sheet.frame = "MOCKINGBIRD", "PROJECT ANKOU"
    sheet.identities[0].paired = False
    for identity in sheet.identities[1:]:
        identity.marked = True
    actual = resolve(canon, ref, bindings(canon))
    result = commit(
        canon,
        ref,
        bindings(canon),
        Commitment(heat=0, identity=sheet.identities[0].id, gain=1),
        actual.source_sha256,
    )
    assert [x.kind for x in result.followups] == ["ankou_feedback"]


def test_known_legacy_resources_use_original_snapshot_proof_after_same_body_draft_change(canon):
    sheet = canon.sheets["2"]
    original_id, original_revision = sheet.character_id, sheet.source_profile_revision
    sheet.character_id = None
    proof = tuple(
        ProfileBinding(
            owner=x.owner,
            character_id=original_id if x.owner == 2 else x.character_id,
            profile_revision=x.source_profile_revision + (1 if x.owner == 2 else 0),
            source_character_id=original_id if x.owner == 2 else x.character_id,
            source_profile_revision=x.source_profile_revision,
        )
        for x in canon.sheets.values()
    )
    ref = ActorRef(kind="pilot", entity="2", incarnation=original_id)
    with pytest.raises(ValueError):
        resolve(canon, ref, proof)
    actual = resolve(canon, ref, proof, require_current_profile=False)
    result = commit(
        canon, ref, proof, Commitment(heat=0), actual.source_sha256, require_current_profile=False
    )
    assert result.state.sheets["2"].character_id is None
    assert result.state.sheets["2"].source_profile_revision == original_revision
    false_proof = tuple(
        x.model_copy(update={"source_profile_revision": original_revision + 1})
        if x.owner == 2
        else x
        for x in proof
    )
    with pytest.raises(ValueError):
        resolve(canon, ref, false_proof, require_current_profile=False)
