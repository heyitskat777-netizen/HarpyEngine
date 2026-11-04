"""Actual Asset contests, human Core confirmation, restart and private native controls."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_gorgon_service import ready as npc_ready
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, start, state, tick
from test_mission_ui import current
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_combat import Contest, Exposure
from girlframe.engine.m3_world import update
from girlframe.services.onboarding import WorkflowError


def ready(store):
    svc, game = npc_ready(store)
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world, gorgons=(*canon.world.gorgons, gorgon("erratic", "rival"))
        )
        game.event(c, 1, "synthetic-rival-placement", "synthetic.world", canon)
    return svc, game


def selection(svc):
    data = svc.contests(ADMIN)
    first = next(x for x in data["attackers"] if x["ref"]["entity"] == "hunter")
    second = next(x for x in first["targets"] if x["ref"]["entity"] == "rival")
    return data, Contest(
        attacker=ActorRef.model_validate(first["ref"]),
        defender=ActorRef.model_validate(second["ref"]),
        attacking_assets=(first["assets"][0]["id"],),
        defending_assets=(second["assets"][0]["id"],),
        attacker_sha256=first["source_sha256"],
        defender_sha256=second["source_sha256"],
        winner="attacker",
        losing_asset=second["assets"][0]["id"],
        approach="direct",
        account="PRIVATE_ACTUAL_CONTEST",
        trigger_confirmed=True,
    )


def contest(svc, key=None, *, data=None, choice=None):
    if data is None:
        data, choice = selection(svc)
    return svc.contest(ADMIN, key or str(uuid4()), data["game_revision"], choice)


def exposure(svc):
    data = svc.cores(ADMIN)
    actor = next(x for x in data["gorgons"] if x["ref"]["entity"] == "rival")
    return data, Exposure(
        actor=ActorRef.model_validate(actor["ref"]),
        source_sha256=actor["source_sha256"],
        account="PRIVATE_ACTUAL_CORE_WEAKNESS_OCCURRED",
        weakness_confirmed=True,
    )


def test_actual_contest_and_core_confirmation_are_atomic_private_and_rebuildable(
    ledger,
):
    svc, game = ready(ledger)
    assert not svc.cores(ADMIN)["gorgons"]
    before = state(game)
    data, pick = selection(svc)
    result = contest(svc, "actual-contest", data=data, choice=pick)
    assert contest(svc, "actual-contest", data=data, choice=pick) == result
    canon = state(game)
    rival = canon.world.gorgons[-1]
    assert len(rival.assets) == 3 and rival.destroyed_assets[0].id == "rival:0"
    assert rival.alive and not rival.exposed and canon.sheets == before.sheets
    assert canon.world.gorgons[1] == before.world.gorgons[1]
    data, choice = exposure(svc)
    core = svc.expose(ADMIN, "actual-core", data["game_revision"], choice)
    assert svc.expose(ADMIN, "actual-core", data["game_revision"], choice) == core
    after = state(game)
    assert after.world.gorgons[-1].exposed and after.world.gorgons[-1].alive
    assert not svc.cores(ADMIN)["gorgons"] and game.dice.calls == 0
    assert after.sheets == before.sheets and after.world.npcs == before.world.npcs
    with ledger.engine.connect() as c:
        events = list(
            c.scalars(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.kind.in_(("m3.gorgon_assets_contested", "m3.gorgon_core_exposed"))
                )
            )
        )
        assert len(events) == 2 and "PRIVATE" not in str(events) and "rival" not in str(events)
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == after


def test_world_reader_cannot_obtain_private_core_plans_or_submit_anothers_contest(ledger):
    svc, game = ready(ledger)
    data, pick = selection(svc)
    for operation in (
        lambda: svc.contests(PLAYER),
        lambda: svc.cores(PLAYER),
        lambda: svc.contest(PLAYER, "not-world-owner", data["game_revision"], pick),
    ):
        with pytest.raises(WorkflowError):
            operation()
    assert not state(game).world.gorgons[-1].destroyed_assets
    contest(svc)
    data, pick = exposure(svc)
    with pytest.raises(WorkflowError):
        svc.expose(PLAYER, "not-your-core", data["game_revision"], pick)
    public = svc.world.get(PLAYER)
    assert "PRIVATE" not in str(public) and "weakness" not in str(public)


def test_pause_pending_play_and_released_permissions_guard_both_new_commands(ledger):
    svc, game = ready(ledger)
    data, pick = selection(svc)
    ledger.safety(PLAYER, "pause-contest", ledger.status(PLAYER)["revision"], pause=True)
    assert svc.contests(ADMIN) == data
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        contest(svc, data=data, choice=pick)
    ledger.safety(PLAYER, "resume-contest", ledger.status(PLAYER)["revision"], pause=False)
    action = start(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        contest(svc, data=data, choice=pick)
    game.abort(ADMIN, "abort-before-contest", action)
    with pytest.raises(WorkflowError, match="restore chat"):
        contest(svc, data=data, choice=pick)
    tick(GameWorker(game), Gateway(), 5)
    contest(svc, data=data, choice=pick)
    data, pick = exposure(svc)
    ledger.safety(PLAYER, "pause-core", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.expose(ADMIN, "paused-core", data["game_revision"], pick)
    assert not state(game).world.gorgons[-1].exposed


@pytest.mark.parametrize("operation", ("contest", "core"))
def test_injected_failure_after_event_preserves_all_assets_and_history_before_retry(
    ledger, monkeypatch, operation
):
    svc, game = ready(ledger)
    if operation == "core":
        contest(svc)
        data, pick = exposure(svc)

        def submit():
            return svc.expose(ADMIN, "retry-combat", data["game_revision"], pick)
    else:
        data, pick = selection(svc)

        def submit():
            return contest(svc, "retry-combat", data=data, choice=pick)

    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after actual combat event")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        submit()
    assert state(game) == before
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.commands.c.interaction_key).where(
                t.commands.c.interaction_key == "retry-combat"
            )
        )
    monkeypatch.setattr(svc.game, "event", original)
    assert submit()


@pytest.mark.parametrize("operation", ("contest", "core"))
def test_concurrent_commands_commit_one_consequence_and_stale_forms_cannot_destroy_another_asset(
    ledger, operation
):
    svc, game = ready(ledger)
    if operation == "core":
        contest(svc)
        data, pick = exposure(svc)

        def submit(key):
            return svc.expose(ADMIN, key, data["game_revision"], pick)
    else:
        data, pick = selection(svc)

        def submit(key):
            return contest(svc, key, data=data, choice=pick)

    def attempt(key):
        try:
            return submit(key)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("first-actual", "second-actual")))
    assert sum(x is not None for x in outcomes) == 1
    assert len(state(game).world.gorgons[-1].destroyed_assets) == 1
    with pytest.raises(WorkflowError, match="STALE_COMBAT"):
        submit("late-actual")
    saved = state(game)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        submit("first-actual")
    assert state(game) == saved


def test_legacy_world_json_gets_empty_history_and_actual_backup_keeps_destroyed_assets(
    ledger, tmp_path
):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m3_gorgon import GorgonService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import OnboardingStore

    svc, game = ready(ledger)
    legacy = state(game).model_dump(mode="json")
    for actor in legacy["world"]["gorgons"]:
        del actor["destroyed_assets"]
    assert all(
        not x.destroyed_assets
        for x in GameState.model_validate_json(json.dumps(legacy)).world.gorgons
    )
    contest(svc)
    data, pick = exposure(svc)
    svc.expose(ADMIN, "actual-exposure", data["game_revision"], pick)
    original = state(game)
    destination = tmp_path / "gorgon-combat.db"
    copy_database(Path(ledger.engine.url.database), destination)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        restored = GorgonService(
            WorldService(MissionService(OnboardingStore(engine, ledger.policy)))
        )
        assert state(restored.game) == original
        assert restored.game.rebuild() > 0 and state(restored.game) == original
    finally:
        engine.dispose()


def test_native_contest_and_core_controls_do_not_commit_until_actual_owned_confirmation(ledger):
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_combat import open_contest, open_exposure

    svc, game = ready(ledger)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_contest(interaction, svc)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        token = next(
            x["token"] for x in svc.contests(ADMIN)["attackers"] if x["ref"]["entity"] == "hunter"
        )
        await picker.open_item(interaction, token)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        target_token = next(key for key, label in picker.options if label == "rival")
        await picker.open_item(interaction, target_token)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(2))
        fields = {x.key: x for x in form.fields}
        form.values.update(
            attacking_assets=("hunter:0",),
            defending_assets=("rival:0",),
            winner=("attacker",),
            approach=("direct",),
            account="PRIVATE_ACTUAL_ASSET_CONTEST",
            confirm=("yes",),
        )
        assert not state(game).world.gorgons[-1].destroyed_assets
        wrong = next(
            key for key, label in fields["losing_asset"].options if label == "Attacker: Asset 0"
        )
        form.values["losing_asset"] = (wrong,)
        await form.confirm.callback(current(1, 7041))
        assert not form.completed and not state(game).world.gorgons[-1].destroyed_assets
        correct = next(
            key for key, label in fields["losing_asset"].options if label == "Defender: Asset 0"
        )
        form.values["losing_asset"] = (correct,)
        await form.confirm.callback(current(1, 7042))
        assert len(state(game).world.gorgons[-1].destroyed_assets) == 1
        assert not state(game).world.gorgons[-1].exposed
        await open_exposure(interaction, svc)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(interaction, picker.options[0][0])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(account="PRIVATE_ACTUAL_CORE_WEAKNESS_OCCURRED", confirm=("yes",))
        await form.confirm.callback(current(1, 7043))
        assert state(game).world.gorgons[-1].exposed and state(game).world.gorgons[-1].alive
        assert game.dice.calls == 0

    asyncio.run(run())


def test_same_asset_id_on_different_gorgons_has_distinct_owned_native_selector_tokens(ledger):
    from girlframe.discord_adapter.m3_gorgon_combat import open_contest

    svc, game = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        changed = []
        for actor in canon.world.gorgons:
            if actor.id in ("hunter", "rival"):
                actor = actor.model_copy(
                    update={
                        "assets": (
                            actor.assets[0].model_copy(update={"id": "shared"}),
                            *actor.assets[1:],
                        ),
                        "core_plan": actor.core_plan.model_copy(update={"assets": ("shared",)}),
                    }
                )
            changed.append(actor)
        canon.world = update(canon.world, gorgons=tuple(changed))
        game.event(c, 1, "synthetic-shared-asset-ids", "synthetic.world", canon)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_contest(interaction, svc)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        token = next(
            x["token"] for x in svc.contests(ADMIN)["attackers"] if x["ref"]["entity"] == "hunter"
        )
        await menu.open_item(interaction, token)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(interaction, next(k for k, v in menu.options if v == "rival"))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        options = next(x.options for x in form.fields if x.key == "losing_asset")
        assert len({key for key, label in options}) == len(options)
        assert all(len(key) <= 100 for key, label in options)
        loser = next(key for key, label in options if label == "Defender: Asset 0")
        form.values.update(
            attacking_assets=("shared",),
            defending_assets=("shared",),
            winner=("attacker",),
            losing_asset=(loser,),
            approach=("direct",),
            account="Actual contest with distinct owned Assets",
            confirm=("yes",),
        )
        await form.confirm.callback(current(1, 7044))
        assert state(game).world.gorgons[-1].destroyed_assets[0].id == "shared"
        assert any(x.id == "shared" for x in state(game).world.gorgons[1].assets)

    asyncio.run(run())
