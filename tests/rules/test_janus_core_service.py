"""Real owner request/controller facts/review, shared hardware and durable native setup."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_janus_core import facts
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_requisition_service import ready as campaign

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_janus import open_core_setup
from girlframe.engine import m3_janus as rules
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_janus import JanusService, prove_core
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    _, game = campaign(store, frame="JANUS-B")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.CORE, rules.BATTERY))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    return JanusService(game), game


def change(service, viewer, identity, **kwargs):
    data = service.get(viewer, identity)
    return service.change(
        viewer, str(uuid4()), identity, data["revision"], data["game_revision"], **kwargs
    )


def admitted(store, tmp_path, monkeypatch):
    service, game = ready(store, tmp_path, monkeypatch)
    identity = service.request(PLAYER, "actual-owner-core-request", 3)["id"]
    change(service, OTHER, identity, facts=facts())
    change(
        service,
        ADMIN,
        identity,
        approve=True,
        account="Actual established original body facts reviewed",
    )
    return service, game, identity, rules.ref(state(game).janus_cores[0])


def test_actual_owner_controller_and_judge_complete_distinct_source_admission_once(
    ledger, tmp_path, monkeypatch
):
    service, game = ready(ledger, tmp_path, monkeypatch)
    initial = state(game)
    original = initial.model_dump_json()
    identity = service.request(PLAYER, "actual-original-core-request", 3)["id"]
    assert not state(game).janus_cores
    request = service.get(OTHER, identity)
    with pytest.raises(WorkflowError):
        service.change(
            PLAYER,
            "cannot-propose-others-facts",
            identity,
            request["revision"],
            request["game_revision"],
            facts=facts(),
        )
    service.change(
        OTHER,
        "actual-controller-facts",
        identity,
        request["revision"],
        request["game_revision"],
        facts=facts(),
    )
    data = service.get(ADMIN, identity)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.change(
            OTHER,
            "cannot-self-foundation-approve",
            identity,
            data["revision"],
            data["game_revision"],
            approve=True,
            account="Not the actual source judge",
        )
    assert state(game).model_dump_json() == before
    result = service.change(
        ADMIN,
        "actual-original-judge",
        identity,
        data["revision"],
        data["game_revision"],
        approve=True,
        account="Actual source review",
    )
    assert (
        service.change(
            ADMIN,
            "actual-original-judge",
            identity,
            data["revision"],
            data["game_revision"],
            approve=True,
            account="Actual source review",
        )
        == result
    )
    actual = state(game)
    assert len(actual.janus_cores) == 1
    actor = rules.ref(actual.janus_cores[0])
    assert actual.sheets == initial.sheets and actual.placements == initial.placements
    assert not actual.harpy_states and not actual.career_archives and actual.world == initial.world
    with ledger.engine.connect() as c:
        value = prove_core(c, game, actual, actor)
        view = resolve(actual, actor, profiles(c, ledger.campaign_id))
        assert view.label == "Harpy Core" and value.controller == 3
    game.rebuild()
    assert state(game).model_dump_json() == actual.model_dump_json()
    assert initial.model_dump_json() == original


def test_actual_native_request_controller_facts_and_review_use_real_confirm_buttons(
    ledger, tmp_path, monkeypatch
):
    service, game = ready(ledger, tmp_path, monkeypatch)

    async def run():
        owner = current(2, 97301)
        await owner.response.defer(ephemeral=True)
        await open_core_setup(owner, service)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(controller=("3",), confirm=("yes",))
        await form.confirm.callback(current(2, 97302))
        assert form.completed and not state(game).janus_cores
        with ledger.engine.connect() as c:
            identity = service._tasks(c, OTHER)[0]["id"]
        controller = current(3, 97303)
        await controller.response.defer(ephemeral=True)
        await open_core_setup(controller, service, identity)
        picker = controller.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(controller, "0")
        form = controller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(2))
        assert not any(field.key == "name" for field in form.fields)
        form.values.update(
            appearance="Actual original unnamed body",
            heat="2",
            identities="Actual ID",
            exposed=("no",),
            account="No existing Girl Assets established, factual approval requested",
        )
        await form.confirm.callback(current(3, 97304))
        assert form.completed and not state(game).janus_cores
        judge = current(1, 97305)
        await judge.response.defer(ephemeral=True)
        await open_core_setup(judge, service, identity)
        review = judge.edit_original_response.call_args.kwargs["view"]
        review.values.update(approve=("yes",), account="Actual source facts reviewed by Foundation")
        await review.confirm.callback(current(1, 97306))
        assert review.completed and len(state(game).janus_cores) == 1
        assert state(game).janus_cores[0].name == "Harpy Core"

    asyncio.run(run())


def test_failed_final_admission_work_rolls_back_actual_core_and_same_source_retry_is_safe(
    ledger, tmp_path, monkeypatch
):
    service, game = ready(ledger, tmp_path, monkeypatch)
    identity = service.request(PLAYER, "owner-request", 3)["id"]
    change(service, OTHER, identity, facts=facts())
    data = service.get(ADMIN, identity)
    before = state(game).model_dump_json()
    original = service._save
    monkeypatch.setattr(
        service, "_save", lambda *args: (_ for _ in ()).throw(RuntimeError("actual work failure"))
    )
    with pytest.raises(RuntimeError):
        service.change(
            ADMIN,
            "retry-owned-admission",
            identity,
            data["revision"],
            data["game_revision"],
            approve=True,
            account="Actual factual review",
        )
    assert state(game).model_dump_json() == before and not state(game).janus_cores
    monkeypatch.setattr(service, "_save", original)
    service.change(
        ADMIN,
        "retry-owned-admission",
        identity,
        data["revision"],
        data["game_revision"],
        approve=True,
        account="Actual factual review",
    )
    assert len(state(game).janus_cores) == 1


def cast_core(service, game, actor):
    from test_cast_service import change as cast_change

    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    approval = service.store.policy.m3_approval
    service.store.policy = service.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    cast = CastService(ActorService(MissionService(service.store)))
    cast_change(cast, OTHER, "join", actor)
    return cast


def test_printed_restrained_blocks_actual_shared_play_before_rng_and_native_menu(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_actor_plays import open_actor_play
    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m3_actor_plays import ActorPlayService

    setup, game, _, actor = admitted(ledger, tmp_path, monkeypatch)
    cast_core(setup, game, actor)
    source = ActorPlayService(game)
    data = source.preview(OTHER, 900, actor)
    calls = game.dice.calls
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="RESTRAINED_CORE"):
        source.begin(
            OTHER,
            "cannot-play-restrained-core",
            900,
            actor,
            data["actor"]["source_sha256"],
            None,
            data["cast_revision"],
            PlayInput(
                play="check_sensors",
                trigger_confirmed=True,
                heat=0,
                context="Actual Core cannot make this Play while Restrained",
            ),
        )
    assert state(game).model_dump_json() == before and game.dice.calls == calls

    async def run():
        caller = current(3, 97310)
        await caller.response.defer(ephemeral=True)
        await open_actor_play(caller, game, actor, channel=900)
        assert "Restrained" in caller.edit_original_response.call_args.kwargs["content"]
        assert caller.edit_original_response.call_args.kwargs.get("view") is None

    asyncio.run(run())


def test_actual_printed_core_pain_tag_has_proved_ooc_source_without_gm_persona_bond(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_tag_setters import ooc_setter

    _, game, _, actor = admitted(ledger, tmp_path, monkeypatch)
    actual = state(game)
    value = rules.core(actual, actor)
    pain = next(x for x in value.tags if x.id == value.baseline_tags["surgery"])
    with ledger.engine.connect() as c:
        assert ooc_setter(c, ledger, actor, pain) == ADMIN.user_id
    assert pain.giver_ref is None and pain.giver_character is None
    assert not actual.actor_bonds


def test_bound_core_frame_voice_is_original_controller_without_spoken_consent_or_pc_alias(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_physical import frame_voice

    _, game, _, actor = admitted(ledger, tmp_path, monkeypatch)
    actual = state(game)
    value = rules.core(actual, actor)
    assert frame_voice(actual, value.frame_owner, value.frame_instance) == OTHER.user_id
    assert value.controller == OTHER.user_id and actor.entity != str(OTHER.user_id)
    with pytest.raises(ValueError, match="MUZZLED_CORE"):
        rules.can_speak(actual, actor)


def test_source_owned_setup_inbox_keeps_original_next_author_and_native_route(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.inbox import InboxView
    from girlframe.services.inbox import InboxService

    service, game = ready(ledger, tmp_path, monkeypatch)
    identity = service.request(PLAYER, "actual-inbox-core-source", 3)["id"]
    inbox = InboxService(ledger)
    player_item = next(x for x in inbox.items(PLAYER) if x.identity == identity)
    owner_item = next(x for x in inbox.items(OTHER) if x.identity == identity)
    assert player_item.task == owner_item.task == "m3_janus_core"
    assert not player_item.incoming and owner_item.incoming

    async def run():
        caller = current(3, 97320)
        await caller.response.defer(ephemeral=True)
        view = InboxView(inbox, 3)
        await view.route(caller, owner_item)
        picker = caller.edit_original_response.call_args.kwargs["view"]
        assert "actual existing Girl Assets" in dict(picker.options)["0"]

    asyncio.run(run())
    change(service, OTHER, identity, facts=facts())
    assert not next(x for x in inbox.items(OTHER) if x.identity == identity).incoming
    assert next(x for x in inbox.items(ADMIN) if x.identity == identity).incoming
    assert not state(game).janus_cores


def test_controller_can_withdraw_pending_setup_during_pause_without_creating_core(
    ledger, tmp_path, monkeypatch
):
    service, game = ready(ledger, tmp_path, monkeypatch)
    identity = service.request(PLAYER, "actual-own-request", 3)["id"]
    data = service.get(OTHER, identity)
    ledger.safety(OTHER, "pause-core-setup", ledger.status(OTHER)["revision"], pause=True)
    result = service.withdraw(
        OTHER, "actual-core-controller-withdrawal", identity, data["revision"]
    )
    assert result["phase"] == "withdrawn" and not state(game).janus_cores
    assert (
        service.withdraw(OTHER, "actual-core-controller-withdrawal", identity, data["revision"])
        == result
    )
    assert not service.menu(PLAYER)["tasks"][0]["actionable"]
