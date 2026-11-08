from uuid import uuid4

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine import m3_comforts as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_requisition_state import GirlAsset

canon, ledger = canon_fixture, ledger_fixture


def purchaser(state):
    return ActorRef(kind="pilot", entity="2", incarnation=state.sheets["2"].character_id)


def paid(canon):
    canon.sheets["2"].permissions = 2
    ref = purchaser(canon)
    state = rules.purchase(
        canon,
        ref,
        bindings(canon),
        resolve(canon, ref, bindings(canon)).source_sha256,
        "purchase",
        "actual-purchase-event",
        "Improve my life",
    )
    return state, ref, state.requisitions[-1]


def offered(canon):
    state, ref, purchase = paid(canon)
    return (
        state,
        ref,
        rules.qualify(
            purchase,
            ref,
            "period",
            "action",
            "go_off_duty",
            8,
            "actual-raw-event",
            "actual-final-event",
        ),
    )


def cast_for(state, refs):
    return SceneCast(
        id="actual-scene",
        channel=900,
        roles=tuple(
            CastRole(
                actor=x,
                controller=resolve(state, x, bindings(state)).controller,
                source_event="actual-join:" + x.token,
            )
            for x in refs
        ),
    )


def scene(state, ref, benefit, refs=None, **kwargs):
    participants = refs or (ref,)
    return rules.record_scene(
        state,
        bindings(state),
        benefit,
        cast_for(state, participants),
        participants,
        2,
        "An actual improvement scene",
        "actual-scene-source",
        kwargs.get("location", "base0"),
    )


def test_paid_comforts_record_immutable_cost_source_without_granting_an_asset(canon):
    state, ref, receipt = paid(canon)
    assert state.sheets["2"].permissions == 1 and canon.sheets["2"].permissions == 2
    assert state.sheets["2"].assets == canon.sheets["2"].assets
    assert (
        receipt.actor == ref
        and receipt.source_event == "actual-purchase-event"
        and receipt.price == 1
    )
    with pytest.raises(ValueError, match="new paid"):
        rules.purchase(
            state,
            ref,
            bindings(state),
            resolve(state, ref, bindings(state)).source_sha256,
            "purchase",
            "different-event",
            "Again",
        )


@pytest.mark.parametrize(
    "play,total,eligible",
    [
        ("go_off_duty", 7, False),
        ("go_off_duty", 8, True),
        ("go_off_duty", 10, True),
        ("go_off_duty", 11, True),
        ("go_off_duty", 20, True),
        ("void_observation", 12, False),
        ("keep_your_head", 12, False),
    ],
)
def test_exact_named_future_roll_trigger_uses_final_eight_plus_total(canon, play, total, eligible):
    state, ref, receipt = paid(canon)
    result = rules.qualify(
        receipt, ref, "period", "action", play, total, "raw-event", "final-event"
    )
    assert (result is not None) == eligible
    assert (
        rules.qualify(
            receipt,
            ref.model_copy(update={"incarnation": "new-body"}),
            "period",
            "action",
            play,
            total,
            "raw-event",
            "final-event",
        )
        is None
    )


def test_optional_opportunity_can_be_declined_only_by_its_actual_purchasing_human(canon):
    state, ref, benefit = offered(canon)
    with pytest.raises(ValueError):
        rules.decline(benefit, 3, "Not mine")
    declined = rules.decline(benefit, 2, "I decline the optional scene")
    assert declined.taken is False and declined.asset_id is None
    assert state.sheets["2"].permissions == 1
    with pytest.raises(ValueError):
        scene(state, ref, declined)


def test_actual_scene_attendance_is_owned_per_human_and_does_not_invent_resource_gain(canon):
    state, ref, benefit = offered(canon)
    other = ActorRef(kind="pilot", entity="3", incarnation=state.sheets["3"].character_id)
    actual = scene(state, ref, benefit, (ref, other))
    assert actual.scene.acknowledgements == (2,) and not rules.ready(actual)
    for wrong in (2, 999):
        with pytest.raises(ValueError):
            rules.attest(actual, wrong)
    with pytest.raises(ValueError):
        rules.grant(
            state,
            bindings(state),
            resolve(state, ref, bindings(state)).source_sha256,
            actual,
            GirlAsset(name="New outfit", description="Reflects the improvement"),
            "new-asset",
        )
    complete = rules.attest(actual, 3)
    assert rules.ready(complete) and not rules.ready(actual)
    assert (
        state.sheets["2"].permissions == 1 and state.sheets["2"].assets == canon.sheets["2"].assets
    )


