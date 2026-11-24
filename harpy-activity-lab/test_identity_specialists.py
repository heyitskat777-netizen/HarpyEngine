"""Activity entry points and original owners of identity and memory effects."""

import json
from types import SimpleNamespace
from uuid import uuid4

import mission_lab

# isort: split
import pytest
import test_changeling
import test_red_queen
from girlframe.engine import m3_changeling, m3_red_queen
from girlframe.engine.m3_actor_bonds import change, current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import WorkflowError
from m3_policy_scenario import configure_m3_fixture
from test_changeling import ready as changeling_ready
from test_enforcer_requisitions import approved as synthetic_approval
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state, tick
from test_red_queen import am, buy, initialize
from test_red_queen import ready as queen_ready

from owned_followups import OwnedFollowups
from ai_native_plays import ActivityNativePlays
from scene_beneath_work import SceneBeneathWork
from specialist_scene import BLANK, CLAY, CONSULT, MEMORY, PANOPTICON, TRANSFER, SpecialistScene
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_scene_beneath_followups import adapter

ledger = ledger_fixture
ROOM = ("relay", "Relay")


@pytest.fixture(autouse=True)
def activity_release(monkeypatch):
    def scoped_release(store, game, *_args, **_kwargs):
        registry = configure_m3_fixture(store)
        assert not Access(store).activity_specialist_enabled(m3_changeling.BLANK)
        mission_lab.enable_private_subsystems(game)
        access = Access(store, registry)
        assert registry.coverage == "RULES_SUBSET"
        for rule in mission_lab.ACTIVITY_SPECIALIST_RULES:
            assert not registry.entry(rule).verified
            assert access.activity_specialist_enabled(rule)
        assert not access.activity_specialist_enabled(m3_changeling.FINGERS)
        assert not access.activity_specialist_enabled(m3_red_queen.CONSULT)
        assert "economy" not in store.policy.m3_approval.subsystems

    monkeypatch.setattr(test_changeling, "approved", scoped_release)
    monkeypatch.setattr(test_red_queen, "approved", scoped_release)


def room_map():
    return {900: ROOM}


def suggestions(game, viewer):
    projection = ActivityNativePlays(SimpleNamespace(
        game=game, handler=ADMIN, scene_plays=adapter(game),
        play_registry=Access(game.store).registry, handler_rooms=room_map,
    ), None)
    with game.store.engine.connect() as c:
        return {
            row["id"]: row for row in projection(
                c, game.scene(c, 900), current_ref(state(game), viewer.user_id)
            )
        }


def popup(scene, viewer, op):
    return next(
        (card, operation)
        for card in scene.view(viewer, ROOM)
        for operation in card["operations"]
        if operation["id"].split(":", 1)[0] == op
    )


def press(scene, viewer, item, values, *, key=None):
    card, operation = item
    return scene.perform(
        viewer,
        key or str(uuid4()),
        card
        | {
            "answer": {"operation": operation["id"], "values": values},
        },
    )


def option(item, name):
    return next(spec for spec in item[1]["fields"] if spec["key"] == name)["options"][
        0
    ][0]


def scoped(game, viewer, op):
    owned = OwnedFollowups(game, room_map)
    scenes = SceneBeneathWork(game, room_map, owned)
    card = next(
        x
        for x in scenes.view(viewer, owned.view(viewer))
        if any(step["id"] == op for step in x.get("operations", []))
    )
    return scenes, card


def respond(scope, viewer, op, values, *, key=None):
    scenes, card = scope
    payload = {k: card[k] for k in ("id", "revision", "action", "root")} | {
        "answer": {"operation": op, "values": values},
    }
    return scenes.perform(viewer, key or str(uuid4()), payload)


def rolled(game, worker, gateway, action):
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    for viewer in (PLAYER, OTHER, ADMIN):
        rows = [row for row in game.choices(viewer) if row["action_id"] == action]
        if any(row["kind"] == "tag_window" for row in rows):
            respond(scoped(game, viewer, "tag_window"), viewer, "tag_window", {})
    if any(row["kind"] == "mockingbird_risk" for row in game.choices(PLAYER)):
        respond(
            scoped(game, PLAYER, "mockingbird_risk"), PLAYER, "mockingbird_risk", {}
        )
    return game.inspect(PLAYER, action)["receipt"]


