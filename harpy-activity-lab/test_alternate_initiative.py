"""Synthetic Activity initiative, owner review, native execution and restart."""

from types import SimpleNamespace

import pytest
from ai_native_plays import ActivityNativePlays
from p2_scene import local_fixture_director
from private_battlefield import TURN_FACT, PrivateBattlefield
from test_activity_shadow_readiness import configure, consent, opt
from test_cast_service import change
from test_gorgon_runtime import gorgon_source
from test_harpy_beneath import prepared as harpy_prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, state, tick
from test_physical_operations import place
from test_world_service import ready as world_ready
from test_world_service import transfer_npc

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.campaign_opening import Opening
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_items import ItemService
from girlframe.services.m3_npc_handover import NpcHandoverService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


def native_case(store, kind, *, npc_job="fan", **gorgon_options):
    if kind == "gorgon":
        game, worker, gateway, _, declaration = gorgon_source(store, begin=False, **gorgon_options)
        source = GorgonPlayService(game)
        assert "attack" not in source.preview(ADMIN, 900)["plays"]
        approval = store.policy.m3_approval
        store.policy = store.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(
                    update=dict(
                        activity_specialist_rules=approval.activity_specialist_rules
                        | {"gorgon.gorgon.attack"}
                    )
                )
            )
        )
        assert "attack" in source.preview(ADMIN, 900)["plays"]
        return game, worker, gateway, ADMIN, declaration.actor, PLAYER, None
    if kind == "external_pilot":
        _, game, _, actor, worker, gateway = harpy_prepared(store, faces=(4, 4))
        with store.transaction() as c:
            canon = state(game)
            canon.order = (OTHER.user_id, PLAYER.user_id)
            game.event(c, ADMIN.user_id, "alternate-status", "synthetic.status", canon)
        return game, worker, gateway, PLAYER, actor, OTHER, None

    world, game = world_ready(store)
    actor = ActorRef(kind="npc", entity="local-contact")
    world.npc(
        ADMIN,
        "contact",
        state(game).revision,
        Npc(
            id=actor.entity,
            name="Local contact",
            detail="A regular on the landing.",
            jobs=(npc_job,),
            cell=(0, 0),
            controller=ADMIN.user_id,
            revealed=True,
        ),
    )
    with store.transaction() as c:
        canon = place(state(game), PLAYER.user_id, mode="outside_frame")
        game.event(c, PLAYER.user_id, "local-body", "synthetic.position", canon)
    change(CastService(ActorService(world.missions)), ADMIN, "join", actor)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(
                    subsystems=approval.subsystems | {"plays", "discipline"},
                    activity_specialist_rules=approval.activity_specialist_rules
                    | {f"npc.npc.{npc_job}"},
                )
            )
        )
    )
    items = ItemService(game)
    proposed = items.propose(
        PLAYER if npc_job == "fan" else ADMIN,
        "own-photo",
        current_ref(state(game), PLAYER.user_id) if npc_job == "fan" else actor,
        "Folded photograph",
        "An actual carried photograph.",
    )
    item = items.confirm(
        ADMIN,
        "proved-photo",
        proposed["id"],
        1,
        exists=True,
        account="I confirm the original custodian of the photograph.",
    )["item"]
    return game, GameWorker(game), Gateway(), ADMIN, actor, PLAYER, item


def activity(game, model, arena=None):
    app = local_fixture_director(game, activity_shadow=True)
    app.models = model
    setup = SimpleNamespace(game=game, play_registry=load_registry())
    app.session.context.native_play_projection = ActivityNativePlays(setup, arena)
    return app


class Stub:
    def __init__(self, target):
        self.target = target
        self.calls = 0

    def generate(self, instructions, packet, response):
        self.calls += 1
        option = next(x for x in packet["role"]["native_plays"] if x["id"].endswith(self.target))
        assert set(option) == {"id", "label", "reach"}
        return response(
            kind="SCENE_OFFER",
            play_id=option["id"],
            text="I make my move now.",
            rationale="Use the current opening.",
        )


