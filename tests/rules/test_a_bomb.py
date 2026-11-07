"""Actual nuclear source, printed exceptions, resource owners and canonical endings."""

import asyncio
from uuid import uuid4

import pytest
from handler_award_scenario import ordinary_pr_award
from test_cockpit_service import command
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_strain_service import D6
from test_world import gorgon

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireABomb, open_advancement
from girlframe.engine import m3_a_bomb as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world import require_usable, update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Board, Goal, Location, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_a_bomb import ABombService, prove_consumed_item, prove_drop
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_items import ItemService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def interaction(uid=1):
    value = current(uid, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


def acquire(service, game):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def run():
        original = interaction()
        await original.response.defer(ephemeral=True)
        await open_advancement(original, HandlerAdvancementService(service.store), award.id)
        form = original.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in form.children if isinstance(x, AcquireABomb))
        selected = interaction()
        await selected.response.defer(ephemeral=True)
        await button.callback(selected)
        child = selected.edit_original_response.call_args.kwargs["view"]
        child.values["account"] = "My actual held Award buys A-Bomb"
        await child.confirm.callback(interaction())
        assert child.completed

    asyncio.run(run())
    return rules.acquisitions(state(game))[0]


def ready(store, tmp_path, monkeypatch, *, casualties=False):
    import test_mission_service

    initial_factory = test_mission_service.setup_game

    def initial_ordinary_frame(campaign, **values):
        import test_ledger
        import test_m2_game

        # The existing initializer separately builds the second player's draft with JANUS-B.
        # Parameterize that genuine creation call too, within this one initial factory invocation.
        original_draft = test_m2_game.selected
        original_profile = test_ledger.DraftInput
        with monkeypatch.context() as creation:
            creation.setattr(
                test_ledger,
                "DraftInput",
                lambda **draft: original_profile(**(draft | {"frame_playbook": "THE ENFORCER"})),
            )
            creation.setattr(
                test_m2_game, "selected", lambda girl, frame: original_draft(girl, "THE ENFORCER")
            )
            return initial_factory(campaign, **(values | {"frame": "THE ENFORCER"}))

    monkeypatch.setattr(test_mission_service, "setup_game", initial_ordinary_frame)
    game, worker, gateway = ordinary_pr_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=store.policy.m3_approval.subsystems
                    | {"world", "strain", "missions", "plays", "playbooks"}
                )
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        if casualties:
            frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
            for asset in frames[2:]:
                asset.damaged = True
        native = AdversaryPilot(
            id="actual-harpy",
            name="Actual native Harpy",
            kind="harpy",
            girl="HARPY",
            frame="HARPY",
            controller=2,
            cell=(1, 2),
            assets=tuple(
                Asset(
                    id="harpy-frame-" + str(i),
                    family="frame",
                    name="Actual Harpy resource " + str(i),
                    description="Existing independent Frame capability",
                )
                for i in range(3)
            ),
        )
        canon.world = update(
            canon.world,
            board=Board(minimum=(-2, -2), maximum=(8, 8)),
            locations=canon.world.locations
            + (
                Location(
                    id="outside-base",
                    name="Actual distant surviving Base",
                    kind="base",
                    cell=(5, 6),
                ),
                Location(
                    id="actual-blast-target",
                    name="Actual hostile installation",
                    kind="important",
                    cell=(3, 3),
                ),
            ),
            npcs=(
                Npc(
                    id="blast-npc",
                    name="PRIVATE_ACTUAL_NPC",
                    jobs=("civilian",),
                    detail="Actual preexisting civilian",
                    controller=1,
                    cell=(1, 0),
                ),
            ),
            gorgons=(
                gorgon("sprite", "actual-sprite", cell=(0, 1), follows="actual-gorgon"),
                gorgon(
                    "directed",
                    "actual-gorgon",
                    cell=(2, 1),
                    goal=Goal(kind="location", entity_id="base0"),
                ),
            )
            if casualties
            else (),
            pilots=(native,) if casualties else (),
        )
        game.event(c, 1, str(uuid4()), "synthetic.initial_blast_world_facts", canon)
    if casualties:
        physical = PhysicalService(store)
        for viewer in (PLAYER, OTHER):
            data, operation = command(physical, "pilot", viewer=viewer)
            physical.operate(viewer, str(uuid4()), data["game_revision"], operation)
        harpy = HarpyDefeatService(store, game=game)
        proposal = harpy.propose_runtime(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            NativeHarpyFacts(
                actor=ActorRef(kind="external_pilot", entity="actual-harpy"),
                linked=True,
                girl_cell=(1, 2),
                frame_cell=(1, 2),
                heat=0,
                frame_shutdown=False,
                body_incapacitated=False,
                custody="free",
                identities=(HarpyIdentity(id="harpy-identity", name="Actual free Harpy"),),
                tags=(),
                account="Actual native Harpy body and original Frame",
                facts_confirmed=True,
            ),
        )
        harpy.review_setup(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            state(game).revision,
            True,
            "Actual current Harpy resource/body review",
        )
    strain = StrainService(OffDutyService(MissionService(store)), dice=D6(1))
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    service = ABombService(store)
    receipt = acquire(service, game)
    return game, service, receipt, worker, gateway, strain


