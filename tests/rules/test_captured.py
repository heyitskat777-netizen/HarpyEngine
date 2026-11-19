"""Original rebel custody, high Identity erasure and a real no-Heat escape roll."""

import asyncio

import pytest
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import place
from test_world_service import ready

from girlframe.discord_adapter.m3_captured import open_capture, open_capture_choice
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_captured import RULE, records
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_captured import CapturedService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_items import prove_item
from girlframe.services.onboarding import WorkflowError


def begin_capture(ledger, faces):
    world, game = ready(ledger)
    game.dice.faces = faces
    faction = Faction(id="actual-rebel-group", name="Rebel group", kind="rebel", cells=((0, 0),))
    world.faction(ADMIN, "rebel-faction", state(game).revision, faction)
    captor = ActorRef(kind="npc", entity="actual-rebel-handler")
    world.npc(
        ADMIN,
        "rebel-captor",
        state(game).revision,
        Npc(
            id=captor.entity,
            name="Rebel Handler",
            jobs=("handler",),
            detail="The original captor at their own base.",
            controller=ADMIN.user_id,
            revealed=True,
            faction=faction.id,
            cell=(0, 0),
        ),
    )
    with ledger.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame")
        canon.sheets["2"].heat = 2
        canon.world = canon.world.model_copy(
            update=dict(
                locations=tuple(
                    x.model_copy(update=dict(allegiance="rebel")) if x.id == "base0" else x
                    for x in canon.world.locations
                )
            )
        )
        game.event(c, ADMIN.user_id, "synthetic-existing-rebel-base", "synthetic.position", canon)
    cast = CastService(ActorService(world.missions))
    change(cast, ADMIN, "join", captor)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays"},
                    activity_specialist_rules=policy.activity_specialist_rules | {RULE},
                )
            )
        )
    )
    service = CapturedService(game)
    original = state(game)
    girl = current_ref(original, PLAYER.user_id)
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_capture(click, service, 900, captor),
            dict(subject=(girl.token,), account="They leave the original Girl alive and hold her."),
            91500,
        )
    )
    capture = records(state(game))[0]
    assert state(game).placements == original.placements
    inbox = InboxService(ledger)

    def native(viewer, values, number):
        item = next(x for x in inbox.items(viewer) if x.task == "m3_captured")

        async def route(click):
            await open_capture_choice(click, service, item.identity)

        return asyncio.run(submit_form(viewer, route, values, number))

    native(PLAYER, dict(choice=("accept",)), 91504)
    assert is_helpless(state(game), girl, captor)
    assert next(x for x in state(game).placements if x.actor == girl).custody == captor
    return game, service, native, original, girl, captor, capture.id


def test_captured_high_erases_original_identity_and_next_roll_cannot_spend_heat(ledger):
    game, service, native, original, girl, captor, identity = begin_capture(ledger, (6, 6))
    original_placement = next(x for x in original.placements if x.actor == girl)
    with pytest.raises(WorkflowError, match="Captured!"):
        game.begin(
            PLAYER,
            "not-off-duty-while-captive",
            900,
            state(game).sheets["2"].revision,
            PlayInput(play="go_off_duty", context="Resting", trigger_confirmed=True, heat=0),
        )
    native(PLAYER, dict(heat="1"), 91508)
    assert state(game).sheets["2"].heat == 1 and game.dice.calls == 1
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, identity)
    native(
        ADMIN,
        dict(choice=("handler",), account="The original Rebel Handler sets the punishment scene."),
        91512,
    )
    erased = original.sheets["2"].identities[0].id
    native(PLAYER, dict(choice=(erased,)), 91516)
    assert all(x.id != erased for x in state(game).sheets["2"].identities)
    with pytest.raises(WorkflowError, match="permitted Heat"):
        service.act(PLAYER, "illegal-followup-heat", identity, state(game).revision, "roll", heat=1)
    assert game.dice.calls == 1
    ledger.engine.dispose()
    game.dice.faces = (4, 5)
    native(PLAYER, dict(zero=("roll",)), 91520)
    native(
        PLAYER,
        dict(choice=("escape",), account="I leave the captured room in the same square."),
        91524,
    )
    canon = state(game)
    result = records(canon)[0]
    assert result.escaped and result.rolls[1].no_heat and result.rolls[1].roll.heat == 0
    assert result.rolls[0].roll.heat == 1 and game.dice.calls == 2
    assert not is_helpless(canon, girl, captor)
    body = next(x for x in canon.placements if x.actor == girl)
    assert body.custody is None and body.frame_cell == original_placement.frame_cell


