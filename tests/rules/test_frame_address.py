"""Only a genuine same-Frame rebirth normalizes an original physical Frame address."""

from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_void import questions

from girlframe.engine import m3_void
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_control import frame_address
from girlframe.engine.m3_void_state import HarpyAsset


def test_true_rebirth_keeps_physical_frame_address_without_inheriting_another_frame_or_cid(canon):
    state, value = questions(canon)
    sheet = state.sheets["2"]
    result = m3_void.rebirth(
        state,
        bindings(state),
        value.id,
        "actual-address-rebirth",
        harpy_id="actual-frame-address-harpy",
        new_vessel="actual-distinct-body",
        archive_id="actual-address-original",
        profile_id=value.actor.incarnation,
        profile_revision=sheet.source_profile_revision,
        retained_identities=(),
        new_identities=(),
        retained_tags=(),
        retained_plays=(),
        owned_plays=(),
        discarded_bonds=(),
        assets=tuple(HarpyAsset(**(x.model_dump() | dict(void=True))) for x in sheet.assets),
        account="Actual original source rebirth",
    )
    body = result.harpy_states[-1]
    current = ActorRef(kind="external_pilot", entity=body.id)
    assert frame_address(result, current, body.frame_instance) == (value.actor, body.frame_instance)
    assert frame_address(result, current, "different-new-frame") == (current, "different-new-frame")
    successor = ActorRef(
        kind="pilot", entity=value.actor.entity, incarnation="different-new-character"
    )
    assert frame_address(result, successor, body.frame_instance) == (successor, body.frame_instance)
    wrong_birth = result.model_copy(deep=True)
    wrong_birth.void_thresholds[-1] = wrong_birth.void_thresholds[-1].model_copy(
        update={"resulting_actor": ActorRef(kind="external_pilot", entity="another-body")}
    )
    assert frame_address(wrong_birth, current, body.frame_instance) == (
        current,
        body.frame_instance,
    )