def test_one_human_controlling_two_real_roles_does_not_need_a_second_invented_response(canon):
    state, ref, benefit = offered(canon)
    npc = ActorRef(kind="npc", entity="2")
    actual = scene(state, ref, benefit, (ref, npc))
    assert (
        len(actual.scene.roles) == 2
        and actual.scene.acknowledgements == (2,)
        and rules.ready(actual)
    )


def test_actual_world_role_must_already_be_at_the_selected_surviving_location(canon):
    state, ref, benefit = offered(canon)
    npc = ActorRef(kind="npc", entity="2")
    with pytest.raises(ValueError, match="does not move"):
        scene(state, ref, benefit, (ref, npc), location="base1")
    actual = scene(state, ref, benefit, location="city0")
    assert actual.scene.location == "city0" and state.placements == []
    with pytest.raises(ValueError, match="does not move"):
        scene(state, ref, benefit, (ref, npc), location="city0")
    with pytest.raises(ValueError, match="actual surviving"):
        scene(state, ref, benefit, location="invented")
    city = next(x for x in state.world.locations if x.id == "city0")
    state.world = state.world.model_copy(
        update={
            "locations": tuple(
                x.model_copy(update={"condition": "destroyed"}) if x.id == city.id else x
                for x in state.world.locations
            )
        }
    )
    with pytest.raises(ValueError, match="actual surviving"):
        scene(state, ref, benefit, location="city0")


def test_owned_scene_grants_one_real_girl_asset_and_preserves_permission_payment(canon):
    state, ref, benefit = offered(canon)
    actual = scene(state, ref, benefit)
    before = state.sheets["2"].model_dump()
    updated, resolved = rules.grant(
        state,
        bindings(state),
        resolve(state, ref, bindings(state)).source_sha256,
        actual,
        GirlAsset(name="My new outfit", description="Reflects the scene"),
        "reward-asset",
    )
    assert resolved.taken and resolved.asset_id == "reward-asset"
    asset = updated.sheets["2"].assets[-1]
    assert asset.family == "girl" and not asset.damaged and not asset.void
    assert updated.sheets["2"].permissions == state.sheets["2"].permissions == 1
    assert state.sheets["2"].model_dump() == before and updated.sheets["3"] == state.sheets["3"]
    for stale in (actual, resolved):
        with pytest.raises(ValueError):
            rules.grant(
                updated,
                bindings(updated),
                resolve(updated, ref, bindings(updated)).source_sha256,
                stale,
                GirlAsset(name="Duplicate", description="Not another reward"),
                str(uuid4()),
            )


def test_comforts_gift_respects_girl_cap_and_never_replaces_a_void_or_frame_asset(canon):
    state, ref, benefit = offered(canon)
    sheet = state.sheets["2"]
    while len([x for x in sheet.assets if x.family == "girl"]) < 4:
        sheet.assets.append(AssetState(id=str(uuid4()), name="Extra", family="girl"))
    ordinary = next(x for x in sheet.assets if x.family == "girl" and not x.void)
    void = next(x for x in sheet.assets if x.family == "girl" and x.void)
    frame = next(x for x in sheet.assets if x.family == "frame")
    actual = scene(state, ref, benefit)
    expected = resolve(state, ref, bindings(state)).source_sha256
    for replacement in (None, frame.id, void.id, "foreign"):
        with pytest.raises(ValueError, match="non-Void"):
            rules.grant(
                state,
                bindings(state),
                expected,
                actual,
                GirlAsset(name="Gift", description="Improvement", replace=replacement),
                "reward-asset",
            )
    updated, done = rules.grant(
        state,
        bindings(state),
        expected,
        actual,
        GirlAsset(name="Gift", description="Improvement", replace=ordinary.id),
        "reward-asset",
    )
    assert len([x for x in updated.sheets["2"].assets if x.family == "girl"]) == 4
    assert not any(x.id == ordinary.id for x in updated.sheets["2"].assets)
    assert any(x.id == void.id for x in updated.sheets["2"].assets)


def test_stale_sheet_and_replacement_body_cannot_take_the_old_paid_benefit(canon):
    state, ref, benefit = offered(canon)
    actual = scene(state, ref, benefit)
    choice = GirlAsset(name="Gift", description="Improvement")
    with pytest.raises(ValueError):
        rules.grant(state, bindings(state), "0" * 64, actual, choice, "reward-asset")
    state.sheets["2"].character_id = "another-body"
    with pytest.raises(ValueError, match="STALE_ACTOR"):
        rules.grant(state, bindings(state), "0" * 64, actual, choice, "reward-asset")
