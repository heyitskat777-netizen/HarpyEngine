"""True original Handler Girl source reaches owned factual setup, targeting and Void rewriting."""

import asyncio
from uuid import uuid4

import pytest
from test_handler_void_service import high_director
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_girl_void import open_handler_girl_void
from girlframe.engine.m3_handler_girl_void import girl_assets
from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService
from girlframe.services.m3_items import prove_item
from girlframe.services.onboarding import WorkflowError


def test_true_handler_girl_void_waits_for_real_facts_caster_target_and_patient_rewrite(
    ledger, monkeypatch
):
    game, worker, gateway, source, work, _, _, _ = high_director(
        ledger, monkeypatch, handler_girl=True
    )
    service = HandlerGirlVoidService(ledger, game)
    initial = state(game)
    episode = initial.handler_girl_void[-1]
    assert episode.phase == "facts" and episode.controller == 1 and episode.caster_controller == 2
    assert episode.judge == 3 and not initial.handler_void
    assert not girl_assets(initial, episode.actor) and game.dice.calls == 1
    assert game.inspect(PLAYER, source)["state"] != "complete"
    with pytest.raises(WorkflowError):
        service.propose(
            PLAYER,
            str(uuid4()),
            work,
            initial.revision,
            "Not mine",
            "No actual ownership",
            "Not the original body",
            damaged=False,
            weapon=False,
        )
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        initial.revision,
        "Established optical implant",
        "A real existing cybernetic eye",
        "The original Handler has used it since before this scene",
        damaged=True,
        weapon=False,
    )
    assert service.get(PLAYER, work)["proposal"] is None
    assert not service.get(PLAYER, work)["can_act"]
    with pytest.raises(WorkflowError):
        service.review(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            allow=True,
            account="Cannot impersonate the selected original judge",
        )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=False,
        account="The source evidence needs the actual device's prior history",
    )
    assert not state(game).held_items[-1].id.startswith("handler-girl-item:")
    assert service.get(ADMIN, work)["phase"] == "facts"
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Established optical implant",
        "A real existing damaged cybernetic eye",
        "Its actual prior existing history is now specified",
        damaged=True,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="Actual source judge verifies this real preexisting device and damage",
    )
    ready = service.get(PLAYER, work)
    assert ready["phase"] == "asset" and ready["can_act"] and len(ready["assets"]) == 1
    item = state(game).held_items[-1]
    with ledger.engine.connect() as c:
        assert prove_item(c, game, state(game), item.id) == item
    with pytest.raises(WorkflowError):
        service.select(ADMIN, str(uuid4()), work, state(game).revision, ready["assets"][0]["id"])
    service.select(PLAYER, str(uuid4()), work, state(game).revision, ready["assets"][0]["id"])
    with pytest.raises(WorkflowError):
        service.rewrite(
            PLAYER, str(uuid4()), work, state(game).revision, "Cannot describe another body"
        )
    before = state(game)
    key, revision = str(uuid4()), before.revision
    result = service.rewrite(
        ADMIN, key, work, revision, "The old optical implant blooms with Void fractals"
    )
    snapshot = state(game).model_dump_json()
    assert (
        service.rewrite(
            ADMIN, key, work, revision, "The old optical implant blooms with Void fractals"
        )
        == result
    )
    assert state(game).model_dump_json() == snapshot
    final = state(game)
    assert result["allure"] and result["assigned_frame"] is None
    assert final.handler_girl_void[-1].phase == "allure"
    assert (
        girl_assets(final, episode.actor)[0].void and girl_assets(final, episode.actor)[0].damaged
    )
    assert (
        final.handler_heat == initial.handler_heat
        and final.director_contexts == initial.director_contexts
    )
    assert final.sheets == initial.sheets and final.placements == initial.placements
    assert final.world == initial.world and final.frame_locks == initial.frame_locks
    assert not final.harpy_states and not final.void_thresholds
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert (
            prove_item(c, game, final, item.id).state_event
            == final.handler_girl_void[-1].corruption_event
        )


