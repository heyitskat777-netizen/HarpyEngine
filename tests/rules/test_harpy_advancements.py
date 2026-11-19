"""The original Harpy advances and uses a separate choice on real native Plays."""

import asyncio

import pytest
from test_director_strain_calls import phone_scene
from test_engage_actual import harpy_opponent
from test_harpy_actor_plays import begin, pass_tags, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_retained_tag_permissions import reborn_with_lock

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director_strain import Command
from girlframe.engine.m3_harpy_advancements import (
    SPARROWS,
    SPARROWS_CHOICES,
    advances,
    strain_capacity,
)
from girlframe.engine.m3_strain import choose as choose_strain
from girlframe.engine.m3_strain_state import Event
from girlframe.services.inbox import InboxService
from girlframe.services.m3_director_strain import DirectorStrainService
from girlframe.services.m3_harpy_advancements import HarpyAdvancementService, capacity
from girlframe.services.m3_npc_orders import NpcOrderService
from girlframe.services.onboarding import WorkflowError


def approve_sparrows(ledger):
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "activity_specialist_rules": approval.activity_specialist_rules | {SPARROWS}
                }
            )
        }
    )


def test_echoes_order_uses_only_actual_harpy_tag_and_recipient_keeps_response(ledger):
    from test_harpy_beneath import prepared, start_native
    from test_harpy_flirt import native_answer, submit_form

    from girlframe.discord_adapter.m3_npc_orders import open_order
    from girlframe.engine.m3_harpy_advancements import ECHOES

    _, game, _, actor, worker, gateway = prepared(ledger, faces=(4, 5))
    app = ledger.policy.m3_approval
    service = NpcOrderService(game)
    mode = "harpy_echoes"
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.preview(PLAYER, 900, OTHER.user_id, origin_kind=mode)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": app.model_copy(
                update={"activity_specialist_rules": app.activity_specialist_rules | {ECHOES}}
            )
        }
    )
    career = HarpyAdvancementService(ledger)
    data = career.get(PLAYER, actor.entity)
    assert data["choices"] == ((ECHOES, "Echoes of Old Command"),)
    career.select(PLAYER, "learn-echoes", actor.entity, data["revision"], ECHOES)
    assert not service.preview(PLAYER, 900, OTHER.user_id, origin_kind=mode)["issuers"]
    source = start_native(game, actor, worker, gateway)
    native_answer(
        game,
        PLAYER,
        "harpy_beneath_select",
        {
            "options": ("tag", "status"),
            "text": "My insult sticks.",
            "fields.tag": "Original Harpy Tag",
        },
        89810,
    )
    assert game.inspect(PLAYER, source)["state"] == "complete"
    tick(worker, gateway, 5)
    original = state(game)
    target = current_ref(original, OTHER.user_id)
    tag = original.sheets[target.entity].tags[-1]
    assert tag.giver_actor == actor
    assert not service.preview(ADMIN, 900, OTHER.user_id, origin_kind=mode)["issuers"]
    assert (
        service.preview(PLAYER, 900, OTHER.user_id, origin_kind=mode)["issuers"][0]["condition"]
        == tag.id
    )
    with pytest.raises(WorkflowError, match="living original Harpy"):
        service.issue(
            PLAYER,
            "other-persona-cannot-issue",
            900,
            current_ref(original, PLAYER.user_id),
            OTHER.user_id,
            original.revision,
            "Hold your position.",
            origin_kind=mode,
        )
    key = asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_order(
                click, service, OTHER.user_id, "Hold your position.", origin_kind=mode
            ),
            dict(issuer=(actor.token,)),
            89820,
            wrong_owner=True,
        )
    )
    order = service.issue(
        PLAYER,
        key,
        900,
        actor,
        OTHER.user_id,
        original.revision,
        "Hold your position.",
        origin_kind=mode,
    )
    ledger.engine.dispose()
    tick(worker, gateway, 4)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "order_response")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            "harpy-cannot-follow-for-girl",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("immediate",)),
        )
    assert game.decision(OTHER, row["id"])["npc_order_issuer"] == "HARPY"
    answer(game, OTHER, "order_response", options=("immediate",))
    assert game.inspect(OTHER, order["action_id"])["state"] == "complete"
    assert state(game).order == original.order and game.dice.calls == 1
    tick(worker, gateway, 5)

    voice = current_ref(state(game), PLAYER.user_id)
    with pytest.raises(WorkflowError, match="actual known voice"):
        service.issue(
            PLAYER,
            "invent-unknown-voice",
            900,
            actor,
            OTHER.user_id,
            state(game).revision,
            "Stand down.",
            origin_kind=mode,
            voice=ActorRef(kind="npc", entity="absent"),
        )
    revision = state(game).revision
    key = asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_order(
                click, service, OTHER.user_id, "Stand down.", origin_kind=mode
            ),
            dict(issuer=(actor.token,), voice=(voice.token,)),
            89830,
            wrong_owner=True,
        )
    )
    order = service.issue(
        PLAYER,
        key,
        900,
        actor,
        OTHER.user_id,
        revision,
        "Stand down.",
        origin_kind=mode,
        voice=voice,
    )
    tick(worker, gateway, 4)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "order_response")
    heard = game.decision(OTHER, row["id"])
    assert heard["heard_order_voice"] == state(game).sheets[voice.entity].callsign
    assert "npc_order_issuer" not in heard
    assert not [k for k, v in heard.items() if k not in ("own", "tags") and actor.entity in str(v)]
    with ledger.engine.connect() as c:
        original_source = game.action(c, order["action_id"])["data"]["npc_order"]
        assert original_source["issuer"] == actor.model_dump(mode="json")
        assert original_source["voice"] == voice.model_dump(mode="json")
    answer(game, OTHER, "order_response", options=("disobey",))
    game.dice.faces = (4, 5)
    disobey = game.begin(
        OTHER,
        "actual-echoes-refusal",
        900,
        state(game).sheets[target.entity].revision,
        PlayInput(
            play="disobey_orders",
            parent=order["action_id"],
            order_id=order["order_id"],
            heat=0,
            context="I push back and reject the original Tag.",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", options=("reject_tag",), denied=(tag.id,))
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(OTHER, disobey)["state"] == "complete" and game.dice.calls == 2
    assert game.inspect(OTHER, order["action_id"])["state"] == "complete"
    assert not any(x.id == tag.id for x in state(game).sheets[target.entity].tags)
    tick(worker, gateway, 5)
    assert not service.preview(PLAYER, 900, OTHER.user_id, origin_kind=mode)["issuers"]
    with pytest.raises(WorkflowError, match="must still carry a Tag"):
        service.issue(
            PLAYER,
            "expired-tag-cannot-issue",
            900,
            actor,
            OTHER.user_id,
            state(game).revision,
            "Hold your position.",
            origin_kind=mode,
        )


def test_harpy_advancement_is_owned_and_adds_sparrows_to_both_native_plays(ledger):
    svc, game, _, actor = ready(ledger, faces=(4, 4))
    inbox = InboxService(ledger)
    career = HarpyAdvancementService(ledger)
    with pytest.raises(WorkflowError, match="implementation and review"):
        career.get(PLAYER, actor.entity)
    assert not any(x.task == "m3_harpy_advancement" for x in inbox.items(PLAYER))
    approve_sparrows(ledger)
    assert career.get(PLAYER, actor.entity)["slots"] == 1
    assert not any(x.task == "m3_harpy_advancement" for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="actual Harpy controller"):
        career.get(OTHER, actor.entity)
    action = begin(svc, actor)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    old = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError, match="original Sparrows"):
        game.respond(
            PLAYER,
            "forge-sparrows",
            old["id"],
            old["revision"],
            ChoiceAnswer(
                options=("beautiful", "in_control"),
                denied=("desperate",),
                fields={"harpy_sparrows": "eyes"},
            ),
        )
    base = state(game).revision
    with pytest.raises(WorkflowError, match="Reopen"):
        career.select(PLAYER, "stale-sparrows", actor.entity, base - 1, SPARROWS)
    ledger.safety(PLAYER, "pause-sparrows", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        career.select(PLAYER, "paused-sparrows", actor.entity, base, SPARROWS)
    ledger.safety(PLAYER, "resume-sparrows", ledger.status(PLAYER)["revision"], pause=False)

    async def native(number, task, fields):
        opening = current(PLAYER.user_id, number)
        opening.channel_id = 900
        await opening.response.defer(ephemeral=True)
        if task == "m3_harpy_advancement":
            entry = next(x for x in inbox.items(PLAYER) if x.task == task)
            await InboxView(inbox, PLAYER.user_id).route(opening, entry)
        else:
            choice = next(x for x in game.choices(PLAYER) if x["kind"] == task)
            await open_choice(opening, game, choice["id"])
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(OTHER.user_id))
        form.values.update(fields)
        click = current(PLAYER.user_id, number + 1)
        await form.confirm.callback(click)
        assert form.completed, click.followup.send.call_args

    base = state(game).revision
    asyncio.run(native(69800, "m3_harpy_advancement", dict(advancement=(SPARROWS,))))
    receipt = career.select(PLAYER, "69801", actor.entity, base, SPARROWS)["receipt"]
    assert advances(state(game), actor)[0].event == receipt
    with pytest.raises(WorkflowError, match="open advancement slot"):
        career.select(PLAYER, "repeat-new-key", actor.entity, state(game).revision, SPARROWS)
    ledger.engine.dispose()
    assert career.get(PLAYER, actor.entity)["learned"] == (SPARROWS,)
    assert "harpy_sparrows" not in game.decision(PLAYER, old["id"])
    answer(game, PLAYER, "actor_keep", options=("beautiful", "in_control"), denied=("desperate",))
    answer(
        game, ADMIN, "handler_keep", flag=True, text="The actual GM adjudicates the ordinary Play"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)

    action = begin(svc, actor)
    tick(worker, gateway, 3)
    pass_tags(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    assert game.decision(PLAYER, choice["id"])["harpy_sparrows"] == SPARROWS_CHOICES
    asyncio.run(
        native(
            69810,
            "actor_keep",
            {
                "options": ("beautiful", "in_control"),
                "denied": ("desperate",),
                "fields.harpy_sparrows": ("eyes",),
            },
        )
    )
    answer(
        game, ADMIN, "handler_keep", flag=True, text="The actual GM adjudicates the ordinary Play"
    )
    result = game.inspect(PLAYER, action)["result"]
    assert result["sparrows"] == dict(choice="eyes", source=receipt)
    assert {"beautiful", "in_control"} <= set(result["positive"])
    tick(worker, gateway, 5)

    action = begin(svc, actor, play="engage", target_actor=harpy_opponent(game))
    tick(worker, gateway, 3)
    pass_tags(game)
    original = state(game).sheets
    asyncio.run(
        native(
            69820,
            "engage_maneuvers",
            dict(
                maneuvers=("cover", "advance", "lure"),
                asset_cover=("actual-harpy-asset",),
                asset_advance=("actual-harpy-asset",),
                asset_lure=("actual-harpy-asset",),
                harpy_sparrows=("haze",),
                text="The actual battlefield maneuvers take effect.",
            ),
        )
    )
    result = game.inspect(PLAYER, action)["result"]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert result["sparrows"] == dict(choice="haze", source=receipt)
    assert state(game).sheets == original and game.dice.calls == 3


def test_harpy_slot_capacity_recovers_actual_past_high_after_director_lowers_it(
    ledger, tmp_path, monkeypatch
):
    strain, game, period, director = phone_scene(ledger, tmp_path, monkeypatch, extra=(SPARROWS,))
    service = DirectorStrainService(strain)
    for value in ("high", "low"):
        service.call(
            OTHER,
            "void-level-" + value,
            900,
            state(game).revision,
            director,
            Command(
                mode="severity",
                track="void",
                severity=value,
                account="The fictional Director calls about Void Strain.",
            ),
        )
    before = state(game)
    assert strain_capacity(before.strain) == 1
    ledger.engine.dispose()
    with ledger.engine.connect() as c:
        slots, source = capacity(c, ledger.campaign_id, state(game), "original-birth")
    assert slots == 2 and source != "original-birth"
    prior = tuple(
        Event(id=str(n), period_id=period, track="void", severity="high", face=n, column=1)
        for n in (1, 2, 3)
    )
    third = Event(id="third-real-void", period_id=period, track="void", severity="high", face=6)
    canonical = before.strain.model_copy(update={"events": (*prior, third), "requests": ()})
    endgame = choose_strain(canonical, third.id, 2)
    assert strain_capacity(endgame) == 3


def test_converted_harpy_has_its_own_advancement_and_preserves_the_original_archive(ledger):
    game, _, _, actor, _, _ = reborn_with_lock(ledger)
    approve_sparrows(ledger)
    career = HarpyAdvancementService(ledger)
    old = state(game)
    with pytest.raises(WorkflowError, match="actual Harpy controller"):
        career.select(OTHER, "steal-advancement", actor.entity, old.revision, SPARROWS)
    receipt = career.select(
        PLAYER, "original-converted-harpy", actor.entity, old.revision, SPARROWS
    )
    current = state(game)
    assert current.career_archives == old.career_archives
    assert current.harpy_states == old.harpy_states
    assert advances(current, actor)[0].event == receipt["receipt"]


@pytest.mark.parametrize("gain", (1, 2))
def test_only_she_matters_native_death_applies_heat_and_keeps_cast_authority(ledger, gain):
    from test_cast_service import change

    from girlframe.discord_adapter.m3_cast import open_cast
    from girlframe.engine.m3_harpy_advancements import ONLY_SHE_MATTERS
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_harpy_only_she import OnlySheMattersService
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.read_only_bot import GuildViewer

    _, game, cast, actor = ready(ledger)
    support = GuildViewer(4, 200, True, False)
    ledger.join(support, "npc-only-controller")
    roles = NpcRoleService(WorldService(cast.actors.missions))
    target = ActorRef(kind="npc", entity="present-original-npc")
    witness = ActorRef(kind="npc", entity="separate-present-npc")
    remote = ActorRef(kind="npc", entity="different-square-npc")
    for ref, controller, candidates in (
        (target, OTHER, (0, 0)),
        (witness, support, (0, 0)),
        (remote, OTHER, (2, 0)),
    ):
        proposed = roles.offer(
            ADMIN,
            "create-" + ref.entity,
            state(game).revision,
            Npc(
                id=ref.entity,
                name=ref.entity,
                detail="An original synthetic civilian.",
                jobs=("civilian",),
                controller=controller.user_id,
                cell=candidates,
                revealed=True,
            ),
        )
        roles.respond(
            controller, "accept-" + ref.entity, proposed["id"], state(game).revision, "accept"
        )
        change(cast, controller, "join", ref)
    game.bind_scene(ADMIN, "unrelated-cast-room", 901)
    current_policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": current_policy.model_copy(
                update={
                    "activity_specialist_rules": current_policy.activity_specialist_rules
                    | {ONLY_SHE_MATTERS}
                }
            )
        }
    )
    career = HarpyAdvancementService(ledger)
    career.select(PLAYER, "learn-only-she", actor.entity, state(game).revision, ONLY_SHE_MATTERS)
    service = OnlySheMattersService(game)
    assert set(service.get(PLAYER, 900, actor)["targets"]) == {target, witness}
    original = state(game)
    with ledger.engine.connect() as c:
        unrelated = game.scene(c, 901)
        assert support.user_id not in game.scene(c, 900)["participants"]
    with pytest.raises(WorkflowError, match="actual living Harpy"):
        service.act(OTHER, "wrong-owner", 900, original.revision, actor, target, 2, "No")
    with pytest.raises(WorkflowError, match="STALE_HARPY"):
        service.act(PLAYER, "stale", 900, original.revision - 1, actor, target, 2, "No")
    with pytest.raises(WorkflowError, match="same|actual square"):
        service.act(PLAYER, "target-remote", 900, original.revision, actor, remote, 2, "No")
    ledger.safety(PLAYER, "pause-only-she", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.act(PLAYER, "paused", 900, original.revision, actor, target, 2, "No")
    ledger.safety(PLAYER, "resume-only-she", ledger.status(PLAYER)["revision"], pause=False)
    account = "The Harpy kills the original civilian in the scene."

    async def native():
        click = current(PLAYER.user_id, 70840)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        select = current(PLAYER.user_id, 70841)
        select.channel_id = 900
        await select.response.defer(ephemeral=True)
        await picker.open_item(select, "only-she:" + actor.token)
        form = select.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(OTHER.user_id))
        form.values.update(target=(target.token,), heat=(str(gain),), account=account)
        submit = current(PLAYER.user_id, 70842)
        await form.confirm.callback(submit)
        assert form.completed, submit.followup.send.call_args

    revision = state(game).revision
    asyncio.run(native())
    ledger.engine.dispose()
    operation = service.act(PLAYER, "70842", 900, revision, actor, target, gain, account)
    after = state(game)
    assert {x.id: x.alive for x in after.world.npcs} == {
        target.entity: False,
        witness.entity: True,
        remote.entity: True,
    }
    assert (
        after.sheets == original.sheets
        and harpy(after, actor).heat == harpy(original, actor).heat + gain
    )
    assert (
        game.dice.calls == 0
        and len([x for x in after.facts if x.get("id") == operation["event"]]) == 1
    )
    with ledger.engine.connect() as c:
        assert game.scene(c, 901) == unrelated
        assert support.user_id not in game.scene(c, 900)["participants"]
    assert any(
        x["ref"] == witness.model_dump(mode="json") for x in cast.view(support, 900)["roles"]
    )
    assert target not in service.get(PLAYER, 900, actor)["targets"]


