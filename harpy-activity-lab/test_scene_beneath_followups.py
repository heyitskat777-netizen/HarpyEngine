"""Exercise the handoffs exposed by the scene modal on a real synthetic ledger."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
import test_m2_game
from ai_native_plays import ActivityNativePlays
from owned_followups import OwnedFollowups
from scene_beneath_work import SceneBeneathWork
from scene_plays import BENEATH, ScenePlays
from test_beneath_discipline import pending
from test_beneath_service import rolled
from test_defeat_service import required
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_m2_game import answer as native_answer

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services import m3_beneath
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import load_registry
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def adapter(game):
    return ScenePlays(game, 900, ADMIN, PLAYER, OTHER, handler_proxy=False)


def options(scene, viewer):
    native = scene.game.scene_info(viewer, 900)
    return scene.play_options(
        viewer,
        native,
        scene.game.sheet(viewer),
        state(scene.game),
        bool(native["lock"] and native["lock"]["state"] != "released"),
        False,
        {},
    )[BENEATH]


def choice(scene, viewer, kind):
    return next(row for row in options(scene, viewer)["choices"] if row["kind"] == kind)


def submit(scene, viewer, item, answer, *, key=None):
    return scene.perform_scene(
        viewer,
        key or str(uuid4()),
        "scene-choice",
        {
            "id": item["id"],
            "revision": item["revision"],
            "role": item["role"],
            "answer": answer,
        },
    )


def test_scene_punishment_is_projected_to_its_owner_and_applied_once(ledger):
    _, game, _, _, root, _ = pending(ledger)
    scene = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
    assigned = scene.view(PLAYER)[0]
    assert not scene.view(OTHER)
    assert "quality_time" in {form["kind"] for form in assigned["forms"]}
    answer = {
        "kind": "quality_time",
        "tag": "Reviewed",
    }
    with pytest.raises(WorkflowError):
        scene_work(scene, OTHER, assigned, answer)
    with pytest.raises(WorkflowError):
        scene_work(SceneBeneathWork(game, dict), PLAYER, assigned, answer)
    key = str(uuid4())
    result = scene_work(scene, PLAYER, assigned, answer, key=key)
    assert scene_work(scene, PLAYER, assigned, answer, key=key) == result
    assert options(adapter(game), PLAYER)["current"]["state"] == "complete"
    assert [tag.label for tag in state(game).sheets["3"].tags].count("Reviewed") == 1
    assert game.inspect(PLAYER, root)["receipt"]["faces"] == [6, 6]


def scene_work(scene, viewer, card, answer, key=None, action=None):
    request = {
        k: v
        for k, v in card.items()
        if k in ("id", "root", "revision", "work_revision", "expected", "permission")
    }
    return scene.perform(
        viewer,
        key or str(uuid4()),
        request | {"action": action or card["action"], "answer": answer},
    )


@pytest.mark.parametrize(
    ("kind", "legacy"),
    [("sedation", False), ("sedation", True), ("frame_disassembly", False)],
)
def test_specialty_followups_keep_their_source_and_actual_owners(ledger, monkeypatch, kind, legacy):
    if kind == "sedation":
        selected = test_m2_game.selected
        ready = test_m2_game.ready
        monkeypatch.setattr(
            test_m2_game,
            "selected",
            lambda girl, frame: selected(girl, "PROJECT ANKOU"),
        )
        monkeypatch.setattr(
            test_m2_game,
            "ready",
            lambda store, girl, frame: ready(store, girl, frame, other_frame="PROJECT ANKOU"),
        )
    _, game, worker, gateway, root, _ = pending(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets["3"]
        if kind == "sedation":
            for identity in sheet.identities[2:]:
                identity.marked = True
            details = {"identities": [identity.id for identity in sheet.identities[:2]]}
        else:
            frames = [asset for asset in sheet.assets if asset.family == "frame"]
            for asset in frames[1:]:
                asset.void = True
            details = {"asset": frames[0].id}
        game.event(c, ADMIN.user_id, "before-scene-punishment", "synthetic.baseline", canon)

    def rooms():
        return {900: ("relay", "Relay operations")}

    followups = OwnedFollowups(game, rooms)
    scene = SceneBeneathWork(game, rooms, followups)

    def specialty(viewer, action):
        result = [
            card
            for card in scene.view(viewer, followups.view(viewer))
            if card.get("specialty") and card["action"] == action
        ]
        assert all(card["root"] == root and card["room"] == "relay" for card in result)
        return result

    assigned = scene.view(PLAYER)[0]
    if kind == "frame_disassembly":
        scene_work(
            scene,
            PLAYER,
            assigned,
            {"kind": kind, **details},
            action="request_punishment_consult",
        )
        scene_work(scene, ADMIN, scene.view(ADMIN)[0], {"approve": True})
        scene_work(scene, PLAYER, scene.view(PLAYER)[0], {})
    else:
        with monkeypatch.context() as old:
            if legacy:
                old.setattr(m3_beneath, "discipline_ready", lambda *args: False)
            scene_work(scene, PLAYER, assigned, {"kind": kind, **details})
    if legacy:
        assert game.inspect(PLAYER, root)["state"] == "awaiting_choices"
        (recovery,) = specialty(OTHER, "recover_scene_followup")
        answer = {"action": recovery["resume_action"]}
        with pytest.raises(WorkflowError):
            scene_work(scene, PLAYER, recovery, answer)
        key = str(uuid4())
        result = scene_work(scene, OTHER, recovery, answer, key=key)
        assert scene_work(scene, OTHER, recovery, answer, key=key) == result
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"

    if kind == "sedation":
        (activation,) = specialty(OTHER, "feedback_activate")
        assert not specialty(PLAYER, "feedback_activate")
        activate = {
            "channel": "900",
            "account": "Continue Feedback in the original scene.",
        }
        with pytest.raises(WorkflowError):
            scene_work(scene, PLAYER, activation, activate)
        with pytest.raises(WorkflowError):
            scene_work(scene, OTHER, activation | {"root": str(uuid4())}, activate)
        key = str(uuid4())
        receipt = scene_work(scene, OTHER, activation, activate, key=key)
        assert scene_work(scene, OTHER, activation, activate, key=key) == receipt
        assert asyncio.run(SourcePauseWorker(game).tick(Gateway()))
        (prompt,) = specialty(OTHER, "feedback_choose")
        scene_work(
            scene,
            OTHER,
            prompt,
            {
                "choice": "purpose",
                "target": current_ref(state(game), PLAYER.user_id).token,
                "account": "Ask the other pilot for a purpose.",
            },
        )
        (response,) = specialty(PLAYER, "feedback_purpose")
        answer = {"given": "yes", "account": "Hold the western relay"}
        with pytest.raises(WorkflowError):
            scene_work(scene, OTHER, response, answer)
        scene_work(scene, PLAYER, response, answer)
        (identity,) = specialty(OTHER, "feedback_identity")
        replacement = state(game).sheets["3"].identities[0].id
        scene_work(scene, OTHER, identity, {"replace": replacement})
        assert not specialty(OTHER, "feedback_identity")
        assert any(x.name == answer["account"] for x in state(game).sheets["3"].identities)
    else:
        (threshold,) = specialty(OTHER, "resolve_void")
        assert not specialty(PLAYER, "resolve_void")
        answer = {
            "operation": "propose_occupancy",
            "values": {
                "mode": "outside_frame",
                "account": "The pilot was outside the cockpit.",
            },
        }
        with pytest.raises(WorkflowError):
            scene_work(scene, PLAYER, threshold, answer)
        scene_work(scene, OTHER, threshold, answer)
        reopened = GameService(ledger)
        followups = OwnedFollowups(reopened, rooms)
        scene = SceneBeneathWork(reopened, rooms, followups)
        (confirmation,) = specialty(ADMIN, "resolve_void")
        scene_work(
            scene,
            ADMIN,
            confirmation,
            {
                "operation": "confirm_occupancy",
                "values": {"account": "The Handler saw the pilot outside."},
            },
        )
        assert followups.void.get(OTHER, threshold["id"])["stage"] == "abandoned"
    assert game.inspect(PLAYER, root)["receipt"]["faces"] == [6, 6]


def test_scene_moderate_proposal_returns_to_inflictor_and_stays_exact(ledger):
    _, game, _, _, root, _ = pending(ledger)
    scene = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
    card = scene.view(PLAYER)[0]
    disassembly = next(form for form in card["forms"] if form["kind"] == "frame_disassembly")
    asset = disassembly["fields"][0]["options"][0][0]
    answer = {"kind": "frame_disassembly", "asset": asset}
    with pytest.raises(WorkflowError, match="HANDLER_CONSULT_REQUIRED"):
        scene_work(scene, PLAYER, card, answer)
    scene_work(scene, PLAYER, card, answer, action="request_punishment_consult")
    assert scene.view(PLAYER)[0]["action"] is None
    approval = scene.view(ADMIN)[0]
    assert approval["root"] == root
    with pytest.raises(WorkflowError):
        scene_work(scene, PLAYER, approval, {"approve": True})
    scene_work(scene, ADMIN, approval, {"approve": True})
    approved = scene.view(PLAYER)[0]
    assert approved["action"] == "apply_approved_punishment"
    scene_work(scene, PLAYER, approved, {})
    assert asset not in {item.id for item in state(game).sheets["3"].assets}
    assert game.inspect(PLAYER, root)["state"] == "complete"


def test_beneath_permission_stays_in_its_original_scene(ledger):
    from test_beneath_permissions import locked

    _, game, worker, gateway, identity = locked(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        tag = canon.sheets["3"].tags[-1]
        tag.marked = True
        game.event(c, 1, "synthetic-marked-tag", "synthetic.state", canon)
    tick(worker, gateway, 5)
    game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            context="The marked Tag comes up again.",
            trigger_confirmed=True,
            heat=0,
        ),
    )
    tick(worker, gateway, 3)
    for viewer in (OTHER, ADMIN):
        native_answer(game, viewer, "tag_window", options=("pass",))
    native_answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(tag.id,),
        number=-1,
        text="The marked Tag affects this confrontation.",
    )
    scene = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
    (card,) = scene.view(PLAYER)
    assert card["id"] == identity and card["action"] == "allow_locked_tag"
    assert not scene.view(ADMIN)
    read_only, blocked = scene.view(OTHER)
    assert read_only["action"] is None and blocked["root"] == card["root"]
    assert [key for key, _ in blocked["decision_fields"][0]["options"]] == ["embrace"]
    with pytest.raises(WorkflowError):
        scene_work(scene, OTHER, blocked, {"options": ["reject"]})
    with pytest.raises(WorkflowError):
        scene_work(scene, OTHER, card, True)
    key = str(uuid4())
    reply = scene_work(scene, PLAYER, card, True, key=key)
    assert scene_work(scene, PLAYER, card, True, key=key) == reply
    read_only, unlocked = SceneBeneathWork(
        GameService(ledger), lambda: {900: ("relay", "Relay operations")}
    ).view(OTHER)
    assert "Consent recorded" in read_only["scene"]
    assert not state(game).sheets["3"].tags[-1].rejection_pending
    with pytest.raises(WorkflowError):
        scene_work(scene, PLAYER, unlocked, {"options": ["reject"]})
    scene_work(scene, OTHER, unlocked, {"options": ["reject"]})
    assert state(game).sheets["3"].tags[-1].rejection_pending
    native_answer(game, OTHER, "actor_keep", options=("vicious", "tough"), denied=("desperate",))
    native_answer(game, ADMIN, "handler_keep", flag=True, text="The pilot holds.")
    tick(worker, gateway, 5)
    saved = next(item for item in state(game).obligations if item.kind == "reject_tag")
    projection = ActivityNativePlays(
        SimpleNamespace(
            game=game,
            handler=ADMIN,
            scene_plays=adapter(game),
            play_registry=load_registry(),
            handler_rooms=lambda: {900: ("relay", "Relay operations")},
        ),
        None,
    )
    with ledger.engine.connect() as c:
        canon = state(game)
        original = game.scene(c, 900)
        assert any(
            row["control"] == "reject_tag"
            for row in projection(c, original, current_ref(canon, OTHER.user_id))
        )
        assert all(
            row["id"] != "reject_tag"
            for row in projection(c, original, current_ref(canon, PLAYER.user_id))
        )
    args = {
        "play": "reject_tag",
        "target": saved.id,
        "context": "The pilot rejects the label in the scene.",
        "confirmed": True,
        "character_revision": game.sheet(OTHER)["revision"],
    }
    with pytest.raises(WorkflowError):
        adapter(game).perform_scene(PLAYER, str(uuid4()), "scene-start", args)
    result = adapter(game).perform_scene(OTHER, str(uuid4()), "scene-start", args)
    tick(worker, gateway, 5)
    assert game.inspect(OTHER, result["action_id"])["state"] == "complete"
    assert all(item.id != tag.id for item in state(game).sheets["3"].tags)


def test_last_girl_asset_passes_punishment_followup_to_handler(ledger):
    _, game, _, _, root, _ = pending(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        assets = [asset for asset in canon.sheets["3"].assets if asset.family == "girl"]
        for asset in assets[1:]:
            asset.damaged = True
        game.event(c, 1, "synthetic-last-girl-asset", "synthetic.state", canon)
    scene = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
    scene_work(
        scene,
        PLAYER,
        scene.view(PLAYER)[0],
        {"kind": "beating", "asset": assets[0].id, "tag": "Beaten"},
    )
    (review,) = scene.view(ADMIN)
    assert review["root"] == root and review["action"] == "punishment_helpless"
    response = {"inside_frame": False, "evidence": "The pilot was outside the Frame."}
    with pytest.raises(WorkflowError):
        scene_work(scene, PLAYER, review, response)
    scene_work(scene, ADMIN, review, response)
    assert game.inspect(PLAYER, root)["state"] == "complete"


def test_passing_responsibility_moves_the_form_to_the_assigned_pilot(ledger):
    _, game, _, _, root, _ = pending(ledger)
    scene = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
    original = scene.view(PLAYER)[0]
    scene_work(
        scene,
        PLAYER,
        original,
        {"kind": "passing_responsibility", "delegate": str(OTHER.user_id)},
    )
    assert not scene.view(PLAYER)
    (delegated,) = scene.view(OTHER)
    assert delegated["id"] == original["id"] and delegated["root"] == root
    with pytest.raises(WorkflowError):
        scene_work(scene, PLAYER, delegated, {"kind": "quality_time", "tag": "Forged"})


def test_pin_response_and_its_handler_ruling_stay_in_the_scene(ledger):
    game, worker, gateway, root = rolled(ledger, (6, 6))
    scene = adapter(game)
    select = choice(scene, PLAYER, "beneath_select")
    submit(
        scene,
        PLAYER,
        select,
        {
            "options": ["tag", "pin"],
            "text": "Record the actual pin.",
            "fields": {"tag": "Pinned"},
        },
    )
    response = choice(scene, OTHER, "beneath_pin_response")
    submit(scene, OTHER, response, {"options": ["play"]})
    handoff = choice(scene, OTHER, "beneath_response_play")
    game.dice.faces = (6, 6)
    answer = {
        "context": "I hold steady under the pressure.",
        "character_revision": handoff["character_revision"],
    }
    with pytest.raises(WorkflowError):
        submit(scene, PLAYER, handoff, answer)
    child = submit(scene, OTHER, handoff, answer)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    pilot = choice(scene, OTHER, "actor_keep")
    submit(scene, OTHER, pilot, {"text": "Steady"})
    ruling = next(
        card for card in scene.handler_choices(ADMIN) if card["choice"]["kind"] == "handler_keep"
    )
    assert ruling["root"] == root
    submit(scene, ADMIN, ruling["choice"], {"flag": True, "text": "It holds steady."})
    reopened = options(adapter(game), OTHER)
    assert reopened["current"]["state"] == "complete"
    assert reopened["child"]["id"] == child
    assert reopened["child"]["result"]["ruling"] == "It holds steady."


@pytest.mark.parametrize("tier", ("mid", "handler_offer", "tag_gift"))
def test_scene_defeat_keeps_its_source_and_assigns_the_actual_next_owner(ledger, tier):
    game, worker, gateway, root = required(ledger)
    scene = adapter(game)
    handoff = choice(scene, PLAYER, "beneath_defeat")
    native = game.scene_info(PLAYER, 900)
    assert (
        scene.play_options(PLAYER, native, game.sheet(PLAYER), state(game), True, False, {})[
            "defeat"
        ]["resume_source"]
        == BENEATH
    )
    assert not options(scene, OTHER)["choices"]
    answer = {
        "context": "The actual last Frame Asset is lost.",
        "character_revision": handoff["character_revision"],
    }
    with pytest.raises(WorkflowError):
        submit(scene, OTHER, handoff, answer)
    game.dice.faces = {"mid": (3, 3), "handler_offer": (1, 1), "tag_gift": (6, 6)}[tier]
    key = str(uuid4())
    child = submit(scene, PLAYER, handoff, answer, key=key)["action_id"]
    assert submit(adapter(game), PLAYER, handoff, answer, key=key)["action_id"] == child
    tick(worker, gateway, 3)
    pass_tags(game)
    scene = adapter(game)
    assert options(scene, PLAYER)["child"]["id"] == child
    selection = choice(scene, PLAYER, "defeat_select")
    assert selection["fields"]
    selected = {
        "mid": ["escape_cockpit_choose_location"],
        "handler_offer": ["handler_ruinous_alternative"],
        "tag_gift": ["lower_status", "another_girl_gives_tag"],
    }[tier]
    answer = {"options": selected, "text": "Record the actual consequence."}
    if tier == "tag_gift":
        answer["fields"] = {"tag_giver": str(OTHER.user_id)}
    submit(scene, PLAYER, selection, answer)
    if tier == "handler_offer":
        entry = next(
            card
            for card in scene.handler_choices(ADMIN)
            if card["choice"]["kind"] == "defeat_alternative"
        )
        assert entry["root"] == root
        offer = entry["choice"]
        answer = {
            "text": "Record a failed extraction as a Tag.",
            "number": 0,
            "flag": True,
            "fields": {"tag": "Extraction failed", "frame_context": "unspecified"},
        }
        with pytest.raises(WorkflowError):
            submit(scene, PLAYER, offer, answer)
        submit(scene, ADMIN, offer, answer)
        consent = choice(scene, PLAYER, "defeat_accept_alternative")
        assert consent["offer"]["tag"] == "Extraction failed"
        with pytest.raises(WorkflowError):
            submit(scene, ADMIN, consent, {"flag": True})
        submit(scene, PLAYER, consent, {"flag": True})
    if tier == "tag_gift":
        gift = choice(scene, OTHER, "defeat_tag_gift")
        with pytest.raises(WorkflowError):
            submit(scene, PLAYER, gift, {"options": ["give"], "text": "Forged"})
        submit(scene, OTHER, gift, {"options": ["give"], "text": "Survivor"})
    reopened = adapter(GameService(ledger))
    present = options(reopened, PLAYER)
    assert present["current"]["id"] == root
    assert present["current"]["state"] == "complete"
    assert present["child"]["state"] == "complete"
    receipts = {row["id"]: row for row in reopened.receipts(PLAYER, {"900": "test"})}
    assert receipts[child]["root"] == root
    assert receipts[child]["roll"]["faces"] == list(game.dice.faces)
    assert receipts[root]["roll"]["faces"] == [1, 1]
    assert game.dice.calls == 2
