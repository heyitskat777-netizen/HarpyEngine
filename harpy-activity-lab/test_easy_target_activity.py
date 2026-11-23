"""Easy Target files the actual reaction, required child, and owned consequence."""

import pytest
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from test_easy_target import CONTEXT, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state, tick

import mission_lab  # noqa: F401
from easy_target_controls import EASY
from specialist_scene import SpecialistScene
from test_identity_specialists import popup, press, respond, scoped, suggestions
from test_prince_activity import pass_windows

ledger = ledger_fixture


@pytest.mark.parametrize("urge", ("request", "use"))
def test_easy_target_keeps_the_child_and_consequence_with_the_original_owner(
    ledger, tmp_path, monkeypatch, urge,
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    assert EASY in suggestions(game, PLAYER) and EASY not in suggestions(game, OTHER)
    game.dice.faces = (3, 4)
    source = press(scene, PLAYER, popup(scene, PLAYER, EASY), {
        "heat": "1", "context": "I state the mistaken coordinates out loud.",
    })
    root = source["action_id"]
    tick(worker, gateway, 3)
    pass_windows(game)
    first = game.inspect(PLAYER, root)["receipt"]
    reactor = current_ref(state(game), OTHER.user_id)
    respond(scoped(game, PLAYER, "easy_target_select"), PLAYER, "easy_target_select", {
        "select": reactor.token, "account": "I choose the actual observer.",
    })
    respond(scoped(game, OTHER, "easy_target_tag"), OTHER, "easy_target_tag", {
        "account": "Mistaken coordinates",
    })
    step = f"easy_target_react:{reactor.token}"
    respond(scoped(game, OTHER, step), OTHER, step, {
        "urge": urge, "play": "keep_your_head", "context": CONTEXT, "account": "I ask for actual work.",
    })
    step = f"easy_target_validate:{reactor.token}"
    respond(scoped(game, ADMIN, step), ADMIN, step, {
        "yes": "yes", "account": "The original stated task has its actual trigger.",
    })
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    step = f"easy_target_child:{reactor.token}"
    child = scoped(fresh, PLAYER, step)
    with pytest.raises(WorkflowError):
        respond(child, OTHER, step, {"heat": "0"})
    game.dice.faces = (4, 5)
    result = respond(child, PLAYER, step, {"heat": "0"}, key="actual-required-keep")
    tick(worker, gateway, 3)
    pass_windows(fresh)
    respond(scoped(fresh, PLAYER, "actor_keep"), PLAYER, "actor_keep", {
        "options": ["desperate", "tough"], "denied": "sexy",
    })
    respond(scoped(fresh, ADMIN, "handler_keep"), ADMIN, "handler_keep", {
        "flag": "yes", "text": "The original assigned work has been performed.",
    })
    step = f"easy_target_{'bond' if urge == 'use' else 'judge'}:{reactor.token}"
    owner = PLAYER if urge == "use" else OTHER
    respond(scoped(fresh, owner, step), owner, step, {
        "yes": "yes", "account": "The original follow-up is approved.",
    })
    assert fresh.inspect(PLAYER, result["action_id"])["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == first and game.dice.calls == 2
    if urge == "use":
        assert depth(state(fresh), current_ref(state(fresh), PLAYER.user_id), reactor) > 0


@pytest.mark.parametrize("play,urge", (("all_out_assault", "hurt"), ("engage", "protect")))
def test_easy_target_source_combat_reopens_for_its_owners(ledger, tmp_path, monkeypatch, play, urge):
    from test_easy_target import choose, source, validate

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), PLAYER.user_id)
    reactor = current_ref(state(game), OTHER.user_id)
    root = source(game, worker, gateway)
    original = game.inspect(PLAYER, root)["receipt"]
    choose(game, OTHER, reactor, urge, play=play, context="The actual response to the original error.")
    validate(game, reactor)
    assignment = f"easy_target_child:{reactor.token}"
    work = rules.identity(root, reactor)
    card = scoped(game, OTHER, assignment)
    assert card[1]["root"] == root
    if urge == "hurt":
        attacking = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)
        opposing = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged)
        assets = {"attacking_asset": attacking.id, "target_asset": opposing.id}
        with pytest.raises(WorkflowError):
            respond(card, PLAYER, assignment, assets)
        declared = respond(card, OTHER, assignment, assets, key="assigned-assault-declaration")
        assert respond(card, OTHER, assignment, assets, key="assigned-assault-declaration") == declared
        assert game.dice.calls == 1
        ledger.engine.dispose()
        game = GameService(ledger, dice=game.dice)
        review = scoped(game, ADMIN, "easy_assault_review")
        assert review[1]["root"] == root
        facts = {"opening": "yes", "reach": "yes", "outside_permission": "yes",
                 "indirect": "no", "evidence": "The original judge confirms the actual conditions."}
        with pytest.raises(WorkflowError):
            respond(review, OTHER, "easy_assault_review", facts)
        respond(review, ADMIN, "easy_assault_review", facts)
        game.dice.faces = (4, 5)
        begun = respond(scoped(game, OTHER, "easy_assault_start"), OTHER, "easy_assault_start", {"piloting": "no"})
    else:
        with pytest.raises(WorkflowError):
            respond(card, PLAYER, assignment, {"heat": "0"})
        game.dice.faces = (4, 4)
        begun = respond(card, OTHER, assignment, {"heat": "0"})
    child = begun["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, child)["state"] == "ready_to_roll":
        respond(scoped(game, OTHER, "roll"), OTHER, "roll", {})
    pass_windows(game)
    receipt = game.inspect(OTHER, child)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    if urge == "hurt":
        for viewer in (ADMIN, PLAYER, OTHER):
            vote = scoped(fresh, viewer, "battle_assault_table")
            assert vote[1]["root"] == root
            respond(vote, viewer, "battle_assault_table", {
                "decision": "no", "account": "No vast advantage in the actual declared attack.",
            })
        assert next(x for x in state(fresh).sheets["2"].assets if x.id == opposing.id).damaged
        case = state(fresh).role_punishments[-1]
        assert case.chooser == target and case.subject == reactor
    else:
        action = scoped(fresh, OTHER, "engage_maneuvers")
        assert action[1]["root"] == root
        assets = [x for x in state(fresh).sheets["3"].assets if not x.damaged][:2]
        values = {"maneuvers": ["protect", "cover"], "asset_protect": assets[0].id,
                  "asset_cover": assets[1].id, "text": "I cover the original pilot in this drill."}
        with pytest.raises(WorkflowError):
            respond(action, PLAYER, "engage_maneuvers", values)
        respond(action, OTHER, "engage_maneuvers", values)
        assert controls.view(PLAYER, work)["work"]["protection_event"]
    assert fresh.inspect(PLAYER, root)["receipt"] == original
    assert fresh.inspect(OTHER, child)["state"] == "complete"
    assert fresh.inspect(OTHER, child)["receipt"] == receipt and game.dice.calls == 2


def test_easy_target_flirt_stays_with_the_genuine_participants(ledger, tmp_path, monkeypatch):
    from test_easy_target import choose, source, validate

    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    reactor = current_ref(state(game), OTHER.user_id)
    root = source(game, worker, gateway)
    original = game.inspect(PLAYER, root)["receipt"]
    choose(game, OTHER, reactor, "request", play="flirt", context="The actual requested conversation.")
    validate(game, reactor)
    step = f"easy_target_child:{reactor.token}"
    pending = scoped(game, PLAYER, step)
    game.dice.faces = (4, 4)
    child = respond(pending, PLAYER, step, {"target": reactor.model_dump_json(), "heat": "0"})["action_id"]
    tick(worker, gateway, 3)
    pass_windows(game)
    respond(scoped(game, PLAYER, "actor_flirt"), PLAYER, "actor_flirt", {"options": "name"})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    target = scoped(fresh, OTHER, "target_flirt")
    assert target[1]["root"] == root
    with pytest.raises(WorkflowError):
        respond(target, PLAYER, "target_flirt", {"text": "Wrong owner."})
    respond(target, OTHER, "target_flirt", {"text": "My choice of name."})
    judge = f"easy_target_judge:{reactor.token}"
    respond(scoped(fresh, OTHER, judge), OTHER, judge, {"yes": "yes", "account": "I received the response."})
    assert fresh.inspect(PLAYER, child)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 2


def test_easy_target_npc_hurt_opens_the_original_newgirls_asset_choice(ledger, tmp_path, monkeypatch):
    from test_easy_target import source

    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc = ActorRef(kind="npc", entity="bystander")
    root = source(game, worker, gateway, selected=npc)
    original = game.inspect(PLAYER, root)["receipt"]
    step = f"easy_target_react:{npc.token}"
    respond(scoped(game, OTHER, step), OTHER, step, {
        "urge": "hurt", "context": "I actually strike the exposed pilot.",
        "account": "The actual NPC owns this reaction.",
    })
    step = f"easy_target_validate:{npc.token}"
    respond(scoped(game, ADMIN, step), ADMIN, step, {
        "yes": "yes", "account": "The genuine contact requires one Girl Asset injury.",
    })
    step = f"easy_target_child:{npc.token}"
    respond(scoped(game, OTHER, step), OTHER, step, {"account": "The actual NPC makes physical contact."})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    step = "battle_target_damage"
    card = scoped(fresh, PLAYER, step)
    assert card[1]["root"] == root
    asset = card[1]["operations"][0]["fields"][0]["options"][0][0]
    with pytest.raises(WorkflowError):
        respond(card, OTHER, step, {"asset": asset})
    result = respond(card, PLAYER, step, {"asset": asset}, key="npc-source-asset")
    assert respond(card, PLAYER, step, {"asset": asset}, key="npc-source-asset") == result
    saved = state(fresh)
    assert any(row.id == asset and row.damaged for row in saved.sheets["2"].assets)
    assert saved.role_punishments[-1].subject == npc
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 1


def test_easy_target_refers_an_order_that_cannot_bind_to_the_original_source(ledger, tmp_path, monkeypatch):
    from test_easy_target import choose, source

    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    review = FacilitatorService(game)
    review.configure(ADMIN, "set-native-facilitator", "user", OTHER.user_id)
    reactor = current_ref(state(game), OTHER.user_id)
    root = source(game, worker, gateway)
    receipt = game.inspect(PLAYER, root)["receipt"]
    choose(game, OTHER, reactor, "request", play="disobey_orders", context="The actual requested refusal.")
    step = f"easy_target_validate:{reactor.token}"
    card = scoped(game, ADMIN, step)
    assert card[1]["action"] == "native_choice_review" and card[1]["root"] == root
    assert review.tasks(ADMIN) == []
    with pytest.raises(WorkflowError):
        respond(card, OTHER, step, {})
    saved = respond(card, ADMIN, step, {}, key="review-the-unbindable-order")
    assert respond(card, ADMIN, step, {}, key="review-the-unbindable-order") == saved
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    record = FacilitatorService(fresh).view(OTHER, saved["review_id"])["request"]
    assert record["source"] == root and record["mandatory"] and record["status"] == "awaiting_ruling"
    assert fresh.inspect(PLAYER, root)["receipt"] == receipt and game.dice.calls == 1