def test_song_of_love_lost_moves_only_the_original_accepting_girl(ledger):
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_cast import open_cast
    from girlframe.discord_adapter.m3_harpy_song import open_song_response
    from girlframe.engine.m3_actor_bonds import depth
    from girlframe.engine.m3_harpy_advancements import SONG_OF_LOVE_LOST
    from girlframe.services.m3_harpy_song import HarpySongService, records

    _, game, casting, actor = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules
                    | {SONG_OF_LOVE_LOST},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-song",
        actor.entity,
        state(game).revision,
        SONG_OF_LOVE_LOST,
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame", cell=(1, 0))
        game.event(c, ADMIN.user_id, "synthetic-song-placement", "synthetic.position", canon)
    original = state(game)
    recipient = current_ref(original, OTHER.user_id)
    song = HarpySongService(game)
    assert song.options(PLAYER, 900, actor)["targets"] == {
        recipient.token: original.sheets["3"].callsign
    }

    async def broadcast():
        interaction = current(PLAYER.user_id, 89600)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_cast(interaction, casting)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        selected = current(PLAYER.user_id, 89601)
        selected.channel_id = 900
        await selected.response.defer(ephemeral=True)
        await picker.open_item(selected, "song:" + actor.token)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(target=(recipient.token,), account="The Harpy sings over the radio.")
        await form.confirm.callback(current(PLAYER.user_id, 89602))
        assert form.completed

    asyncio.run(broadcast())
    inbox = InboxService(ledger)
    (task,) = [x for x in inbox.items(OTHER) if x.task == "m3_harpy_song"]
    assert not [x for x in inbox.items(PLAYER) if x.task == "m3_harpy_song"]
    with pytest.raises(WorkflowError, match="unavailable"):
        song.get(PLAYER, task.identity)
    assert depth(state(game), actor, recipient) == 0
    ledger.engine.dispose()

    async def step():
        interaction = current(OTHER.user_id, 89603)
        await interaction.response.defer(ephemeral=True)
        await open_song_response(interaction, song, task.identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            choice=("accept",), account="I step into the next square toward the Harpy."
        )
        await form.confirm.callback(current(OTHER.user_id, 89604))
        assert form.completed

    asyncio.run(step())
    updated = state(game)
    actual = next(x for x in updated.placements if x.actor == recipient)
    assert actual.girl_cell == (0, 0) and actual.frame_cell == (1, 0)
    assert depth(updated, actor, recipient) == 1 and records(updated)[0].moved
    assert game.dice.calls == 0


