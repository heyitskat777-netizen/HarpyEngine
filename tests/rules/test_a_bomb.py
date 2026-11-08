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


def world_interaction_award(strain, game, *, slot=6):
    """Real additional Void Award; preserves the active period and other actual work."""
    from test_strain import facts

    from girlframe.engine.m3_janus_storage import effective_assets

    canon = state(game)
    assert not canon.strain.requests
    actual_void = sum(
        any(x.void for x in effective_assets(canon, current_ref(canon, uid))) for uid in canon.order
    )
    assert 2 * actual_void >= len(canon.order)
    old_awards = {x.id for x in awards.awards(canon)}
    period = strain.periods.begin(ADMIN, str(uuid4()))
    frames = [
        [x for x in canon.sheets[str(uid)].assets if x.family == "frame"] for uid in canon.order
    ]
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        1,
        state(game).revision,
        facts(
            at_least_half_have_void=True,
            no_girl_void=False,
            frame_full_or_all_frames_some_repairs=(
                any(values and all(x.damaged for x in values) for values in frames)
                or bool(frames)
                and all(any(x.damaged for x in values) for values in frames)
            ),
        ),
    )
    strain.dice = D6(6)
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "void" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(ADMIN, str(uuid4()), request.id, 1, state(game).revision, slot, endgame=True)
    service = HandlerAdvancementService(game.store)
    identity = request.id + ":effect"
    current = service.view(ADMIN, identity)
    service.claim_void(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        current["work_revision"],
        "The actual Void Endgame grants this original Handler another advancement",
    )
    award = next(x for x in awards.awards(state(game)) if x.id not in old_awards)
    assert award.rule == "strain.void.endgame." + str(slot) and award.phase == "held"
    with game.store.engine.connect() as c:
        assert service._proof(c, award.id)[-1] == award
    return award


def test_actual_armoured_ship_intercepts_blast_then_unarmoured_base_is_destroyed(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine import m3_handler_ordinary as ordinary
    from girlframe.engine import m3_ship_base as ships
    from girlframe.services.m3_ship_base import ShipBaseService
    from girlframe.services.m3_ship_base import paid as ship_paid

    game, bomb, acquisition, _, _, strain = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, ships.RULE, ordinary.RULE, *awards.RULES),
    )
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(6))
    award = world_interaction_award(strain, game)
    ship = ShipBaseService(ledger)
    receipt = ship.buy(
        ADMIN,
        str(uuid4()),
        award.id,
        state(game).revision,
        "outside-base",
        "The genuine second Award makes this existing remote Base Armoured",
    )["id"]
    before = state(game)
    original = next(x for x in before.world.locations if x.id == "outside-base")
    assert original.ship.armoured and original.operational
    pending = before.strain.requests
    first_device = device(bomb, game, acquisition, "Actual Armoured-Base nuclear device", (3, 3))
    first_key = str(uuid4())
    arguments = (
        ADMIN,
        first_key,
        acquisition.id,
        state(game).revision,
        first_device,
        (6, 6),
        ("gentle_fallout", "cores"),
        "Actual carried nuclear release at 3,3 reaches the remote Armoured Base at 5,6",
    )
    first = bomb.drop(*arguments)["id"]
    after = state(game)
    intercepted = next(x for x in after.world.locations if x.id == original.id)
    assert intercepted.condition == original.condition == "intact"
    assert intercepted.cell == original.cell
    assert not intercepted.ship.armoured and intercepted.ship.damage_count == 1
    assert not intercepted.operational and intercepted.fallout_sources == (first,)
    assert not any(
        x.get("kind") == "structure_destroyed_source" and x.get("entity") == original.id
        for x in after.facts
    )
    assert not any(x.entity == original.id for x in after.strain.triggers)
    assert after.order == before.order and after.placements == before.placements
    assert after.strain.requests == pending
    assert bomb.drop(*arguments)["id"] == first and state(game) == after
    bomb.finish(ADMIN, str(uuid4()), first, after.revision)
    second_device = device(bomb, game, acquisition, "Actual unarmoured-Base nuclear device", (3, 3))
    second = bomb.drop(
        ADMIN,
        str(uuid4()),
        acquisition.id,
        state(game).revision,
        second_device,
        (6, 6),
        ("gentle_fallout", "cores"),
        "A distinct real nuclear device strikes the now actually unarmoured Base",
    )["id"]
    destroyed = state(game)
    actual = next(x for x in destroyed.world.locations if x.id == original.id)
    assert actual.condition == "destroyed" and actual.ship.damage_count == 1
    stamps = [
        x
        for x in destroyed.facts
        if x.get("kind") == "structure_destroyed_source" and x.get("entity") == original.id
    ]
    assert len(stamps) == 1 and stamps[0]["source"] == second
    assert len([x for x in destroyed.strain.triggers if x.entity == original.id]) == 1
    with ledger.engine.connect() as c:
        assert ship_paid(game, c, destroyed, receipt).award == award.id
        assert (
            prove_drop(game, c, destroyed, first).device
            != prove_drop(game, c, destroyed, second).device
        )
    bomb.finish(ADMIN, str(uuid4()), second, destroyed.revision)
    public = WorldService(MissionService(ledger)).get(OTHER)["world"]
    site = next(x for x in public["locations"] if x["id"] == original.id)
    assert site["condition"] == "destroyed"
    assert site["ship"] == {"armoured": False, "airborne": False}
    assert "fallout_sources" not in site
    assert award.id not in str(public) and "PRIVATE_NUCLEAR_CAPABILITY" not in str(public)


