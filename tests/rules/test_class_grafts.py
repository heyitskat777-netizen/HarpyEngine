"""Five named implemented Class grafts use actual paid sources and existing consumers."""

import asyncio
import copy
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_privileges import change
from test_repair_service import ready as repairs_ready
from test_strain import facts

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_untouchable import open_purchase
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_dampener as dampener
from girlframe.engine import m3_kicked_puppy as kicked
from girlframe.engine import m3_martyr as martyr
from girlframe.engine import m3_modular as modular
from girlframe.engine import m3_privileges as privileges
from girlframe.engine import m3_untouchable as untouchable
from girlframe.engine.m2 import AssetState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_assets import frame_capacity
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_access import Access
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_dampener import DampenerService
from girlframe.services.m3_kicked_puppy import KickedPuppyService
from girlframe.services.m3_martyr import MartyrService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_modular import ModularService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_privileges import PrivilegeService, purchase_proof
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_untouchable import UntouchableService
from girlframe.services.onboarding import WorkflowError


def funds(game, amount=6):
    with game.store.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = amount
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", actual)


def acquire(game, source, *, extra=()):
    data = source.menu(PLAYER)
    assert data["kind"] == "frame_grafting" and data["price"] == 3
    actor = ActorRef.model_validate(data["actor"])
    args = (
        PLAYER,
        str(uuid4()),
        data["revision"],
        actor,
        data["frame"],
        "Actual Class graft acquisition",
        *extra,
        data["donors"][0],
    )
    before = state(game).sheets["2"].permissions
    result = source.buy(*args)
    assert source.buy(*args) == result
    assert state(game).sheets["2"].permissions == before - 3
    paid = next(x for x in state(game).requisitions if x.id == result["id"])
    with game.store.engine.connect() as c:
        purchase_proof(c, game.store, paid)
    if paid.rule_id != modular.RULE:
        check_suspended_source(state(game), paid)
    return paid


def check_suspended_source(actual, paid):
    """The genuine paid source is withdrawn/restored without changing hardware or costs."""
    characters = {int(uid): sheet.character_id for uid, sheet in actual.sheets.items()}
    removed = privileges.revoke(
        actual, 2, 1, paid.id, "Actual condition", str(uuid4()), str(uuid4()), characters
    )
    assert grafts.held(removed, paid.actor, paid.rule_id) is None
    assert removed.sheets == actual.sheets and removed.requisitions == actual.requisitions
    gate = removed.obligations[-1]
    gate.details["restoration_allowed"] = "true"
    restored = privileges.restore(removed, gate.id, paid.actor.incarnation, None)
    assert grafts.held(restored, paid.actor, paid.rule_id) == paid
    assert restored.sheets == actual.sheets and restored.requisitions == actual.requisitions


def test_grafted_untouchable_native_purchase_and_actual_engage_tag_substitution(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame="CONSUME")
    approved(ledger, game, tmp_path, monkeypatch, extra=(untouchable.RULE,))
    funds(game, 3)
    data = UntouchableService(game).menu(PLAYER)
    before = state(game)
    with pytest.raises(ValueError, match="eligible Class donor"):
        UntouchableService(game).buy(
            PLAYER,
            str(uuid4()),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            "Missing donor cannot charge",
        )
    assert state(game) == before
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].tags.append(TagState(id="own-tag", label="My actual Tag", giver=2))
        game.event(c, 1, str(uuid4()), "synthetic.actual_unmarked_tag", actual)

    async def purchase():
        own = current(2, 993101)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, UntouchableService(game))
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Frame Grafting" in form.text() and "3 Permissions" in form.text()
        form.values.update(account="Actual Untouchable graft", donor=("THE ENFORCER",))
        await form.confirm.callback(current(2, 993102))
        assert form.completed

    asyncio.run(purchase())
    actual = state(game)
    actor = current_ref(actual, 2)
    paid = untouchable.held(actual, actor)
    assert paid and paid.kind == "frame_grafting" and paid.price == 3
    check_suspended_source(actual, paid)
    original = copy.deepcopy(actual.sheets["2"].assets)
    game.dice.faces = (1, 2)
    identity = start(game, play="engage", target_actor=current_ref(actual, 3))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover",),
        fields={"cover": original[0].id, "untouchable_tag": "own-tag"},
        text="My actual Asset provides cover",
    )
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw and game.dice.calls == 1
    actual = state(game)
    assert actual.sheets["2"].assets == original and actual.sheets["2"].permissions == 0
    assert next(x for x in actual.sheets["2"].tags if x.id == "own-tag").marked
    assert final["result"]["damaged"] == []
    fact = next(x for x in actual.facts if x.get("kind") == "untouchable_frame_used")
    assert fact["receipt"] == paid.id


