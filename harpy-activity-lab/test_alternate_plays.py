"""Typed alternate Plays through the real Activity review and decision routes."""

import pytest
from test_alternate_initiative import activity, native_case, setup_initiative, submit_choice
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_harpy_flirt import prepared as flirt_ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, state, tick
from test_physical_operations import place
from test_world_service import ready as world_ready
from test_world_service import transfer_npc

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_erratic_gorgon import RULE as ERRATIC
from girlframe.services.m3_gorgon_play import RULES
from girlframe.services.m3_npc_intelligence import RULE as INTELLIGENCE
from girlframe.services.onboarding import WorkflowError


class Plan:
    def __init__(self, play):
        self.play = play

    def generate(self, instructions, packet, response):
        options = packet["role"]["native_plays"]
        move = next(x for x in options if x["id"] == self.play)
        assert set(move) == {"id", "label", "reach"}
        if packet["role"]["actor"]["kind"] == "gorgon":
            assert "concrete physical details and no speech" in instructions
            account = "The Gorgon braces a low forelimb, its plates scraping the floor."
        else:
            account = "I'll try while the opening holds."
        return response(
            kind="SCENE_OFFER", play_id=move["id"], text=account, rationale="Actual role"
        )


def approve_play(app, scene, owner, actor, chooser=ADMIN):
    app.write(
        owner,
        actor.token,
        scene,
        "scene-alternate-control",
        {
            "actor": actor.model_dump(mode="json"),
            "enabled": True,
            "revision": None,
        },
    )
    option = next(
        item
        for item in app.read(chooser, scene, "scene-initiative")["options"]
        if item["source"]["kind"] == "native" and item["actor"]["entity"] == actor.entity
    )
    request = app.write(
        chooser,
        "open:" + option["id"],
        scene,
        "scene-initiative-open",
        {
            "option": option["id"],
        },
    )
    proposal = app.write(
        chooser,
        "generate:" + option["id"],
        scene,
        "reaction-generate",
        {
            "request": request["id"],
        },
    )["id"]
    app.write(
        owner,
        "approve:" + proposal,
        scene,
        "npc-review",
        {
            "proposal": proposal,
            "decision": "approve",
            "reason": "Exact source intent.",
            "recipients": [],
        },
    )
    return proposal


@pytest.mark.parametrize("kind", ("growth_regrow", "warp", "collateral", "corrupt"))
def test_gorgon_type_and_environment_forms_use_native_owners_and_resources(ledger, kind):
    game, worker, gateway, owner, actor, _, _ = native_case(
        ledger,
        "gorgon",
        types=("growth", "sentinel"),
        damaged=True,
        exposed=kind == "warp",
    )
    approval = game.store.policy.m3_approval
    game.store.policy = game.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "activity_specialist_rules": approval.activity_specialist_rules | {RULES[kind]},
                }
            ),
        }
    )
    model = Plan(f"gorgon_declaration_{kind}:environment")
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, owner, actor)
    binding = app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    fields = {field["key"]: field["options"] for field in binding["fields"]}
    choices = {}
    if kind == "growth_regrow":
        choices = {
            "eaten": fields["eaten"][0][0],
            "replacement": "Glass filament",
            "description": "Glass threads weave a new brace.",
        }
    elif kind == "collateral":
        choices = {"assets": [fields["assets"][-1][0]]}
    if fields:
        with pytest.raises(WorkflowError, match="INITIATIVE_PLAY_CHOICES"):
            app.write(
                owner,
                "forged-field",
                scene,
                "scene-alternate-start",
                {
                    "proposal": proposal,
                    "choices": {"asset": "someone else's Asset"},
                },
            )
    action = app.write(
        owner,
        "start",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": choices,
        },
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(owner, "advance", scene, "scene-alternate-advance", {"id": action})
    if kind == "warp":
        submit_choice(
            app,
            scene,
            owner,
            "gorgon_warp",
            options=["evolve"],
            text="The plates rearrange around the exposed gap.",
            fields={"name": "New guard", "description": "A hinged new plate."},
        )
    elif kind == "collateral":
        submit_choice(
            app,
            scene,
            owner,
            "gorgon_collateral",
            options=["environment"],
            text="It tears loose the floor around it.",
        )
    result = game.inspect(owner, action)
    assert game.dice.calls == 0 and result["receipt"] is None
    ledger.engine.dispose()
    reopened = activity(game, model)
    assert (
        reopened.write(
            owner,
            "start-again",
            scene,
            "scene-alternate-start",
            {
                "proposal": proposal,
                "choices": choices,
            },
        )["action_id"]
        == action
    )
    assert game.inspect(owner, action)["state"] == result["state"]