def device(service, game, receipt, label, cell=(1, 1)):
    items = ItemService(game)
    source = items.propose(
        ADMIN,
        str(uuid4()),
        active_handler(state(game)),
        label,
        "Actual carried nuclear device with source-proved existence",
        weapon=True,
    )
    items.confirm(
        ADMIN,
        str(uuid4()),
        source["id"],
        items.get(ADMIN, source["id"])["revision"],
        exists=True,
        account="Actual factual nuclear object, carried by this original Handler",
    )
    actual = next(x for x in state(game).held_items if x.name == label)
    result = service.certify_device(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        actual.id,
        cell,
        (
            "PRIVATE_NUCLEAR_CAPABILITY: actual nuclear device carried/released at this "
            "known map square"
        ),
    )
    return result["id"]


def damage_all(service, game, identity):
    for row in next(x for x in rules.drops(state(game)) if x.id == identity).resources:
        viewer = ADMIN if row.controller == 1 else PLAYER if row.controller == 2 else OTHER
        service.damage(
            viewer, str(uuid4()), identity, state(game).revision, row.actor, row.assets[:2]
        )


def actual_mission(store, game):
    service = MissionService(store)
    offer = service.offer(ADMIN, str(uuid4()), "Prevent the actual nuclear-site threat", (2, 3))
    for viewer in (PLAYER, OTHER):
        current = service.get(viewer, offer["id"])["mission"]
        service.respond(viewer, str(uuid4()), offer["id"], current["revision"], "accept")
    current = service.get(ADMIN, offer["id"])["mission"]
    service.start(ADMIN, str(uuid4()), offer["id"], current["revision"])
    return service, offer["id"]