def test_actual_nuclear_perimeter_breach_removes_relief_and_protected_study_before_destruction(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine import m3_contaminant_zone as zones
    from girlframe.engine import m3_handler_ordinary as ordinary
    from girlframe.engine.m3_strain import effective_levels
    from girlframe.services.m3_contaminant_zone import ContaminantZoneService, zone_proof

    game, bomb, acquisition, _, _, strain = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, zones.RULE, ordinary.RULE, *awards.RULES),
    )
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(6))
    award = world_interaction_award(strain, game)
    quarantine = ContaminantZoneService(ledger)
    source = quarantine.buy(
        ADMIN,
        str(uuid4()),
        award.id,
        state(game).revision,
        "The genuine second Award grants my original quarantine authority",
    )["id"]
    world = WorldService(MissionService(ledger))
    manager = Npc(
        id="actual-nuclear-study-manager",
        name="PRIVATE_ORIGINAL_RESEARCH_MANAGER",
        jobs=("scientist",),
        detail="Actual scientist assigned to the real protected field study",
        controller=1,
        cell=(4, 3),
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, manager)
    request = zones.Quarantine(
        cells=((4, 3), (4, 4)),
        effects=("void_relief", "field_study"),
        perimeter="The actual continuous containment fence surrounding these two map squares",
        account="The original Handler physically establishes this real two-square quarantine",
        study=zones.StudySetup(
            location=Location(
                id="actual-nuclear-study",
                name="Actual protected field study",
                kind="important",
                cell=(4, 3),
            ),
            manager=manager.id,
        ),
    )
    quarantine.quarantine(ADMIN, str(uuid4()), source, state(game).revision, request)
    before = state(game)
    original = zones.zones(before)[0]
    site = next(x for x in before.world.locations if x.id == request.study.location.id)
    assert site.protection_sources == (original.id,) and site.condition == "intact"
    assert (
        before.strain.levels["void"] == "high" and effective_levels(before.strain)["void"] == "low"
    )
    assert original.id in before.strain.void_relief_sources
    public_before = world.get(OTHER)["world"]
    assert any(x["protected"] for x in public_before["field_studies"])
    assert manager.name not in str(public_before) and "manager" not in str(public_before)
    nuclear = device(bomb, game, acquisition, "Actual containment-breach nuclear device", (3, 3))
    key = str(uuid4())
    arguments = (
        ADMIN,
        key,
        acquisition.id,
        state(game).revision,
        nuclear,
        (5, 3),
        ("gentle_fallout", "cores"),
        "Actual nuclear release at 3,3 crosses the original containment fence at impact 5,3",
    )
    evidence = {
        original.id: (
            "PRIVATE_ACTUAL_BREACH: the crossing blast physically destroys "
            "the original recorded fence at the 4,3 to 5,3 boundary"
        )
    }
    identity = bomb.drop(*arguments, breaches=evidence)["id"]
    after = state(game)
    breached = zones.zones(after)[0]
    value = next(x for x in rules.drops(after) if x.id == identity)
    assert breached.broken_event == value.initial_event and breached.breach_actor is None
    assert (
        breached.breach_cell in original.cells and breached.breach_account == evidence[original.id]
    )
    destroyed = next(x for x in after.world.locations if x.id == site.id)
    assert destroyed.condition == "destroyed" and not destroyed.protection_sources
    assert not next(x for x in after.world.field_studies if x.zone == original.id).protected
    assert not next(x for x in after.world.npcs if x.id == manager.id).alive
    assert after.world.territory == before.world.territory
    assert (
        after.strain.levels["void"] == "high" and effective_levels(after.strain)["void"] == "high"
    )
    assert original.id not in after.strain.void_relief_sources
    assert (
        after.strain.events == before.strain.events
        and after.strain.requests == before.strain.requests
    )
    assert bomb.drop(*arguments, breaches=evidence)["id"] == identity and state(game) == after
    with ledger.engine.connect() as c:
        assert zone_proof(game, c, after, original.id) == breached
        assert prove_drop(game, c, after, identity).breaches == evidence
    bomb.finish(ADMIN, str(uuid4()), identity, after.revision)
    public = world.get(OTHER)["world"]
    assert not next(x for x in public["field_studies"] if x["location"] == site.id)["protected"]
    assert manager.name not in str(public) and "manager" not in str(public)
    assert "PRIVATE_ACTUAL_BREACH" not in str(public)
    assert source not in str(public) and award.id not in str(public)
    assert any(x.get("kind") == "a_bomb_perimeter_breach" for x in state(game).facts)