def test_grafted_dampener_uses_smaller_basis_and_actual_full_heat_cost(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame="CONSUME")
    approved(ledger, game, tmp_path, monkeypatch, extra=(dampener.RULE,))
    funds(game)
    paid = acquire(game, DampenerService(game))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].heat = 5
        game.event(c, 1, str(uuid4()), "synthetic.actual_heat", actual)
    game.dice.faces = (1, 2)
    identity = start(game, heat=5, dampener_modifier=3)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert raw["heat"] == 5 and raw["base_modifier"] == 3 and raw["pre_total"] == 6
    assert raw["dampener_purchase"] == paid.id and state(game).sheets["2"].heat == 0
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual response is enough")
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw and game.dice.calls == 1


def test_grafted_kicked_puppy_actual_damaged_basis_target_gift_and_care_question(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame="CONSUME")
    approved(ledger, game, tmp_path, monkeypatch, extra=(kicked.RULE,))
    funds(game)
    paid = acquire(game, KickedPuppyService(game))
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        sheet.heat = 5
        for asset in sheet.assets:
            if asset.family == "girl":
                asset.damaged = True
        damaged = sum(x.family == "girl" and x.damaged for x in sheet.assets)
        giver = current_ref(actual, 3)
        sheet.tags.append(
            TagState(
                id="target-gift",
                label="Their original gift",
                giver=3,
                giver_actor=giver,
                giver_character=giver.incarnation,
                observers=(2, 3),
            )
        )
        game.event(c, 3, str(uuid4()), "synthetic.actual_damage_and_gift", actual)
    game.dice.faces = (3, 3)
    identity = start(game, play="flirt", target=3, kicked_puppy_basis=True)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert raw["heat"] == 0 and raw["base_modifier"] == damaged
    assert raw["kicked_purchase"] == paid.id and state(game).sheets["2"].heat == 5
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=("target-gift",),
        number=1,
        text="Their actual gift describes why I seek their care",
    )
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_flirt", options=(kicked.QUESTION,))
    answer(game, OTHER, "target_flirt", text="I want to care for you through shared rest")
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw and game.dice.calls == 1
    assert final["result"]["question"] == kicked.QUESTION and final["result"]["target_answer"]
    assert final["modifiers"][-1]["amount"] == 1
    assert next(x for x in state(game).sheets["2"].tags if x.id == "target-gift").marked
    assert any(
        x.kind == "flirt_followthrough" and x.state == "pending" for x in state(game).obligations
    )


def test_grafted_martyr_actual_original_death_memorial_and_budget_exclusion(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame="CONSUME")
    approved(ledger, game, tmp_path, monkeypatch, extra=(martyr.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "playbooks"}}
            )
        }
    )
    strain = StrainService(OffDutyService(MissionService(ledger)))
    strain.configure(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "falling_apart",
        frozenset({"void", "rebellion", "budget"}),
    )
    funds(game)
    source = MartyrService(game)
    paid = acquire(game, source)
    before = state(game)
    event = str(uuid4())
    with ledger.transaction() as c:
        ended = end_in_transaction(
            c,
            game,
            before,
            paid.actor,
            reason="death",
            source_event=event,
            account="Actual unprevented original death",
            archive_id=str(uuid4()),
        )
        game.event(c, 2, str(uuid4()), "m3.synthetic_ending", ended, event_id=event)
        synchronize_end(c, game, ended.career_archives[-1])
    actual = state(game)
    episode = martyr.episodes(actual)[0]
    assert actual.strain.levels == {"void": "high", "rebellion": "low", "budget": "low"}
    assert martyr.budget_death_excluded(actual, event) and paid.actor.entity not in actual.sheets
    data = source.get(PLAYER, episode.id)
    result = source.choose(
        PLAYER,
        "actual-graft-memorial",
        episode.id,
        data["revision"],
        "obscurity",
        "The original pilot is consigned to quiet obscurity",
    )
    assert (
        source.choose(
            PLAYER,
            "actual-graft-memorial",
            episode.id,
            data["revision"],
            "obscurity",
            "The original pilot is consigned to quiet obscurity",
        )
        == result
    )
    assert source.get(PLAYER, episode.id)["episode"]["memorial"] == "obscurity"
    period = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    actual = state(game)
    count = sum(any(x.void for x in s.assets) for s in actual.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period,
        1,
        actual.revision,
        facts(
            at_least_half_have_void=2 * count >= len(actual.order),
            no_girl_void=count == 0,
            girl_death_or_severe=False,
        ),
    )
    assert state(game).strain.levels["budget"] == "low"
    assert next(x for x in state(game).strain.requests if x.track == "budget").severity == "low"


