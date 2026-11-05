"""Actual Harpy carrier and guest bodies retain their own sole resource authority."""

from uuid import uuid4

from test_cast_service import change
from test_dive import choose, threshold_source
from test_harpy_actor_plays import begin
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mockingbird_communion import respond
from test_void_keep import keep
from test_void_service import five_no
from test_void_service import respond as void_respond

from girlframe.engine import m3_physical
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird import CALL
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services import m3_mockingbird_call as call
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_mockingbird_communion import CallService
from girlframe.services.m3_passengers import PassengerService
from girlframe.services.m3_void import VoidService


def place(game, actor, mode):
    with game.store.transaction() as c:
        canon = state(game)
        actual = resolve(
            canon, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        canon = m3_physical.initial(
            canon,
            profiles(c, game.store.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=actual.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode=mode,
                account="Actual existing original body and Frame",
                facts_confirmed=True,
            ),
            "actual-body-" + actor.entity,
            "actual-facts-" + actor.entity,
            "actual-review-" + actor.entity,
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_body", canon)


def test_real_retained_call_uses_harpy_carrier_and_guest_own_pilot_without_account_proxy(
    ledger, monkeypatch
):
    game, worker, gateway, parent, work = threshold_source(ledger, girl="MOCKINGBIRD")
    keep(game, worker, gateway, parent, work, controlled=False)
    service = VoidService(ledger)
    five_no(service, work)
    package = service.get(PLAYER, work)["rebirth_choice"] | dict(
        retained_plays=[CALL], account="Actual source retained Call"
    )
    void_respond(
        service, work, "save_rebirth", dict(choice=package, account="Actual owned source choice")
    )
    void_respond(service, work, "rebirth", dict(choice=package, account="Actual same-person birth"))
    tick(worker, gateway, 8)
    body = state(game).harpy_states[-1]
    carrier = ActorRef(kind="external_pilot", entity=body.id)
    assert CALL in body.plays and "2" not in state(game).sheets
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    change(CastService(ActorService(MissionService(ledger))), PLAYER, "join", carrier)
    guest = current_ref(state(game), 3)
    place(game, guest, "outside_frame")
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    identity = begin(
        ActorPlayService(game), carrier, play="dive_deep", context="Actual retained Call"
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, call.BOARD)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"target": guest.token},
        text="Actual Harpy cockpit invitation and contact",
    )
    communion = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(communion, OTHER, session, "accept")
    before = state(game)
    slot = next(x for x in before.sheets["3"].identities if not x.protected)
    respond(
        communion,
        OTHER,
        session,
        "effect",
        option="table_replaces_identity",
        identity=slot.id,
        replacement="Actual agreed guest Identity",
    )
    from test_ledger import ADMIN

    for viewer in (ADMIN, PLAYER, OTHER):
        respond(communion, viewer, session, "table", accepted=True)
    assert game.inspect(PLAYER, identity)["state"] == "complete" and "2" not in state(game).sheets
    placed = next(x for x in state(game).placements if x.actor == guest)
    assert (
        placed.occupied_frame_owner == carrier
        and placed.frame_instance != placed.occupied_frame_instance
    )
    assert (
        next(x for x in state(game).sheets["3"].identities if x.id == slot.id).name
        == "Actual agreed guest Identity"
    )
    assert game.dice.calls == 3


def test_actual_native_harpy_guest_table_choice_and_leave_never_mutate_same_human_pilot(
    ledger, monkeypatch
):
    from test_mockingbird_sex_closure import source

    game, worker, gateway, previous, _, guest = source(ledger, monkeypatch, target_harpy=True)
    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "deception"},
    )
    assert game.inspect(PLAYER, previous)["state"] == "complete"
    tick(worker, gateway, 8)
    actor = current_ref(state(game), 2)
    place(game, actor, "piloting")
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual source Call",
            trigger_confirmed=True,
            heat=0,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, call.BOARD)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"target": guest.token},
        text="Actual invitation to this original Harpy",
    )
    communion = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    original = state(game).sheets["3"].model_dump_json()
    respond(communion, OTHER, session, "accept")
    respond(
        communion,
        OTHER,
        session,
        "effect",
        option="table_replaces_identity",
        identity="actual-partner-free",
        replacement="Actual Harpy's new Identity",
    )
    from test_ledger import ADMIN

    for viewer in (ADMIN, PLAYER, OTHER):
        respond(communion, viewer, session, "table", accepted=True)
    physical = PassengerService(game)
    view = physical.get(OTHER, session)
    physical.respond(
        OTHER,
        str(uuid4()),
        session,
        view["revision"],
        "leave",
        "My actual Harpy body leaves the unlocked cockpit",
        actor=guest,
    )
    from girlframe.engine.m3_harpy_defeat import harpy

    actual = harpy(state(game), guest)
    assert not actual.linked and actual.identities[0].name == "Actual Harpy's new Identity"
    assert state(game).sheets["3"].model_dump_json() == original
    assert (
        state(game).passengers[-1].state == "left"
        and game.inspect(PLAYER, identity)["state"] == "complete"
    )
