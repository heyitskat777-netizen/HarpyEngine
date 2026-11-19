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
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_captured import RULE, records
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_captured import CapturedService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError


def test_captured_high_erases_original_identity_and_next_roll_cannot_spend_heat(ledger):
    world, game = ready(ledger)
    game.dice.faces = (6, 6)
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
    original_placement = next(x for x in original.placements if x.actor == girl)
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

        asyncio.run(submit_form(viewer, route, values, number))

    native(PLAYER, dict(choice=("accept",)), 91504)
    assert is_helpless(state(game), girl, captor)
    assert next(x for x in state(game).placements if x.actor == girl).custody == captor
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
        service.get(OTHER, capture.id)
    native(
        ADMIN,
        dict(choice=("handler",), account="The original Rebel Handler sets the punishment scene."),
        91512,
    )
    erased = original.sheets["2"].identities[0].id
    native(PLAYER, dict(choice=(erased,)), 91516)
    assert all(x.id != erased for x in state(game).sheets["2"].identities)
    with pytest.raises(WorkflowError, match="permitted Heat"):
        service.act(
            PLAYER, "illegal-followup-heat", capture.id, state(game).revision, "roll", heat=1
        )
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
