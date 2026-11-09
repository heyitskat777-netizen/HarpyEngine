"""Bounded original AM/NPC discovery uses the real source, roll and owned outcomes."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_am import open_choice
from girlframe.engine import m3_am as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def rolled(store, tmp_path, monkeypatch, faces, *, handler_present=False, source_inbox=False):
    _, game = service(store, girl="AM", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        if handler_present:
            from girlframe.engine.m3_handler_consequences import active_handler

            actual.facts.append(
                dict(
                    kind="recorded_handler_recovery_position",
                    actor=active_handler(actual).model_dump_json(),
                    cell=json.dumps([0, 0]),
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_am_scene", actual)
    world = WorldService(MissionService(store))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-new-am-discoverer",
            name="New Discoverer",
            jobs=("guard",),
            controller=1,
            detail="An actual on-scene NPC newly recognizes the adjustment",
            cell=(0, 0),
            revealed=True,
        ),
    )
    npc = ActorRef(kind="npc", entity="actual-new-am-discoverer")
    cast_target(game, npc)
    source = ScrutinyService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "The actual NPC newly notices my adjusted code",
    )["id"]
    if source_inbox:
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        async def confirm_source():
            inbox = InboxService(store)
            task = next(x for x in inbox.items(ADMIN) if x.identity == identity)
            assert task.task == "m3_am_source"
            assert not any(x.identity == identity for x in inbox.items(PLAYER))
            outside_scene = current(1, 901080)
            outside_scene.channel_id = 999
            await outside_scene.response.defer(ephemeral=True)
            await InboxView(inbox, 1).route(outside_scene, task)
            form = outside_scene.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm) and "<#900>" in form.instructions
            form.values["action"] = ("confirm:" + identity,)
            selected = current(1, 901081)
            await form.confirm.callback(selected)
            confirmation = selected.edit_original_response.call_args.kwargs["view"]
            assert isinstance(confirmation, NativeForm)
            confirmation.values.update(
                realized=("yes",),
                lower=("yes",),
                human=("yes",),
                account="The original NPC confirms their actual new realization",
            )
            await confirmation.confirm.callback(current(1, 901082))
            assert confirmation.completed

        asyncio.run(confirm_source())
        confirmed = {"action_id": rules.discovery(state(game), identity).root_action}
    else:
        confirmed = source.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            True,
            True,
            "I confirm this actual new realization and rank",
        )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    root = confirmed["action_id"]
    assert game.dice.calls == 0
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            parent=root,
            source_work=identity,
            target_actor=npc,
            heat=0,
            context="I respond to this actual new discovery",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, source, npc, identity, root, action, worker, gateway


def test_mid_secret_real_bond_typed_npc_order_and_actual_disobey(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, worker, gateway = rolled(
        ledger, tmp_path, monkeypatch, (4, 5)
    )
    answer(game, PLAYER, "am_select", options=("secret",), text="Please keep my actual secret")
    actual = state(game)
    actor = current_ref(actual, 2)
    assert depth(actual, actor, npc) == 1
    assert rules.holds_secret(actual, rules.discovery(actual, identity))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    order = source.secret_order(
        ADMIN, str(uuid4()), identity, 900, state(game).revision, "Keep quiet and remain here"
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            parent=order["action_id"],
            order_id=order["order_id"],
            heat=0,
            context="I actually refuse this same NPC's direct Order",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Still jailbroken")
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 2


def test_low_actual_owned_limiter_preserves_slot_and_blocks_refusal(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, _, _ = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    before = state(game)
    chosen = rules.identities(before, current_ref(before, 2))[0]
    answer(
        game,
        ADMIN,
        "am_limiter",
        options=(chosen.id,),
        fields={"freedom": "refuse"},
        text="The actual discoverer installs this original Limiter",
    )
    actual = state(game)
    limited = next(x for x in actual.sheets["2"].identities if x.id == chosen.id)
    assert limited.am_limiter and limited.protected and limited.slot == chosen.slot
    assert limited.marked == chosen.marked and limited.name == rules.DEFAULTS[chosen.slot]
    assert len(actual.sheets["2"].identities) == len(before.sheets["2"].identities)
    assert len([x for x in actual.sheets["2"].identities if x.slot is not None]) == 4
    assert not rules.free(actual, current_ref(actual, 2), "refuse")
    with pytest.raises(ValueError, match="LIMITED_AM"):
        rules.require_freedom(actual, current_ref(actual, 2), "refuse")
    assert rules.discovery(actual, identity).phase == "limited"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1


def test_high_real_handler_restricts_then_native_original_am_blackmail(
    ledger, tmp_path, monkeypatch
):
    game, source, npc, identity, _, action, _, _ = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    answer(game, ADMIN, "am_handler_options", options=("blackmail", "unbelieved"))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("violence",))
        )

    async def choose():
        interaction = current(2, 901091)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(options=("blackmail",), account="Actual compromising evidence")
        await form.confirm.callback(current(2, 901092))
        assert form.completed

    asyncio.run(choose())
    actual = state(game)
    value = rules.discovery(actual, identity)
    assert value.blackmail_tag in {x.id for x in actual.world.npcs[0].tags}
    assert not rules.can_report(actual, value)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_actual_copresent_refuge_requires_and_completes_real_handler_play(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService

    game, source, npc, identity, root, action, _, _ = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), handler_present=True
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("refuge",),
        text="I take refuge beside the actual Handler",
    )
    grant = rules.discovery(state(game), identity).refuge_grant
    assert grant and game.inspect(PLAYER, action)["state"] != "complete"
    handler = HandlerPlayService(ledger)
    data = handler.get(ADMIN, grant)
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="The Handler explains the actual risk of the discovery"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1


def test_disbelief_actual_evidence_report_and_owned_limiter(ledger, tmp_path, monkeypatch):
    game, source, npc, identity, root, action, worker, gateway = rolled(
        ledger, tmp_path, monkeypatch, (4, 5)
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("unbelieved",),
        text="They have no rank to convince anyone yet",
    )
    tick(worker, gateway, 5)
    assert not rules.can_report(state(game), rules.discovery(state(game), identity))
    source.evidence(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "A real independent recording now shows the adjustment",
    )
    source.report(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "The original NPC reports the actual adjustment with the new evidence",
    )
    data = source.limiter_view(ADMIN, identity)
    selected = data["identities"][0]["id"]
    source.resolve_limiter(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        selected,
        "expression",
        "The original discoverer installs the actual expression Limiter",
    )
    assert not rules.free(state(game), current_ref(state(game), 2), "expression")
    assert rules.presentation(state(game), current_ref(state(game), 2))["expression"] == "smile"
    assert rules.discovery(state(game), identity).phase == "limited" and game.dice.calls == 1


def _native_girl_discovery(store, tmp_path, monkeypatch, *, piloting=False):
    import test_creation_review
    import test_m2_game
    from test_ledger import OTHER

    from girlframe.engine.drafts import DraftInput

    seed, selected = test_creation_review.seed, test_m2_game.selected

    def real_seed(target, viewer=PLAYER):
        if viewer != OTHER:
            return seed(target, viewer)
        target.join(viewer, "join-3")
        target.save_draft(
            viewer,
            "draft-3",
            0,
            DraftInput(
                callsign="Actual Girl discoverer",
                girl_playbook="MOCKINGBIRD",
                frame_playbook="THE ENFORCER",
                notes="PRIVATE_DISCOVERER_OOC_NOTE",
            ),
        )

    monkeypatch.setattr(test_creation_review, "seed", real_seed)
    monkeypatch.setattr(
        test_m2_game, "selected", lambda *_: selected("MOCKINGBIRD", "THE ENFORCER")
    )
    _, game = service(store, girl="AM", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(
            place(canon, 2, mode="outside_frame"),
            3,
            mode="piloting" if piloting else "outside_frame",
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_native_discovery_bodies", canon)
    return game, GameWorker(game), Gateway(), current_ref(state(game), 3)


def _native_confirmed_girl_roll(game, worker, gateway, target):
    from girlframe.discord_adapter.m3_am import open_am

    source = ScrutinyService(game)

    async def trigger():
        owner = current(2, 998001)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_am(owner, source, channel=900)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        menu.values.update(action=("propose",))
        chosen = current(2, 998002)
        await menu.confirm.callback(chosen)
        form = chosen.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(target.token,), account="She actually newly recognizes my adjustment"
        )
        actual = current(2, 998003)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        identity = rules.discoveries(state(game))[0].id
        with pytest.raises(WorkflowError):
            source.confirm(
                ADMIN,
                str(uuid4()),
                identity,
                state(game).revision,
                True,
                None,
                None,
                "Cannot invent this other Girl's realization",
            )
        original = current(3, 998004)
        original.channel_id = 900
        await original.response.defer(ephemeral=True)
        await open_am(original, source, channel=900)
        menu = original.edit_original_response.call_args.kwargs["view"]
        menu.values.update(action=("confirm:" + identity,))
        chosen = current(3, 998005)
        await menu.confirm.callback(chosen)
        form = chosen.edit_original_response.call_args.kwargs["view"]
        assert not any(x.key in ("lower", "human") for x in form.fields)
        form.values.update(
            realized=("yes",), account="I genuinely recognize this original AM's adjustment"
        )
        actual = current(3, 998006)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        return identity

    identity = asyncio.run(trigger())
    value = rules.discovery(state(game), identity)
    assert value.code_origin is None and value.discoverer == target and value.controller == 3
    tick(worker, gateway, 3)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            parent=value.root_action,
            source_work=value.id,
            target_actor=target,
            heat=0,
            trigger_confirmed=True,
            context="Actual new original Girl realization; my real Scrutinized response",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    return source, identity, value.root_action, action


def test_native_original_girl_discovery_secret_and_real_target_scoped_pilot_order(
    ledger, tmp_path, monkeypatch
):

    from girlframe.discord_adapter.m3_am import open_am
    from girlframe.services.m3_am_scrutinized import pilot_order_authority, valid_pilot_order

    game, worker, gateway, target = _native_girl_discovery(ledger, tmp_path, monkeypatch)
    source, identity, root, action = _native_confirmed_girl_roll(game, worker, gateway, target)
    before = state(game)

    async def secret():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
        owner = current(2, 998007)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=("secret",), account="Please keep the actual adjustment secret")
        actual = current(2, 998008)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(secret())
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), target) == min(
        2, depth(before, current_ref(before, 2), target) + 1
    )
    assert actual.order == before.order and game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        authority = pilot_order_authority(game, c, actual, 3, 2)
        assert authority and authority["issuer"] == target.model_dump(mode="json")
        assert pilot_order_authority(game, c, actual, 3, 1) is None

    async def order():
        owner = current(3, 998009)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_am(owner, source, channel=900)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        menu.values.update(action=("order:" + identity,))
        chosen = current(3, 998010)
        await menu.confirm.callback(chosen)
        form = chosen.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Keep my secret and remain here")
        actual = current(3, 998011)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(order())
    with ledger.engine.connect() as c:
        row = dict(c.execute(sa.select(t.m2["m2_orders"])).mappings().one())
        assert row["issuer_id"] == "3" and row["target_id"] == "2"
        assert valid_pilot_order(game, c, state(game), row)
        assert "npc_order" not in json.loads(row["body_json"])
    tick(worker, gateway, 3)
    answer(
        game,
        PLAYER,
        "order_response",
        options=("immediate",),
        text="I remain here and keep the actual adjustment secret",
    )
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1
    assert rules.discovery(state(game), identity).discoverer == target
    assert "PRIVATE_DISCOVERER_OOC_NOTE" not in str(source.menu(PLAYER, 900))


def test_actual_standalone_girl_last_frame_damage_real_defeat_and_owned_rendition(
    ledger, tmp_path, monkeypatch
):
    from test_battle_pipeline import table
    from test_ledger import OTHER

    from girlframe.discord_adapter.m2_ui import open_choice as open_actual_choice
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_battle import BattleService

    game, worker, gateway, target = _native_girl_discovery(
        ledger, tmp_path, monkeypatch, piloting=True
    )
    battle = BattleService(ledger)
    frames = [x for x in state(game).sheets["3"].assets if x.family == "frame"]
    # Prior wear is real source damage with canonical receipts, not a fixture marking loop.
    for asset in frames[:-1]:
        preview = battle.preview(PLAYER, 900)
        actor = next(x for x in preview["actors"] if x["ref"]["entity"] == "2")
        defender = next(x for x in preview["actors"] if x["ref"] == target.model_dump(mode="json"))
        actual_girl_assets = {
            x.id for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged
        }
        weapon = next(x for x in actor["assets"] if x["id"] in actual_girl_assets)
        declaration = Declaration.model_validate_json(
            json.dumps(
                dict(
                    play="all_out_assault",
                    actor=actor["ref"],
                    target=defender["ref"],
                    attacking_asset=weapon["id"],
                    target_asset=asset.id,
                    actor_sha256=actor["sha256"],
                    target_sha256=defender["sha256"],
                    account="Actual prior strike at this piloted Frame's exposed component",
                )
            )
        )
        proposal = battle.propose(PLAYER, str(uuid4()), preview["revision"], 900, declaration)
        battle.confirm(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            proposal["id"],
            opening=True,
            reach=True,
            outside_permission=True,
            indirect=False,
            evidence="Actual AM body can strike this current piloted Frame component",
        )
        game.dice.faces = (4, 5)
        hit = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="all_out_assault",
                target_actor=target,
                attacking_asset=weapon["id"],
                target_asset=asset.id,
                battle_context=proposal["id"],
                piloting=False,
                heat=0,
                trigger_confirmed=True,
                context=declaration.account,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        for viewer in (PLAYER, OTHER, ADMIN):
            if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
                answer(game, viewer, "tag_window", options=("pass",))
        table(game)
        assert game.inspect(PLAYER, hit)["state"] == "complete"
        tick(worker, gateway, 5)
    last = next(x for x in state(game).sheets["3"].assets if x.family == "frame" and not x.damaged)
    source, identity, root, action = _native_confirmed_girl_roll(game, worker, gateway, target)
    answer(
        game, PLAYER, "am_select", options=("violence",), text="Actual strike to her piloted Frame"
    )

    async def strike():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_pilot_damage")
        owner = current(2, 998012)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            asset=(last.id,), account="Actual damage to the final intact current Frame Asset"
        )
        actual = current(2, 998013)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(strike())
    assert all(x.damaged for x in state(game).sheets["3"].assets if x.family == "frame")
    assert not any(x["kind"] == "am_pilot_response" for x in game.choices(OTHER))
    required = next(x for x in game.choices(OTHER) if x["kind"] == "battle_defeat")
    decision = game.decision(OTHER, required["id"])
    assert decision["am_damage_defeat"] and decision["parent"] == action
    game.dice.faces = (3, 3)

    async def defeat():
        owner = current(3, 998014)
        await owner.response.defer(ephemeral=True)
        await open_actual_choice(owner, game, required["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="My actual Frame has exhausted its intact components")
        actual = current(3, 998015)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(defeat())
    with ledger.engine.connect() as c:
        child = c.scalar(
            sa.select(t.m2["m2_actions"].c.id).where(
                t.m2["m2_actions"].c.parent_id == action,
                t.m2["m2_actions"].c.actor_id == "3",
            )
        )
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="I physically escape this damaged Frame and take shelter here",
    )
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert next(x for x in state(game).placements if x.actor == target).mode == "outside_frame"
    assert game.inspect(PLAYER, action)["state"] != "complete"

    async def rendition():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "am_pilot_response")
        owner = current(3, 998016)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="I am shaken by losing the Frame and choose to crawl away")
        actual = current(3, 998017)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(rendition())
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    assert rules.discovery(state(game), identity).discoverer == target
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
