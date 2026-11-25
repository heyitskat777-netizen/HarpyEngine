"""Mission Control must point to the native work that blocks debrief."""

from uuid import uuid4

import mission_lab

# isort: split
import pytest
from mission_desk import MissionDesk
from play_continuations import PlayContinuations
from scene_plays import ScenePlays
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_replacement import supplied
from test_replacement_service import pending
from test_supply_drop import acquire, launch, native_receive, propose, ready, settle

from girlframe.delivery.m2_worker import GameWorker
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


@pytest.fixture(autouse=True)
def set_registry(monkeypatch):
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json"))


def work(desk, viewer, mission, kind):
    return next(
        item
        for row in desk.view(viewer, "Viewer", lifecycle=True)["offers"]
        if row["id"] == mission
        for item in row["followups"]
        if item["kind"] == kind
    )


def post(continuations, viewer, card, operation, values, key=None):
    return continuations.perform(
        viewer,
        key or str(uuid4()),
        card | {"answer": {"operation": operation, "values": values}},
    )


def test_mission_reopens_doctor_replacement_for_the_actual_pilot_and_handler(ledger):
    svc, game, mission, root = pending(ledger)
    desk = MissionDesk(svc.missions)
    followups = PlayContinuations(game)
    assert work(desk, PLAYER, mission["id"], "doctor_frame_replacement")["id"] == root
    assert not any(row["followups"] for row in desk.view(OTHER, "Other", lifecycle=True)["offers"])
    card = next(x for x in followups.view(PLAYER) if x["id"] == root)
    result = post(followups, PLAYER, card, "propose:THE ENFORCER", {})
    package = work(desk, ADMIN, mission["id"], "frame_replacement_package")
    assert package["id"] == result["package_id"]
    card = next(x for x in followups.view(ADMIN) if x["id"] == package["id"])
    quote = supplied()
    values = {"explanation": quote.explanation}
    for index, asset in enumerate(quote.assets):
        values[f"name{index}"] = asset.name
        values[f"description{index}"] = asset.description
    post(followups, ADMIN, card, "package", values)
    card = next(x for x in followups.view(PLAYER) if x["id"] == root)
    operation = next(x["id"] for x in card["operations"] if x["id"].startswith("apply:"))
    post(followups, PLAYER, card, operation, {"confirm": "yes"})
    assert state(game).sheets["2"].frame == "THE ENFORCER"
    assert svc.missions.complete(ADMIN, "mission-reward", mission["id"], mission["revision"])[
        "rewards_committed"
    ]


@pytest.mark.parametrize("in_battle", (False, True))
def test_mission_supply_expiry_opens_only_the_assigned_context_review(
    ledger, tmp_path, monkeypatch, in_battle
):
    game, supply, missions, award = ready(ledger, tmp_path, monkeypatch)
    acquire(supply, award)
    mission = launch(missions)
    use = propose(supply, game, mission)
    native_receive(supply, use)
    with ledger.transaction() as c:
        actual = state(game)
        for asset in actual.sheets["2"].assets:
            if asset.family == "frame" and asset.id != "supply-drop:" + use:
                asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_frame_damage", actual)
    ended = missions.end(
        ADMIN,
        str(uuid4()),
        mission,
        missions.get(ADMIN, mission)["mission"]["revision"],
        True,
    )
    assert ended["phase"] == "ending"
    followups = PlayContinuations(game)
    item = work(MissionDesk(missions), ADMIN, mission, "supply_drop_frame_context")
    card = next(x for x in followups.view(ADMIN) if x.get("mission_work") == item["id"])
    assert card["id"] == use
    values = {
        "battle": "yes" if in_battle else "no",
        "account": "The Handler files the circumstances of the final Frame Asset loss.",
    }
    with pytest.raises(WorkflowError):
        post(followups, PLAYER, card, "review", values)
    key = "supply-loss-review"
    result = post(followups, ADMIN, card, "review", values, key=key)
    assert result["defeat_required"] is in_battle
    assert post(PlayContinuations(game), ADMIN, card, "review", values, key=key) == result
    if in_battle:
        with pytest.raises(WorkflowError, match="pending"):
            missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
        defeat = work(MissionDesk(missions), PLAYER, mission, "defeat")
        reopened = GameService(ledger, dice=game.dice)
        scene = ScenePlays(reopened, 900, ADMIN, PLAYER, OTHER, handler_proxy=False)
        reopened.dice.faces = (3, 3)
        action = scene.start_scene_play(
            PLAYER,
            "expiry-defeat",
            {
                "play": "defeat",
                "target": defeat["id"],
                "confirmed": True,
                "context": "The last usable Frame Asset expired in combat.",
                "character_revision": state(reopened).sheets["2"].revision,
            },
        )["action_id"]
        worker, gateway = GameWorker(reopened), Gateway()
        tick(worker, gateway, 3)
        pass_tags(reopened)
        answer(
            reopened,
            PLAYER,
            "defeat_select",
            options=("escape_cockpit_choose_location",),
            text="I escape the damaged Frame.",
        )
        resolved = GameService(ledger).inspect(PLAYER, action)
        assert resolved["state"] == "complete" and resolved["receipt"]["faces"] == [3, 3]
        tick(worker, gateway, 6)
    assert missions.complete(ADMIN, "supply-reward", mission, ended["revision"])[
        "rewards_committed"
    ]
    assert settle(missions, game, mission)["phase"] == "complete"
