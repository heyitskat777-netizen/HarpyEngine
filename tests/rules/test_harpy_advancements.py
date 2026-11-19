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
from girlframe.engine.m2 import ChoiceAnswer
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


def test_harpy_advancement_is_owned_and_adds_sparrows_to_both_native_plays(ledger):
    svc, game, _, actor = ready(ledger, faces=(4, 4))
    inbox = InboxService(ledger)
    career = HarpyAdvancementService(ledger)
    with pytest.raises(ValueError, match="implementation and review"):
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
