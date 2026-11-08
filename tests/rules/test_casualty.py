"""Whole ordinary Casualty: real body costs, sources, combat, intimacy and endings."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_battle_service import confirm as battle_confirm
from test_battle_service import prepared as battle_prepared
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Board, World
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_casualty import CasualtyService, prove_override, prove_parts
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError

RULES = (rules.BARELY, rules.BETTER, rules.GOD, rules.SEX)


def ready(store, tmp_path, monkeypatch, *, piloting=False, marked=False):
    _, game = service(store, girl="CASUALTY", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=RULES)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        original = state(game)
        original.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        original = place(original, 2, mode="piloting" if piloting else "outside_frame")
        original = place(original, 3, mode="outside_frame")
        original.sheets["2"].permissions = 3
        if marked:
            for sheet in original.sheets.values():
                for identity in sheet.identities:
                    identity.marked = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_Casualty_body_resources", original)
    return game, GameWorker(game), Gateway(), CasualtyService(game)


def tags(game, *, push=None):
    for person in (PLAYER, OTHER, ADMIN):
        answer(game, person, "tag_window", options=("pass",))
    if any(x["kind"] == "casualty_roll_push" for x in game.choices(PLAYER)):
        answer(
            game,
            PLAYER,
            "casualty_roll_push",
            options=(push,) if push else ("skip",),
            text="I actually push this real body part beyond its limits" if push else "",
        )


def choose(game, viewer, kind, *, native=False, **values):
    if not native:
        return answer(game, viewer, kind, **values)
    from girlframe.discord_adapter.m3_casualty import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def use():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=values.get("options", ()), text=values.get("text", ""))
        if kind in ("casualty_present", "casualty_high_part"):
            form.values["parts"] = values.get("options", ())
        if kind == "casualty_focus":
            form.values.update({k: (v,) for k, v in values["fields"].items()})
        if kind == "casualty_low_both":
            form.values.update(values.get("fields", {}))
        if kind == "casualty_unmark":
            form.values["identity"] = values.get("denied", ())
        if kind == "casualty_high_asset":
            form.values["asset"] = values["denied"]
        if kind == "casualty_high_heat":
            form.values["heat"] = (str(values["number"]),)
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(use())


def native_operation(controls, viewer, operation, **values):
    from girlframe.discord_adapter.m3_casualty import open_casualty

    async def use():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_casualty(interaction, controls)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = (operation,)
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        await menu.confirm.callback(opened)
        if operation == "body":
            return
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(use())


def sex(game, worker, gateway, controls, faces, *, native=False):
    before = state(game)
    if native:
        native_operation(
            controls,
            PLAYER,
            "sex",
            target=(current_ref(before, 3).token,),
            account="PRIVATE_CASUALTY_INTIMACY actual voluntarily proposed encounter",
        )
        identity = rules.records(state(game), rules.SexSession)[-1].id
    else:
        identity = controls.invite(
            PLAYER,
            str(uuid4()),
            900,
            current_ref(before, 3),
            before.revision,
            "PRIVATE_CASUALTY_INTIMACY actual voluntary source",
        )["id"]
    controls.confirm(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "My own actual voluntarily confirmed participation",
    )
    game.dice.faces = faces
    before = state(game)
    heat = before.sheets["2"].heat if before.sheets["2"].heat >= 5 else 0
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=current_ref(before, 3),
            heat=heat,
            context="Actual voluntarily performed intimacy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    tags(game)
    return identity, action


def finished(game, worker, gateway, controls, identity, action):
    assert controls.view(PLAYER, identity)["phase"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_barely_real_identity_to_asset_repair_once_private_saved_source(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    handler = HandlerPlayService(ledger)
    original = state(game)
    source = handler.start(ADMIN, str(uuid4()), original.revision, (current_ref(original, 2),))[
        "id"
    ]
    asset = next(x for x in original.sheets["2"].assets if x.family == "girl")
    handler.submit(
        ADMIN,
        str(uuid4()),
        source,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="Actual performed damage to the original Girl Asset",
            target=current_ref(original, 2),
            asset=asset.id,
        ),
    )
    before = state(game)
    assert next(x for x in before.sheets["2"].assets if x.id == asset.id).damaged
    old = before.sheets["2"].identities[0]
    frozen = state(game)
    with pytest.raises(WorkflowError):
        controls.barely(PLAYER, str(uuid4()), before.revision - 1, old.id, asset.id, "Stale")
    assert state(game) == frozen
    args = (
        PLAYER,
        str(uuid4()),
        before.revision,
        old.id,
        asset.id,
        "PRIVATE_BARELY actual identity sacrifice",
    )
    result = controls.barely(*args)
    assert controls.barely(*args) == result
    actual = state(game)
    assert not next(x for x in actual.sheets["2"].assets if x.id == asset.id).damaged
    assert all(x.id != old.id for x in actual.sheets["2"].identities)
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    assert actual.sheets["3"] == before.sheets["3"]
    with pytest.raises(WorkflowError):
        controls.view(OTHER, result["id"])

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.identity == result["id"] and x.task == "m3_casualty"
        )
        interaction = current(2, 98101)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        content = interaction.edit_original_response.call_args.kwargs["content"]
        assert old.name in content and asset.name in content and "PRIVATE_BARELY" in content

    asyncio.run(reopen())
    with ledger.engine.connect() as c:
        assert "PRIVATE_BARELY" not in " ".join(c.scalars(sa.select(t.events.c.payload_json)))


def test_actual_push_broken_brain_real_high_keep_preserves_raw_receipt_and_living_original(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    game.dice.faces = (2, 3)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I actually push through danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        raw = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.action_id == action
            )
        )
    tags(game, push="brain")
    assert game.inspect(PLAYER, action)["result"] is None
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["result"]["total"] == 11
    assert rules.part_state(state(game), current_ref(state(game), 2), "brain") == "broken"
    assert not state(game).career_archives
    answer(game, PLAYER, "actor_keep", text="Actual high evasion from the pushed body")
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual outcome adjudication")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        assert prove_override(game, c, state(game), actual) == 11
        assert (
            c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.action_id == action
                )
            )
            == raw
        )
        forged = dict(actual) | {"data": json.loads(json.dumps(actual["data"]))}
        forged["data"]["casualty_override"]["total"] = 20
        with pytest.raises(WorkflowError):
            prove_override(game, c, state(game), forged)
    tick(worker, gateway, 5)


def test_no_one_better_actual_high_assault_extra_cover_then_real_assault_costs(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, battle, data, declaration = battle_prepared(ledger, girl="CASUALTY")
    approved(ledger, game, tmp_path, monkeypatch, extra=RULES)
    source = battle_confirm(battle, game, data, declaration)
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=source,
            heat=0,
            piloting=True,
            context=declaration.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    tags(game)
    answer(
        game,
        PLAYER,
        "engage_assault_extra",
        options=("cover",),
        fields={"cover": declaration.attacking_asset},
        text="I establish real cover in this battlefield",
    )
    for human in (ADMIN, PLAYER, OTHER):
        answer(
            game,
            human,
            "battle_assault_table",
            flag=False,
            text="Actual shared battlefield judgment",
        )
    answer(game, ADMIN, "battle_handler", options=("damage_actor_asset",))
    own = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(game, PLAYER, "battle_actor_damage", fields={"asset": own.id})
    assert next(x for x in state(game).sheets["2"].assets if x.id == own.id).damaged
    assert any(
        x.get("kind") == "engage_maneuver" and json.loads(x["body"])["kind"] == "cover"
        for x in state(game).facts
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)


def test_actual_owned_dive_void_onset_resisted_with_real_part_cost_and_source_completion(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, marked=True)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep", heat=0, context="Actual dangerous communion", trigger_confirmed=True
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    tags(game)
    answer(
        game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual printed source"
    )
    before = state(game)
    asset = next(x for x in before.sheets["2"].assets if x.family == "girl" and not x.void)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={
            "asset": asset.id,
            "casualty_part": "hands",
            "casualty_site_account": "This body Asset onset infects my Hands; I snap them",
        },
        text="The actual pending Void alteration being resisted",
    )
    actual = state(game)
    assert not next(x for x in actual.sheets["2"].assets if x.id == asset.id).void
    assert rules.part_state(actual, current_ref(actual, 2), "hands") == "broken"
    assert rules.records(actual, rules.Resistance)[-1].consumed
    assert not any(x.marked for x in actual.sheets["2"].identities)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        prove_parts(game, c, actual, current_ref(actual, 2))
    tick(worker, gateway, 5)


def test_true_helpless_push_native_rejection_then_actual_finder_bond_without_automatic_cure(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    source = controls.push_helpless(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        "legs",
        "I actually push my original legs and collapse Helpless",
    )["id"]
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 2))
    frozen = actual.model_dump_json()
    with pytest.raises(WorkflowError, match="[Hh]elpless"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            actual.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Cannot defend while actually helpless",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == frozen and game.dice.calls == 0
    before = depth(actual, current_ref(actual, 2), current_ref(actual, 3))
    controls.record_found(
        OTHER,
        str(uuid4()),
        source,
        actual.revision,
        current_ref(actual, 3),
        900,
        "My actual original Girl finds her collapsed in this room",
    )
    final = state(game)
    assert depth(final, current_ref(final, 2), current_ref(final, 3)) == min(before + 1, 2)
    assert is_helpless(final, current_ref(final, 2))
    assert rules.part_state(final, current_ref(final, 2), "legs") == "broken"


def test_actual_handler_beating_breaks_link_stops_piloting_paid_native_repair_restores_control(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch, piloting=True)
    controls.body(PLAYER, str(uuid4()))
    original = state(game)
    actor = current_ref(original, 2)
    handler = HandlerPlayService(ledger)
    source = handler.start(ADMIN, str(uuid4()), original.revision, (actor,))["id"]
    handler.submit(
        ADMIN,
        str(uuid4()),
        source,
        state(game).revision,
        "punish",
        Effect(
            kind="punish",
            account="Actual source discipline",
            target=actor,
            executor=current_ref(original, 1),
        ),
    )
    case = state(game).role_punishments[-1]
    role = RolePunishmentService(game)

    def apply(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="beating", body_part="link", tag="The Handler broke my Link")
    apply(ADMIN, instruction=Instruction(kind="beating", details_json=details.model_dump_json()))
    apply(ADMIN, scene="The actual Handler damages the original Link as this source Punishment")
    apply(PLAYER, attest=True)
    apply(ADMIN, execute=True, account="I actually break the original Casualty Link")
    stopped = state(game)
    placement = next(x for x in stopped.placements if x.actor == actor)
    before_place = next(x for x in original.placements if x.actor == actor)
    assert placement.mode == "inside_frame" and placement.girl_cell == before_place.girl_cell
    assert (
        placement.frame_instance == before_place.frame_instance
        and placement.vessel_id == before_place.vessel_id
    )
    physical = PhysicalService(ledger)
    with ledger.engine.connect() as c:
        pose = resolve(stopped, actor, profiles(c, ledger.campaign_id)).position_sha256
    command = CockpitAction(
        actor=actor,
        operation="pilot",
        expected_position=pose,
        account="I attempt actual control of my existing Frame",
        confirmed=True,
    )
    with pytest.raises(WorkflowError):
        physical.operate(PLAYER, str(uuid4()), stopped.revision, command)
    permissions = stopped.sheets["2"].permissions
    native_operation(controls, PLAYER, "repair", part=("link",))
    repaired = state(game)
    assert repaired.sheets["2"].permissions == permissions - 1
    assert rules.part_state(repaired, actor, "link") == "intact"
    with ledger.engine.connect() as c:
        pose = resolve(repaired, actor, profiles(c, ledger.campaign_id)).position_sha256
    physical.operate(
        PLAYER,
        str(uuid4()),
        repaired.revision,
        command.model_copy(update=dict(expected_position=pose)),
    )
    assert next(x for x in state(game).placements if x.actor == actor).mode == "piloting"


def test_real_source_authored_brain_destruction_ends_original_not_broken_brain_counter(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    actor = current_ref(original, 2)
    with pytest.raises(WorkflowError):
        controls.damage_part(
            OTHER, str(uuid4()), original.revision, actor, "brain", "destroyed", "No Handler alias"
        )
    assert state(game) == original
    result = controls.damage_part(
        ADMIN,
        str(uuid4()),
        original.revision,
        actor,
        "brain",
        "destroyed",
        "Actual original Handler-authored performed destruction of this Brain",
    )
    final = state(game)
    archive = next(x for x in final.career_archives if x.actor == actor)
    assert archive.ending == "death" and "2" not in final.sheets
    assert json.loads(archive.sheet_json)["permissions"] == original.sheets["2"].permissions
    assert controls.view(PLAYER, result["id"])["record"]["condition"] == "destroyed"
    with pytest.raises(WorkflowError):
        game.sheet(PLAYER)
    assert game.dice.calls == 0


def test_actual_dormant_work_owned_resistance_native_cost_reopen_and_real_completion(
    ledger, tmp_path, monkeypatch
):
    import test_battle_pipeline as pipeline
    from test_battle_pipeline import dormant_source, table

    from girlframe.discord_adapter.m3_battle_dormant import open_dormant
    from girlframe.services.m3_battle_dormant import DormantService

    def reviewed_source(store, **values):
        result = battle_prepared(store, **values)
        approved(store, result[0], tmp_path, monkeypatch, extra=RULES)
        return result

    original_tags = pipeline.pass_tags

    def complete_tags(game):
        original_tags(game)
        answer(game, PLAYER, "casualty_roll_push", options=("skip",))

    monkeypatch.setattr(pipeline, "prepared", reviewed_source)
    monkeypatch.setattr(pipeline, "pass_tags", complete_tags)
    game, worker, gateway, parent, work = dormant_source(
        ledger, monkeypatch, girl="CASUALTY", faces=(4, 5)
    )
    source = DormantService(ledger, game)
    data = source.get(PLAYER, work)
    asset = next(x["id"] for x in data["assets"] if x["family"] == "girl")
    before = state(game)
    actor = current_ref(before, 2)
    account = "The actual Dormant's onset reaches my original Hands; I snap them off"
    description = "This actual pending body alteration is resisted at its infected site"
    with ledger.engine.connect() as c:
        choices_before = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_choices"]))
        responses_before = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_responses"]))

    async def use():
        interaction = current(2, 43020)
        await interaction.response.defer(ephemeral=True)
        await open_dormant(interaction, source, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert any(x.key == "casualty_part" for x in form.fields)
        form.values = dict(
            asset=(asset,),
            description=description,
            piloting=("yes",),
            casualty_part=("part:hands",),
            casualty_site_account=account,
        )
        await form.confirm.callback(current(2, 43021))
        assert form.completed

    asyncio.run(use())
    after = state(game)
    assert not next(x for x in after.sheets["2"].assets if x.id == asset).void
    assert rules.part_state(after, actor, "hands") == "broken"
    receipt = next(x for x in rules.records(after, rules.Resistance) if x.work == work)
    assert receipt.actor == actor and receipt.asset == asset and receipt.consumed
    assert receipt.action is None and receipt.choice is None
    assert source.get(PLAYER, work)["state"] == "resolved"
    assert source.get(PLAYER, work)["phase"] == "complete"
    with ledger.engine.connect() as c:
        prove_parts(game, c, after, actor)
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_choices"])) == choices_before
        )
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_responses"]))
            == responses_before
        )
    committed = after.model_dump_json()
    retried = source.alter(
        PLAYER,
        "43021",
        work,
        data["revision"],
        data["game_revision"],
        asset,
        description,
        piloting=True,
        casualty_part="part:hands",
        casualty_site_account=account,
    )
    assert retried["phase"] == "complete" and state(game).model_dump_json() == committed
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    table(game)
    assert game.inspect(PLAYER, parent)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_sex_mid_real_parts_focus_optional_unmarks_and_hesitation_reciprocal_tags(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, marked=True)
    identity, action = sex(game, worker, gateway, controls, (4, 5), native=True)
    choose(
        game,
        PLAYER,
        "casualty_present",
        native=True,
        options=("legs", "hands", "eyes"),
        text="I actually present these three original ideal parts",
    )
    choose(
        game,
        OTHER,
        "casualty_focus",
        native=True,
        fields={"legs": "focus", "hands": "focus", "eyes": "hesitate"},
        text="My actual reactions to each presented part",
    )
    for human, choices in ((PLAYER, ("identity:0", "identity:1")), (OTHER, ("identity:0", None))):
        for identity_id in choices:
            choose(
                game,
                human,
                "casualty_unmark",
                native=True,
                options=("unmark",) if identity_id else ("skip",),
                denied=(identity_id,) if identity_id else (),
            )
        choose(
            game,
            human,
            "casualty_mutual_tag",
            native=True,
            text="Actual hesitation impression from " + str(human.user_id),
        )
    assert sum(not x.marked for x in state(game).sheets["2"].identities) == 2
    assert sum(not x.marked for x in state(game).sheets["3"].identities) == 1
    assert len(state(game).sheets["2"].tags) == len(state(game).sheets["3"].tags) == 1
    finished(game, worker, gateway, controls, identity, action)
    empty, empty_action = sex(game, worker, gateway, controls, (4, 5))
    choose(game, PLAYER, "casualty_present", options=(), text="I actually present no parts")
    finished(game, worker, gateway, controls, empty, empty_action)


def test_sex_high_actual_each_heat_reciprocal_asset_part_damage_bond_and_closure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity, action = sex(game, worker, gateway, controls, (6, 6))
    before = state(game)
    choose(game, PLAYER, "casualty_high_heat", native=True, number=3)
    choose(game, OTHER, "casualty_high_heat", native=True, number=4)
    asset = next(x.id for x in before.sheets["3"].assets if x.family == "girl" and not x.damaged)
    choose(
        game,
        PLAYER,
        "casualty_high_asset",
        native=True,
        denied=(asset,),
        text="I actually damage her chosen Asset",
    )
    choose(
        game,
        OTHER,
        "casualty_high_part",
        native=True,
        options=("hands",),
        text="I actually break her original Hands",
    )
    after = state(game)
    assert after.sheets["2"].heat == before.sheets["2"].heat + 3
    assert after.sheets["3"].heat == before.sheets["3"].heat + 4
    assert next(x for x in after.sheets["3"].assets if x.id == asset).damaged
    assert rules.part_state(after, current_ref(after, 2), "hands") == "broken"
    assert depth(after, current_ref(after, 2), current_ref(after, 3)) == 2
    finished(game, worker, gateway, controls, identity, action)


def test_sex_low_actual_agreement_optional_tag_and_disagreement_optional_both_tags(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    for agree, give in ((True, True), (True, False), (False, True), (False, False)):
        identity, action = sex(game, worker, gateway, controls, (1, 1))
        before = state(game)
        choose(
            game,
            PLAYER,
            "casualty_unsatisfied",
            native=True,
            text="I actually tell them they are unsatisfied",
        )
        choose(
            game,
            OTHER,
            "casualty_agree",
            native=True,
            options=("agree",) if agree else ("disagree",),
            text="My own actual answer about this encounter",
        )
        if agree:
            choose(
                game,
                OTHER,
                "casualty_low_tag",
                native=True,
                options=("give",) if give else ("decline",),
                text="My actual unsatisfied impression" if give else "",
            )
        else:
            choose(
                game,
                PLAYER,
                "casualty_low_both",
                native=True,
                options=("give",) if give else ("decline",),
                fields={"self": "My own numbness", "other": "Our actual awkwardness"}
                if give
                else {},
            )
        assert len(state(game).sheets["2"].tags) == len(before.sheets["2"].tags) + int(give)
        assert len(state(game).sheets["3"].tags) == len(before.sheets["3"].tags) + int(
            give and not agree
        )
        finished(game, worker, gateway, controls, identity, action)
