"""Fictional phone powers use separate owners, private receipt and native effects."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import D6, prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_custom_strain import Slot
from girlframe.engine.m3_director_strain import RULE, Command, calls
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_director_strain import DirectorStrainService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def phone_scene(store, tmp_path, monkeypatch, extra=()):
    original, game = ready(store)
    policy = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(update={"subsystems": policy.subsystems | {"world"}})
        }
    )
    board = initial()
    world = WorldService(original.missions)
    world.initialize(
        ADMIN, "phone-map", state(game).revision, board.board, board.locations, board.gorgons[0]
    )
    director = ActorRef(kind="npc", entity="original-caller")
    roles = NpcRoleService(world)
    offer = roles.offer(
        ADMIN,
        "appoint-fictional-caller",
        state(game).revision,
        Npc(
            id=director.entity,
            name="The real Director",
            detail="Calls from her office.",
            jobs=("director",),
            cell=(0, 0),
            controller=OTHER.user_id,
        ),
    )
    roles.respond(OTHER, "join-fictional-office", offer["id"], state(game).revision, "accept")
    change(CastService(ActorService(original.missions)), OTHER, "join", director)
    with pytest.raises(WorkflowError, match="implementation and review"):
        DirectorStrainService(original).view(OTHER, 900, director)
    period = prepared(original, game)
    approved(store, game, tmp_path, monkeypatch, extra=(RULE, *extra))
    missions = MissionService(store)
    return StrainService(OffDutyService(missions), dice=D6(5)), game, period, director


def native_phone(strain, director, mode, number, **values):
    async def run():
        cast = CastService(ActorService(strain.missions))
        opening = current(OTHER.user_id, number)
        opening.channel_id = 900
        await opening.response.defer(ephemeral=True)
        await open_cast(opening, cast)
        role_menu = opening.edit_original_response.call_args.kwargs["view"]
        action = next(x for x, _ in role_menu.options if x == "phone:" + director.token)
        choose = current(OTHER.user_id, number + 1)
        await choose.response.defer(ephemeral=True)
        await role_menu.open_item(choose, action)
        modes = choose.edit_original_response.call_args.kwargs["view"]
        edit = current(OTHER.user_id, number + 2)
        await edit.response.defer(ephemeral=True)
        await modes.open_item(edit, mode)
        form = edit.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirm = current(OTHER.user_id, number + 3)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    asyncio.run(run())


def test_director_severity_and_event_are_native_distinct_powers(ledger, tmp_path, monkeypatch):
    strain, game, period, director = phone_scene(ledger, tmp_path, monkeypatch)
    service = DirectorStrainService(strain)
    requests = {x.track: x.id for x in state(game).strain.requests}
    strain.roll(ADMIN, "pre-call-budget-die", requests["budget"], 1, state(game).revision)
    before = state(game)
    account = "PRIVATE_DIRECTOR_ACCOUNT"
    command = Command(mode="severity", track="budget", severity="high", account=account)
    with pytest.raises(WorkflowError, match="original joined fictional Director"):
        service.call(ADMIN, "handler-cannot-call", 900, before.revision, director, command)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.call(OTHER, "stale-call", 900, before.revision - 1, director, command)
    ledger.safety(PLAYER, "pause-call", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.call(OTHER, "paused-call", 900, before.revision, director, command)
    ledger.safety(PLAYER, "resume-call", ledger.status(PLAYER)["revision"], pause=False)
    native_phone(
        strain, director, "severity", 39700, track=("budget",), severity=("high",), account=account
    )
    saved = service.call(OTHER, "39703", 900, before.revision, director, command)
    assert saved["effect"] is None and len(calls(state(game))) == 1
    assert state(game).strain.levels["budget"] == "high"
    assert state(game).strain.events == before.strain.events
    assert strain.work(ADMIN, requests["budget"])["body"]["severity"] == "low"

    native_phone(
        strain,
        director,
        "severity",
        39710,
        track=("rebellion",),
        severity=("high",),
        account=account,
    )
    row = strain.work(ADMIN, requests["rebellion"])
    assert row["revision"] == 2 and row["body"]["severity"] == "high"
    with pytest.raises(WorkflowError, match="STALE_WORK"):
        strain.roll(ADMIN, "old-rebellion", requests["rebellion"], 1, state(game).revision)
    assert strain.dice.calls == 1
    command = Command(
        mode="trigger",
        track="rebellion",
        severity="low",
        account=account,
        slot=Slot(track="rebellion", severity="low", face=1, column=2),
    )
    revision = state(game).revision
    native_phone(strain, director, "trigger", 39720, event=(command.target_rule,), account=account)
    record = service.call(OTHER, "39723", 900, revision, director, command)
    effect = record["effect"]
    assert effect and not state(game).refusal_bonuses
    assert len(calls(state(game))) == 3 and strain.dice.calls == 1
    effects = EffectService(strain)
    with pytest.raises(WorkflowError):
        effects.get(OTHER, effect)
    assert effects.get(ADMIN, effect)["off_duty_id"] == period
    receipt = effects.apply(
        ADMIN,
        "apply-phone-effect",
        effect,
        1,
        state(game).revision,
        Choice(rule_id=command.target_rule or "", account="Actual change to next disobedience"),
    )
    assert receipt["state"] == "resolved" and state(game).refusal_bonuses[-1].id == effect
    ledger.engine.dispose()
    assert service.receipt(ADMIN, record["id"]).command.account == account
    assert service.receipt(OTHER, record["id"]).effect == effect
    assert not any(x.task == "m3_director_strain_call" for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="original participants"):
        service.receipt(PLAYER, record["id"])

    async def read():
        inbox = InboxService(ledger)
        card = next(x for x in inbox.items(ADMIN) if x.identity == record["id"])
        click = current(ADMIN.user_id, 39730)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, card)
        assert "PRIVATE" in str(click.edit_original_response.call_args)

    asyncio.run(read())
    change(CastService(ActorService(strain.missions)), OTHER, "withdraw", director)
    with pytest.raises(WorkflowError, match="joined fictional Director"):
        service.call(OTHER, "call-after-withdrawal", 900, state(game).revision, director, command)
