"""Exercise the Activity desk with real HarpyEngine services and a synthetic ledger."""

from uuid import uuid4

import mission_lab  # adds the bundled engine and its synthetic fixtures
import pytest
from handler_punishments import HandlerPunishments
from off_duty_followups import OffDutyFollowups
from test_handler_plays import begin, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import prepared, recover_both

from girlframe.engine import m3_handler_plays as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.onboarding import WorkflowError


@pytest.fixture(autouse=True)
def bundled_registry(monkeypatch):
    monkeypatch.setenv(
        "GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules" / "registry.json")
    )


def test_advanced_punishment_assigns_surgery_to_original_owners(ledger):
    service, game = ready(ledger)
    source = begin(service, game)
    before = state(game)
    service.submit(
        ADMIN,
        str(uuid4()),
        source,
        before.revision,
        "punish",
        Effect(
            kind="punish",
            account="Disciplinary instruction for synthetic testing",
            target=current_ref(before, PLAYER.user_id),
            executor=current_ref(before, ADMIN.user_id),
        ),
    )

    desk = HandlerPunishments(game)

    def submit(actor, action, answer, *, acting_as=None):
        card = next(card for card in desk.view(actor) if card["action"] == action)
        assert all(candidate["action"] != action for candidate in desk.view(OTHER))
        return desk.perform(
            acting_as or actor,
            str(uuid4()),
            {
                "id": card["id"],
                "revision": card["revision"],
                "action": action,
                "answer": answer,
            },
        )

    instruction = next(card for card in desk.view(ADMIN) if card["action"] == "instruct")
    assert {
        "frame_disassembly",
        "compliance_surgery",
        "correctional_programming",
        "lobotomization",
    } <= {form["kind"] for form in instruction["forms"]}
    submit(ADMIN, "instruct", {"kind": "lobotomization"})
    submit(ADMIN, "scene", "Synthetic inflictor and patient report to surgery")
    submit(PLAYER, "attest", True)
    execution = submit(ADMIN, "execute", "Start the recorded experimental surgery")
    assert execution["state"] == "surgery_pending"
    submit(
        ADMIN,
        "surgery_plan",
        {
            "options": ["name"],
            "room": "Procedure room",
            "restraints": "Arm straps",
            "tools": "Name terminal",
            "new_name": "RENAMED",
        },
    )
    response = {"name": "The patient records their own response"}
    with pytest.raises(WorkflowError):
        submit(PLAYER, "surgery_responses", response, acting_as=ADMIN)
    submit(PLAYER, "surgery_responses", response)
    submit(ADMIN, "surgery_ready", True)
    assert state(game).sheets[str(PLAYER.user_id)].callsign == "RENAMED"
    assert rules.record(state(game), source).state == "complete"
    assert all(not HandlerPunishments(game).view(actor) for actor in (ADMIN, PLAYER, OTHER))


@pytest.mark.parametrize("kind", ["routine", "punish"])
def test_final_off_duty_review_validates_owners_and_persists_world_advance(ledger, kind):
    cycle, game, identity = prepared(ledger)
    desk = OffDutyFollowups(game)

    def payload(actor, action, answer):
        view = desk.view(actor)
        return {k: view[k] for k in ("period", "revision", "game_revision")} | {
            "action": action,
            "answer": answer,
        }

    def submit(actor, action, answer):
        return desk.perform(actor, str(uuid4()), payload(actor, action, answer))

    assert desk.view(ADMIN)["closing"]["phase"] == "preparing"
    assert desk.view(PLAYER) is None
    submit(ADMIN, "activate_period", {})
    recover_both(cycle, game, identity)
    assert "routine" in desk.view(ADMIN)["closing"]["scene_kinds"]
    submit(
        ADMIN,
        "set_handler_scene",
        {
            "kind": kind,
            "participants": [str(PLAYER.user_id)],
            "summary": "Restricted review scene",
            "recipient": str(PLAYER.user_id) if kind == "punish" else None,
            "context": None,
        },
    )
    assert desk.view(PLAYER)["closing"]["attendance"]["summary"] == "Restricted review scene"
    other = desk.view(OTHER)
    assert other is None or other["closing"] is None
    with pytest.raises(WorkflowError):
        desk.perform(OTHER, str(uuid4()), payload(ADMIN, "acknowledge_handler_scene", {}))
    submit(ADMIN, "acknowledge_handler_scene", {})
    submit(PLAYER, "acknowledge_handler_scene", {})
    assert desk.view(PLAYER)["closing"]["attendance"]["confirmed"]
    if kind == "punish":
        discipline = HandlerPunishments(game)
        card = next(
            row for row in discipline.view(ADMIN) if row["action"] == "apply_off_duty_punishment"
        )
        disassembly = next(form for form in card["forms"] if form["kind"] == "frame_disassembly")
        assert disassembly["available"]
        asset = disassembly["fields"][0]["options"][0][0]
        answer = {key: card[key] for key in ("id", "revision", "work_revision", "action")}
        answer["answer"] = {"kind": "frame_disassembly", "asset": asset}
        with pytest.raises(WorkflowError):
            discipline.perform(OTHER, str(uuid4()), answer)
        discipline.perform(ADMIN, str(uuid4()), answer)
        assert asset not in {item.id for item in state(game).sheets[str(PLAYER.user_id)].assets}
    assert desk.view(ADMIN)["closing"]["status_ready"]
    status = {
        "order": [str(OTHER.user_id), str(PLAYER.user_id)],
        "account": "Annual review",
    }
    with pytest.raises(WorkflowError):
        desk.perform(PLAYER, str(uuid4()), payload(ADMIN, "review_status", status))
    submit(ADMIN, "review_status", status)
    before = state(game).world
    choices = desk.view(ADMIN)["closing"]["finish"]
    moves = [
        {"gorgon": choice["id"], "destination": choice["cells"][0]} for choice in choices["moves"]
    ]
    assert moves
    finish = payload(ADMIN, "finish_period", {"moves": moves, "changes": []})
    key = str(uuid4())
    saved = desk.perform(ADMIN, key, finish)
    assert saved["phase"] == "complete"
    assert desk.perform(ADMIN, key, finish) == saved
    assert state(game).world.gorgons[1].cell != before.gorgons[1].cell
    assert state(game).order == (OTHER.user_id, PLAYER.user_id)
    assert state(game).world.completed_off_duty == (identity,)
    assert OffDutyFollowups(game).view(ADMIN) is None