def test_actual_handler_girl_void_native_owners_and_pending_factual_review_pause(
    ledger, monkeypatch
):
    game, _, _, _, work, _, _, _ = high_director(ledger, monkeypatch, handler_girl=True)
    service = HandlerGirlVoidService(ledger, game)

    async def native(user, identity, values):
        caller = current(user, identity)
        await caller.response.defer(ephemeral=True)
        await open_handler_girl_void(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(4))
        form.values.update(values)
        await form.confirm.callback(current(user, identity + 1))
        assert form.completed

    asyncio.run(
        native(
            1,
            99901,
            dict(
                name="Established forearm cybernetics",
                description="Original carried mechanical arm apparatus",
                evidence="Actual prior original ownership",
                damaged=("no",),
                weapon=("no",),
            ),
        )
    )
    ledger.safety(OTHER, "pause-girl-void-facts", ledger.status(OTHER)["revision"], pause=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.review(
            OTHER, str(uuid4()), work, state(game).revision, allow=True, account="Actual facts"
        )
    assert state(game).model_dump_json() == before
    ledger.safety(OTHER, "resume-girl-void-facts", ledger.status(OTHER)["revision"], pause=False)
    asyncio.run(
        native(3, 99903, dict(allow=("yes",), account="Actual verified preexisting arm apparatus"))
    )
    asset = service.get(PLAYER, work)["assets"][0]["id"]
    asyncio.run(native(2, 99905, dict(asset=(asset,))))
    asyncio.run(
        native(1, 99907, dict(description="The original apparatus branches into Void geometry"))
    )
    assert state(game).handler_girl_void[-1].allure and game.dice.calls == 1


def test_source_completion_label_never_replaces_actual_sole_item_asset_corruption(
    ledger, monkeypatch
):
    from girlframe.services.m3_handler_girl_void import _complete

    game, _, _, _, work, _, _, _ = high_director(ledger, monkeypatch, handler_girl=True)
    service = HandlerGirlVoidService(ledger, game)
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Existing apparatus",
        "Actual original apparatus",
        "Actual preexisting source facts",
        damaged=False,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="The actual source judge verifies the old ownership facts",
    )
    asset = service.get(PLAYER, work)["assets"][0]["id"]
    service.select(PLAYER, str(uuid4()), work, state(game).revision, asset)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="actual sole Item Asset mutation"):
        with ledger.transaction() as c:
            canon, row, episode = service._owned(c, ADMIN, work)
            event, key = str(uuid4()), str(uuid4())
            fake = episode.model_copy(
                update={
                    "phase": "allure",
                    "allure": True,
                    "corruption_event": event,
                    "rewrite": "A label without any real Asset rewrite",
                }
            )
            canon.handler_girl_void = [
                fake if x.id == episode.id else x for x in canon.handler_girl_void
            ]
            game.event(
                c,
                ADMIN.user_id,
                key,
                "m3.handler_girl_void_rewritten",
                canon,
                event_id=event,
                work_id=work,
                asset_id=asset,
            )
            _complete(game, c, row, fake, event, ADMIN, key)
    assert state(game).model_dump_json() == before


def test_original_director_human_finishes_only_owned_factual_review_after_true_director_death(
    ledger, monkeypatch
):
    game, _, _, source, work, director_service, damage_work, director = high_director(
        ledger, monkeypatch, handler_girl=True
    )
    director_service.respond(
        OTHER,
        str(uuid4()),
        damage_work,
        director_service.get(OTHER, damage_work)["revision"],
        "death",
        "The actual original Director dies from the earlier real injury",
    )
    corpse = next(x for x in state(game).world.npcs if x.id == director.entity)
    assert not corpse.alive and not state(game).director_contexts[-1].active
    service = HandlerGirlVoidService(ledger, game)
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Established implant",
        "Actual original-body preexisting implant",
        "Actual source facts from before this episode",
        damaged=False,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="The original human reviews only this already-owned factual question",
    )
    asset = service.get(PLAYER, work)["assets"][0]["id"]
    service.select(PLAYER, str(uuid4()), work, state(game).revision, asset)
    service.rewrite(
        ADMIN, str(uuid4()), work, state(game).revision, "The actual implant becomes Void geometry"
    )
    assert next(x for x in state(game).world.npcs if x.id == director.entity) == corpse
    assert not state(game).director_contexts[-1].active
    assert state(game).handler_girl_void[-1].allure
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1


