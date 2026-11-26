"""Check Activity assignments with the same synthetic ledgers as the native Plays."""

from http import HTTPStatus
from uuid import uuid4

import pytest
from specialist_work import SpecialistWork
from test_artwork_activity import request
from test_campaign_role_access import CONFIG, role_activity
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_handler_conversion import actual_captured
from test_harpy_actor_plays import ready as ready_advancement
from test_harpy_advancements import approve_sparrows
from test_harpy_defeat import ready as ready_defeat
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_leviathan_layers import source as leviathan_source
from test_m2_game import pass_tags, state, tick

from girlframe.engine.m3_harpy_advancements import SPARROWS
from girlframe.services.onboarding import WorkflowError


def file(work, viewer, record, operation, **values):
    return work.write(
        viewer,
        str(uuid4()),
        {key: record[key] for key in ("kind", "id", "revision")}
        | {"operation": operation, "values": values},
    )


def test_managed_discord_session_gates_specialist_records(tmp_path):
    with role_activity(tmp_path) as host:
        endpoint = "/api/specialist-work"
        request(host, endpoint, status=HTTPStatus.UNAUTHORIZED)
        nonce = request(host, "/api/discord/challenge", data={})["nonce"]
        session = request(
            host,
            "/api/discord/session",
            data={
                "code": "role-pilot",
                "nonce": nonce,
                "guild_id": CONFIG.guild_id,
            },
        )
        token = session["session"]
        campaign = request(host, "/api/campaigns", token)["campaigns"][0]["id"]
        assert request(host, f"{endpoint}?campaign={campaign}", token) == {"work": []}
        request(
            host,
            f"{endpoint}?campaign={campaign}&kind=advancement&id=unknown",
            token,
            status=HTTPStatus.FORBIDDEN,
        )


def test_harpy_advancement_assignment_is_owned_and_survives_reopen(ledger):
    _, game, _, actor = ready_advancement(ledger)
    work = SpecialistWork(game)
    assert not work.list(PLAYER)["work"]
    approve_sparrows(ledger)
    (item,) = work.list(PLAYER)["work"]
    assert item["id"] == actor.entity
    draft = work.read(PLAYER, item["kind"], item["id"])
    assert draft["operations"][0]["fields"][0]["options"]
    assert not work.list(OTHER)["work"]
    with pytest.raises(WorkflowError, match="controller"):
        file(work, OTHER, draft, "learn", advancement=SPARROWS)
    file(work, PLAYER, draft, "learn", advancement=SPARROWS)
    ledger.engine.dispose()
    reopened = SpecialistWork(game).read(PLAYER, "advancement", actor.entity)
    assert "1 / 1" in reopened["text"] and not reopened["operations"]
    with pytest.raises(WorkflowError, match="changed"):
        file(work, PLAYER, draft, "learn", advancement=SPARROWS)


@pytest.mark.parametrize("name", ("gaze", "song"))
def test_harpy_specialist_start_and_private_counterparty_are_scene_bound(ledger, name):
    from test_physical_operations import place

    from girlframe.engine.m3_actor_bonds import current_ref, depth
    from girlframe.engine.m3_harpy_advancements import MANIC_PIXIE, SONG_OF_LOVE_LOST
    from girlframe.services.m3_harpy_gaze import records as gaze_records

    _, game, _, actor = ready_advancement(ledger)
    rule = {"gaze": MANIC_PIXIE, "song": SONG_OF_LOVE_LOST}[name]
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={"m3_approval": approval.model_copy(update={"activity_specialist_rules": {rule}})}
    )
    rooms = {900: ("ward", "Relay ward")}
    work = SpecialistWork(game, rooms)
    file(work, PLAYER, work.read(PLAYER, "advancement", actor.entity), "learn", advancement=rule)
    with ledger.transaction() as connection:
        canon = place(
            state(game),
            OTHER.user_id,
            mode="outside_frame",
            cell=(1, 0) if name == "song" else (0, 0),
        )
        game.event(connection, ADMIN.user_id, str(uuid4()), "synthetic.harpy_presence", canon)
    recipient = current_ref(state(game), OTHER.user_id)
    item = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "advancement_start")
    assert "Relay ward" in item["title"]
    draft = work.read(PLAYER, item["kind"], item["id"])
    file(work, PLAYER, draft, "file", target=recipient.token, account="Original encounter.")
    ledger.engine.dispose()
    work = SpecialistWork(game, rooms)
    kind = "advancement_" + name
    item = next(item for item in work.list(OTHER)["work"] if item["kind"] == kind)
    assert all(item["kind"] != kind for item in work.list(ADMIN)["work"])
    with pytest.raises(WorkflowError):
        work.read(ADMIN, kind, item["id"])
    reply = work.read(OTHER, kind, item["id"])
    if name == "gaze":
        file(
            work,
            OTHER,
            reply,
            "file",
            choices=["hands", "promise"],
            account="I take her hands.",
            promise="I will come back.",
        )
        assert gaze_records(state(game))[0].promise == "I will come back."
    else:
        file(work, OTHER, reply, "file", choice="yes", account="I step forward.")
        assert depth(state(game), actor, recipient) == 1


