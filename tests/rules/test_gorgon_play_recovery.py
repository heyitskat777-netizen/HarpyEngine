"""Mixed-role root recovery preserves the actual Gorgon, human choices and child dice."""

import asyncio
from uuid import uuid4

import pytest
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def interrupt(game, worker, gateway, root):
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    return next(x for x in RecoveryService(game).saved(ADMIN) if x["id"] == root)


def finish_damage(game, action):
    answer(game, PLAYER, "gorgon_defend", options=("damage",), text="Take actual source damage")
    with game.store.engine.connect() as c:
        row = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_damage_asset")
    asset = game.decision(PLAYER, row["id"])["detail"]["assets"][0]["id"]
    answer(game, PLAYER, "gorgon_damage_asset", options=(asset,), text="The actual damaged Asset")


def new_declaration(game, old):
    service = GorgonPlayService(game)
    data = service.preview(ADMIN, 900)
    actor = next(x for x in data["actors"] if x["ref"] == old.actor.model_dump(mode="json"))
    target = next(x for x in data["actors"] if x["ref"] == old.target.model_dump(mode="json"))
    declaration = old.model_copy(
        update=dict(actor_sha256=actor["source_sha256"], target_sha256=target["source_sha256"])
    )
    return service.begin(ADMIN, str(uuid4()), 900, data["revision"], declaration)["action_id"]


@pytest.mark.parametrize("director", [False, True])
def test_actual_mixed_gorgon_response_resumes_original_owner_without_false_cancel(ledger, director):
    game, worker, gateway, root, _ = gorgon_source(ledger, npc=True, director=director)
    before = state(game)
    saved = interrupt(game, worker, gateway, root)
    service = RecoveryService(game)
    assert not saved["rolled"] and not saved["cancellable"]
    with pytest.raises(WorkflowError, match="discarded"):
        service.recover(
            ADMIN, "cannot-discard-started-gorgon", root, saved["revision"], cancel=True
        )
    with pytest.raises(WorkflowError, match="root actor"):
        service.recover(PLAYER, "wrong-gorgon-controller", root, saved["revision"])
    result = service.recover(ADMIN, "recover-original-gorgon", root, saved["revision"])
    assert service.recover(ADMIN, "recover-original-gorgon", root, saved["revision"]) == result
    tick(worker, gateway, 3)
    assert state(game) == before and game.dice.calls == 0
    assert [x["kind"] for x in game.choices(PLAYER)] == ["gorgon_defend"]
    finish_damage(game, root)
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "complete"
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_gorgon_child_roll_and_prior_answers_survive_whole_chain_recovery(ledger):
    game, worker, gateway, root, _ = gorgon_source(ledger)
    answer(game, PLAYER, "gorgon_defend", options=("play",), text="My actual original response")
    game.dice.faces = (2, 3)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            piloting=True,
            parent=root,
            context="Actual original avoidance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    answer(game, PLAYER, "tag_window", options=("pass",))
    receipt = game.inspect(PLAYER, child)["receipt"]
    saved = interrupt(game, worker, gateway, root)
    assert saved["rolled"] and saved["descendants"] == 1
    RecoveryService(game).recover(ADMIN, "restore-actual-known-child", root, saved["revision"])
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, child)["receipt"] == receipt and game.dice.calls == 1
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual original response is enough")
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == game.action(c, child)["state"] == "complete"
    assert game.dice.calls == 1


def test_unstarted_actual_gorgon_cancels_under_safety_pause_without_resource_refund(ledger):
    game, worker, gateway, first, declaration = gorgon_source(ledger)
    finish_damage(game, first)
    tick(worker, gateway, 4)
    root = new_declaration(game, declaration)
    before = state(game)
    saved = interrupt(game, worker, gateway, root)
    assert saved["cancellable"] and not saved["rolled"]
    ledger.safety(PLAYER, "pause-unstarted-gorgon", ledger.status(PLAYER)["revision"], pause=True)
    RecoveryService(game).recover(
        ADMIN, "cancel-real-unstarted-gorgon", root, saved["revision"], cancel=True
    )
    assert state(game) == before and game.dice.calls == 0
    assert not RecoveryService(game).saved(ADMIN)