def setup_initiative(game, scene, app):
    opt(app, scene)
    configure(app, scene)
    plan = Opening(
        scene="trial-introduction",
        channel=901,
        handler=ADMIN.user_id,
        audience=(ADMIN.user_id, PLAYER.user_id, OTHER.user_id),
        plan="trial-plan",
        goals="Watch the landing.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        handler_control="player",
    )
    with game.store.transaction() as c:
        game.store._audit(
            c, ADMIN.user_id, "approved-alternate-plan", EVENT, plan.model_dump(mode="json")
        )


def propose(app, scene, owner, actor):
    control = dict(actor=actor.model_dump(mode="json"), enabled=True, revision=None)
    with pytest.raises(WorkflowError, match="INITIATIVE_CONTROL_OWNER"):
        app.write(OTHER, "wrong-control", scene, "scene-alternate-control", control)
    app.write(owner, "enable-original", scene, "scene-alternate-control", control)
    (option,) = app.read(ADMIN, scene, "scene-initiative")["options"]
    assert option["actor"] == control["actor"]
    request = app.write(
        ADMIN, "open-original", scene, "scene-initiative-open", {"option": option["id"]}
    )
    saved = app.write(
        ADMIN, "stub-generation", scene, "reaction-generate", {"request": request["id"]}
    )
    approved = {
        "proposal": saved["id"],
        "decision": "approve",
        "reason": "I own this intent.",
        "recipients": [],
    }
    app.write(owner, "approved-original", scene, "npc-review", approved)
    return saved["id"]


def submit_choice(app, scene, actor, kind, **answer):
    choice = next(
        item
        for item in app.read(actor, scene, "scene-alternate-choices")["choices"]
        if item["kind"] == kind
    )
    projected = {field["key"] for field in choice["fields"]}
    assert {"options", "text"} <= projected
    provided = answer.keys() | {"fields." + key for key in answer.get("fields", {})}
    assert all(not field["required"] or field["key"] in provided for field in choice["fields"])
    payload = {"id": choice["id"], "revision": choice["revision"], "answer": answer}
    receipt = app.write(actor, kind, scene, "scene-alternate-answer", payload)
    assert app.write(actor, kind, scene, "scene-alternate-answer", payload) == receipt
    return receipt


@pytest.mark.parametrize("kind", ("npc", "external_pilot", "gorgon"))
def test_alternate_play_uses_approved_native_role_and_recovers_on_restart(ledger, kind):
    game, worker, gateway, owner, actor, target, item = native_case(ledger, kind)
    target_ref = current_ref(state(game), target.user_id)
    model = Stub(target_ref.token)
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    before = state(game)
    proposal = propose(app, scene, owner, actor)
    assert state(game) == before and model.calls == 1
    draft = app.read(owner, scene, "npc-owner-review", proposal)
    binding = draft["native_play"]["alternate"]
    assert binding["target_token"] == target_ref.token
    choices = (
        {"heat": 1}
        if kind == "external_pilot"
        else {"asset": next(iter(binding["choices"]["asset"]))}
        if kind == "gorgon"
        else {}
    )
    payload = {"proposal": proposal, "choices": choices}
    with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
        app.write(OTHER, "wrong-start", scene, "scene-alternate-start", payload)
    with pytest.raises(WorkflowError, match="INITIATIVE_PLAY_CHOICES"):
        app.write(
            owner,
            "illegal-target",
            scene,
            "scene-alternate-start",
            payload | {"choices": choices | {"target": "forged"}},
        )
    result = app.write(owner, "native-start", scene, "scene-alternate-start", payload)
    if kind == "npc":
        service = NpcHandoverService(game)
        with pytest.raises(WorkflowError):
            service.respond(owner, "fake-response", result["id"], state(game).revision, item)
        transferred = service.respond(
            target, "own-response", result["id"], state(game).revision, item
        )
        assert transferred["transfer"] and state(game).held_items[0].holder == actor
    else:
        tick(worker, gateway, 3)
        if kind == "external_pilot":
            from test_harpy_flirt import pass_tags

            pass_tags(game)
            assert game.inspect(owner, result["action_id"])["receipt"]
            submit_choice(
                app,
                scene,
                owner,
                "harpy_beneath_select",
                options=["tag", "status"],
                fields={"tag": "The real Harpy reproach"},
                text="I press the point.",
            )
            assert game.inspect(owner, result["action_id"])["state"] == "complete"
            assert resolve(state(game), actor, ()).heat == resolve(before, actor, ()).heat - 1
            assert state(game).sheets[str(owner.user_id)] == before.sheets[str(owner.user_id)]
        else:
            assert not app.read(owner, scene, "scene-alternate-choices")["choices"]
            submit_choice(
                app, scene, target, "gorgon_defend", options=["damage"], text="I take the blow."
            )
            choice = next(x for x in game.choices(target) if x["kind"] == "gorgon_damage_asset")
            asset = game.decision(target, choice["id"])["detail"]["assets"][0]["id"]
            submit_choice(
                app,
                scene,
                target,
                "gorgon_damage_asset",
                options=[asset],
                text="This Asset takes it.",
            )
            assert game.inspect(owner, result["action_id"])["state"] == "complete"
    after = state(game)
    calls = game.dice.calls
    ledger.engine.dispose()
    reopened = activity(game, model)
    assert reopened.read(owner, scene, "npc-owner-review", proposal)["receipt"] == result
    assert (
        reopened.write(owner, "transport-retry", scene, "scene-alternate-start", payload) == result
    )
    assert state(game) == after and game.dice.calls == calls and model.calls == 1