def test_harpy_core_uses_its_own_assets_through_declaration_review_and_roll(ledger):
    _, game, cast, actor = ready(ledger, heat=1, faces=(4, 4))
    target = ActorRef(kind="npc", entity="trial-core-target")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                *canon.world.npcs,
                Npc(
                    id=target.entity,
                    name="Trial guard",
                    jobs=("guard",),
                    detail="Synthetic Core target.",
                    controller=OTHER.user_id,
                    revealed=True,
                    cell=(0, 0),
                ),
            ),
        )
        game.event(c, ADMIN.user_id, "introduce-trial-guard", "synthetic.world", canon)
        scene = game.scene(c, 900)["id"]
    change(cast, OTHER, "join", target)
    model = Plan("harpy_battle_go_for_the_core:" + target.token)
    app = activity(game, model)
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, PLAYER, actor)
    native = app.read(PLAYER, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    (field,) = native["fields"]
    before = state(game)
    declaration = app.write(
        PLAYER,
        "declare-core",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"weapon": field["options"][0][0]},
        },
    )["id"]
    with pytest.raises(WorkflowError, match="judge's approval"):
        app.write(
            PLAYER,
            "premature",
            scene,
            "scene-alternate-battle-commit",
            {"id": declaration, "heat": 0},
        )
    review = app.read(ADMIN, scene, "scene-alternate-battles")["battles"][0]
    assert review["id"] == declaration and review["review"]
    result = dict(
        id=declaration,
        revision=review["revision"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual openings and reach were verified.",
    )
    with pytest.raises(WorkflowError, match="source adjudicator"):
        app.write(PLAYER, "wrong-judge", scene, "scene-alternate-battle-review", result)
    app.write(ADMIN, "judge", scene, "scene-alternate-battle-review", result)
    ledger.engine.dispose()
    app = activity(game, model)
    commit = {"id": declaration, "heat": 0}
    action = app.write(PLAYER, "commit", scene, "scene-alternate-battle-commit", commit)[
        "action_id"
    ]
    tick(GameWorker(game), Gateway(), 3)
    app.write(PLAYER, "advance-core", scene, "scene-alternate-advance", {"id": action})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    saved = game.inspect(PLAYER, action)
    assert saved["state"] == "complete" and saved["receipt"]["pre_total"] == 8
    assert not next(row for row in state(game).world.npcs if row.id == target.entity).alive
    assert state(game).sheets == before.sheets and game.dice.calls == 1
    ledger.engine.dispose()
    assert (
        activity(game, model).write(
            PLAYER, "commit-again", scene, "scene-alternate-battle-commit", commit
        )["action_id"]
        == action
    )
    assert game.inspect(PLAYER, action)["receipt"] == saved["receipt"] and game.dice.calls == 1


@pytest.mark.parametrize("kind", ("gorgon_dormant_void", "battle_sprite_intercept"))
def test_gorgon_attack_native_source_work_stays_with_its_controller(ledger, kind):
    dormant = kind == "gorgon_dormant_void"
    target = (
        ActorRef(kind="gorgon", entity="opposing-gorgon")
        if dormant
        else ActorRef(kind="npc", entity="actual-guard")
    )
    game, worker, gateway, owner, actor, _, _ = native_case(
        ledger,
        "gorgon",
        target=target.entity,
        opposing=dormant,
        opposing_class="dormant",
        npc=not dormant,
        sprites=not dormant,
    )
    app = activity(game, Plan("gorgon_attack:" + target.token))
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, owner, actor)
    binding = app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    asset = next(iter(binding["choices"]["asset"]))
    event = app.write(
        owner,
        "attack",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"asset": asset},
        },
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(owner, "advance", scene, "scene-alternate-advance", {"id": event})
    form = next(
        x for x in app.read(owner, scene, "scene-alternate-choices")["choices"] if x["kind"] == kind
    )
    selected = form["fields"][0]["options"][-1][0]
    request = {k: form[k] for k in ("id", "revision", "game_revision")}
    request["answer"] = {"options": [selected], "text": "The original creature takes the contact."}
    assert not any(
        x["id"] == form["id"] for x in app.read(OTHER, scene, "scene-alternate-choices")["choices"]
    )
    with pytest.raises(WorkflowError, match="own required work"):
        app.write(OTHER, "wrong-owner", scene, "scene-alternate-work", request)
    prior = state(game)
    applied = app.write(owner, "native-answer", scene, "scene-alternate-work", request)
    ledger.engine.dispose()
    assert app.write(owner, "native-answer", scene, "scene-alternate-work", request) == applied
    after = state(game)
    assert game.dice.calls == 0 and after.sheets == prior.sheets
    if dormant:
        assert any(
            x.id == selected and x.void
            for creature in after.world.gorgons
            if creature.id == actor.entity
            for x in creature.assets
        )
    else:
        assert next(x for x in after.world.npcs if x.id == target.entity).alive
        assert game.inspect(owner, event)["state"] == "complete"