def test_song_of_love_lost_only_the_actual_handler_can_answer(ledger):
    from test_cast_service import change

    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.engine.m3_harpy_advancements import SONG_OF_LOVE_LOST
    from girlframe.services.m3_harpy_song import HarpySongService, records

    _, game, casting, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules
                    | {SONG_OF_LOVE_LOST},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-song-for-handler",
        harpy.entity,
        state(game).revision,
        SONG_OF_LOVE_LOST,
    )
    role = active_handler(state(game))
    assert role
    song = HarpySongService(game)
    assert song.options(PLAYER, 900, harpy)["handler"] is None
    with ledger.transaction() as c:
        canon = state(game)
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=role.model_dump_json(),
                cell="[0, 0]",
                event="synthetic-handler-position",
            )
        )
        game.event(c, ADMIN.user_id, "synthetic-handler-position", "synthetic.position", canon)
    change(casting, ADMIN, "join", role)
    view = song.options(PLAYER, 900, harpy)
    assert view["handler"] is not None
    offered = song.act(
        PLAYER,
        "sing-to-original-handler",
        900,
        harpy,
        view["revision"],
        "handler",
        "The song travels on the original radio channel.",
    )["id"]
    inbox = InboxService(ledger)
    assert [x.identity for x in inbox.items(ADMIN) if x.task == "m3_harpy_song"] == [offered]
    assert not [x for x in inbox.items(OTHER) if x.task == "m3_harpy_song"]
    private = song.get(ADMIN, offered)
    song.respond(
        ADMIN,
        "original-handler-flinch",
        offered,
        private["revision"],
        accept=True,
        account="The Handler flinches and lowers the volume.",
    )
    response = records(state(game))[0]
    assert response.recipient == role and response.reaction and not response.moved