@pytest.mark.parametrize("job", ("patron", "smuggler"))
def test_activity_npc_handover_initiative_uses_only_the_npcs_own_item(ledger, job):
    game, _, _, owner, actor, target, item = native_case(ledger, "npc", npc_job=job)
    target_role = current_ref(state(game), target.user_id)
    app = activity(game, Stub(target_role.token))
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = propose(app, scene, owner, actor)
    menu = app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    assert menu["play"] == job and list(menu["choices"]["item"]) == [item]
    payload = {"proposal": proposal, "choices": {"item": item}}
    with pytest.raises(WorkflowError, match="INITIATIVE_PLAY_CHOICES"):
        app.write(
            owner,
            "bad-offer",
            scene,
            "scene-alternate-start",
            payload
            | {
                "choices": {"item": "an-unowned-item"},
            },
        )
    started = app.write(owner, "job-offer", scene, "scene-alternate-start", payload)
    assert state(game).held_items[0].holder == actor
    assert app.read(OTHER, scene, "scene-alternate-handovers")["handovers"] == []
    (offer,) = app.read(target, scene, "scene-alternate-handovers")["handovers"]
    assert offer["id"] == started["id"] and offer["job"] == job
    accepted = app.write(
        target,
        "accept-item",
        scene,
        "scene-alternate-handover-answer",
        {
            "id": offer["id"],
            "revision": offer["revision"],
            "item": item,
        },
    )
    assert accepted["transfer"] and state(game).held_items[0].holder == target_role
    ledger.engine.dispose()
    assert (
        activity(game, Stub(target_role.token)).write(
            owner, "retry-job-offer", scene, "scene-alternate-start", payload
        )
        == started
    )


@pytest.mark.parametrize(
    ("opponent", "source_option"),
    (("actual-guard", "npc"), ("actual-pitted-harpy", "harpy"), ("opposing-gorgon", "opposing")),
)
def test_activity_gorgon_attack_resolves_actual_cross_role_targets(ledger, opponent, source_option):
    game, worker, gateway, owner, actor, _, _ = native_case(
        ledger, "gorgon", target=opponent, **{source_option: True}
    )
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
        cast = next(x for x in state(game).scene_casts if x.id == scene)
    target = next(x.actor for x in cast.roles if x.actor.entity == opponent)
    app = activity(game, Stub(target.token))
    setup_initiative(game, scene, app)
    proposal = propose(app, scene, owner, actor)
    preview = app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    assert preview["target_token"] == target.token
    receipt = app.write(
        owner,
        "cross-role-start",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"asset": next(iter(preview["choices"]["asset"]))},
        },
    )
    action = receipt["action_id"]
    original_sheets = state(game).sheets
    tick(worker, gateway, 3)
    if source_option == "npc":
        assert not next(x for x in state(game).world.npcs if x.id == opponent).alive
    else:
        defender = PLAYER if source_option == "harpy" else ADMIN
        with ledger.engine.connect() as c:
            row = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_contest_assets")
        if source_option == "harpy":
            assert app.read(owner, scene, "scene-alternate-choices")["choices"] == []
        assets = game.decision(defender, row["id"])["detail"]["assets"]
        asset = next(
            x["id"] for x in assets if source_option == "opposing" or x["family"] == "girl"
        )
        submit_choice(
            app, scene, defender, "gorgon_contest_assets", options=[asset], text="I brace with it."
        )
        assert app.read(OTHER, scene, "scene-alternate-choices")["choices"] == []
        submit_choice(
            app,
            scene,
            owner,
            "gorgon_contest_judge",
            options=["attacker"],
            fields={"asset": asset},
            text="The attacker removes the pitted Asset.",
        )
        assert state(game).facts[-1]["kind"] == "gorgon_asset_contest"
        assert state(game).facts[-1]["asset"] == asset
    assert game.inspect(owner, action)["state"] == "complete"
    assert state(game).sheets == original_sheets
    assert game.dice.calls == 0