def test_actual_casualties_core_exposure_owned_damage_safe_defeat_ejection_history(
    ledger, tmp_path, monkeypatch
):
    game, service, receipt, worker, gateway, _ = ready(
        ledger, tmp_path, monkeypatch, casualties=True
    )
    nuclear = device(service, game, receipt, "Actual first nuclear device")
    actor = current_ref(state(game), 2)
    initial = state(game)
    command_key = str(uuid4())
    arguments = (
        ADMIN,
        command_key,
        receipt.id,
        initial.revision,
        nuclear,
        (1, 1),
        ("safe_ejection", "cores"),
        "Actual source-owned release of the carried nuclear device",
    )
    with pytest.raises(WorkflowError):
        service.drop(OTHER, str(uuid4()), *arguments[2:])
    with pytest.raises(WorkflowError):
        service.drop(ADMIN, str(uuid4()), receipt.id, initial.revision - 1, *arguments[4:])
    assert state(game) == initial
    original_initial = service._initial

    def interrupted(*args):
        original_initial(*args)
        raise RuntimeError("interruption after actual canonical blast/effect staging")

    with monkeypatch.context() as failure:
        failure.setattr(service, "_initial", interrupted)
        with pytest.raises(RuntimeError, match="canonical blast"):
            service.drop(*arguments)
    assert state(game) == initial
    assert not rules.drops(state(game))
    result = service.drop(*arguments)
    identity = result["id"]
    committed = state(game)
    assert service.drop(*arguments) == result and state(game) == committed
    blast = state(game)
    assert not next(x for x in blast.world.gorgons if x.id == "actual-sprite").alive
    assert not blast.world.npcs[0].alive
    assert next(x for x in blast.world.gorgons if x.id == "actual-gorgon").exposed
    assert blast.world.pilots[0].exposed
    assert blast.strain.levels["budget"] == blast.strain.levels["rebellion"] == "high"
    with pytest.raises(WorkflowError):
        service.drop(
            ADMIN,
            str(uuid4()),
            receipt.id,
            blast.revision,
            nuclear,
            (1, 1),
            ("safe_ejection", "cores"),
            "No second actual device exists",
        )
    with pytest.raises(WorkflowError):
        service.damage(ADMIN, str(uuid4()), identity, blast.revision, actor, ("frame:0",))
    damage_all(service, game, identity)
    after = state(game)
    assert sum(x.damaged for x in after.world.gorgons[-1].assets) == 2
    assert sum(x.damaged for x in after.world.pilots[0].assets) == 2
    with ledger.engine.connect() as c:
        value = prove_drop(game, c, after, identity)
        consumed = next(x for x in after.held_items if x.id == value.device)
        prove_consumed_item(game, c, after, consumed)
        forged = after.model_copy(deep=True)
        rules.put(forged, value.model_copy(update=dict(cells=((8, 8),))))
        with pytest.raises(WorkflowError):
            prove_drop(game, c, forged, identity)
    owed = next(x for x in value.resources if x.actor == actor).work[0]
    game.dice = Dice((3, 3))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        after.sheets["2"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            source_work=owed,
            context="My actual Frame was disabled by nuclear damage",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="I actually eject from this fully damaged Frame into the source-protected blast area",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert "2" in state(game).sheets
    assert next(x for x in state(game).placements if x.actor == actor).mode == "outside_frame"
    tick(worker, gateway, 3)
    unprotected_device = device(
        service, game, receipt, "Actual distinct unprotected nuclear device"
    )
    unprotected = service.drop(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        unprotected_device,
        (0, 0),
        ("gentle_fallout", "cores"),
        "Actual original release at 1,1 and physical device impact at 0,0",
    )["id"]
    assert any(x.actor == actor and x.ending == "death" for x in state(game).career_archives)
    original_other = next(
        x.actor for x in value.resources if x.actor.kind == "pilot" and x.actor.entity == "3"
    )
    second_owed = next(x for x in value.resources if x.actor == original_other).work[0]
    game.dice = Dice((3, 3))
    second_action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            source_work=second_owed,
            context=(
                "My actual Frame is fully damaged and the second blast has unprotected radiation"
            ),
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (ADMIN, PLAYER, OTHER):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="I actually eject into the second unprotected nuclear area",
    )
    assert game.inspect(OTHER, second_action)["state"] == "complete"
    assert any(
        x.actor == original_other and x.ending == "death" for x in state(game).career_archives
    )
    assert any(
        x.get("kind") == "a_bomb_radiation"
        and x.get("actor") == original_other.model_dump_json()
        and x.get("outcome") == "death"
        for x in state(game).facts
    )
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        assert next(x for x in service._tasks(c, ADMIN) if x["id"] == identity)["pending"]
    service.finish(ADMIN, str(uuid4()), identity, state(game).revision)
    service.finish(ADMIN, str(uuid4()), unprotected, state(game).revision)
    public = WorldService(MissionService(ledger)).get(OTHER)
    assert public["world"]["fallout"][0]["active"]
    assert "PRIVATE_NUCLEAR_CAPABILITY" not in str(public)
    assert "fallout_sources" not in str(public)
    item = next(x for x in InboxService(ledger).items(ADMIN) if x.identity == identity)

    async def reopen():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await InboxView(InboxService(ledger), 1).route(own, item)
        assert "Actual nuclear drop" in str(own.edit_original_response.call_args.kwargs)

    asyncio.run(reopen())
    before = state(game).model_dump_json()
    assert game.rebuild() > 0 and state(game).model_dump_json() == before


def complete_mission(service, game, mission, success):
    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_punishments import PunishmentService

    service.end(
        ADMIN, str(uuid4()), mission, service.get(ADMIN, mission)["mission"]["revision"], success
    )
    punishment = PunishmentService(service.store, service.access.registry)
    for work in service.get(ADMIN, mission)["work"]:
        if work["kind"] == "punishment":
            actual = punishment.get(ADMIN, work["id"])
            if actual["state"] == "resolved":
                continue
            punishment.apply(
                ADMIN,
                str(uuid4()),
                work["id"],
                actual["revision"],
                actual["game_revision"],
                Details(kind="stimulant_injection"),
            )
    current = service.get(ADMIN, mission)["mission"]
    if current["phase"] != "complete":
        service.complete(ADMIN, str(uuid4()), mission, current["revision"])