def test_aggressive_extra_hit_is_owned_and_opens_no_extra_roll(ledger):
    game, worker, gateway, owner, actor, victim, _ = native_case(
        ledger,
        "gorgon",
        gorgon_class="aggressive",
    )
    with ledger.transaction() as c:
        scene = game.scene(c, 900)["id"]
        canon = state(game)
        body = canon.sheets[str(victim.user_id)]
        ref = current_ref(canon, victim.user_id)
        frames = [x for x in body.assets if x.family == "frame"]
        for asset in frames[:-1]:
            asset.damaged = True
        game.event(c, ADMIN.user_id, "last-frame", "synthetic.prior_actual_battle", canon)
    model = Plan("gorgon_attack:" + ref.token)
    app = activity(game, model)
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, owner, actor)
    binding = app.read(owner, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    action = app.write(
        owner,
        "take-opening",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"asset": next(iter(binding["choices"]["asset"]))},
        },
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(owner, "advance", scene, "scene-alternate-advance", {"id": action})
    submit_choice(app, scene, victim, "gorgon_defend", options=["damage"], text="I take the blow.")
    submit_choice(
        app,
        scene,
        victim,
        "gorgon_damage_asset",
        options=[frames[-1].id],
        text="The blow cracks my last Frame Asset.",
    )
    hit = next(
        x
        for x in app.read(owner, scene, "scene-alternate-choices")["choices"]
        if x["kind"] == "battle_aggressive_damage"
    )
    selected = hit["fields"][0]["options"][1][0]
    request = {k: hit[k] for k in ("id", "revision", "game_revision")}
    request["answer"] = {
        "options": [selected],
        "text": "Its forelimb comes through the open cockpit.",
    }
    with pytest.raises(WorkflowError, match="own required work"):
        app.write(victim, "take-over", scene, "scene-alternate-work", request)
    saved = app.write(owner, "extra-hit", scene, "scene-alternate-work", request)
    ledger.engine.dispose()
    assert (
        activity(game, model).write(owner, "extra-hit", scene, "scene-alternate-work", request)
        == saved
    )
    assert next(x for x in state(game).sheets[ref.entity].assets if x.id == selected).damaged
    assert game.dice.calls == 0


