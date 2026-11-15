"""Real original rebirth retention then actual native book start, with no account Pilot proxy."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from harpy_sin_scenario import place_sin_recipient
from test_cast_service import change
from test_dive import threshold_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_void_keep import keep
from test_void_service import five_no, respond

from girlframe.discord_adapter.m3_mockingbird_plays import open_request
from girlframe.engine import m3_harpy_bond_void as sin
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import SEX as SEX_RULE
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService
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
    place_sin_recipient(game, OTHER, ADMIN)
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
    receipt = game.inspect(PLAYER, identity)["receipt"]
    asset = next(x for x in state(game).sheets["3"].assets if not x.void)
    answer(game, PLAYER, "mockingbird_sex_infect", fields={"asset": asset.id})
    answer(game, OTHER, "mockingbird_sex_rewrite", text="Actual other original person's alteration")
    effect = next(x for x in sin.cases(state(game)) if x.source_action == identity)
    assert effect.harpy == actor and effect.actor == target and effect.phase == "rewrite"
    assert effect.controller == OTHER.user_id
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).void
    row = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_bond_void")
    view = HarpyBondVoidService(game).view(OTHER, effect.id)
    selected = next(x["id"] for x in view["assets"] if x["family"] == "frame")
    owned = ChoiceAnswer(
        options=(selected,), text="The affected original Girl chooses the separate Sin alteration"
    )
    result = game.respond(OTHER, "retained-intimacy-owned-sin", row["id"], row["revision"], owned)
    assert (
        game.respond(OTHER, "retained-intimacy-owned-sin", row["id"], row["revision"], owned)
        == result
    )
    actual = state(game)
    assert sin.get(actual, effect.id).phase == "complete"
    assert len([x for x in sin.cases(actual) if x.source_action == identity]) == 1
    assert game.inspect(PLAYER, identity)["receipt"] == receipt
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == original_calls + 1 and "2" not in state(game).sheets