def test_song_of_love_lost_crowd_adds_only_the_actual_local_npcs(ledger):
    from girlframe.discord_adapter.m3_harpy_song import open_song_response
    from girlframe.engine.m3_harpy_advancements import SONG_OF_LOVE_LOST
    from girlframe.engine.m3_world import update
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_harpy_song import HarpySongService, crowds

    _, game, _, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules
                    | {SONG_OF_LOVE_LOST},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-song-crowd",
        harpy.entity,
        state(game).revision,
        SONG_OF_LOVE_LOST,
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=tuple(
                Npc(
                    id=name,
                    name=name,
                    detail="Actual ordinary NPC",
                    jobs=("civilian",),
                    cell=cell,
                    controller=ADMIN.user_id,
                    revealed=True,
                )
                for name, cell in (("Broker", (0, 0)), ("Cook", (0, 0)), ("Remote", (1, 0)))
            ),
        )
        game.event(c, ADMIN.user_id, "synthetic-song-crowd", "synthetic.npcs", canon)
    service = HarpySongService(game)
    options = service.options(PLAYER, 900, harpy)
    assert options["crowd"] is True
    offered = service.act(
        PLAYER,
        "song-to-actual-crowd",
        900,
        harpy,
        options["revision"],
        "crowd",
        "The original Harpy sings across the square.",
    )
    task = offered["id"]
    inbox = InboxService(ledger)
    assert [x.identity for x in inbox.items(ADMIN) if x.task == "m3_harpy_song"] == [task]
    assert not [x for x in inbox.items(OTHER) if x.task == "m3_harpy_song"]

    async def review():
        interaction = current(ADMIN.user_id, 89700)
        await interaction.response.defer(ephemeral=True)
        await open_song_response(interaction, service, task)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        key = next(field for field in form.fields if field.key == "choice").options[0][0]
        form.values.update(choice=(key,), account="The Broker and Cook run up to the Harpy.")
        await form.confirm.callback(current(ADMIN.user_id, 89701))
        assert form.completed

    asyncio.run(review())
    updated = state(game)
    result = crowds(updated)[0]
    assert result.reaction and {x.entity for x in result.audience} == {"Broker", "Cook"}
    scene = next(x for x in updated.scene_casts if x.id == result.scene)
    assert {x.actor.entity for x in scene.roles if x.actor.kind == "npc"} == {"Broker", "Cook"}