def test_npc_inquiry_goes_to_its_gm_then_only_the_original_agent(ledger):
    world, game = world_ready(ledger)
    faction = Faction(id="private-cell", name="Synthetic secret", kind="rebel", cells=((0, 0),))
    world.faction(ADMIN, "add-cell", state(game).revision, faction)
    agent = ActorRef(kind="npc", entity="agent")
    witness = ActorRef(kind="npc", entity="witness")
    cast = CastService(ActorService(world.missions))
    for role, job, hidden in (
        (agent, "intelligence_agent", ()),
        (witness, "base_personnel", (faction.id,)),
    ):
        world.npc(
            ADMIN,
            "add:" + role.entity,
            state(game).revision,
            Npc(
                id=role.entity,
                name=role.entity,
                detail="An original test NPC.",
                jobs=(job,),
                controller=ADMIN.user_id,
                revealed=True,
                cell=(0, 0),
                secret_factions=hidden,
            ),
        )
    transfer_npc(world, ADMIN, PLAYER, agent.entity)
    change(cast, PLAYER, "join", agent)
    change(cast, ADMIN, "join", witness)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(
                update={
                    "subsystems": policy.subsystems | {"plays"},
                    "activity_specialist_rules": policy.activity_specialist_rules | {INTELLIGENCE},
                }
            )
        }
    )
    model = Plan("npc_inquiry:" + witness.token)
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, PLAYER, agent)
    identity = app.write(
        PLAYER,
        "start-inquiry",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {},
        },
    )["id"]
    assert app.read(PLAYER, scene, "scene-alternate-handovers")["inquiries"] == []
    gc = app.read(ADMIN, scene, "scene-alternate-handovers")["inquiries"]
    (review,) = gc
    assert review["id"] == identity and review["factions"] == {faction.id: faction.name}
    payload = dict(
        id=identity,
        revision=review["revision"],
        faction=faction.id,
        finding="A signed ledger puts the witness inside the cell.",
    )
    with pytest.raises(WorkflowError, match="assigned to you"):
        app.write(OTHER, "wrong-review", scene, "scene-alternate-inquiry-review", payload)
    saved = app.write(ADMIN, "assign-finding", scene, "scene-alternate-inquiry-review", payload)
    ledger.engine.dispose()
    app = activity(game, model)
    assert (
        app.write(ADMIN, "assign-finding", scene, "scene-alternate-inquiry-review", payload)
        == saved
    )
    (report,) = app.read(PLAYER, scene, "scene-alternate-handovers")["inquiries"]
    assert report["step"] == "report" and report["finding"] == payload["finding"]
    assert app.read(OTHER, scene, "scene-alternate-handovers")["inquiries"] == []
    assert game.dice.calls == 0


def test_erratic_tag_uses_the_original_world_actor_and_npc(ledger):
    game, _, _, owner, actor, _, _ = native_case(ledger, "gorgon", npc=True)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(
                update={
                    "activity_specialist_rules": policy.activity_specialist_rules | {ERRATIC},
                }
            )
        }
    )
    model = Plan("gorgon_erratic_tag:npc:actual-guard")
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, owner, actor)
    payload = {"proposal": proposal, "choices": {"tag": "Dusted with white glass"}}
    tagged = app.write(owner, "tag-guard", scene, "scene-alternate-start", payload)["event"]
    ledger.engine.dispose()
    assert (
        activity(game, model).write(
            owner,
            "recover-tag",
            scene,
            "scene-alternate-start",
            payload,
        )["event"]
        == tagged
    )
    guard = next(x for x in state(game).world.npcs if x.id == "actual-guard")
    (tag,) = guard.tags
    assert tag.id == tagged and ActorRef.model_validate_json(tag.giver_entity) == actor
    assert game.dice.calls == 0


def test_harpy_dive_records_a_real_voiced_choice_and_original_void_asset(ledger):
    _, game, _, actor = ready(ledger, heat=0, faces=(4, 5))
    model = Plan("harpy_dive_deep:self")
    app = activity(game, model)
    with ledger.transaction() as c:
        scene = game.scene(c, 900)["id"]
        canon = state(game)
        body = next(x for x in canon.world.pilots if x.id == actor.entity)
        body = body.model_copy(
            update={
                "assets": tuple(asset.model_copy(update={"void": False}) for asset in body.assets)
            }
        )
        canon.world = update(canon.world, pilots=(body,))
        game.event(c, ADMIN.user_id, "surface-asset", "synthetic.native_asset", canon)
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, PLAYER, actor)
    action = app.write(
        PLAYER,
        "start-dive",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"heat": 0},
        },
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    app.write(PLAYER, "roll-dive", scene, "scene-alternate-advance", {"id": action})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    submit_choice(
        app,
        scene,
        PLAYER,
        "dive_select",
        options=["void_and_unmark_all"],
        text="Witness the shape of the new brace.",
    )
    decision = next(
        x
        for x in app.read(PLAYER, scene, "scene-alternate-choices")["choices"]
        if x["kind"] == "dive_effect"
    )
    selected = decision["fields"][0]["options"][0][0]
    submit_choice(
        app,
        scene,
        PLAYER,
        "dive_effect",
        fields={"asset": selected},
        text="Thin glass braces run along the original Asset.",
    )
    saved = game.inspect(PLAYER, action)
    assert saved["receipt"]["faces"] == [4, 5] and saved["state"] == "complete"
    assert any(
        asset.id == selected and asset.void
        for item in state(game).world.pilots
        if item.id == actor.entity
        for asset in item.assets
    )
    assert game.dice.calls == 1


