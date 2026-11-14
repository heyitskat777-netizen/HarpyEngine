"""Atomic actual Gorgon/NPC attacks; no borrowed Girl, secret leaks or second death."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, start, state, tick
from test_mission_ui import current
from test_world import gorgon
from test_world_service import ready as world_ready
from test_world_service import transfer_npc

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_gorgon import NpcAttack
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.onboarding import WorkflowError


def ready(store):
    world, game = world_ready(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    world.npc(
        ADMIN,
        "actual-npc-introduction",
        state(game).revision,
        Npc(
            id="npc",
            name="PRIVATE_NPC_NAME",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_NPC_DETAIL",
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, PLAYER, "npc")
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=(*canon.world.gorgons, gorgon("erratic", "hunter", name="PRIVATE_HUNTER")),
        )
        game.event(c, 1, "synthetic-gorgon-placement", "synthetic.world_setup", canon)
    return GorgonService(world), game


def selection(service):
    data = service.preview(ADMIN)
    first = data["attackers"][0]
    target = first["targets"][0]
    attack = NpcAttack(
        attacker=ActorRef.model_validate(first["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        assets=(first["assets"][0]["id"],),
        attacker_sha256=first["source_sha256"],
        target_sha256=target["source_sha256"],
        account="PRIVATE_ATTACK_AND_ACTUAL_REACH",
        trigger_confirmed=True,
    )
    return data, attack


def apply(service, key=None, *, data=None, attack=None, viewer=ADMIN):
    fresh, choice = selection(service) if data is None else (data, attack)
    return service.attack(viewer, key or str(uuid4()), fresh["game_revision"], choice)


def test_actual_owned_npc_death_is_atomic_private_replayable_and_survives_rebuild(ledger):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    before = state(game)
    result = apply(svc, "actual-attack", data=data, attack=attack)
    assert apply(svc, "actual-attack", data=data, attack=attack) == result
    after = state(game)
    assert not after.world.npcs[0].alive
    assert after.sheets == before.sheets and after.bonds == before.bonds
    assert after.world.gorgons == before.world.gorgons and game.dice.calls == 0
    assert not svc.preview(ADMIN)["attackers"]
    history = svc.history(ADMIN)
    assert history == [{"id": result["id"], "attack": attack.model_dump(mode="json")}]
    with ledger.engine.connect() as c:
        event = c.execute(sa.select(t.events).where(t.events.c.id == result["id"])).mappings().one()
        assert event["kind"] == "m3.gorgon_attacked_npc"
        assert "PRIVATE" not in event["payload_json"] and "hunter" not in event["payload_json"]
        outcome = c.scalar(
            sa.select(t.commands.c.outcome_json).where(
                t.commands.c.interaction_key == "actual-attack"
            )
        )
        assert json.loads(outcome) == result and "PRIVATE" not in outcome
        for outbox in (t.outbox, t.m2["m2_outbox"]):
            assert "PRIVATE_ATTACK" not in str(list(c.execute(sa.select(outbox)).mappings()))
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == after
    assert svc.history(ADMIN) == history
    assert apply(svc, "actual-attack", data=data, attack=attack) == result


@pytest.mark.parametrize("viewer", (PLAYER, OTHER))
def test_another_human_cannot_view_or_control_gorgon_through_their_own_npc(ledger, viewer):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    before = state(game)
    for operation in (
        lambda: svc.preview(viewer),
        lambda: svc.history(viewer),
        lambda: apply(svc, viewer=viewer, data=data, attack=attack),
    ):
        with pytest.raises(WorkflowError):
            operation()
    assert state(game) == before
    assert "PRIVATE_HUNTER" not in str(svc.world.get(PLAYER))
    assert "PRIVATE_ATTACK" not in str(game.sheet(PLAYER))


def test_safety_pending_play_and_unrestored_chat_block_attack_without_any_death(ledger):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    before = state(game)
    ledger.safety(PLAYER, "pause-attack", ledger.status(PLAYER)["revision"], pause=True)
    assert svc.preview(ADMIN) == data
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        apply(svc, data=data, attack=attack)
    ledger.safety(PLAYER, "resume-attack", ledger.status(PLAYER)["revision"], pause=False)
    action = start(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        apply(svc, data=data, attack=attack)
    game.abort(ADMIN, "abort-before-attack", action)
    with pytest.raises(WorkflowError, match="restore chat"):
        apply(svc, data=data, attack=attack)
    tick(GameWorker(game), Gateway(), 5)
    assert state(game) == before
    apply(svc, data=data, attack=attack)
    assert not state(game).world.npcs[0].alive


def test_scope_revocation_also_blocks_cached_replay_without_new_effects(ledger):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    apply(svc, "committed-before-revoke", data=data, attack=attack)
    after = state(game)
    policy = ledger.policy
    for subsystem in ("world", "plays"):
        ledger.policy = policy.model_copy(
            update={
                "m3_approval": policy.m3_approval.model_copy(
                    update={"subsystems": policy.m3_approval.subsystems - {subsystem}}
                )
            }
        )
        with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
            apply(svc, "committed-before-revoke", data=data, attack=attack)
    assert state(game) == after


def test_stale_target_world_and_conflicting_command_cannot_redirect_an_attack(ledger):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    transfer_npc(svc.world, PLAYER, OTHER, "npc")
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE_ATTACK"):
        apply(svc, data=data, attack=attack)
    assert state(game) == before
    data, attack = selection(svc)
    apply(svc, "actual-attack", data=data, attack=attack)
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        apply(
            svc, "actual-attack", data=data, attack=attack.model_copy(update={"account": "changed"})
        )


def test_failure_after_event_rolls_back_death_history_fact_and_command_before_retry(
    ledger, monkeypatch
):
    svc, game = ready(ledger)
    data, attack = selection(svc)
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after attack event")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        apply(svc, "atomic-retry", data=data, attack=attack)
    assert state(game) == before and not svc.history(ADMIN)
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.commands.c.interaction_key).where(
                t.commands.c.interaction_key == "atomic-retry"
            )
        )
        assert not c.scalar(
            sa.select(t.events.c.id).where(t.events.c.kind == "m3.gorgon_attacked_npc")
        )
    monkeypatch.setattr(svc.game, "event", original)
    assert apply(svc, "atomic-retry", data=data, attack=attack)


def test_concurrent_different_keys_commit_exactly_one_actual_death(ledger):
    svc, game = ready(ledger)
    data, attack = selection(svc)

    def attempt(key):
        try:
            return apply(svc, key, data=data, attack=attack)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("first", "second")))
    assert sum(x is not None for x in results) == 1
    assert len(svc.history(ADMIN)) == 1 and not state(game).world.npcs[0].alive


def test_actual_backup_preserves_private_attack_source_and_replay(ledger, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import OnboardingStore

    svc, game = ready(ledger)
    data, attack = selection(svc)
    result = apply(svc, "backed-up-attack", data=data, attack=attack)
    target = tmp_path / "attack-backup.db"
    copy_database(Path(ledger.engine.url.database), target)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(target)))
    try:
        restored = GorgonService(
            WorldService(MissionService(OnboardingStore(engine, ledger.policy)))
        )
        assert restored.history(ADMIN) == svc.history(ADMIN)
        assert apply(restored, "backed-up-attack", data=data, attack=attack) == result
        assert state(restored.game) == state(game)
    finally:
        engine.dispose()


def test_other_campaign_cannot_read_or_apply_an_actual_attack_from_this_campaign(ledger):
    from girlframe.services.handler_setup import HandlerService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import OnboardingStore
    from girlframe.services.read_only_bot import GuildViewer

    svc, game = ready(ledger)
    data, attack = selection(svc)
    policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    store = OnboardingStore(ledger.engine, policy)
    viewer = GuildViewer(1, 201, True, True)
    store.join(viewer, "join-other")
    HandlerService(store).appoint(viewer, "appoint-other", 0, 1)
    world = WorldService(MissionService(store))
    with store.transaction() as c:
        from girlframe.engine.m2 import GameState

        world.game.event(c, 1, "synthetic-other-state", "synthetic.state", GameState(handler=1))
    other = GorgonService(world)
    before = state(game)
    assert not other.preview(viewer)["attackers"] and not other.history(viewer)
    with pytest.raises(WorkflowError):
        other.attack(viewer, "foreign-attack", data["game_revision"], attack)
    assert state(game) == before and not svc.history(ADMIN)


def test_known_rolled_abort_after_restoring_chat_still_blocks_world_attack(ledger):
    from test_actor_play_service import begin
    from test_actor_play_service import ready as actor_ready

    from girlframe.services.m3_world import WorldService

    plays, game, cast, ref, director = actor_ready(ledger)
    svc = GorgonService(WorldService(cast.actors.missions))
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world, gorgons=(*canon.world.gorgons, gorgon("erratic", "hunter"))
        )
        game.event(c, 1, "synthetic-attack-setup", "synthetic.world", canon)
    action = begin(plays, ref)
    tick(GameWorker(game), Gateway())
    assert game.dice.calls == 1
    game.abort(ADMIN, "known-attack-abort", action)
    tick(GameWorker(game), Gateway(), 5)
    before = state(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        apply(svc)
    assert state(game) == before and game.dice.calls == 1


def test_world_facilitator_can_control_actual_gorgon_while_handler_is_under_director_rules(ledger):
    svc, game = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                *canon.world.npcs,
                Npc(
                    id="director",
                    name="Director",
                    jobs=("director",),
                    detail="Actual presence",
                    controller=3,
                    cell=(0, 0),
                ),
            ),
        )
        canon = enter(
            canon,
            1,
            "director",
            "synthetic-presence-event",
            ("Afraid", "Defiant"),
            "synthetic-work",
        )
        game.event(c, 1, "synthetic-presence", "synthetic.director", canon)
    before = state(game)
    apply(svc)
    after = state(game)
    assert after.director_contexts == before.director_contexts
    assert after.handler_heat == before.handler_heat and after.sheets == before.sheets
    assert not after.world.npcs[0].alive and after.world.npcs[-1].alive
    with pytest.raises(WorkflowError):
        svc.preview(OTHER)


def test_native_world_attack_dropdown_is_private_owned_and_requires_explicit_confirmation(ledger):
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon import open_gorgon_attack
    from girlframe.discord_adapter.m3_punishments import Picker
    from girlframe.discord_adapter.m3_world import open_world

    svc, game = ready(ledger)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_world(interaction, svc.world)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        assert "gorgon_attack" in dict(menu.options)
        await menu.open_item(interaction, "gorgon_attack")
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker) and len(picker.options) == 1
        assert not await picker.interaction_check(current(2))
        assert state(game).world.npcs[0].alive
        await picker.open_item(interaction, picker.options[0][0])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        fields = {x.key: x for x in form.fields}
        assert fields["target"].options and fields["assets"].options
        assert not await form.interaction_check(current(2))
        assert state(game).world.npcs[0].alive
        form.values.update(
            target=(fields["target"].options[0][0],),
            assets=("hunter:0",),
            account="Actual reachable Attack",
            confirm=("yes",),
        )
        await form.confirm.callback(current(1, 90123))
        assert not state(game).world.npcs[0].alive and len(svc.history(ADMIN)) == 1
        await open_gorgon_attack(interaction, svc)
        assert "No eligible" in interaction.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())