@pytest.mark.parametrize("changed", ("turn", "controller", "consent", "control"))
def test_changed_authority_or_turn_rejects_approved_start(ledger, changed):
    import json

    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    game, _, _, owner, actor, listener, _ = native_case(ledger, "npc")
    model = Stub(current_ref(state(game), listener.user_id).token)
    arena = PrivateBattlefield.__new__(PrivateBattlefield)
    arena.store, arena.game, arena.channel = game.store, game, 900
    app = activity(game, model, arena)
    with ledger.transaction() as c:
        room = game.scene(c, 900)
        canon = state(game)
        eligible = arena.placed(c, canon, room)
        assert actor.token in eligible
        order = [actor.token, *[ref for ref in eligible if ref != actor.token]]
        canon.facts.append(
            dict(
                kind=TURN_FACT,
                scene=room["id"],
                body=json.dumps(
                    dict(order=order, offset=0, epoch="test-turn"),
                ),
            )
        )
        game.event(c, ADMIN.user_id, "initial-turn", "synthetic.test_turn", canon)
    scene = room["id"]
    setup_initiative(game, scene, app)
    proposal = propose(app, scene, owner, actor)
    assert (
        app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]["turn"]
        == "test-turn:0"
    )
    if changed == "turn":
        arena.change_turn(
            owner, "end-original-turn", "end-turn", {"revision": state(game).revision}
        )
        error = "INITIATIVE_STALE"
    elif changed == "controller":
        transfer_npc(WorldService(MissionService(ledger)), owner, OTHER, actor.entity)
        error = "REACTION_NOT_OWNED"
    elif changed == "consent":
        consent(app, scene, listener, value=False)
        error = "OBSERVATION_DISABLED"
    else:
        (control,) = app.read(owner, scene, "scene-alternate-actors")["actors"]
        app.write(
            owner,
            "revoke-original",
            scene,
            "scene-alternate-control",
            {
                "actor": control["actor"],
                "enabled": False,
                "revision": control["revision"],
            },
        )
        error = "INITIATIVE_CONTROL_OWNER"
    before = state(game)
    with pytest.raises(WorkflowError, match=error):
        app.write(
            owner,
            "stale-alternate-start",
            scene,
            "scene-alternate-start",
            {"proposal": proposal, "choices": {}},
        )
    assert state(game) == before and game.dice.calls == 0


def test_unsupported_npc_play_reaches_only_assigned_facilitator(ledger):
    game, _, _, owner, actor, listener, _ = native_case(ledger, "npc")
    app = activity(game, Stub("unused"))
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    service = FacilitatorService(game)
    service.configure(ADMIN, "set-tribunal", "user", OTHER.user_id)
    control = {"actor": actor.model_dump(mode="json"), "enabled": True, "revision": None}
    app.write(owner, "enable-new-actor", scene, "scene-alternate-control", control)
    referral = {"actor": control["actor"]}
    first = app.write(owner, "refer-unsupported", scene, "scene-alternate-refer", referral)
    assert app.write(owner, "refer-unsupported", scene, "scene-alternate-refer", referral) == first
    assert "Independent NPC initiation has no native form" in str(service.view(OTHER, first["id"]))
    with pytest.raises(WorkflowError):
        service.view(listener, first["id"])
    assert game.dice.calls == 0