def test_actual_original_handler_body_death_closes_owed_girl_void_without_asset_or_frame_invention(
    ledger, monkeypatch
):
    from girlframe.engine import m3_handler_consequences as rules
    from girlframe.services.m3_handler_consequences import finish_callback

    game, _, _, source, work, _, _, _ = high_director(ledger, monkeypatch, handler_girl=True)
    before = state(game)
    # Trusted physical-ending boundary; genuine Core source provenance is separately combat-tested.
    with ledger.transaction() as c:
        event, key = str(uuid4()), str(uuid4())
        canon, request = rules.require(
            before,
            rules.active_handler(before),
            trigger="helpless",
            source_action=None,
            source_event="synthetic-already-owed-physical-fatal-source",
            opponent=None,
            appointment=before.handler_girl_void[-1].appointment,
            occurrence="synthetic-actual-original-body-death",
        )
        canon = rules.apply(canon, request, "death", "Actual original physical body death", event)
        record = next(x for x in canon.handler_consequences if x.id == request)
        game.event(
            c, 1, key, "m3.handler_consequence_resolved", canon, event_id=event, consequence=request
        )
        finish_callback(game, c, record, event, ADMIN, key)
    final = state(game)
    assert final.handler_girl_void[-1].phase == "ended"
    assert final.handler_girl_void[-1].ended_event
    assert not final.handler_girl_void[-1].corruption_event
    assert final.held_items == before.held_items and final.sheets == before.sheets
    assert final.placements == before.placements and not final.harpy_states
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1
    with pytest.raises(WorkflowError):
        HandlerGirlVoidService(ledger, game).propose(
            ADMIN,
            str(uuid4()),
            work,
            final.revision,
            "New body's implant",
            "Cannot inherit this source",
            "Wrong body",
            damaged=False,
            weapon=False,
        )


def test_nonempty_already_void_actual_assets_coalesce_new_source_without_fabricated_answer(
    ledger, monkeypatch
):
    import sqlalchemy as sa
    from test_m2_game import answer, pass_tags

    from girlframe.database import tables as t
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_mockingbird_state import SEX
    from girlframe.services.m3_mockingbird_plays import MockingbirdService

    game, worker, gateway, _, work, _, _, _ = high_director(ledger, monkeypatch, handler_girl=True)
    service = HandlerGirlVoidService(ledger, game)
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Established implant",
        "Actual original preexisting implant",
        "Actual prior ownership facts",
        damaged=False,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="Actual source verified",
    )
    selected = service.get(PLAYER, work)["assets"][0]["id"]
    service.select(PLAYER, str(uuid4()), work, state(game).revision, selected)
    service.rewrite(
        ADMIN, str(uuid4()), work, state(game).revision, "The actual implant becomes Void"
    )
    tick(worker, gateway, 5)
    prior = state(game).handler_girl_void[-1]
    before_item = state(game).held_items[-1]
    source = MockingbirdService(game)
    trigger = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        prior.caster,
        SEX,
        (prior.actor,),
        "A second actual original-party interaction occurred",
    )
    source.attest(ADMIN, str(uuid4()), trigger["id"], prior.actor, True)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual second owned source",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "mockingbird_sex_high_commit", flag=True)
    latest = state(game).handler_girl_void[-1]
    assert latest.work != work and latest.phase == "allure" and latest.allure
    assert latest.asset is None and latest.corruption_event == latest.source_event
    assert latest.assigned_frame is None and state(game).held_items[-1] == before_item
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 2
    with ledger.engine.connect() as c:
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        continuation = c.scalar(
            sa.select(choices.c.id).where(
                choices.c.action_id == action, choices.c.kind == "mockingbird_handler_girl_void"
            )
        )
        assert continuation is not None
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(responses)
                .where(responses.c.choice_id == continuation)
            )
            == 0
        )


def test_saved_handler_girl_void_source_remains_read_only_under_withdrawn_release(
    ledger, monkeypatch
):
    game, _, _, _, work, _, _, _ = high_director(ledger, monkeypatch, handler_girl=True)
    service = HandlerGirlVoidService(ledger, game)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    saved = service.get(ADMIN, work)
    assert saved["phase"] == "facts" and not saved["can_act"]
    with ledger.engine.connect() as c:
        task = next(x for x in service._tasks(c, ADMIN) if x["id"] == work)
    assert not task["can_act"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.propose(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            "Unreviewed new item",
            "Cannot register under withdrawn release",
            "No write authority",
            damaged=False,
            weapon=False,
        )
    assert state(game).model_dump_json() == before
