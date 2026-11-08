"""Real original rebirth retention then actual native book start, with no account Pilot proxy."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from test_cast_service import change
from test_dive import threshold_source
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_void_keep import keep
from test_void_service import five_no, respond

from girlframe.discord_adapter.m3_mockingbird_plays import open_request
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import SEX as SEX_RULE
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_void import VoidService


def test_actual_retained_sex_native_start_and_owned_patient_effect_use_one_harpy_receipt(
    ledger, monkeypatch
):
    game, worker, gateway, parent, work = threshold_source(ledger, girl="MOCKINGBIRD")
    keep(game, worker, gateway, parent, work, controlled=False)
    service = VoidService(ledger)
    five_no(service, work)
    view = service.get(PLAYER, work)
    package = view["rebirth_choice"] | dict(
        retained_plays=[SEX_RULE],
        account="Actual original player retains the actual owned Sex rule",
    )
    respond(
        service, work, "save_rebirth", dict(choice=package, account="Actual chosen retained rule")
    )
    respond(
        service, work, "rebirth", dict(choice=package, account="Actual same-person Harpy birth")
    )
    tick(worker, gateway, 8)
    body = state(game).harpy_states[-1]
    actor = ActorRef(kind="external_pilot", entity=body.id)
    assert SEX_RULE in body.plays and "2" not in state(game).sheets
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    change(CastService(ActorService(MissionService(ledger))), PLAYER, "join", actor)
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    assert plays.sex_ready()
    book = plays.MockingbirdService(game)
    target = current_ref(state(game), 3)
    trigger = book.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        SEX,
        (target,),
        "Actual source interaction by this original Harpy",
    )
    book.attest(OTHER, str(uuid4()), trigger["id"], target, True)
    original_calls = game.dice.calls
    game.dice.faces = (6, 6)

    async def start():
        interaction = current(2, 961001)
        await interaction.response.defer(ephemeral=True)
        await open_request(interaction, book, trigger["id"], continue_source=True)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 961002))
        form.values.update(heat=("0",), identity=(), gain=("0",))
        await form.confirm.callback(current(2, 961003))
        assert form.completed

    asyncio.run(start())
    with ledger.engine.connect() as c:
        lock = game.lock(c, 900)
        action = game.action(c, lock["action_id"])
        assert action["data"]["actor_basic"]["ref"] == actor.model_dump(mode="json")
        identity = action["id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    asset = next(x for x in state(game).sheets["3"].assets if not x.void)
    answer(game, PLAYER, "mockingbird_sex_infect", fields={"asset": asset.id})
    answer(game, OTHER, "mockingbird_sex_rewrite", text="Actual other original person's alteration")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == original_calls + 1 and "2" not in state(game).sheets