@pytest.mark.parametrize("kind", ("npc", "external_pilot", "gorgon"))
def test_alternate_approval_and_native_start_over_activity_http(ledger, monkeypatch, kind):
    import json
    from http.cookiejar import CookieJar
    from queue import Queue
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from uuid import uuid4

    import mission_lab

    from girlframe.services.m3_missions import MissionService

    game, _, _, owner, actor, target, item = native_case(ledger, kind)
    model = Stub(current_ref(state(game), target.user_id).token)
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    startup = Queue()
    servers = Queue()

    class FixtureServer(mission_lab.ActivityHTTPServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            servers.put(self)

    monkeypatch.setattr(mission_lab, "ActivityHTTPServer", FixtureServer)
    monkeypatch.setattr(
        mission_lab, "print", lambda value, **_: startup.put(json.loads(value)), raising=False
    )
    monkeypatch.setattr(mission_lab, "local_fixture_director", lambda *_, **__: app)
    monkeypatch.setattr(mission_lab, "OFFERED", ADMIN)
    monkeypatch.setattr(mission_lab, "OTHER", PLAYER)
    monkeypatch.setattr(mission_lab, "HANDLER", ADMIN)
    server_thread = Thread(
        target=mission_lab.serve,
        daemon=True,
        args=(MissionService(ledger), 0, False),
        kwargs=dict(
            scene_dice=game.dice,
            p2_fixture=True,
            p2_shadow_readiness=True,
        ),
    )
    server_thread.start()
    server = servers.get(timeout=15)
    try:
        metadata = startup.get(timeout=15)
        origin = metadata["origin"]
        gm, pilot = (build_opener(HTTPCookieProcessor(CookieJar())) for _ in range(2))
        for client, label in ((gm, "Invited pilot"), (pilot, "Other pilot")):
            with client.open(metadata["pilots"][label], timeout=10) as response:
                assert response.status == 200
        controller = gm if owner == ADMIN else pilot

        def request(client, route, payload=None):
            path = f"{origin}/api/director/{scene}/{route}"
            headers = {
                "Origin": origin,
                "Content-Type": "application/json",
                "Idempotency-Key": str(uuid4()),
            }
            data = json.dumps(payload).encode() if payload is not None else None
            with client.open(Request(path, data=data, headers=headers), timeout=10) as response:
                return json.load(response)

        request(
            controller,
            "scene-alternate-control",
            dict(actor=actor.model_dump(mode="json"), enabled=True, revision=None),
        )
        (controlled,) = request(controller, "scene-alternate-actors")["actors"]
        assert controlled["plays"]
        (option,) = request(gm, "scene-initiative")["options"]
        prepared = request(gm, "scene-initiative-open", {"option": option["id"]})
        proposal = request(gm, "reaction-generate", {"request": prepared["id"]})["id"]
        request(
            controller,
            "npc-review",
            dict(
                proposal=proposal,
                decision="approve",
                reason="I confirm my own Play.",
                recipients=[],
            ),
        )
        preview = request(controller, "npc-owner-review/" + proposal)
        native = preview["native_play"]["alternate"]
        assert next(
            play for play in controlled["plays"] if play["target"] == native["target_token"]
        ) == {
            "id": preview["native_play"]["id"],
            "label": preview["native_play"]["label"],
            "target": native["target_token"],
            "reach": native["reach"],
            "costs": native["costs"],
            "choices": native["choices"],
        }
        choices = {field: next(iter(options)) for field, options in native["choices"].items()}
        payload = dict(proposal=proposal, choices=choices)
        receipt = request(controller, "scene-alternate-start", payload)
        assert request(controller, "scene-alternate-start", payload) == receipt
        assert request(controller, "npc-owner-review/" + proposal)["receipt"] == receipt
        if kind == "npc":
            assert request(gm, "scene-alternate-handovers")["handovers"] == []
            (offer,) = request(pilot, "scene-alternate-handovers")["handovers"]
            answer = dict(id=receipt["id"], revision=offer["revision"], item=item)
            with pytest.raises(HTTPError) as denied:
                request(gm, "scene-alternate-handover-answer", answer)
            with denied.value as error:
                assert error.code == 409
            assert request(pilot, "scene-alternate-handover-answer", answer)["transfer"]
            assert state(game).held_items[0].holder == actor
    finally:
        server.shutdown()
        server_thread.join(timeout=15)
        assert not server_thread.is_alive()