def test_harpy_assault_uses_actual_contest_and_table_not_its_controllers_pilot(ledger):
    _, game, _, actor = ready(ledger, heat=0, faces=(4, 4))
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id)
        game.event(c, OTHER.user_id, "opposing-frame", "synthetic.position", canon)
        scene = game.scene(c, 900)["id"]
    target = current_ref(state(game), OTHER.user_id)
    model = Plan("harpy_battle_all_out_assault:" + target.token)
    app = activity(game, model)
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, PLAYER, actor)
    binding = app.read(PLAYER, scene, "npc-owner-review", proposal)["native_play"]["alternate"]
    choices = {item["key"]: item["options"][0][0] for item in binding["fields"]}
    declaration = app.write(
        PLAYER,
        "assault",
        scene,
        "scene-alternate-start",
        {"proposal": proposal, "choices": choices},
    )["id"]
    (review,) = app.read(ADMIN, scene, "scene-alternate-battles")["battles"]
    app.write(
        ADMIN,
        "assault-ruling",
        scene,
        "scene-alternate-battle-review",
        dict(
            id=declaration,
            revision=review["revision"],
            opening=True,
            reach=True,
            outside_permission=True,
            indirect=False,
            evidence="An actual exposed route.",
        ),
    )
    action = app.write(
        PLAYER, "commit", scene, "scene-alternate-battle-commit", {"id": declaration, "heat": 0}
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    app.write(PLAYER, "advance", scene, "scene-alternate-advance", {"id": action})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    submit_choice(
        app,
        scene,
        PLAYER,
        "engage_assault_extra",
        options=["cover"],
        fields={"cover": choices["weapon"]},
        text="The Harpy holds the corridor.",
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(
            app,
            scene,
            viewer,
            "battle_assault_table",
            flag=False,
            text="There is no overwhelming advantage here.",
        )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert next(
        x for x in state(game).sheets["3"].assets if x.id == choices["opposing_asset"]
    ).damaged
    assert state(game).sheets["2"] == canon.sheets["2"]


def test_harpy_flirt_and_owed_followthrough_stay_with_each_recipient(ledger):
    _, game, _, actor, worker, gateway = flirt_ready(ledger)
    target = current_ref(state(game), OTHER.user_id)
    model = Plan("harpy_flirt:" + target.token)
    app = activity(game, model)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)
    proposal = approve_play(app, scene, PLAYER, actor)
    action = app.write(
        PLAYER,
        "start-flirt",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {"heat": 0},
        },
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(PLAYER, "advance-flirt", scene, "scene-alternate-advance", {"id": action})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    submit_choice(app, scene, PLAYER, "harpy_flirt_actor", options=["name"])
    submit_choice(app, scene, OTHER, "harpy_flirt_target", text="Use my actual callsign.")
    grant = next(x for x in state(game).obligations if x.kind == "harpy_flirt_followthrough")
    tick(worker, gateway, 5)
    model.play = "harpy_followthrough_" + grant.id + ":" + target.token
    follow = next(
        x
        for x in app.read(ADMIN, scene, "scene-initiative")["options"]
        if x["subject"] == "Follow through on Flirt · " + state(game).sheets["3"].callsign
    )
    request = app.write(
        ADMIN, "open-grant", scene, "scene-initiative-open", {"option": follow["id"]}
    )
    proposal = app.write(
        ADMIN, "generate-grant", scene, "reaction-generate", {"request": request["id"]}
    )["id"]
    app.write(
        PLAYER,
        "review-grant",
        scene,
        "npc-review",
        {
            "proposal": proposal,
            "decision": "approve",
            "reason": "Use the original callsign.",
            "recipients": [],
        },
    )
    second = app.write(
        PLAYER,
        "start-grant",
        scene,
        "scene-alternate-start",
        {
            "proposal": proposal,
            "choices": {},
        },
    )["action_id"]
    tick(worker, gateway, 3)
    submit_choice(
        app,
        scene,
        OTHER,
        "harpy_flirt_followthrough_confirm",
        flag=True,
        text="Yes. The Harpy used my callsign.",
    )
    assert depth(state(game), actor, target) == 1
    assert game.inspect(PLAYER, second)["receipt"] is None
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [4, 5] and game.dice.calls == 1