def test_eagle_cracks_the_actual_exposed_cockpit_and_holds_the_original_girl(ledger):
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_harpy_eagle import open_eagle
    from girlframe.engine.m2 import TagState
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_harpy_advancements import EAGLE
    from girlframe.engine.m3_harpy_eagle import held, missing
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_harpy_eagle import EagleService
    from girlframe.services.m3_physical import PhysicalService

    _, game, _, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules | {EAGLE},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-eagle",
        harpy.entity,
        state(game).revision,
        EAGLE,
    )
    target = current_ref(state(game), OTHER.user_id)
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id)
        canon.sheets["3"].tags.append(
            TagState(
                id="actual-harpy-tag",
                label="An exposed flaw",
                giver=PLAYER.user_id,
                giver_actor=harpy,
                observers=(PLAYER.user_id, OTHER.user_id),
            ),
        )
        game.event(c, ADMIN.user_id, "synthetic-eagle-setup", "synthetic.position", canon)
    service = EagleService(game)
    assert service.get(PLAYER, 900, harpy)["targets"] == {}
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    exposure = BattleService(game.store).expose(
        OTHER,
        "expose-original-for-harpy",
        state(game).revision,
        target,
        "The Girl willingly exposes this exact cockpit's Core to the Harpy.",
        opponent=harpy,
        willing=True,
        scene=scene,
    )
    view = service.get(PLAYER, 900, harpy)
    key = next(iter(view["targets"]))

    async def capture():
        interaction = current(PLAYER.user_id, 89800)
        await interaction.response.defer(ephemeral=True)
        await open_eagle(interaction, service, 900, harpy)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(target=(key,), account="The Harpy takes the actual exposed cockpit.")
        await form.confirm.callback(current(PLAYER.user_id, 89801))
        assert form.completed

    asyncio.run(capture())
    captured = state(game)
    record = held(captured, target)
    assert record.harpy == harpy and record.exposure == exposure["event"]
    assert next(x for x in captured.sheets["3"].tags if x.id == record.tag).marked
    with ledger.engine.connect() as c:
        actual = resolve(captured, target, profiles(c, ledger.campaign_id))
    assert actual.cell is None and actual.frame_cell == (0, 0) and actual.offstage_source
    assert actual.piloting is False and missing(captured, target, record.frame)
    ledger.engine.dispose()
    with pytest.raises(WorkflowError, match="hold only one"):
        service.act(
            PLAYER,
            "second-cockpit",
            900,
            harpy,
            state(game).revision,
            key,
            "A second attempt.",
        )
    service.act(
        PLAYER,
        "release-original-cockpit",
        900,
        harpy,
        state(game).revision,
        "release",
        "The Harpy releases the actual original Girl into the square.",
    )
    returned = state(game)
    assert held(returned, target) is None and missing(returned, target, record.frame)
    with ledger.engine.connect() as c:
        actual = resolve(returned, target, profiles(c, ledger.campaign_id))
    assert actual.cell == (0, 0) and not actual.inside_frame
    command = CockpitAction(
        actor=target,
        operation="sit",
        expected_position=actual.position_sha256,
        account="I try to return to the original cockpit.",
        confirmed=True,
    )
    physical = PhysicalService(ledger)
    with pytest.raises(WorkflowError, match="cockpit removed"):
        physical.operate(OTHER, "eagle-missing-cockpit", returned.revision, command, channel=900)
    service.restore(
        ADMIN,
        "reinstall-original-eagle-cockpit",
        record.event,
        returned.revision,
        "The actual recovered cockpit was fitted to its original Frame in this square.",
    )
    fixed = state(game)
    assert not missing(fixed, target, record.frame)
    physical.operate(OTHER, "eagle-restored-cockpit", fixed.revision, command, channel=900)
    assert next(x for x in state(game).placements if x.actor == target).mode == "inside_frame"

    assert game.dice.calls == 0


