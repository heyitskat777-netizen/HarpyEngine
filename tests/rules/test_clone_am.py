"""Real separate clone resources, shared native Heat, normal Tags/Bonds and source Plays."""

import asyncio
from uuid import uuid4

import pytest
from test_actor_play_service import pass_tags
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_clone_am import open_purchase
from girlframe.engine import m3_clone_am as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_clone_am import CloneService, prove_additional
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

CANARY = "SYNTHETIC_ORIGINAL_PRIVATE_NOTES_DO_NOT_COPY"


def prepared(store, tmp_path, monkeypatch, *, graft=False):
    _, game = service(store, girl="ALPHA", frame="JANUS-B" if graft else "THE RED QUEEN")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "playbooks"})
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2), 3)
        canon.sheets["2"].permissions = 6
        canon.facts.append(dict(kind="synthetic_private_memory", body=CANARY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_clone_prior", canon)
    source = CloneService(game)
    data = source.menu(PLAYER)
    if graft:
        args = (
            PLAYER,
            str(uuid4()),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            "Actual original Autocrat graft",
            "THE PRINCE",
        )
        result = source.buy(*args)
        assert result["cost"] == 3 and source.buy(*args) == result
    else:

        async def buy():
            owner = current(2, 929001)
            owner.channel_id = 900
            await owner.response.defer(ephemeral=True)
            await open_purchase(owner, source)
            form = owner.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values["account"] = "Actual original native Clone AM"
            await form.confirm.callback(current(2, 929002))
            assert form.completed

        asyncio.run(buy())
    canon = state(game)
    (copy,) = rules.copies(canon)
    assert copy.identity.name == "Perfect Copy" and not copy.identity.marked and not copy.tags
    assert set(canon.sheets) == {"2", "3"} and canon.order == (2, 3)
    assert CANARY not in copy.model_dump_json()
    return game, source, copy.ref, GameWorker(game), Gateway()


def cast_copy(game, ref):
    cast = CastService(ActorService(MissionService(game.store)))
    change(cast, PLAYER, "join", ref)
    return cast


def start(game, ref, *, play="keep_your_head", faces=(4, 5), target=None, **extra):
    source = ActorPlayService(game)
    data = source.preview(PLAYER, 900, ref)
    game.dice.faces = faces
    args = (
        PLAYER,
        str(uuid4()),
        900,
        ref,
        data["actor"]["source_sha256"],
        ActorRef.model_validate(data["adjudicator"]["ref"]) if data["adjudicator"]["ref"] else None,
        data["cast_revision"],
        PlayInput(
            play=play,
            heat=0,
            context="Actual Frame-resident copy interaction",
            trigger_confirmed=True,
            target_actor=target,
            **extra,
        ),
    )
    return source.begin(*args)["action_id"]


def finish_keep(game, *, high=False, mid=False):
    answer(
        game,
        PLAYER,
        "actor_keep",
        options=() if high else ("tough", "sexy") if mid else ("tough",),
        denied=("desperate",) if mid else (),
        text="Actual copy's own Tag" if high else "",
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="Actual source GM judges the original copy sufficient",
    )


def test_native_copy_identity_is_actual_additional_source_in_native_game_and_private_sheet(
    ledger, tmp_path, monkeypatch
):
    game, source, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    original = state(game)
    identity = rules.current(original, ref).identity.id
    private = game.sheet(PLAYER, 2)
    assert private["additional_identities"][0]["id"] == identity
    assert "additional_identities" not in game.sheet(OTHER, 2)
    assert not source.view(OTHER)["owned"]

    async def native_selector():
        owner = current(2, 929011)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_play(owner, game, _pilot=True)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert identity in dict(next(x for x in form.fields if x.key == "identity").options)

    asyncio.run(native_selector())
    casting = cast_copy(game, ref)
    change(casting, PLAYER, "withdraw", current_ref(state(game), 2))
    before_denial = state(game)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            before_denial.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="A clone-only cast cannot stand in for my original Pilot",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == before_denial and game.dice.calls == 0
    change(casting, PLAYER, "join", current_ref(state(game), 2))
    original = state(game)
    game.dice.faces = (2, 3)
    key = str(uuid4())
    args = (
        PLAYER,
        key,
        900,
        original.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=3,
            identity=identity,
            gain=3,
            context="My original copy Identity reinforces my actual action",
            trigger_confirmed=True,
        ),
    )
    action = game.begin(*args)["action_id"]
    assert not rules.current(state(game), ref).identity.marked and game.dice.calls == 0
    assert game.begin(*args)["action_id"] == action
    tick(worker, gateway, 3)
    assert rules.current(state(game), ref).identity.marked and state(game).sheets["2"].heat == 0
    pass_tags(game)
    finish_keep(game, mid=True)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    canon = state(game)
    assert [x.marked for x in canon.sheets["2"].identities] == [
        x.marked for x in original.sheets["2"].identities
    ]
    assert (
        len(canon.sheets["2"].identities) == 4
        and canon.sheets["2"].assets == original.sheets["2"].assets
    )
    with pytest.raises(ValueError, match="actual Identity IDs"):
        rules.unmark_additional(canon, 2, ("not-a-clone-identity",))
    assert source.view(PLAYER)["heat"] == 0 and CANARY not in str(source.view(PLAYER))
    forged = type(canon).model_validate_json(canon.model_dump_json())
    copy = rules.current(forged, ref)
    rules.put(
        forged,
        copy.model_copy(update=dict(identity=copy.identity.model_copy(update=dict(marked=False)))),
    )
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="actual saved"):
        prove_additional(game, c, forged, 2, identity)
    tick(worker, gateway, 5)
    game.dice.faces = (4, 5)
    dive = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="The original Pilot, rather than her copy, communes with her actual Frame",
            piloting=True,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual original Pilot embraces her Frame",
    )
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields=dict(asset=asset.id),
        text="The actual Frame Asset is rewritten by Void",
    )
    assert game.inspect(PLAYER, dive)["state"] == "complete"
    assert not rules.current(state(game), ref).identity.marked and game.dice.calls == 2
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).void


