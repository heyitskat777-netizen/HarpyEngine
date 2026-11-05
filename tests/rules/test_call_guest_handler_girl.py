"""Actual registered Girl-rules body, real Void transfer, then one owned guest consequence."""

from uuid import uuid4

from test_dive import choose
from test_handler_void_service import high_director
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mockingbird_communion import respond

from girlframe.engine import m3_physical
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_girl_void import girl_assets
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services import m3_mockingbird_call as call
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.m3_mockingbird_communion import CallService


def test_actual_handler_girl_guest_chooses_own_existing_asset_without_frame_or_fake_ack(
    ledger, monkeypatch
):
    game, worker, gateway, original, work, _, _, _ = high_director(
        ledger, monkeypatch, handler_girl=True
    )
    service = HandlerGirlVoidService(ledger, game)
    patient = state(game).handler_girl_void[-1].actor
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Actual existing optic",
        "The real preexisting damaged implant",
        "Its actual preexisting source history",
        damaged=True,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="Actual original judge reviews existing fact",
    )
    asset = service.get(PLAYER, work)["assets"][0]["id"]
    service.select(PLAYER, str(uuid4()), work, state(game).revision, asset)
    service.rewrite(
        ADMIN, str(uuid4()), work, state(game).revision, "Actual existing source corruption"
    )
    assert game.inspect(PLAYER, original)["state"] == "complete"
    tick(worker, gateway, 8)
    actor = current_ref(state(game), 2)
    book = MockingbirdService(game)
    trigger = book.propose(
        PLAYER, str(uuid4()), 900, actor, SEX, (patient,), "Actual new source interaction"
    )
    book.attest(ADMIN, str(uuid4()), trigger["id"], patient, True)
    game.dice.faces = (4, 5)
    source = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual transfer",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset, "destination": actor.token, "destination_asset": ""},
    )
    answer(
        game,
        ADMIN,
        "mockingbird_sex_restore",
        text="The original damaged implant without its transferred corruption",
    )
    answer(
        game,
        PLAYER,
        "mockingbird_sex_self",
        fields={"name": "Actual collected Void", "replace": ""},
        text="An actual self-written alteration",
    )
    assert (
        game.inspect(PLAYER, source)["state"] == "complete"
        and not girl_assets(state(game), patient)[0].void
    )
    tick(worker, gateway, 8)
    with ledger.transaction() as c:
        canon = state(game)
        actual = resolve(
            canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False
        )
        canon = m3_physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=actual.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting",
                account="Actual existing original pilot and carrier Frame",
                facts_confirmed=True,
            ),
            "original-call-body",
            "original-call-facts",
            "actual-call-review",
        )
        game.event(c, 2, str(uuid4()), "synthetic.actual_existing_carrier", canon)
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    dive = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual owned Call",
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
        fields={"target": patient.token},
        text="Actual invitation and contact at my cockpit",
    )
    communion = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(communion, ADMIN, session, "accept")
    before = state(game)
    respond(
        communion,
        ADMIN,
        session,
        "effect",
        option="void_and_unmark_all",
        asset=asset,
        description="My actual guest-owned rewrite",
    )
    after = state(game)
    assert game.inspect(PLAYER, dive)["state"] == "complete" and game.dice.calls == 3
    assert girl_assets(after, patient)[0].void and girl_assets(after, patient)[0].damaged
    assert len(girl_assets(after, patient)) == 1 and len(after.held_items) == len(before.held_items)
    assert after.handler_girl_void[-1].allure and after.handler_girl_void[-1].assigned_frame is None
    assert not after.harpy_states and not after.void_thresholds
    assert after.sheets == before.sheets and not any(x.actor == patient for x in after.placements)
