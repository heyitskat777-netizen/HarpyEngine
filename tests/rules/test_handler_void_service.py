"""One actual rolled Mock source waits for real original Handler Void outcomes."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current
from test_mockingbird_sex import high_handler

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_void import open_handler_void
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("choice", ["knife", "drugs", "surgery"])
def test_real_source_owned_three_choices_and_required_followthrough_never_touch_pilot_resources(
    ledger, monkeypatch, choice
):
    game, worker, gateway, source, work = high_handler(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)
    initial = state(game)
    sheets = {k: x.model_dump_json() for k, x in initial.sheets.items()}
    data = service.get(ADMIN, work)
    with pytest.raises(WorkflowError):
        service.choose(
            OTHER,
            str(uuid4()),
            work,
            data["revision"],
            choice,
            "Not the real affected Handler",
            site="Left arm",
            manifestation="flesh",
        )
    key = str(uuid4())
    kwargs = dict(site="Left forearm", manifestation="flesh" if choice == "drugs" else None)
    result = service.choose(
        ADMIN,
        key,
        work,
        data["revision"],
        choice,
        "Actual performed cut/injection or actual personnel surgery request",
        **kwargs,
    )
    snapshot = state(game).model_dump_json()
    assert (
        service.choose(
            ADMIN,
            key,
            work,
            data["revision"],
            choice,
            "Actual performed cut/injection or actual personnel surgery request",
            **kwargs,
        )
        == result
    )
    assert state(game).model_dump_json() == snapshot and game.dice.calls == 1
    if choice == "surgery":
        assert game.inspect(PLAYER, source)["state"] != "complete"
        assert state(game).handler_void[-1].void_present
        with pytest.raises(WorkflowError):
            service.record_surgery(
                ADMIN,
                str(uuid4()),
                work,
                state(game).revision,
                "Not yet performed",
                performed=False,
                removed=False,
            )
        service.record_surgery(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            "Actual personnel performed source-local surgery and removed this corruption",
            performed=True,
            removed=True,
        )
    else:
        assert game.inspect(PLAYER, source)["state"] == "complete"
    if choice == "drugs":
        assert state(game).handler_void[-1].void_present
        with ledger.engine.connect() as c:
            task = next(x for x in service._tasks(c, ADMIN) if x["id"] == work)
        assert task["state"] == "stabilized" and task["can_act"]
        service.choose(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            "surgery",
            "Actual follow-through removal request",
        )
        service.record_surgery(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            "Actual later surgery removes the original localized corruption",
            performed=True,
            removed=True,
        )
    final = state(game)
    assert final.handler_void[-1].phase == "removed" and not final.handler_void[-1].void_present
    assert {k: x.model_dump_json() for k, x in final.sheets.items()} == sheets
    assert final.order == initial.order and final.handler_heat == initial.handler_heat
    assert final.handler_void[-1].body == initial.handler_void[-1].body
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_native_original_handler_drugs_and_performed_surgery_preserve_pause_and_ownership(
    ledger, monkeypatch
):
    game, _, _, _, work = high_handler(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)

    async def choose():
        caller = current(1, 99801)
        await caller.response.defer(ephemeral=True)
        await open_handler_void(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        form.values.update(
            choice=("drugs",),
            site="Left hand",
            manifestation=("bones",),
            account="Actual injection halts the growth in my hand",
        )
        await form.confirm.callback(current(1, 99802))
        assert form.completed

    asyncio.run(choose())
    assert state(game).handler_void[-1].phase == "stabilized"
    ledger.safety(OTHER, "pause-source-treatment", ledger.status(OTHER)["revision"], pause=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.choose(ADMIN, str(uuid4()), work, state(game).revision, "surgery", "Actual request")
    assert state(game).model_dump_json() == before
    ledger.safety(OTHER, "resume-source-treatment", ledger.status(OTHER)["revision"], pause=False)
    service.choose(
        ADMIN, str(uuid4()), work, state(game).revision, "surgery", "Actual removal request"
    )

    async def surgery():
        caller = current(1, 99803)
        await caller.response.defer(ephemeral=True)
        await open_handler_void(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            account="Actual personnel removed localized corruption on site",
            performed=("yes",),
            removed=("yes",),
        )
        await form.confirm.callback(current(1, 99804))
        assert form.completed

    asyncio.run(surgery())
    assert not state(game).handler_void[-1].void_present and game.dice.calls == 1


def high_director(store, monkeypatch, *, handler_girl=False):
    from types import SimpleNamespace

    from test_battle_director import source
    from test_cast_service import change
    from test_m2_game import Dice, Gateway, answer, pass_tags

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_mockingbird_state import SEX
    from girlframe.services import m3_mockingbird_plays as plays
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    game, _, _, _, director_service, damage_work, director = source(store)
    game.dice, game.rng_source = Dice((6, 6)), "test_injected"
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    monkeypatch.setattr(plays, "sex_ready", lambda: True)
    cast = CastService(ActorService(MissionService(store)))
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    target = director
    if handler_girl:
        from girlframe.engine.m3_actor_state import ActorRef

        target = ActorRef(
            kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id
        )
        change(cast, ADMIN, "join", target)
    actor = current_ref(state(game), PLAYER.user_id)
    source_service = plays.MockingbirdService(game)
    trigger = source_service.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        SEX,
        (target,),
        "Actual player-authored interaction with this original counterpart",
    )
    source_service.attest(
        ADMIN if handler_girl else OTHER, str(uuid4()), trigger["id"], target, True
    )
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual owned Director source",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "mockingbird_sex_high_commit", flag=True)
    return (
        game,
        worker,
        gateway,
        identity,
        state(game).handler_girl_void[-1].work
        if handler_girl
        else state(game).handler_void[-1].work,
        director_service,
        damage_work,
        director,
    )


def test_real_director_handler_void_belongs_to_her_actual_controller_and_never_main_handler(
    ledger, monkeypatch
):
    game, _, _, source, work, _, _, director = high_director(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)
    initial = state(game)
    episode = initial.handler_void[-1]
    assert episode.actor == episode.body == director and episode.controller == 3
    with pytest.raises(WorkflowError):
        service.choose(
            ADMIN, str(uuid4()), work, initial.revision, "knife", "Not that body", site="Arm"
        )
    service.choose(
        OTHER,
        str(uuid4()),
        work,
        initial.revision,
        "knife",
        "The actual Director cuts the source corruption from her forearm",
        site="Forearm",
    )
    final = state(game)
    assert final.handler_void[-1].phase == "removed"
    assert final.handler_heat == initial.handler_heat and final.handler_tags == initial.handler_tags
    assert final.sheets == initial.sheets and final.world == initial.world
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1


def test_real_original_director_death_closes_only_her_owed_void_source_without_removal_or_successor(
    ledger, monkeypatch
):
    game, _, _, source, work, director_service, damage_work, director = high_director(
        ledger, monkeypatch
    )
    director_service.respond(
        OTHER,
        str(uuid4()),
        damage_work,
        director_service.get(OTHER, damage_work)["revision"],
        "death",
        "The actual original Director dies from her already owed source injury",
    )
    episode = state(game).handler_void[-1]
    assert episode.actor == director and episode.phase == "ended"
    assert episode.void_present and not episode.removal_event
    assert game.inspect(PLAYER, source)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert all(x["id"] != work for x in HandlerVoidService(ledger, game)._tasks(c, OTHER))


def test_source_label_cannot_complete_real_handler_void_from_another_human(ledger, monkeypatch):
    game, _, _, _, work = high_handler(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="authenticated"):
        with ledger.transaction() as c:
            canon, row, episode = service._proof(c, work)
            event, key = str(uuid4()), str(uuid4())
            fake = episode.model_copy(
                update={
                    "phase": "removed",
                    "choice": "knife",
                    "choice_event": event,
                    "void_present": False,
                    "removal_event": event,
                    "wound": "A label cannot impersonate the actual original patient's action",
                }
            )
            canon.handler_void = [fake if x.id == episode.id else x for x in canon.handler_void]
            game.event(
                c,
                OTHER.user_id,
                key,
                "m3.handler_void_choice",
                canon,
                event_id=event,
                work_id=work,
                episode_id=episode.id,
                choice="knife",
            )
            service._complete(c, row, fake, event, OTHER, key)
    assert state(game).model_dump_json() == before


def test_saved_actual_handler_void_is_private_read_only_when_m3_release_is_withdrawn(
    ledger, monkeypatch
):
    game, _, _, _, work = high_handler(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    saved = service.get(ADMIN, work)
    assert saved["episode"]["phase"] == "choice" and not saved["can_act"]
    with ledger.engine.connect() as c:
        task = next(x for x in service._tasks(c, ADMIN) if x["id"] == work)
    assert not task["can_act"]
    with pytest.raises(WorkflowError):
        service.get(OTHER, work)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.choose(
            ADMIN,
            str(uuid4()),
            work,
            state(game).revision,
            "knife",
            "Cannot write under a withdrawn release",
            site="Forearm",
        )
    assert state(game).model_dump_json() == before