def test_captured_cell_scene_grants_a_real_shiv_and_clears_only_capture_helplessness(ledger):
    game, service, native, original, girl, captor, identity = begin_capture(ledger, (4, 5))
    with ledger.transaction() as c:
        separate = "other-helpless-source"
        changed = make_helpless(state(game), girl, captor, separate)
        game.event(c, ADMIN.user_id, separate, "synthetic.helpless", changed, event_id=separate)
    native(PLAYER, dict(heat="0"), 91530)
    pending = state(game)
    roll = records(pending)[0].current.roll
    assert roll.result == "mid" and not pending.held_items
    account = "I wait in the cell as they bring in a meal."
    with pytest.raises(WorkflowError, match="unavailable"):
        service.act(
            OTHER, "another-girl", identity, pending.revision, "mid", choice="cell", account=account
        )
    key = native(PLAYER, dict(choice=("cell",), account=account), 91534)
    ledger.engine.dispose()
    actual = state(game)
    receipt = service.act(
        PLAYER, key, identity, pending.revision, "mid", choice="cell", account=account
    )
    assert receipt["event"] == records(actual)[0].current.completed
    assert service.get(PLAYER, identity)["step"] == "roll"
    assert state(game) == actual and game.dice.calls == 1
    assert records(actual)[0].current.roll == roll
    assert is_helpless(actual, girl, captor)
    (condition,) = actual.helpless_conditions
    assert condition.source_events == (separate,)
    first_body = next(x for x in original.placements if x.actor == girl)
    body = next(x for x in actual.placements if x.actor == girl)
    assert body.custody == captor and body.frame_cell == first_body.frame_cell
    assert actual.sheets[girl.entity].assets == original.sheets[girl.entity].assets
    (shiv,) = actual.held_items
    with ledger.engine.connect() as c:
        assert prove_item(c, game, actual, shiv.id) == shiv
    assert shiv.holder == girl and shiv.weapon and shiv.source_event == receipt["event"]


def test_captured_low_requires_optional_approval_and_continues_the_same_person(
    ledger, tmp_path, monkeypatch
):
    from test_ancillary_creation import enable
    from test_harpy_actor_plays import begin, pass_tags
    from test_m2_game import Gateway, answer, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine import m3_ancillary as ancillary
    from girlframe.engine.m3_actor_bonds import depth
    from girlframe.services.m3_actor_plays import ActorPlayService

    game, service, native, original, girl, captor, identity = begin_capture(ledger, (1, 2))
    native(PLAYER, dict(heat="1"), 91600)
    held = state(game)
    original_roll = records(held)[0].current.roll
    assert original_roll.result == "low" and not service.get(ADMIN, identity)["can_stage_low"]
    with pytest.raises(WorkflowError, match="MODULE_DISABLED"):
        service.act(
            ADMIN,
            "optional-disabled",
            identity,
            held.revision,
            "low_review",
            choice="handler",
            account="Actual scene.",
            new_identity="New oath",
        )
    assert state(game) == held
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE, ancillary.CAPTURED_LOW))
    native(
        ADMIN,
        dict(
            choice=("handler",),
            account="The rebel has her in their custody.",
            new_identity="New oath",
        ),
        91604,
    )
    assert state(game).sheets["2"] == held.sheets["2"]
    ledger.engine.dispose()
    native(PLAYER, dict(choice=("REVOLUTIONARY IDEALIST",)), 91608)
    canon = state(game)
    captured = records(canon)[0].current
    converted = ancillary.find(canon, captured.ancillary)
    assert captured.roll == original_roll and converted.draft.original == girl
    assert converted.draft.handler == captor and converted.controller == PLAYER.user_id
    assert [x.name for x in converted.identities] == ["New oath"] and converted.heat == 1
    assert "2" not in canon.sheets and canon.career_archives[-1].ending == "rebel_ancillary"
    original_body = next(x for x in original.placements if x.actor == girl)
    parked = next(x for x in canon.parked_frames if x.owner == girl)
    assert (parked.frame_instance, parked.cell) == (
        original_body.frame_instance,
        original_body.frame_cell,
    )
    friend = current_ref(original, OTHER.user_id)
    assert depth(canon, converted.actor, friend) == depth(original, girl, friend)
    assert game.dice.calls == 1
    game.dice.faces = (4, 5)
    played = begin(
        ActorPlayService(game),
        converted.actor,
        context="I keep my head under the new Handler's pressure.",
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "vicious"), denied=("desperate",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The actual test GM rules on the chosen traits.",
    )
    assert game.inspect(PLAYER, played)["state"] == "complete" and game.dice.calls == 2
