"""Reachable actual body facts and immutable starting-source repair; deferred P1 normals."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_changeling import define
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_world import initial
from test_world_service import transfer_npc

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter import m3_body_facts as native
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService, npc_originals, prove_npc_original
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import ChangelingService, prove_node
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch):
    # Activation predates plays approval: genuine reviewed initial anchors exist, no new hook ran.
    missions, game = service(store, girl="OLDGEN", frame=rules.FRAME)
    acquisition = approved(
        store, game, tmp_path, monkeypatch, extra=(rules.STRINGS, rules.BLANK, rules.FINGERS)
    )
    missions.access.registry = acquisition.registry
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    world = WorldService(missions)
    initial_world = initial()
    world.initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        initial_world.board,
        initial_world.locations,
        initial_world.gorgons[0],
    )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        preview = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            preview["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(preview["actor"]),
                frame_instance=preview["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting" if viewer == PLAYER else "outside_frame",
                account="Actual original body and its first placement",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposed["id"],
            1,
            "accept",
            "I witness these original physical bodies and positions",
        )
    return game, BodyFactsService(game), world, CastService(ActorService(missions))


def record(game, bodies, viewer, account="Actual original brain in this proved original vessel"):
    return bodies.record(
        viewer,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), viewer.user_id),
        "girl",
        account,
    )


def native_history(monkeypatch, bodies, viewer, identity):
    captured = []
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: viewer)

    async def reply(interaction, text, view=None):
        captured.append((text, view))

    monkeypatch.setattr(native, "reply", reply)
    asyncio.run(
        native.open_body_facts(
            SimpleNamespace(user=SimpleNamespace(id=viewer.user_id), channel_id=999),
            bodies,
            identity,
        )
    )
    return captured[0][1]


def test_non_changeling_body_owner_native_history_then_genuine_bond_deepen(
    ledger, tmp_path, monkeypatch
):
    game, bodies, _, _ = ready(ledger, tmp_path, monkeypatch)
    assert state(game).sheets["3"].frame == "JANUS-B"
    own = bodies.menu(OTHER, 900)
    assert next(row for row in own["actors"] if row["actor"]["kind"] == "pilot")["joined"]
    private = "My actual original brain.\n  PRIVATE_BODY_EVIDENCE @everyone"
    request = (
        OTHER,
        "actual-native-body",
        own["revision"],
        900,
        current_ref(state(game), 3),
        "girl",
        private,
    )
    saved = bodies.record(*request)
    assert bodies.record(*request) == saved
    record(game, bodies, PLAYER)
    with pytest.raises(WorkflowError):
        bodies.view(ADMIN, saved["id"])
    history = native_history(monkeypatch, bodies, OTHER, saved["id"])
    assert native.clean(private) in "".join(p.body for p in history.pages)
    controls = ChangelingService(game)
    source = define(game, controls)
    game.dice.faces = (4, 4)
    worker, gateway = GameWorker(game), Gateway()
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="changeling_blank_slate",
            context="Actual defining speech changes my self-image",
            source_work=source,
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    nodes = [
        value for value in rules.records(state(game), rules.String) if value.origin == "deepen"
    ]
    assert len(nodes) == 1 and nodes[0].subject.actor == current_ref(state(game), 3)
    with ledger.engine.connect() as c:
        assert prove_node(game, c, state(game), nodes[0].id) == nodes[0]


def test_actual_handler_without_girl_and_witnessed_npc_setup_preserve_private_authorship(
    ledger, tmp_path, monkeypatch
):
    game, bodies, world, casts = ready(ledger, tmp_path, monkeypatch)
    assert "1" not in state(game).sheets
    handler = active_handler(state(game))
    view = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", handler
    )
    own = bodies.record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        handler,
        "handler",
        "My actual original Handler body has its original brain",
    )
    original_role = state(game).sheets["2"].review.creation.npc_bonds[0]
    npc = Npc(
        id="actual-body-witness",
        name=original_role.name or "Actual starting person",
        jobs=("civilian",),
        controller=1,
        cell=(0, 0),
        revealed=True,
        detail="Ordinary existing civilian from the actual saved starting role",
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, npc)
    transfer_npc(world, ADMIN, OTHER, npc.id)
    world.import_starting_npc(
        PLAYER, str(uuid4()), state(game).revision, original_role.slot, npc.id
    )
    target = ActorRef(kind="npc", entity=npc.id)
    view = casts.view(OTHER, 900)
    casts.change(
        OTHER, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", target
    )
    witnessed = bodies.record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        "human_npc",
        "Actual witnessed ordinary human anatomy",
    )
    assert bodies.view(OTHER, witnessed["id"])["fact"]["author"] == handler.model_dump(mode="json")
    assert bodies.view(ADMIN, own["id"])["fact"]["kind"] == "handler"
    with pytest.raises(WorkflowError):
        bodies.view(PLAYER, witnessed["id"])
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        bodies.record(
            OTHER, str(uuid4()), state(game).revision, 900, target, "human_npc", "No proxy"
        )
    assert state(game).model_dump_json() == before and game.dice.calls == 0
    owner = current_ref(state(game), 2)
    record(game, bodies, PLAYER)
    before_source = state(game)
    candidate = next(
        row
        for row in bodies.menu(ADMIN, 900)["npc_originals"]
        if row["slot"] == original_role.slot and row["owner"] == owner.model_dump(mode="json")
    )
    assert not candidate["gap"]
    assert not rules.records(before_source, rules.String)
    account = (
        "I positively witness this exact original brain/body from the saved starting role."
        "\n  PRIVATE_ORIGINAL_NPC_EVIDENCE"
    )
    source_request = (
        ADMIN,
        "actual-original-npc-body",
        state(game).revision,
        900,
        owner,
        original_role.slot,
        account,
    )
    before_positive = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        bodies.establish_npc_original(
            OTHER, str(uuid4()), state(game).revision, 900, owner, original_role.slot, account
        )
    assert state(game).model_dump_json() == before_positive
    established = bodies.establish_npc_original(*source_request)
    assert bodies.establish_npc_original(*source_request) == established
    assert not rules.records(state(game), rules.String)  # Evidence alone never imports a grant.
    factual = next(value for value in npc_originals(state(game)) if value.id == established["id"])
    assert (
        factual.subject == target
        and factual.brain == bodies.view(OTHER, witnessed["id"])["fact"]["brain"]
    )
    with ledger.engine.connect() as c:
        assert prove_npc_original(game, c, state(game), factual) == factual
    saved_history = native_history(monkeypatch, bodies, PLAYER, factual.id)
    assert native.clean(account) in "".join(page.body for page in saved_history.pages)
    offered = bodies.menu(PLAYER, 999)["imports"][0]
    verified_npc = next(
        row for row in offered["subjects"] if row["actor"] == target.model_dump(mode="json")
    )
    assert not verified_npc["gap"] and not verified_npc["imported"]
    imported = bodies.import_starting(
        PLAYER, "import-actual-original-npc", state(game).revision, owner, offered["source_event"]
    )
    assert imported["imported"] == 1
    node = next(
        value
        for value in rules.records(state(game), rules.String)
        if value.subject.actor == target and value.origin == "start"
    )
    controls = ChangelingService(game)
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        node.id,
        "question",
        "Use my actual original NPC starting String",
        question="What matters to you?",
    )
    question = rules.get(state(game), used["id"]).question
    controls.answer(
        OTHER,
        str(uuid4()),
        state(game).revision,
        question,
        "The actual human authors this character's answer",
    )
    assert rules.get(state(game), used["id"]).completed_event
    assert rules.record(state(game), rules.String, node.id).spent_by == used["id"]
    assert game.dice.calls == 0


def test_legacy_reviewed_starting_source_repairs_once_and_never_refreshes_spent_string(
    ledger, tmp_path, monkeypatch
):
    game, bodies, _, _ = ready(ledger, tmp_path, monkeypatch)
    record(game, bodies, PLAYER)
    record(game, bodies, OTHER)
    actor = current_ref(state(game), 2)
    assert not rules.records(state(game), rules.StartingBond)
    original = state(game).model_dump_json()
    offered = bodies.menu(PLAYER, 999)["imports"][0]
    assert offered.get("ready"), offered
    assert offered["eligible"] == 1
    original_npc_roles = {
        anchor.reference
        for anchor in state(game).sheets["2"].review.psych_strings
        if anchor.kind == "npc_role"
    }
    assert original_npc_roles and any(
        row["reference"] in original_npc_roles and "SOURCE_STARTING_NPC_LINK_REQUIRED" in row["gap"]
        for row in offered["unresolved"]
    )
    assert offered["pending"] and state(game).model_dump_json() == original
    request = (
        PLAYER,
        "repair-original-reviewed-source",
        state(game).revision,
        actor,
        offered["source_event"],
    )
    repaired = bodies.import_starting(*request)
    assert bodies.import_starting(*request) == repaired
    assert repaired["imported"] == 1
    assert repaired["unresolved"] == offered["unresolved"]
    still_pending = bodies.menu(PLAYER, 999)["imports"][0]
    assert still_pending["pending"] and not still_pending["ready"]
    assert still_pending["eligible"] == 0 and still_pending["unresolved"] == offered["unresolved"]
    nodes = [value for value in rules.records(state(game), rules.String) if value.origin == "start"]
    assert len(nodes) == 1 and nodes[0].subject.actor == current_ref(state(game), 3)
    controls = ChangelingService(game)
    use = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[0].id,
        "question",
        "Use my actual original starting String",
        question="What do you want to preserve?",
    )
    pending = rules.get(state(game), use["id"])
    controls.answer(
        OTHER, str(uuid4()), state(game).revision, pending.question, "My original memories"
    )
    controls.counter(OTHER, str(uuid4()), state(game).revision, pending.id, "pass")
    again = bodies.import_starting(
        PLAYER, str(uuid4()), state(game).revision, actor, offered["source_event"]
    )
    assert again["imported"] == 0 and again["unresolved"] == offered["unresolved"]
    assert rules.record(state(game), rules.String, nodes[0].id).spent_by == pending.id
    assert (
        len(
            [value for value in rules.records(state(game), rules.String) if value.origin == "start"]
        )
        == 1
    )
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        bodies.import_starting(
            OTHER, str(uuid4()), state(game).revision, actor, offered["source_event"]
        )
    with pytest.raises(WorkflowError):
        bodies.import_starting(PLAYER, str(uuid4()), state(game).revision, actor, "not-a-birth")
    assert state(game).model_dump_json() == before and game.dice.calls == 0