def test_grafted_copy_real_keep_tag_repeated_in_next_scene_replaces_only_copy_identity(
    ledger, tmp_path, monkeypatch
):
    game, source, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch, graft=True)
    cast_copy(game, ref)
    original = state(game)
    action = start(game, ref, faces=(6, 6))
    tick(worker, gateway, 3)
    pass_tags(game)
    finish_keep(game, high=True)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    (tag,) = rules.tags(state(game), ref)
    for round_no in (0, 1):
        if round_no:
            game.close_scene(ADMIN, str(uuid4()), 900)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            game.join_scene(PLAYER, str(uuid4()), 900)
            game.join_scene(OTHER, str(uuid4()), 900)
            game.join_scene(ADMIN, str(uuid4()), 900)
            cast_copy(game, ref)
        action = start(game, ref, faces=(2, 3))
        tick(worker, gateway, 3)
        answer(game, ADMIN, "tag_window", options=("pass",))
        answer(game, PLAYER, "tag_window", options=("pass",))
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=(tag.id,),
            number=1,
            fields={"as_actor": current_ref(state(game), 3).token},
            text="Actual observed copy Tag relevance",
        )
        if round_no:
            copy = rules.current(state(game), ref)
            decision = game.decision(
                PLAYER, next(x for x in game.choices(PLAYER) if x["kind"] == "tag_resolution")["id"]
            )
            assert decision["copy_identity_cap"] == 1
            answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(copy.identity.id,))
        finish_keep(game)
        tick(worker, gateway, 5)
        assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = state(game)
    assert rules.current(actual, ref).identity.name == tag.label and not rules.tags(actual, ref)
    assert actual.sheets["2"].identities == original.sheets["2"].identities
    assert actual.sheets["2"].tags == original.sheets["2"].tags and actual.sheets["2"].heat == 0
    data = ActorPlayService(game).preview(PLAYER, 900, ref)
    before = actual.model_dump_json()
    with pytest.raises((ValueError, WorkflowError), match="cannot Dive Deep"):
        ActorPlayService(game).begin(
            PLAYER,
            str(uuid4()),
            900,
            ref,
            data["actor"]["source_sha256"],
            None,
            data["cast_revision"],
            PlayInput(
                play="dive_deep",
                heat=0,
                context="Forbidden actual clone Dive",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == before and game.dice.calls == 3


def flirt(game, ref, worker, gateway, *, faces=(4, 5), extra=None):
    action = start(game, ref, play="flirt", target=current_ref(state(game), 3), faces=faces)
    tick(worker, gateway, 3)
    pass_tags(game)
    if sum(faces) > 7:
        answer(
            game,
            PLAYER,
            "clone_flirt_actor",
            options=("name",),
            fields=dict(extra=extra) if extra else {},
            text="Actual source complication" if extra else "",
        )
    answer(game, OTHER, "clone_flirt_target", text="Use my actual chosen name")
    return action


def test_actual_copy_flirt_mid_followthrough_confirmation_bond_then_low_weakens_only_copy_edge(
    ledger, tmp_path, monkeypatch
):
    game, source, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    cast_copy(game, ref)
    target = current_ref(state(game), 3)
    original_bond = depth(state(game), current_ref(state(game), 2), target)
    action = flirt(game, ref, worker, gateway)
    assert (
        game.inspect(PLAYER, action)["state"] == "complete" and depth(state(game), ref, target) == 0
    )
    tick(worker, gateway, 5)
    owed = next(x for x in state(game).obligations if x.kind == "clone_flirt_followthrough")
    follow = source.fulfill_followthrough(
        PLAYER, str(uuid4()), owed.id, "I actually use her chosen name", channel=900
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    answer(
        game,
        OTHER,
        "clone_flirt_followthrough_confirm",
        flag=True,
        text="She actually followed through",
    )
    assert (
        game.inspect(PLAYER, follow)["state"] == "complete" and depth(state(game), ref, target) == 1
    )
    tick(worker, gateway, 5)
    low = flirt(game, ref, worker, gateway, faces=(2, 3))
    assert game.inspect(PLAYER, low)["state"] == "complete" and depth(state(game), ref, target) == 0
    assert depth(state(game), current_ref(state(game), 2), target) == original_bond
    assert game.dice.calls == 2


def test_copy_flirt_high_owed_tag_is_separate_then_real_handler_response_holds_and_finishes(
    ledger, tmp_path, monkeypatch
):
    game, _, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    cast_copy(game, ref)
    high = flirt(game, ref, worker, gateway, faces=(6, 6), extra="owe")
    answer(game, OTHER, "clone_flirt_owe", text="Actual owed copy Tag")
    assert game.inspect(PLAYER, high)["state"] == "complete"
    (tag,) = rules.tags(state(game), ref)
    assert tag.giver_actor == current_ref(state(game), 3)
    assert any(
        x.kind == "clone_cannot_refuse_until_tag_resolved" and x.details["tag"] == tag.id
        for x in state(game).obligations
    )
    assert not state(game).sheets["2"].tags
    assert rules.cannot_refuse(state(game), ref, current_ref(state(game), 3))
    assert not rules.cannot_refuse(
        state(game), current_ref(state(game), 2), current_ref(state(game), 3)
    )
    tick(worker, gateway, 5)
    noticed = flirt(game, ref, worker, gateway, faces=(6, 6), extra="handler")
    grant = state(game).handler_plays[-1]
    assert set(grant.targets) == {ref, current_ref(state(game), 3)}
    assert game.inspect(PLAYER, noticed)["state"] != "complete"
    handler = HandlerPlayService(ledger)
    data = handler.get(ADMIN, grant.id)
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="Actual GM supplies the concrete scene information"),
    )
    assert game.inspect(PLAYER, noticed)["state"] == "complete" and game.dice.calls == 2
    resolved = state(game)
    old_native = resolved.sheets["2"].identities.copy()
    rules.tag(resolved, ref, tag.id, marked=True)
    rules.embrace(resolved, ref, tag.id, (rules.current(resolved, ref).identity.id,))
    assert not rules.cannot_refuse(resolved, ref, current_ref(resolved, 3))
    assert resolved.sheets["2"].identities == old_native


def test_copy_flirt_high_escape_has_real_original_target_helplessness(
    ledger, tmp_path, monkeypatch
):
    game, _, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    cast_copy(game, ref)
    action = flirt(game, ref, worker, gateway, faces=(6, 6), extra="escape")
    answer(game, OTHER, "clone_flirt_escape", options=("helpless",))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert is_helpless(state(game), current_ref(state(game), 3), ref)
    assert not is_helpless(state(game), current_ref(state(game), 3), current_ref(state(game), 2))


def test_copy_flirt_escape_actual_asset_and_actual_child_play_preserve_source_and_receipts(
    ledger, tmp_path, monkeypatch
):
    game, _, ref, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    cast_copy(game, ref)
    first = flirt(game, ref, worker, gateway, faces=(6, 6), extra="escape")
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "frame" and not x.damaged)
    answer(game, OTHER, "clone_flirt_escape", options=("damage",), denied=(asset.id,))
    assert game.inspect(PLAYER, first)["state"] == "complete"
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    tick(worker, gateway, 5)
    second = flirt(game, ref, worker, gateway, faces=(6, 6), extra="escape")
    answer(game, OTHER, "clone_flirt_escape", options=("play",))
    assert game.inspect(PLAYER, second)["state"] != "complete"
    game.dice.faces = (2, 3)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            parent=second,
            context="My actual original Girl acts to escape the copy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual escaping Girl's own result")
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, second)["state"] == "complete"
    )
    assert game.dice.calls == 3