def test_changed_actual_scene_role_cannot_inherit_original_gorgon_recovery(ledger):
    game, worker, gateway, root, _ = gorgon_source(ledger)
    saved = interrupt(game, worker, gateway, root)
    with ledger.transaction() as c:
        canon = state(game)
        cast = next(x for x in canon.scene_casts if x.channel == 900)
        roles = tuple(
            x.model_copy(update=dict(source_event="unproved-rejoined-role"))
            if x.actor.kind == "pilot" and x.actor.entity == "2"
            else x
            for x in cast.roles
        )
        canon.scene_casts = [
            x.model_copy(update=dict(roles=roles, revision=x.revision + 1))
            if x.id == cast.id
            else x
            for x in canon.scene_casts
        ]
        game.event(c, 1, str(uuid4()), "synthetic.changed_actual_source_role", canon)
    with pytest.raises(WorkflowError, match="proved original"):
        RecoveryService(game).recover(
            ADMIN, "cannot-replace-original-role", root, saved["revision"]
        )
    assert game.dice.calls == 0


def test_native_actual_gorgon_declaration_starts_only_after_owned_confirmation(ledger):
    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play

    game, worker, gateway, first, _ = gorgon_source(ledger)
    finish_damage(game, first)
    tick(worker, gateway, 4)

    async def run():
        interaction = current(1, 93001)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_gorgon_play(interaction, game)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(2))
        own = form.fields[0].options[0][0]
        next_interaction = current(1, 93002)
        await next_interaction.response.defer(ephemeral=True)
        await form.submit_action(next_interaction, dict(actor=(own,), play=("attack",)))
        details = next_interaction.edit_original_response.call_args.kwargs["view"]
        data = GorgonPlayService(game).preview(ADMIN, 900)
        victim = next(
            x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
        )
        asset_field = next(x for x in details.fields if x.key == "assets")
        details.values.update(
            target=(victim["token"],),
            assets=(asset_field.options[0][0],),
            account="Actual physical native source declaration",
            reach=("confirmed",),
        )
        final = current(1, 93003)
        await details.confirm.callback(final)
        with ledger.engine.connect() as c:
            lock = game.lock(c, 900)
            action = game.action(c, lock["action_id"])
            assert action["state"] == "acquiring"
            assert action["data"]["receipt"] is None
            assert (
                action["data"]["gorgon_play"]["declaration"]["account"] == details.values["account"]
            )
        assert game.dice.calls == 0

    asyncio.run(run())


def test_actual_gorgon_source_table_cannot_be_rewritten_by_action_body_alone(ledger):
    game, _, _, root, _ = gorgon_source(ledger)
    with ledger.transaction() as c:
        action = game.action(c, root)
        action["data"]["participants"].append(999)
        game.save_action(c, action)
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="human table"):
        GorgonPlayService(game).source(c, game.action(c, root))
    assert game.dice.calls == 0


def test_legacy_world_harpy_without_factual_runtime_rejects_before_new_chat_lock(ledger):
    game, worker, gateway, first, old = gorgon_source(ledger, harpy=True)
    finish_damage(game, first)
    tick(worker, gateway, 4)
    with ledger.transaction() as c:
        canon = state(game)
        canon.native_harpies = []
        game.event(c, 1, str(uuid4()), "synthetic.legacy_harpy_without_runtime", canon)
    service = GorgonPlayService(game)
    data = service.preview(ADMIN, 900)
    actual = next(x for x in data["actors"] if x["ref"] == old.actor.model_dump(mode="json"))
    victim = next(x for x in data["actors"] if x["ref"]["entity"] == "actual-pitted-harpy")
    declaration = Declaration(
        kind="attack",
        actor=old.actor,
        actor_sha256=actual["source_sha256"],
        target=ActorRef.model_validate(victim["ref"]),
        target_sha256=victim["source_sha256"],
        assets=old.assets,
        account="An actual raw-world Harpy needs factual setup before this Attack",
        reach_confirmed=True,
    )
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="factual runtime"):
        service.begin(ADMIN, str(uuid4()), 900, data["revision"], declaration)
    with ledger.engine.connect() as c:
        lock = game.lock(c, 900)
        assert lock["action_id"] == first and lock["state"] == "released"
    assert state(game).model_dump_json() == before and game.dice.calls == 0


def test_gorgon_cannot_silently_skip_actual_dormant_counter_cost_before_lock(ledger):
    from girlframe.database import tables as t

    with pytest.raises(WorkflowError, match="Dormant awakening cost"):
        gorgon_source(ledger, target="opposing-gorgon", opposing=True, opposing_class="dormant")
    with ledger.engine.connect() as c:
        assert not list(c.execute(t.m2["m2_actions"].select()))
        assert not list(c.execute(t.m2["m2_locks"].select()))
        assert not list(c.execute(t.m2["m2_receipts"].select()))