def test_harpy_gaze_records_owned_promise_and_only_then_the_actual_tag(ledger):
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_harpy_gaze import open_gaze_response
    from girlframe.engine.m3_harpy_advancements import MANIC_PIXIE
    from girlframe.services.m3_harpy_gaze import GazeService, records

    _, game, _, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules | {MANIC_PIXIE},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-gaze",
        harpy.entity,
        state(game).revision,
        MANIC_PIXIE,
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        game.event(c, ADMIN.user_id, "synthetic-gaze-placement", "synthetic.position", canon)
    recipient = current_ref(state(game), OTHER.user_id)
    service = GazeService(game)
    options = service.targets(PLAYER, 900, harpy)
    identity = service.start(
        PLAYER,
        "original-gaze",
        900,
        harpy,
        options["revision"],
        recipient.token,
        "The Harpy meets the original Girl’s eyes.",
    )["id"]
    inbox = InboxService(ledger)
    assert [x.identity for x in inbox.items(OTHER) if x.task == "m3_harpy_gaze"] == [identity]
    assert not [x for x in inbox.items(ADMIN) if x.task == "m3_harpy_gaze"]

    async def choose():
        interaction = current(OTHER.user_id, 89900)
        await interaction.response.defer(ephemeral=True)
        await open_gaze_response(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            choices=("hands", "promise"),
            account="I take her hands and make a promise.",
            promise="I will bring back the recording.",
        )
        await form.confirm.callback(current(OTHER.user_id, 89901))
        assert form.completed

    asyncio.run(choose())
    assert records(state(game))[0].promise == "I will bring back the recording."
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, identity)
    ledger.engine.dispose()
    course = service.get(OTHER, identity)
    service.respond(OTHER, "withdraw-harpy-promise", identity, course["revision"], "break")
    allowed = service.get(PLAYER, identity)
    service.respond(
        PLAYER,
        "name-broken-original-promise",
        identity,
        allowed["revision"],
        "tag",
        account="Promise broken",
    )
    tags = [x for x in state(game).sheets["3"].tags if x.id == "gaze:" + identity]
    assert len(tags) == 1 and tags[0].giver_actor == harpy
    assert set(tags[0].observers) == {PLAYER.user_id, OTHER.user_id}


def test_harpy_gaze_failed_keep_applies_actual_owned_void(ledger):
    from test_physical_operations import place

    from girlframe.engine.m3_harpy_advancements import MANIC_PIXIE
    from girlframe.services.m3_harpy_gaze import GazeService, records
    from girlframe.services.m3_void import VoidService

    _, game, _, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules | {MANIC_PIXIE},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-gaze-for-keep",
        harpy.entity,
        state(game).revision,
        MANIC_PIXIE,
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        sheet = canon.sheets["3"]
        sheet.girl = "PRINCESS"
        sheet.girl_runtime = None
        assets = [x for x in sheet.assets if x.family == "girl"]
        for x in assets[:-1]:
            x.void = True
        game.event(c, ADMIN.user_id, "synthetic-gaze-keep", "synthetic.position", canon)
    recipient = current_ref(state(game), OTHER.user_id)
    service = GazeService(game)
    source = service.start(
        PLAYER,
        "original-gaze-keep",
        900,
        harpy,
        state(game).revision,
        recipient.token,
        "The Harpy meets the original Girl’s eyes.",
    )["id"]
    service.respond(
        OTHER,
        "choose-actual-resistance",
        source,
        state(game).revision,
        "choose",
        choices=("hands", "keep"),
        account="I take her hands and try to clear my head.",
    )
    assert service.get(OTHER, source)["step"] == "keep"
    from test_privacy_game_delivery import PrivateGateway

    worker, gateway = GameWorker(game), PrivateGateway()
    child = game.begin(
        OTHER,
        "original-gaze-resistance",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            source_work=source,
            context="I try to keep my head through the original gaze.",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 5)
    for player in (OTHER, PLAYER, ADMIN):
        answer(game, player, "tag_window", options=("pass",))
    answer(game, OTHER, "actor_keep", options=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=False, text="The danger was too strong.")
    tick(worker, gateway, 5)
    canon = state(game)
    case = records(canon)[0]
    assert case.keep_action == child and case.enough is False
    assert case.void_event is None
    data = service.get(OTHER, source)
    assert data["step"] == "void"
    actual = next(iter(data["assets"]))
    service.respond(
        OTHER,
        "original-gaze-void",
        source,
        data["revision"],
        "void",
        choices=(actual,),
        account="The original Asset twists toward the Harpy’s voice.",
    )
    final = state(game)
    assert next(x for x in final.sheets["3"].assets if x.id == actual).void
    case = records(final)[0]
    assert case.void_asset == actual and case.void_work
    assert VoidService(ledger).get(OTHER, case.void_work)["stage"] == "allured"
    with pytest.raises(WorkflowError):
        VoidService(ledger).get(PLAYER, case.void_work)