def test_grafted_modular_actual_hardware_suspension_restore_and_source_priced_repair(
    ledger, tmp_path, monkeypatch
):
    source, cycle, game, period = repairs_ready(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(modular.RULE,))
    cycle.missions.access = Access(ledger)
    funds(game, 9)
    # Fill the fifth ordinary slot before acquiring the genuinely additional sixth one.
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        actual.order = (3, 2)
        while sum(x.family == "frame" for x in sheet.assets) < 5:
            sheet.assets.append(
                AssetState(
                    id="spare:" + str(len(sheet.assets)), family="frame", name="Actual spare"
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_hardware", actual)
    paid = acquire(
        game,
        ModularService(game),
        extra=("Grafted modular hardware", "Actual sixth counted Frame Asset"),
    )
    acquired = state(game)
    hardware = copy.deepcopy(acquired.sheets["2"].assets)
    assert frame_capacity(acquired.sheets["2"], acquired) == 6
    assert sum(x.family == "frame" for x in hardware) == 6
    # Genuine social Punishment and owned restoration preserve all six physical Assets.
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={
                    "beneath_private_choices": "affected_owner",
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            )
        }
    )
    game.dice.faces = (6, 6)
    identity = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual discipline",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual discipline"},
        text="Actual discipline",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    data = discipline.get(OTHER, work)
    discipline.apply(
        OTHER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Actual restoration condition",
        ),
    )
    assert game.inspect(OTHER, identity)["state"] == "complete"
    tick(worker, gateway, 5)
    removed = state(game)
    assert (
        frame_capacity(removed.sheets["2"], removed) == 5 and removed.sheets["2"].assets == hardware
    )
    menu = ModularService(game).menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        ModularService(game).buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            paid.actor,
            paid.frame_instance,
            "Cannot duplicate suspended hardware",
            "Duplicate",
            "Duplicate",
            "DOCTORDOCTOR MK. II",
        )
    assert state(game) == removed
    gate = next(x for x in removed.obligations if x.kind == "revoked_requisition")
    restore = PrivilegeService(ledger)
    change(restore, OTHER, gate.id, allow=True)
    change(restore, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert (
        frame_capacity(restored.sheets["2"], restored) == 6
        and restored.sheets["2"].assets == hardware
    )
    quoted = source.offer(ADMIN, str(uuid4()), restored.revision, period, 2, "frame:1", 2)
    data = source.get(PLAYER, quoted["id"])
    calls = game.dice.calls
    replacement = modular.Replacement(
        asset="frame:1",
        name="Grafted repair replacement",
        description="New hardware instead of actual repair",
    )
    args = (
        PLAYER,
        "actual-grafted-repair",
        quoted["id"],
        data["game_revision"],
        data["revision"],
        True,
    )
    result = source.respond(*args, replacement=replacement)
    assert source.respond(*args, replacement=replacement) == result
    final = state(game)
    assert (
        final.sheets["2"].permissions == restored.sheets["2"].permissions - 2
        and game.dice.calls == calls
    )
    assert "frame:1" not in {x.id for x in final.sheets["2"].assets}
    new = next(x for x in final.sheets["2"].assets if x.name == replacement.name)
    assert not new.void and not new.damaged and len(final.sheets["2"].assets) == len(hardware)
    fact = next(x for x in final.facts if x.get("kind") == "modular_repair")
    assert fact["purchase"] == paid.id and fact["source"] == "repair_quote:" + quoted["id"]