def test_harpy_kiss_requires_original_flirt_and_private_consent(ledger):
    from test_harpy_flirt import native_answer, prepared, start_native

    from girlframe.engine.m3_harpy_advancements import KISS
    from girlframe.engine.m3_harpy_defeat import harpy, update
    from girlframe.services.m3_harpy_intimacy import RULE, records

    _, game, _, actor, worker, gateway = prepared(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(update={"activity_specialist_rules": {KISS, RULE}})
        }
    )
    work = SpecialistWork(game, {900: ("relay", "Relay ward")})
    file(work, PLAYER, work.read(PLAYER, "advancement", actor.entity), "learn", advancement=KISS)
    with ledger.transaction() as connection:
        canon = update(state(game), actor, linked=False)
        game.event(connection, PLAYER.user_id, str(uuid4()), "synthetic.harpy_position", canon)
    action = start_native(game, actor, worker, gateway)
    own = harpy(state(game), actor).identities[0].id
    other = state(game).sheets["3"].identities[0].id
    native_answer(game, PLAYER, "harpy_flirt_actor", dict(options=("name",), denied=(own,)), 93572)
    native_answer(
        game,
        OTHER,
        "harpy_flirt_target",
        dict(options=("fears",), denied=(other,), text="Her own reply."),
        93576,
    )
    native_answer(game, PLAYER, "harpy_flirt_answer", dict(text="Her original answer."), 93580)
    tick(worker, gateway, 5)
    start = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "advancement_start")
    file(
        work,
        PLAYER,
        work.read(PLAYER, start["kind"], start["id"]),
        "file",
        source=action,
        choice="kiss",
        account="The original Flirt surprised her.",
    )
    review = next(item for item in work.list(ADMIN)["work"] if item["kind"] == "advancement_kiss")
    file(work, ADMIN, work.read(ADMIN, review["kind"], review["id"]), "file", choice="yes")
    ledger.engine.dispose()
    (encounter,) = records(state(game))
    consent = work.read(OTHER, "advancement_private", encounter.id)
    with pytest.raises(WorkflowError):
        file(work, PLAYER, consent, "file", choice="accept")
    file(work, OTHER, consent, "file", choice="decline")
    assert records(state(game))[0].phase == "complete" and not records(state(game))[0].consent


def test_harpy_defeat_keeps_the_original_owned_roll(ledger):
    service, game, worker, gateway, _, identity, _ = ready_defeat(ledger)
    work = SpecialistWork(game)
    assert any(item["id"] == identity for item in work.list(PLAYER)["work"])
    assert all(item["id"] != identity for item in work.list(OTHER)["work"])
    draft = work.read(PLAYER, "harpy_defeat", identity)
    action = file(work, PLAYER, draft, "begin", confirm="yes")["action_id"]
    tick(worker, gateway, 1)
    if service.inspect(PLAYER, action)["receipt"] is None:
        followup = work.read(PLAYER, "defeat_roll", action)
        file(work, PLAYER, followup, "roll")
    choice = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "defeat_choice")
    entry = work.read(PLAYER, choice["kind"], choice["id"])
    file(work, PLAYER, entry, "answer", mode="pass")
    original = service.inspect(PLAYER, action)["receipt"]
    ledger.engine.dispose()
    assert original["faces"] == [3, 4]
    assert service.inspect(PLAYER, action)["receipt"] == original
    assert game.dice.calls == 1
    assert all(item["id"] != choice["id"] for item in work.list(PLAYER)["work"])