def test_visions_of_infinity_low_copies_actual_identities_and_exposes_original_core(ledger):
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_harpy_visions import open_visions_response
    from girlframe.engine.m3_harpy_advancements import VISIONS
    from girlframe.engine.m3_harpy_defeat import harpy as actual_harpy
    from girlframe.engine.m3_harpy_visions import records
    from girlframe.services.m3_harpy_visions import VisionsService

    _, game, _, harpy = ready(ledger, faces=(1, 2), heat=2)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules | {VISIONS},
                )
            ),
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER,
        "learn-visions",
        harpy.entity,
        state(game).revision,
        VISIONS,
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        game.event(c, ADMIN.user_id, "synthetic-visions-placement", "synthetic.position", canon)
    original = state(game)
    recipient = current_ref(original, OTHER.user_id)
    service = VisionsService(game)
    offered = service.start(
        PLAYER,
        "begin-original-visions",
        900,
        harpy,
        original.revision,
        recipient.token,
        "The Harpy asks to touch the original Girl and share the vision.",
    )["id"]
    assert game.dice.calls == 0
    assert [
        x.identity for x in InboxService(ledger).items(OTHER) if x.task == "m3_harpy_visions"
    ] == [offered]
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(ADMIN, offered)
    view = service.get(OTHER, offered)
    service.respond(
        OTHER, "allow-original-visions", offered, view["revision"], "consent", choice=True
    )
    roll_view = service.get(PLAYER, offered)
    rolled = service.respond(
        PLAYER, "roll-original-visions", offered, roll_view["revision"], "roll", heat=1
    )
    assert (
        service.respond(
            PLAYER, "roll-original-visions", offered, roll_view["revision"], "roll", heat=1
        )
        == rolled
    )
    assert game.dice.calls == 1 and actual_harpy(state(game), harpy).heat == 1
    assert state(game).sheets["3"].identities == original.sheets["3"].identities
    ledger.engine.dispose()

    async def accept():
        interaction = current(OTHER.user_id, 89960)
        await interaction.response.defer(ephemeral=True)
        await open_visions_response(interaction, service, offered)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["choice"] = (form.fields[0].options[0][0],)
        await form.confirm.callback(current(OTHER.user_id, 89961))
        assert form.completed

    asyncio.run(accept())
    final = state(game)
    assert [x.name for x in final.sheets["3"].identities] == ["Free"]
    assert actual_harpy(final, harpy).identities == actual_harpy(original, harpy).identities
    assert next(x for x in final.world.pilots if x.id == harpy.entity).exposed
    assert records(final)[0].resolved and records(final)[0].roll.faces == (1, 2)


