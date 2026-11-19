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