def test_gorgon_core_counter_uses_the_exact_attacker_and_assigned_judge(ledger, monkeypatch):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "go_for_the_core"))
    game, worker, gateway, parent, _ = gorgon_source(ledger, exposed=True)
    work = SpecialistWork(game)
    defense = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "gorgon_choice")
    response = work.read(PLAYER, defense["kind"], defense["id"])
    file(work, PLAYER, response, "answer", options="play", text="I strike the exposed Core.")
    item = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "gorgon_counter")
    card = work.read(PLAYER, item["kind"], item["id"])
    core = next(item for item in card["operations"] if item["id"] == "go_for_the_core")
    weapon = next(item for item in core["fields"] if item["key"] == "weapon")["options"][0][0]
    created = file(
        work, PLAYER, card, "go_for_the_core", weapon=weapon, account="The Core is open."
    )
    identity = created["id"]
    review = work.read(ADMIN, "gorgon_counter_context", identity)
    assert not work.read(PLAYER, "gorgon_counter_context", identity)["operations"]
    with pytest.raises(WorkflowError):
        file(work, OTHER, review, "review", facts=["opening", "reach"], account="Forged")
    file(work, ADMIN, review, "review", facts=["opening", "reach"], account="The Core is open.")
    game.dice.faces = (6, 6)
    ledger.engine.dispose()
    ready = SpecialistWork(game).read(PLAYER, "gorgon_counter_context", identity)
    child = file(work, PLAYER, ready, "begin", heat="0")["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not next(x for x in state(game).world.gorgons if x.id == "source-gorgon").alive
    assert game.inspect(PLAYER, child)["receipt"]["faces"] == [6, 6]
    with ledger.engine.connect() as connection:
        assert game.action(connection, parent)["state"] == "complete"


def test_repossession_keeps_custodian_review_and_activation_separate(ledger, tmp_path, monkeypatch):
    from girlframe.engine.creation_catalog import CATALOG
    from girlframe.engine.m3_harpy_defeat import harpy

    game, _, _, actor = actual_captured(ledger, tmp_path, monkeypatch)
    work = SpecialistWork(game)
    prepared = work.read(ADMIN, "repossession", "captured")
    source = file(work, ADMIN, prepared, "open", actor=actor.entity)["id"]

    def stage(viewer, operation, **values):
        draft = work.read(viewer, "repossession", source)
        return file(work, viewer, draft, operation, **values)

    stage(OTHER, "extract", account="The custodian separates the connected captured Harpy.")
    assert harpy(state(game), actor).linked
    stage(ADMIN, "physical_review", allow="yes", account="The physical outcome is verified.")
    assert not harpy(state(game), actor).linked
    stage(
        OTHER, "transport", destination="treatment-base", account="Transfer to the treatment base."
    )
    stage(ADMIN, "physical_review", allow="yes", account="Arrival is verified.")
    stage(
        ADMIN,
        "treat",
        purge="Poison cleared.",
        organs="Organs reviewed.",
        conditioning="Treatment completed.",
        recovery="awake",
    )
    draft = work.read(PLAYER, "repossession", source)
    fields = {field["key"]: field["options"] for field in draft["operations"][0]["fields"]}
    assets = CATALOG["MOCKINGBIRD"]["assets"][:2]
    stage(
        PLAYER,
        "package",
        assets=list(assets),
        void=assets[0],
        description1="Original restraint.",
        description2="Altered perception.",
        appearance="Original body after treatment.",
        girl=fields["girl"][0][0],
        npc="actual-guard",
        role="2",
    )
    ledger.engine.dispose()
    stage(ADMIN, "review", position="1", account="The exact conversion package is verified.")
    assert not work.read(OTHER, "repossession", source)["operations"]
    stage(PLAYER, "complete", confirm="confirm")
    assert state(game).sheets["2"].girl == "MOCKINGBIRD"


def test_leviathan_influence_popup_starts_against_the_original_target(ledger, monkeypatch):
    from girlframe.engine.rules_registry import Registry
    from girlframe.services.m3_leviathan_obsession import ROLL, TYPE

    original = Registry.require_available

    def reviewed(registry, identity):
        if identity in (TYPE, ROLL):
            return next(entry for entry in registry.entries if entry.id == identity)
        return original(registry, identity)

    monkeypatch.setattr(Registry, "require_available", reviewed)
    game, worker, gateway, _, _ = leviathan_source(ledger)
    work = SpecialistWork(game, {900: ("source", "Leviathan chamber")})
    item = next(item for item in work.list(ADMIN)["work"] if item["kind"] == "leviathan_start")
    draft = work.read(ADMIN, item["kind"], item["id"])
    label = state(game).sheets["2"].callsign
    verb = next(row["id"] for row in draft["operations"] if row["label"].endswith(" → " + label))
    result = file(work, ADMIN, draft, verb, mode="give", account="There is actual co-presence.")
    tick(worker, gateway, 3)
    receipt = game.inspect(PLAYER, result["action_id"])
    assert receipt["state"] == "complete" and receipt["result"]["tag"]
    assert game.dice.calls == 0


def test_npc_flirt_followthrough_uses_the_original_recipient_and_receipt(
    ledger, tmp_path, monkeypatch
):
    from test_cast_service import change
    from test_enforcer_requisitions import approved
    from test_npc_flirt import finish_roll, ready

    from girlframe.engine import m3_npc_flirt as rules
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref, depth
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch, inside=False)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
        ),
    )
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(update={"subsystems": policy.subsystems | {"world"}})
        }
    )
    mission = MissionService(ledger)
    ref = ActorRef(kind="npc", entity="original-contact")
    WorldService(mission).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=ref.entity,
            name="Relay contact",
            jobs=("civilian",),
            controller=ADMIN.user_id,
            detail="Contact on the relay deck.",
            revealed=True,
            cell=(0, 0),
        ),
    )
    change(CastService(ActorService(mission)), ADMIN, "join", ref)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            heat=0,
            target_actor=ref,
            context="I ask their name.",
            trigger_confirmed=True,
        ),
    )["action_id"]
    game.dice.faces = (4, 4)
    finish_roll(game, worker, gateway, action)
    work = SpecialistWork(game)
    actor = next(item for item in work.list(PLAYER)["work"] if item["kind"] == "npc_flirt")
    file(work, PLAYER, work.read(PLAYER, actor["kind"], actor["id"]), "answer", question="name")
    target = next(item for item in work.list(ADMIN)["work"] if item["kind"] == "npc_flirt")
    file(
        work,
        ADMIN,
        work.read(ADMIN, target["kind"], target["id"]),
        "answer",
        text="Call me the relay keeper.",
    )
    tick(worker, gateway, 5)
    original = game.inspect(PLAYER, action)["receipt"]
    before = depth(state(game), current_ref(state(game), PLAYER.user_id), ref)
    draft = work.read(PLAYER, "npc_followthrough", action)
    receipt = file(work, PLAYER, draft, "perform", account="I called them the relay keeper.")
    ledger.engine.dispose()
    draft = work.read(ADMIN, "npc_followthrough", action)
    with pytest.raises(WorkflowError):
        file(work, OTHER, draft, receipt["id"], accepted="yes", account="Forged.")
    file(work, ADMIN, draft, receipt["id"], accepted="yes", account="The request was fulfilled.")
    assert before < depth(state(game), current_ref(state(game), PLAYER.user_id), ref)
    assert original == game.inspect(PLAYER, action)["receipt"] and game.dice.calls == 1