def test_visions_high_requires_eight_ordered_private_effects(ledger):
    from test_harpy_flirt import submit_form
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_harpy_visions import open_visions_response
    from girlframe.engine.m3_actor_bonds import depth, set_depth
    from girlframe.engine.m3_harpy_advancements import VISIONS
    from girlframe.engine.m3_harpy_visions import Adjustment, records
    from girlframe.engine.m3_identity_slots import bind
    from girlframe.services.m3_harpy_visions import VisionsService

    _, game, _, harpy = ready(ledger, faces=(5, 5), heat=1)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(activity_specialist_rules=policy.activity_specialist_rules | {VISIONS})
            )
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER, "learn-high-visions", harpy.entity, state(game).revision, VISIONS
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        girl = current_ref(canon, OTHER.user_id)
        canon.sheets[girl.entity] = bind(canon.sheets[girl.entity])
        canon = set_depth(canon, girl, harpy, 2, "synthetic-existing-bond")
        game.event(c, ADMIN.user_id, "synthetic-high-placement", "synthetic.position", canon)
    original = state(game)
    original_sheet = original.sheets[girl.entity]
    original_identity = next(x for x in original_sheet.identities if x.slot == 0)
    service = VisionsService(game)
    identity = service.start(
        PLAYER,
        "initiate-high-visions",
        900,
        harpy,
        original.revision,
        girl.token,
        "Share a vision.",
    )["id"]
    view = service.get(OTHER, identity)
    service.respond(
        OTHER, "approve-high-visions", identity, view["revision"], "consent", choice=True
    )
    view = service.get(PLAYER, identity)
    service.respond(PLAYER, "roll-high-visions", identity, view["revision"], "roll", heat=1)
    view = service.get(PLAYER, identity)
    assert view["tier"] == "high" and view["descriptions"] is None
    with pytest.raises(WorkflowError, match="exactly eight"):
        service.respond(
            PLAYER,
            "seven-effects-do-not-satisfy-high",
            identity,
            view["revision"],
            "plan",
            choices=(Adjustment(effect="tag", slot=0),) * 7,
        )

    def open_response(interaction):
        return open_visions_response(interaction, service, identity)

    selections = ("tag:0", "identity", "tag:0", "identity", "tag:0", "identity", "weaken", "remove")
    values = {f"effect_{i}": (choice,) for i, choice in enumerate(selections)}
    asyncio.run(submit_form(PLAYER, open_response, values | {"names": "One\nTwo\nThree"}, 89970))
    assert state(game).sheets[girl.entity].identities == original_sheet.identities
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(ADMIN, identity)
    assert [
        x.identity for x in InboxService(ledger).items(OTHER) if x.task == "m3_harpy_visions"
    ] == [identity]
    view = service.get(OTHER, identity)
    assert len(view["descriptions"]) == 8 and original_identity.name in view["descriptions"][0]
    asyncio.run(submit_form(OTHER, open_response, {"choice": ("yes",)}, 89974, wrong_owner=True))
    final = state(game)
    receipt = records(final)[0]
    sheet = final.sheets[girl.entity]
    assert game.dice.calls == 1 and receipt.roll.faces == (5, 5) and receipt.roll.heat == 1
    assert receipt.resolved and len(receipt.proposed.choices) == 8
    assert next(x.name for x in sheet.identities if x.slot == 0) == "Three"
    assert [(x.label, x.giver_actor) for x in sheet.tags[-3:]] == [
        (original_identity.name, harpy),
        ("One", harpy),
        ("Two", harpy),
    ]
    assert depth(final, girl, harpy) == 0


def test_visions_mid_suspends_actual_play_until_verified_foundation_care(ledger):
    from test_cast_service import change
    from test_harpy_flirt import submit_form
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_harpy_visions import (
        open_visions_recovery,
        open_visions_response,
    )
    from girlframe.engine.m3_harpy_advancements import VISIONS
    from girlframe.engine.m3_harpy_visions import restrictions
    from girlframe.services.m3_harpy_visions import VisionsService

    _, game, cast, harpy = ready(ledger, faces=(4, 5), heat=0)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(activity_specialist_rules=policy.activity_specialist_rules | {VISIONS})
            )
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER, "learn-mid-visions", harpy.entity, state(game).revision, VISIONS
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        game.event(c, ADMIN.user_id, "reconditioning-site", "synthetic.position", canon)
    original = state(game)
    girl = current_ref(original, OTHER.user_id)
    service = VisionsService(game)
    encounter = service.start(
        PLAYER, "mid-visions", 900, harpy, original.revision, girl.token, "Share a vision."
    )["id"]
    service.respond(OTHER, "consent-mid", encounter, state(game).revision, "consent", choice=True)
    service.respond(PLAYER, "roll-mid", encounter, state(game).revision, "roll", heat=0)
    assert service.get(PLAYER, encounter)["tier"] == "mid"

    def encounter_view(interaction):
        return open_visions_response(interaction, service, encounter)

    asyncio.run(submit_form(PLAYER, encounter_view, {"effect_0": ("play:keep_your_head",)}, 90030))
    asyncio.run(submit_form(OTHER, encounter_view, {"choice": ("yes",)}, 90034))
    restriction = restrictions(state(game))[0]
    change(cast, PLAYER, "withdraw", harpy)
    play = PlayInput(play="keep_your_head", context="A danger", trigger_confirmed=True, heat=0)
    with pytest.raises(WorkflowError, match="requires Foundation reconditioning"):
        game.begin(OTHER, "blocked-before-care", 900, state(game).sheets["3"].revision, play)

    notice = next(
        x for x in InboxService(ledger).items(OTHER) if x.task == "m3_harpy_visions_recovery"
    )
    with pytest.raises(WorkflowError, match="unavailable"):
        service.recovery(PLAYER, notice.identity)
    view = service.recovery(OTHER, notice.identity)
    site = next(key for key in view["sites"] if key.endswith(":base0"))

    def recovery_view(interaction):
        return open_visions_recovery(interaction, service, notice.identity)

    asyncio.run(
        submit_form(
            OTHER,
            recovery_view,
            {"site": (site,), "account": "I completed a retraining session at the base."},
            90038,
        )
    )
    assert notice.identity == restriction.id
    assert restrictions(state(game))[0].restored is None
    ledger.engine.dispose()
    assert service.recovery(ADMIN, notice.identity)["step"] == "verify"
    asyncio.run(
        submit_form(
            ADMIN,
            recovery_view,
            {"verified": ("yes",), "account": "Confirmed the original session restored the Play."},
            90042,
        )
    )
    assert restrictions(state(game))[0].restored is not None
    action = game.begin(OTHER, "keep-after-care", 900, state(game).sheets["3"].revision, play)
    assert action["action_id"]