def test_consult_and_panopticon_only_offer_owned_approved_sources(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr(test_red_queen, "approved", synthetic_approval)
    game, worker, gateway, court = queen_ready(ledger, tmp_path, monkeypatch)
    initialize(court)
    bought = buy(court, m3_red_queen.PANOPTICON)
    assert bought
    queen = am(game, "The Queen")
    court.mark(PLAYER, "mark-queen-source", 900, state(game).revision, queen.id, "status", amount=1)
    native = SpecialistScene(game, 900)
    consult = popup(native, PLAYER, CONSULT)
    assert suggestions(game, PLAYER)[CONSULT]["control"] == consult[0]["id"]
    assert PANOPTICON not in suggestions(game, PLAYER)
    game.dice.faces = (3, 4)
    result = press(native, PLAYER, consult, {"heat": "1", "account": "Consult from the original cockpit."})
    rolled(game, worker, gateway, result["action_id"])
    assigned = scoped(game, PLAYER, CONSULT)
    with pytest.raises(WorkflowError):
        respond(assigned, OTHER, CONSULT, {"options": queen.id, "text": "Wrong owner."})
    respond(assigned, PLAYER, CONSULT, {"options": queen.id, "text": "Keep relay equipment intact."})
    assert game.inspect(PLAYER, result["action_id"])["state"] == "complete"
    tick(worker, gateway, 5)
    game.leave_scene(OTHER, "observer-target-outside", 900)

    observer, target = (current_ref(state(game), viewer.user_id) for viewer in (PLAYER, OTHER))
    form = popup(native, PLAYER, "distant")
    source = press(native, PLAYER, form, {
        "target": target.model_dump_json(), "account": "I can see the pilot across the compound."
    })
    ready = popup(native, PLAYER, PANOPTICON)
    assert suggestions(game, PLAYER)[PANOPTICON]["control"] == ready[0]["id"]
    assert PANOPTICON not in suggestions(game, OTHER)
    original = option(ready, "observation")
    assert json.loads(original) == {"id": source["id"], "target": target.model_dump(mode="json")}
    game.dice.faces = (2, 3)
    play = press(native, PLAYER, ready, {"heat": "0", "account": "Observe the target.",
                                        "observation": original})
    rolled(game, worker, gateway, play["action_id"])
    respond(scoped(game, PLAYER, "red_queen_questions"), PLAYER, "red_queen_questions", {"options": "where"})
    ledger.engine.dispose()
    reopened = GameService(ledger, dice=game.dice)
    target_response = scoped(reopened, OTHER, "red_queen_answers")
    assert target_response[1]["root"] == play["action_id"]
    question = next(op for op in target_response[1]["operations"] if op["id"] == "red_queen_answers")
    assert question["fields"][0]["label"] == m3_red_queen.QUESTIONS["where"]
    with pytest.raises(WorkflowError):
        respond(target_response, ADMIN, "red_queen_answers", {"answer:where": "Wrong owner."})
    respond(target_response, OTHER, "red_queen_answers", {"answer:where": "At the relay station."})
    respond(scoped(reopened, OTHER, "red_queen_reciprocal"), OTHER, "red_queen_reciprocal", {"options": "ashamed"})
    answer = scoped(reopened, PLAYER, "red_queen_reciprocal_answer")
    respond(answer, PLAYER, "red_queen_reciprocal_answer", {"answer:ashamed": "I left the watch early."})
    assert reopened.inspect(PLAYER, play["action_id"])["state"] == "complete"
    assert reopened.inspect(PLAYER, play["action_id"])["receipt"]["faces"] == [2, 3]
    assert game.dice.calls == 2


def test_blank_slate_reopens_for_original_owner_to_adopt_a_disclosed_identity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = changeling_ready(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    defining = popup(scene, OTHER, "define")
    press(
        scene,
        OTHER,
        defining,
        {"target": option(defining, "target"), "words": "You are our expert."},
    )
    start = popup(scene, PLAYER, BLANK)
    assert suggestions(game, PLAYER)[BLANK]["control"] == start[0]["id"]
    assert BLANK not in suggestions(game, OTHER)
    game.dice.faces = (6, 6)
    action = press(
        scene,
        PLAYER,
        start,
        {
            "source": option(start, "source"),
            "heat": "1",
            "account": "I accept the original defining words.",
        },
    )["action_id"]
    original = rolled(game, worker, gateway, action)
    tick(worker, gateway, 5)
    actors = [current_ref(state(game), viewer.user_id) for viewer in (PLAYER, OTHER)]
    talks = []
    for viewer, target in zip((PLAYER, OTHER), reversed(actors), strict=True):
        entry = popup(scene, viewer, "talk")
        talks.append(
            press(
                scene,
                viewer,
                entry,
                {
                    "target": target.model_dump_json(),
                    "words": f"This is my entry {viewer.user_id}.",
                },
            )["id"]
        )
    disclose = popup(scene, OTHER, "disclose")
    press(scene, OTHER, disclose, {"disclosure": option(disclose, "disclosure")})
    reopened = GameService(ledger)
    scope = scoped(reopened, PLAYER, "copy")
    assert scope[1]["root"] == action
    forms = scope[1]["operations"][0]["fields"]
    value = next(spec for spec in forms if spec["key"] == "copy")["options"][0][0]
    request = {"copy": value, "first": talks[0], "second": talks[1]}
    with pytest.raises(WorkflowError):
        respond(scope, OTHER, "copy", request)
    key = str(uuid4())
    result = respond(scope, PLAYER, "copy", request, key=key)
    assert respond(scope, PLAYER, "copy", request, key=key) == result
    grant = m3_changeling.records(state(reopened), m3_changeling.BlankSlate)[-1]
    assert grant.copied_from == actors[1] and grant.replaced_event
    assert reopened.inspect(PLAYER, action)["receipt"] == original


@pytest.mark.parametrize("high", [True, False])
def test_memory_extraction_collects_each_owner_and_preserves_original_roll(
    ledger, tmp_path, monkeypatch, high
):
    game, worker, gateway, service = queen_ready(
        ledger, tmp_path, monkeypatch, inside=False
    )
    initialize(service)
    buy(service, m3_red_queen.MEMORY)
    scene = SpecialistScene(game, 900)
    brain = popup(scene, OTHER, "brain")
    press(
        scene,
        OTHER,
        brain,
        {
            "target": option(brain, "target"),
            "account": "The original brain access is established.",
        },
    )
    start = popup(scene, PLAYER, MEMORY)
    assert suggestions(game, PLAYER)[MEMORY]["control"] == start[0]["id"]
    assert MEMORY not in suggestions(game, OTHER)
    game.dice.faces = (5, 5) if high else (2, 3)
    action = press(
        scene,
        PLAYER,
        start,
        {
            "memory": option(start, "memory"),
            "heat": "1",
            "account": "I extract one fictional memory.",
        },
    )["action_id"]
    original = rolled(game, worker, gateway, action)
    reopened = GameService(ledger)
    select = scoped(reopened, PLAYER, "red_queen_memory_category")
    assert select[1]["root"] == action
    values = {
        "category": "person",
        "scope": "Instructor",
        **({"am": am(game, "The Consort").id} if high else {}),
    }
    with pytest.raises(WorkflowError):
        respond(select, ADMIN, "red_queen_memory_category", values)
    respond(select, PLAYER, "red_queen_memory_category", values)
    if high:
        handled = scoped(reopened, ADMIN, "red_queen_memory_handler")
        respond(
            handled,
            ADMIN,
            "red_queen_memory_handler",
            {"category": "place", "scope": "Training hall"},
        )
    links = scoped(reopened, OTHER, "red_queen_memory_links")
    identity = state(game).sheets["3"].identities[0].id
    linked = {
        "memories0": "Instructor's introduction\nTheir last lesson",
        **({"identities0": [identity]} if high else {}),
    }
    if high:
        linked.update(memories1="Arrival at the training hall", identities1=[identity])
    key = str(uuid4())
    receipt = respond(links, OTHER, "red_queen_memory_links", linked, key=key)
    assert respond(links, OTHER, "red_queen_memory_links", linked, key=key) == receipt
    losses = [
        x
        for x in m3_red_queen.records(state(reopened), m3_red_queen.Extraction)
        if x.session == action
    ]
    assert len(losses) == (2 if high else 1) and len(losses[0].memories) == 2
    assert (
        identity not in {x.id for x in state(reopened).sheets["3"].identities}
    ) == high
    assert (losses[0].am is not None) == high
    if not high:
        assert am(game, "The Consort").bearer == current_ref(
            state(game), PLAYER.user_id
        )
        with ledger.transaction() as c:
            changes = state(reopened)
            identities = changes.sheets["3"].identities
            replace_at = next(
                i
                for i, item in enumerate(identities)
                if not (item.protected or item.paired or item.am_limiter)
            )
            identities[replace_at] = identities[replace_at].model_copy(
                update={"id": "new-reminder", "name": "Remembered the instructor"}
            )
            reopened.event(
                c,
                OTHER.user_id,
                str(uuid4()),
                "synthetic.new_associated_identity",
                changes,
            )
        restore = scoped(GameService(ledger), OTHER, "restore")
        assert restore[1]["root"] == action
        association = next(
            value
            for value, label in restore[1]["operations"][0]["fields"][0]["options"]
            if label == "Remembered the instructor"
        )
        values = {
            "association": association,
            "account": "The new Identity recalls the instructor.",
        }
        with pytest.raises(WorkflowError):
            respond(restore, PLAYER, "restore", values)
        respond(restore, OTHER, "restore", values)
        recovered = m3_red_queen.get(
            state(reopened), m3_red_queen.Extraction, losses[0].id
        )
        assert recovered.restored_source == "new-reminder"
    assert reopened.inspect(PLAYER, action)["receipt"] == original


@pytest.mark.parametrize("kind", ("bond", "sex", "punishment"))
def test_transfer_uses_a_proven_completed_source_once(ledger, tmp_path, monkeypatch, kind):
    owner, wrong = PLAYER, OTHER
    if kind == "sex":
        from test_court_native_am_transfer import prepare_native_am_transfer
        from test_intracadre_marriage import FOUR

        game, _, actor, other, _, sex, source = prepare_native_am_transfer(
            ledger, tmp_path, monkeypatch
        )
        owner, wrong = OTHER, PLAYER
        assert TRANSFER not in suggestions(game, owner)
        sex.perform(
            FOUR,
            str(uuid4()),
            source,
            state(game).revision,
            "Confirm the already accepted scene is complete.",
            circuits_touched=False,
        )
    else:
        game, worker, gateway, service = queen_ready(ledger, tmp_path, monkeypatch, inside=False)
        initialize(service)
        actor, other = (current_ref(state(game), user.user_id) for user in (PLAYER, OTHER))
        if kind == "punishment":
            from test_red_queen_transfer_sources import (
                finish_ordinary_punishment,
                prepare_ordinary_punishment,
            )

            action, source = prepare_ordinary_punishment(game, worker, gateway)
            assert TRANSFER not in suggestions(game, owner)
            finish_ordinary_punishment(game, worker, gateway, action, source)
        else:
            with ledger.transaction() as c:
                state_before = state(game)
                for delta in (1, -1):
                    event = str(uuid4())
                    state_before = change(state_before, actor, other, delta, event)
                    game.event(
                        c,
                        PLAYER.user_id,
                        str(uuid4()),
                        "synthetic.bond_source",
                        state_before,
                        event_id=event,
                    )
            source = None

    scene = SpecialistScene(game, 900)
    transfer = popup(scene, owner, TRANSFER)
    assert suggestions(game, owner)[TRANSFER]["control"] == transfer[0]["id"]
    assert TRANSFER not in suggestions(game, wrong)
    encoded = option(transfer, "source")
    provenance = json.loads(encoded)
    assert provenance["kind"] == kind
    assert source is None or provenance["id"] == source
    values = {"am": option(transfer, "am"), "source": encoded}
    before = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError):
        press(scene, wrong, transfer, values)
    assert state(game) == before
    key = str(uuid4())
    reply = press(scene, owner, transfer, values, key=key)
    assert press(scene, owner, transfer, values, key=key) == reply
    after = state(game)
    assert game.dice.calls == calls
    reopened = GameService(ledger)
    assert state(reopened) == after
    saved = next(
        x for x in m3_red_queen.records(after, m3_red_queen.Assignment) if x.id == reply["id"]
    )
    assert saved.previous == actor and saved.target == other
    assert any(x.bearer == actor for x in m3_red_queen.records(after, m3_red_queen.CourtAM))
    assert not any(
        op["id"] == TRANSFER
        for card in SpecialistScene(reopened, 900).view(owner, ROOM)
        for op in card["operations"]
    )
    assert TRANSFER not in suggestions(reopened, owner)


def test_mid_clay_uses_disclosed_appearance_and_handler_taste(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = changeling_ready(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    entry = popup(scene, OTHER, "appearance")
    press(
        scene,
        OTHER,
        entry,
        {name: "Synthetic " + name for name in m3_changeling.FACETS},
    )
    show = popup(scene, OTHER, "show-appearance")
    press(
        scene,
        OTHER,
        show,
        {"appearance": option(show, "appearance"), "target": option(show, "target")},
    )
    buy_clay = popup(scene, PLAYER, "buy-clay")
    press(scene, PLAYER, buy_clay, {"account": "Purchase with two Permissions."})
    start = popup(scene, PLAYER, CLAY)
    assert suggestions(game, PLAYER)[CLAY]["control"] == start[0]["id"]
    assert CLAY not in suggestions(game, OTHER)
    game.dice.faces = (4, 4)
    action = press(
        scene,
        PLAYER,
        start,
        {"heat": "1", "account": "I allow my Frame to change me."},
    )["action_id"]
    original = rolled(game, worker, gateway, action)
    scope = scoped(game, PLAYER, "changeling_clay_owner")
    choice = next(
        x for x in scope[1]["operations"] if x["id"] == "changeling_clay_owner"
    )
    copy = next(f for f in choice["fields"] if f["key"] == "copy")["options"][0][0]
    request = {"copy": copy, "account": "Copy the disclosed appearance."}
    with pytest.raises(WorkflowError):
        respond(scope, OTHER, "changeling_clay_owner", request)
    respond(scope, PLAYER, "changeling_clay_owner", request)
    taste = scoped(GameService(ledger), ADMIN, "changeling_taste")
    respond(
        taste,
        ADMIN,
        "changeling_taste",
        {
            "taste": "no",
            "tag": "Needs refinement",
            "account": "The Handler records its opinion.",
        },
    )
    assert any(x.label == "Needs refinement" for x in state(game).sheets["2"].tags)
    assert game.inspect(PLAYER, action)["receipt"] == original


def test_blank_slate_mid_exposes_one_overstep_to_the_original_speaker(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = changeling_ready(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    defining = popup(scene, OTHER, "define")
    press(
        scene,
        OTHER,
        defining,
        {
            "target": option(defining, "target"),
            "words": "You are our specialist.",
        },
    )
    game.dice.faces = (4, 4)
    start = popup(scene, PLAYER, BLANK)
    action = press(
        scene,
        PLAYER,
        start,
        {
            "source": option(start, "source"),
            "heat": "1",
            "account": "Play from the original definition.",
        },
    )["action_id"]
    original = rolled(game, worker, gateway, action)
    tick(worker, gateway, 3)
    reopened = SpecialistScene(GameService(ledger), 900)
    overstep = popup(reopened, OTHER, "overstep")
    with pytest.raises(WorkflowError):
        press(reopened, PLAYER, overstep, {"words": "Someone else's words."})
    press(reopened, OTHER, overstep, {"words": "I push the original definition."})
    submit = popup(reopened, OTHER, "overstep-tag")
    key = str(uuid4())
    reply = press(reopened, OTHER, submit, {"tag": "Uncompromising"}, key=key)
    assert press(reopened, OTHER, submit, {"tag": "Uncompromising"}, key=key) == reply
    assert not any(
        op["id"].startswith("overstep")
        for card in reopened.view(OTHER, ROOM)
        for op in card["operations"]
    )
    canon = state(game)
    assert canon.order == (PLAYER.user_id, OTHER.user_id)
    assert any(x.label == "Uncompromising" for x in canon.sheets["2"].tags)
    assert game.inspect(PLAYER, action)["receipt"] == original
