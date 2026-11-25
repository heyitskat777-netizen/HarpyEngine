"""The real Performer declaration and original owners in the Activity popup."""

import json

import mission_lab  # noqa: F401
import pytest
from handler_punishments import HandlerPunishments
from prince_controls import EXCEPTION, EXCEPTION_PLAY, PERFORMER
from scene_beneath_work import SceneBeneathWork
from specialist_scene import SpecialistScene
from test_identity_specialists import (
    option,
    popup,
    press,
    respond,
    room_map,
    scoped,
    suggestions,
)
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state, tick
from test_prince import perform, ready
from test_scene_beneath_followups import scene_work
from test_vatgrown import ready as doll_ready
from test_vatgrown import roll as doll_roll

from girlframe.engine import m3_prince as rules
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def pass_windows(game):
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(row["kind"] == "tag_window" for row in game.choices(viewer)):
            respond(scoped(game, viewer, "tag_window"), viewer, "tag_window", {"options": "pass"})


@pytest.mark.parametrize("tier", ("low", "mid", "high"))
def test_performer_reopens_for_original_caster_and_counterpart(ledger, tmp_path, monkeypatch, tier):
    game, worker, gateway, control = ready(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    assert suggestions(game, PLAYER)[PERFORMER]["control"] == PERFORMER
    assert PERFORMER not in suggestions(game, OTHER)
    private = "PRIVATE_PART_ACCOUNT: I actually take this part."
    exception = ""
    if tier == "high":
        press(scene, PLAYER, popup(scene, PLAYER, EXCEPTION), {"context": private})
        form = popup(scene, PLAYER, EXCEPTION_PLAY)
        game.dice.faces = (6, 6)
        action = press(
            scene,
            PLAYER,
            form,
            {
                "source": option(form, "source"),
                "play": "keep_your_head",
                "heat": "0",
                "piloting": "no",
            },
        )
        tick(worker, gateway, 3)
        ledger.engine.dispose()
        window = scoped(GameService(ledger, dice=game.dice), PLAYER, "tag_window")
        assert window[1]["root"] == action["action_id"]
        pass_windows(game)
        respond(
            scoped(game, PLAYER, "actor_keep"),
            PLAYER,
            "actor_keep",
            {"text": "I keep my nerve in the face of my actual contrary act."},
        )
        respond(
            scoped(game, ADMIN, "handler_keep"),
            ADMIN,
            "handler_keep",
            {"flag": "yes", "text": "The original danger was met."},
        )
        tick(worker, gateway, 5)
        exception = rules.records(state(game), rules.DemandException)[-1].id
        assert game.inspect(PLAYER, action["action_id"])["state"] == "complete"
    form = popup(scene, PLAYER, PERFORMER)
    target = next(
        value
        for value, _ in next(row for row in form[1]["fields"] if row["key"] == "target")["options"]
        if json.loads(value)["entity"] == str(OTHER.user_id)
    )
    record = press(
        scene,
        PLAYER,
        form,
        {
            "target": target,
            "part": "The composed public pilot",
            "following": "no" if exception else "yes",
            "context": private,
        },
    )
    with pytest.raises(WorkflowError):
        control.view(ADMIN, record["id"])
    assert "account" not in control.view(OTHER, record["id"])["record"]
    roll_form = popup(scene, PLAYER, PERFORMER)
    assert option(roll_form, "source") == record["id"]
    before = game.dice.calls
    game.dice.faces = {"low": (2, 3), "mid": (4, 4), "high": (6, 6)}[tier]
    values = {"source": record["id"], "heat": "0", "piloting": "no"}
    if exception:
        values["exception"] = exception
    action = press(scene, PLAYER, roll_form, values, key="actual-performer")
    tick(worker, gateway, 3)
    pass_windows(game)
    original = game.inspect(PLAYER, action["action_id"])["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    if tier == "low":
        step = scoped(fresh, OTHER, "prince_falter")
        with pytest.raises(WorkflowError):
            respond(step, PLAYER, "prince_falter", {"option": "pass"})
        respond(step, OTHER, "prince_falter", {"option": "tag", "account": "False composure"})
        assert any(tag.label == "False composure" for tag in state(fresh).sheets["2"].tags)
    else:
        if tier == "high":
            respond(
                scoped(fresh, PLAYER, "prince_conform"),
                PLAYER,
                "prince_conform",
                {"account": "The revised part follows my Fanbase demands."},
            )
        first = scoped(fresh, PLAYER, "prince_choose_actor")
        with pytest.raises(WorkflowError):
            respond(first, OTHER, "prince_choose_actor", {"option": "status"})
        respond(first, PLAYER, "prince_choose_actor", {"option": "status"})
        respond(
            scoped(fresh, OTHER, "prince_choose_target"),
            OTHER,
            "prince_choose_target",
            {"option": "bond", "account": "I deepen this actual Bond."},
        )
    saved = fresh.inspect(PLAYER, action["action_id"])
    assert saved["state"] == "complete" and saved["receipt"] == original
    assert press(scene, PLAYER, roll_form, values, key="actual-performer") == action
    assert fresh.dice.calls == before + 1


@pytest.mark.parametrize("play", ("prince", "vatgrown_doll"))
def test_original_counterpart_can_complete_the_scenebound_punishment(
    ledger,
    tmp_path,
    monkeypatch,
    play,
):
    if play == "prince":
        game, worker, gateway, control = ready(ledger, tmp_path, monkeypatch)
        _, original = perform(game, worker, gateway, control, (1, 1))
        step, values = "prince_falter", {"option": "punish"}
    else:
        game, worker, gateway, _ = doll_ready(ledger, tmp_path, monkeypatch)
        original = doll_roll(game, worker, gateway, faces=(1, 1))
        step, values = "vat_doll_attention", {"options": "punish"}
    respond(scoped(game, OTHER, step), OTHER, step, values)
    old = game.inspect(PLAYER, original)["receipt"]
    case = state(game).role_punishments[-1]
    assert case.source_kind == play
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scene = SceneBeneathWork(fresh, room_map)
    punishments = HandlerPunishments(fresh)

    def card(viewer, action):
        saved = next(
            row
            for row in scene.view(viewer, role_cards=punishments.view(viewer))
            if row["id"] == case.id and row["action"] == action
        )
        assert saved["root"] == original
        return saved

    start = card(OTHER, "instruct")
    assert any(form["kind"] == "stimulant_injection" for form in start["forms"])
    with pytest.raises(WorkflowError):
        scene_work(scene, PLAYER, start, {"kind": "stimulant_injection"})
    scene_work(scene, OTHER, start, {"kind": "stimulant_injection"})
    scene_work(scene, OTHER, card(OTHER, "scene"), "The original counterpart administers it.")
    attend = card(PLAYER, "attest")
    with pytest.raises(WorkflowError):
        scene_work(scene, OTHER, attend, True)
    scene_work(scene, PLAYER, attend, True)
    before = state(fresh).sheets["2"].heat
    final = card(OTHER, "execute")
    saved = scene_work(
        scene, OTHER, final, "I carry out the assigned effect.", key="original-role-punishment"
    )
    assert (
        scene_work(
            scene, OTHER, final, "I carry out the assigned effect.", key="original-role-punishment"
        )
        == saved
    )
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        scene_work(scene, OTHER, final, "I change the account.", key="original-role-punishment")
    with pytest.raises(WorkflowError):
        scene_work(scene, OTHER, final, "I carry out the assigned effect.", key="different-command")
    with pytest.raises(WorkflowError):
        scene_work(
            scene, PLAYER, final, "I carry out the assigned effect.", key="original-role-punishment"
        )
    assert state(fresh).sheets["2"].heat == before + 7
    if play == "vatgrown_doll":
        respond(
            scoped(fresh, PLAYER, "vat_doll_benefits"),
            PLAYER,
            "vat_doll_benefits",
            {"options": "quiet"},
        )
    assert fresh.inspect(PLAYER, original)["state"] == "complete"
    assert fresh.inspect(PLAYER, original)["receipt"] == old and game.dice.calls == 1
