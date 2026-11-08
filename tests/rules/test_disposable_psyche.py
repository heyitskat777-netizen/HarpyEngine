"""Actual additional Heat, permanent Tag rebuilding and complete ordinary OffDuty."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, roll_for
from test_physical_operations import place
from test_strain_effect_service import selected
from test_strain_service import D6
from test_strain_service import prepared as prepare_strain
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_disposable_psyche as rules
from girlframe.engine import m3_dose_up as drugs
from girlframe.engine.m2 import GameState, PlayInput, mark_identity
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_disposable_psyche import PsycheService, prove_disposal
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="STIM-BLISSED", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, drugs.RULE, drugs.SELF_RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "world", "playbooks"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_body_world_context", actual)
    return MissionService(store), game, GameWorker(game), Gateway(), PsycheService(store, game)


def mark_native(game, identity, gain, extra, heat):
    from girlframe.discord_adapter.m2_ui import open_play

    async def prepare():
        interaction = current(2, 98801 + extra)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_play(interaction, game, _pilot=True)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert any(x.key == "disposable_heat" for x in form.fields)
        form.values.update(
            play=("keep_your_head",),
            target=(),
            identity=(identity,),
            gain=(str(gain),),
            pair_share=("0",),
            heat=(str(heat),),
            piloting=("no",),
            witnessed=("no",),
            context="I rely on this real Identity and discard it while evading danger",
            trigger=("yes",),
            disposable_heat=(str(extra),),
        )
        response = current(2, 98811 + extra)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with game.store.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == game.store.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    return asyncio.run(prepare())


def real_period(missions, game):
    strain = StrainService(OffDutyService(missions), dice=D6())
    identity = prepare_strain(strain, game)
    effects = EffectService(strain)
    for track, face, column, choice in (
        ("void", 1, 1, selected()),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="An actual local group appears",
                target="city0",
                faction=Faction(
                    id="group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2", account="Actual rooms reassigned", rooms=((2, 3),)
            ),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    cycle = CycleService(strain.periods)
    activate(cycle, game, identity)
    return cycle, identity


def test_actual_disposals_mandatory_native_rebuild_period_closure_private_history_retry(
    ledger, tmp_path, monkeypatch
):
    missions, game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    removed_ids = [x.id for x in original.sheets["2"].identities[:2]]
    actions = []
    for identity, gain, extra, heat in ((removed_ids[0], 1, 3, 4), (removed_ids[1], 2, 4, 6)):
        before = state(game)
        game.dice.faces = (1, 1)
        action = mark_native(game, identity, gain, extra, heat)
        actions.append(action)
        assert state(game).sheets["2"] == before.sheets["2"]
        assert game.dice.calls == len(actions) - 1
        tick(worker, gateway, 3)
        pass_tags(game)
        total = game.inspect(PLAYER, action)["result"]
        # Total is private until both actual result owners finish.
        assert total is None
        if heat == 4:
            answer(game, PLAYER, "actor_keep", options=("tough",))
        else:
            answer(
                game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",)
            )
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual evasion result")
        actual = state(game)
        assert not any(x.id == identity for x in actual.sheets["2"].identities)
        assert actual.sheets["2"].heat == 0 and actual.sheets["3"] == before.sheets["3"]
        value = rules.disposals(actual)[-1]
        assert value.identity == next(x for x in before.sheets["2"].identities if x.id == identity)
        assert (value.gain, value.extra, value.spent) == (gain, extra, heat)
        receipt = game.inspect(PLAYER, action)["receipt"]
        assert receipt["disposable_psyche"] == action and receipt["pre_total"] == 2 + heat
        assert receipt["ruleset"] == "girlframe-m3-core-1"
        assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        with ledger.engine.connect() as c:
            assert prove_disposal(game, c, actual, action) == value
            forged = GameState.model_validate_json(actual.model_dump_json())
            fact = next(
                x
                for x in forged.facts
                if x.get("kind") == "disposable_disposal" and x["id"] == action
            )
            fact["body"] = value.model_copy(update={"gain": 3}).model_dump_json()
            with pytest.raises(WorkflowError):
                prove_disposal(game, c, forged, action)
        with pytest.raises(WorkflowError):
            controls.view(OTHER, action)
        tick(worker, gateway, 5)
    assert len(state(game).sheets["2"].identities) == 2 and game.dice.calls == 2
    game.dice.faces = (6, 6)
    dose = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dose_up",
            heat=0,
            context="I actually dose myself with the cocktail",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "dose_up_components", options=("quick", "strong"))
    answer(game, ADMIN, "dose_up_components", options=("calm",))
    assert game.inspect(PLAYER, dose)["state"] == "complete"
    tick(worker, gateway, 5)
    cycle, period = real_period(missions, game)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    tasks = controls.menu(PLAYER)["tasks"]
    work = next(x for x in tasks if x["pending"])
    actual = state(game)
    data = controls.view(PLAYER, work["id"])
    assert data["count"] == 2 and len(data["tags"]) == 3
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    with pytest.raises(WorkflowError, match="effects"):
        call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    tags = data["tags"]
    replaced = actual.sheets["2"].identities[0]
    selections = tuple(
        rules.TagSelection(tag=x["id"], replace=replaced.id if i == 0 else None)
        for i, x in enumerate(tags)
    )
    with pytest.raises(WorkflowError):
        controls.convert(OTHER, str(uuid4()), work["id"], state(game).revision, selections)
    with pytest.raises(WorkflowError):
        controls.convert(PLAYER, str(uuid4()), work["id"], state(game).revision - 1, selections)
    before_conversion = state(game)
    key = str(uuid4())

    async def convert_native():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.identity == work["id"])
        assert item.state == "pending" and item.incoming
        interaction = current(2, 98901)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(tags=tuple(x["id"] for x in tags), replace=(replaced.id,))
        response = current(2, 98902)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(convert_native())
    converted = rules.conversions(state(game))[-1]
    assert len(converted.created) == 3 and converted.replaced == (replaced,)
    assert [x.name for x in converted.created] == [x["label"] for x in tags]
    assert len(state(game).sheets["2"].identities) == 4 and not state(game).sheets["2"].tags
    assert state(game).sheets["2"].heat == before_conversion.sheets["2"].heat
    assert state(game).sheets["2"].assets == before_conversion.sheets["2"].assets
    assert state(game).sheets["3"] == before_conversion.sheets["3"]
    # Exact native replay uses the original request key and frozen payload.
    outcome = controls.convert(PLAYER, "98902", work["id"], before_conversion.revision, selections)
    assert outcome["identities"] == [x.id for x in converted.created]
    with pytest.raises(WorkflowError):
        controls.convert(PLAYER, key, work["id"], state(game).revision, selections)
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assert controls.view(PLAYER, work["id"])["phase"] == "converted"
    assert not any(x["pending"] for x in controls.menu(PLAYER)["tasks"])
    assert not any(x.identity in (*actions, work["id"]) for x in InboxService(ledger).items(OTHER))
    assert controls.view(PLAYER, actions[0])["extra"] == 3
    assert controls.view(PLAYER, actions[1])["extra"] == 4


def test_existing_protected_identity_guards_reject_before_mutation(ledger, tmp_path, monkeypatch):
    _, game, _, _, _ = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    for guard in ("protected", "sedation", "obsession"):
        scratch = GameState.model_validate_json(original.model_dump_json())
        sheet = scratch.sheets["2"]
        selected_identity = sheet.identities[0]
        if guard == "protected":
            selected_identity.protected = True
        elif guard == "sedation":
            sheet.sedation_locked = (selected_identity.id,)
        else:
            selected_identity.obsession_sources = ("actual-source-lock",)
        saved = sheet.model_dump_json()
        with pytest.raises(ValueError):
            mark_identity(sheet, selected_identity.id, 1, state=scratch, disposable_heat=3)
        assert sheet.model_dump_json() == saved
    assert state(game) == original and game.dice.calls == 0