def test_actual_causal_mission_waiver_real_expiry_and_independent_high_noop(
    ledger, tmp_path, monkeypatch
):
    game, service, receipt, _, _, _ = ready(ledger, tmp_path, monkeypatch)
    missions, mission = actual_mission(ledger, game)
    nuclear = device(service, game, receipt, "Actual conditional nuclear device", cell=(3, 3))
    identity = service.drop(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        nuclear,
        (3, 3),
        ("gentle_fallout", "mission_budget"),
        "Actual drop caused the Mission objective to succeed",
        mission=mission,
    )["id"]
    assert state(game).strain.levels["rebellion"] == "low"
    service.judge_mission(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "Actual source-specific blast led to this actual Mission objective's success",
    )
    complete_mission(missions, game, mission, True)
    assert state(game).strain.levels["budget"] == "low"
    service.finish(ADMIN, str(uuid4()), identity, state(game).revision)
    with pytest.raises(ValueError, match="unusable"):
        require_usable(state(game).world, (3, 3))
    # A second genuine conditional drop and a distinct nuclear device both write High.
    # The latter remains an independent operation even though its write changes no value.
    missions, second = actual_mission(ledger, game)
    second_device = device(service, game, receipt, "Actual second conditional weapon", cell=(3, 3))
    second_drop = service.drop(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        second_device,
        (6, 6),
        ("safe_ejection", "mission_budget"),
        "Actual release at 3,3 and real nuclear delivery to 6,6",
        mission=second,
    )["id"]
    third_device = device(service, game, receipt, "Actual independent nuclear weapon", cell=(3, 3))
    third_drop = service.drop(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        third_device,
        (6, 6),
        ("safe_ejection", "cores"),
        "Actual second physical nuclear delivery from 3,3 to 6,6",
    )["id"]
    service.judge_mission(
        ADMIN,
        str(uuid4()),
        second_drop,
        state(game).revision,
        True,
        "Both actual nuclear drops materially accomplished this actual objective",
    )
    complete_mission(missions, game, second, True)
    assert state(game).strain.levels["budget"] == "high"
    writes = [x for x in state(game).facts if x.get("kind") == "a_bomb_budget_operation"]
    assert next(x for x in writes if x["source"] == second_drop)["waived"] == "yes"
    assert next(x for x in writes if x["source"] == third_drop)["waived"] == "no"
    service.finish(ADMIN, str(uuid4()), second_drop, state(game).revision)
    service.finish(ADMIN, str(uuid4()), third_drop, state(game).revision)
    missions, failed = actual_mission(ledger, game)
    failed_device = device(
        service, game, receipt, "Actual failed-Mission nuclear weapon", cell=(3, 3)
    )
    failed_drop = service.drop(
        ADMIN,
        str(uuid4()),
        receipt.id,
        state(game).revision,
        failed_device,
        (6, 6),
        ("safe_ejection", "mission_budget"),
        "Actual nuclear delivery occurred but the Mission ultimately failed",
        mission=failed,
    )["id"]
    service.judge_mission(
        ADMIN,
        str(uuid4()),
        failed_drop,
        state(game).revision,
        True,
        "Actual drop attempted the objective; actual Mission outcome still controls the exception",
    )
    complete_mission(missions, game, failed, False)
    assert state(game).strain.levels["budget"] == "high"
    assert (
        next(
            x
            for x in state(game).facts
            if x.get("kind") == "a_bomb_budget_operation" and x["source"] == failed_drop
        )["waived"]
        == "no"
    )
    service.finish(ADMIN, str(uuid4()), failed_drop, state(game).revision)
    period = OffDutyService(missions).begin(ADMIN, str(uuid4()))
    cleared = next(x for x in state(game).world.fallout if x.id == identity)
    assert cleared.expired_event and period["phase"] == "preparing"
    require_usable(state(game).world, (3, 3))
    with pytest.raises(ValueError, match="unusable"):
        require_usable(state(game).world, (6, 6))
    public = WorldService(missions).get(OTHER)
    assert any(not x["active"] for x in public["world"]["fallout"])
    assert any(x["active"] for x in public["world"]["fallout"])
    assert "PRIVATE_NUCLEAR_CAPABILITY" not in str(public)
