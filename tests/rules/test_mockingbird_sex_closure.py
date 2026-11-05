"""Actual source-owned Mockingbird Sex branches and their shared continuations."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def source(
    store,
    monkeypatch,
    faces=(4, 5),
    *,
    seed_void=False,
    join_handler=False,
    target_npc=False,
    extra_handler=False,
    last_girl=False,
    target_harpy=False,
    extra_npc=False,
):
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    assert plays.sex_ready()
    game, worker, gateway = ready(store, faces)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    casts = CastService(ActorService(MissionService(store)))
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    if seed_void:
        with store.transaction() as c:
            value = state(game)
            asset = next(x for x in value.sheets["3"].assets if x.family == "girl")
            asset.void = True
            asset.damaged = True
            asset.description = "Existing actual Void alteration, still damaged"
            game.event(c, 3, str(uuid4()), "synthetic.existing_source_corruption", value)
    if last_girl:
        with store.transaction() as c:
            value = state(game)
            girls = [x for x in value.sheets["3"].assets if x.family == "girl"]
            assert len(girls) >= 2
            for asset in girls[:-1]:
                asset.void = True
            girls[-1].void = False
            from girlframe.engine.m3_girl_runtime_state import GirlRuntime, PlaySwap

            event = str(uuid4())
            runtime = value.sheets["3"].girl_runtime or GirlRuntime()
            value.sheets["3"].girl_runtime = runtime.model_copy(
                update={
                    "swaps": (
                        *runtime.swaps,
                        PlaySwap(
                            removed_rule="girl.mockingbird.risk-factor",
                            acquired_rule="girl.alpha.itching-for-a-fight",
                            source_playbook="ALPHA",
                            source_event=event,
                        ),
                    )
                }
            )
            game.event(
                c,
                3,
                str(uuid4()),
                "synthetic.actual_prior_swap_and_partial_corruption",
                value,
                event_id=event,
            )
    if join_handler or extra_handler:
        change(casts, ADMIN, "join", active_handler(state(game)))
    npc_target = None
    if target_npc or extra_npc:
        from test_world import initial

        with store.transaction() as c:
            value = state(game)
            value.world = initial()
            game.event(c, 1, str(uuid4()), "synthetic.existing_actual_world", value)
        from girlframe.engine.m3_world_state import Npc
        from girlframe.services.m3_npc_roles import NpcRoleService
        from girlframe.services.m3_world import WorldService

        roles = NpcRoleService(WorldService(MissionService(store)))
        offered = roles.offer(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id="actual-sex-counterpart",
                name="Actual counterpart",
                jobs=("civilian",),
                detail="The actual preexisting adult source person",
                controller=3,
                cell=(0, 0),
                revealed=True,
            ),
        )
        roles.respond(OTHER, str(uuid4()), offered["id"], state(game).revision, "accept")
        npc_target = ActorRef(kind="npc", entity="actual-sex-counterpart")
        change(casts, OTHER, "join", npc_target)
        if target_npc:
            target = npc_target
    if target_harpy:
        from test_world import initial

        from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
        from girlframe.engine.m3_void_state import HarpyIdentity
        from girlframe.engine.m3_world import update
        from girlframe.engine.m3_world_state import AdversaryPilot, Asset
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        store.policy = store.policy.model_copy(
            update={
                "m3_approval": store.policy.m3_approval.model_copy(
                    update={"subsystems": store.policy.m3_approval.subsystems | {"playbooks"}}
                )
            }
        )
        target = ActorRef(kind="external_pilot", entity="actual-void-partner")
        with store.transaction() as c:
            value = state(game)
            value.world = update(
                initial(),
                pilots=(
                    AdversaryPilot(
                        id=target.entity,
                        name="Actual source Harpy",
                        kind="harpy",
                        girl="harpy",
                        frame="harpy",
                        controller=3,
                        cell=(0, 0),
                        revealed=True,
                        assets=(
                            Asset(
                                id="actual-void-body",
                                name="Actual Void body",
                                description="The real established Void alteration",
                                family="girl",
                                void=True,
                            ),
                        ),
                    ),
                ),
            )
            game.event(c, 1, str(uuid4()), "synthetic.actual_existing_harpy", value)
        setup = HarpyDefeatService(store, game)
        proposed = setup.propose_runtime(
            OTHER,
            str(uuid4()),
            state(game).revision,
            NativeHarpyFacts(
                actor=target,
                linked=True,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                heat=0,
                frame_shutdown=False,
                body_incapacitated=False,
                custody="free",
                identities=(HarpyIdentity(id="actual-partner-free", name="Free"),),
                tags=(),
                account="Actual source owner supplies only existing facts",
                facts_confirmed=True,
            ),
        )
        setup.review_setup(
            ADMIN,
            str(uuid4()),
            proposed["id"],
            state(game).revision,
            True,
            "Actual source review confirms the existing original Harpy",
        )
        change(casts, OTHER, "join", target)
    service = plays.MockingbirdService(game)
    participants = (
        (target, active_handler(state(game)))
        if extra_handler
        else (target, npc_target)
        if extra_npc
        else (target,)
    )
    trigger = service.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        SEX,
        participants,
        "Actual player-authored source interaction",
        primary=target if extra_handler or extra_npc else None,
    )
    service.attest(OTHER, str(uuid4()), trigger["id"], target, True)
    if extra_npc:
        service.attest(OTHER, str(uuid4()), trigger["id"], npc_target, True)
    if extra_handler:
        service.attest(ADMIN, str(uuid4()), trigger["id"], participants[1], True)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual source interaction",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, action, actor, target


def test_true_high_caster_selects_asset_patient_rewrites_once_and_original_damage_survives(
    ledger, monkeypatch
):
    game, _, _, action, actor, target = source(ledger, monkeypatch, (6, 6))
    before = state(game)
    asset = next(x for x in before.sheets["3"].assets if not x.void)
    answer(game, PLAYER, "mockingbird_sex_infect", fields={"asset": asset.id})
    row = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_sex_rewrite")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Cannot author the other actual body"),
        )
    response = ChoiceAnswer(text="Actual patient-owned Void rewrite")
    result = game.respond(
        OTHER, "actual-patient-rewrite-once", row["id"], row["revision"], response
    )
    assert (
        game.respond(OTHER, "actual-patient-rewrite-once", row["id"], row["revision"], response)
        == result
    )
    after = state(game)
    actual = next(x for x in after.sheets["3"].assets if x.id == asset.id)
    assert actual.void and actual.damaged == asset.damaged and actual.name == asset.name
    assert before.sheets["2"].assets == after.sheets["2"].assets
    assert depth(after, actor, target) == min(2, depth(before, actor, target) + 1)
    assert (
        len(after.mockingbird.exposures) == 1 and not after.mockingbird.exposures[0].disclosed_event
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_mid_takes_real_void_writes_one_self_asset_and_never_repairs_source(ledger, monkeypatch):
    game, _, _, action, actor, target = source(ledger, monkeypatch, seed_void=True)
    original = state(game)
    asset = next(x for x in original.sheets["3"].assets if x.void)
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset.id, "destination": actor.token, "destination_asset": ""},
    )
    answer(game, OTHER, "mockingbird_sex_restore", text="The real source Asset without its Void")
    answer(
        game,
        PLAYER,
        "mockingbird_sex_self",
        fields={"name": "Actual inherited whisper", "replace": ""},
        text="My actual new self-written Void Asset",
    )
    final = state(game)
    source_asset = next(x for x in final.sheets["3"].assets if x.id == asset.id)
    acquired = next(x for x in final.sheets["2"].assets if x.id == "mock-sex-self:" + action)
    assert not source_asset.void and source_asset.damaged and source_asset.name == asset.name
    assert acquired.void and acquired.family == "girl"
    assert len(final.sheets["2"].assets) == len(original.sheets["2"].assets) + 1
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_mid_redirect_to_different_actual_asset_is_atomic_and_source_damage_remains(
    ledger, monkeypatch
):
    game, _, _, action, actor, target = source(ledger, monkeypatch, seed_void=True)
    before = state(game)
    source_asset = next(x for x in before.sheets["3"].assets if x.void)
    destination = next(x for x in before.sheets["3"].assets if not x.void)
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={
            "source_asset": source_asset.id,
            "destination": target.token,
            "destination_asset": destination.id,
        },
    )
    answer(game, OTHER, "mockingbird_sex_restore", text="Actual ordinary source Asset")
    assert next(x for x in state(game).sheets["3"].assets if x.id == source_asset.id).void
    answer(game, OTHER, "mockingbird_sex_rewrite", text="Actual destination corruption")
    final = state(game)
    assert not next(x for x in final.sheets["3"].assets if x.id == source_asset.id).void
    assert next(x for x in final.sheets["3"].assets if x.id == source_asset.id).damaged
    assert next(x for x in final.sheets["3"].assets if x.id == destination.id).void
    assert depth(final, actor, target) == min(2, depth(before, actor, target) + 1)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_mid_redirect_to_actual_group_npc_uses_owned_manifestation_without_new_assets(
    ledger, monkeypatch
):
    game, _, _, action, actor, partner = source(ledger, monkeypatch, seed_void=True, extra_npc=True)
    before = state(game)
    asset = next(x for x in before.sheets["3"].assets if x.void)
    npc = ActorRef(kind="npc", entity="actual-sex-counterpart")
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset.id, "destination": npc.token, "destination_asset": ""},
    )
    answer(game, OTHER, "mockingbird_sex_restore", text="Actual original feature restored")
    answer(game, ADMIN, "mockingbird_sex_redirect_npc", fields={"manifestation": "bones"})
    final = state(game)
    original = next(x for x in final.sheets["3"].assets if x.id == asset.id)
    assert not original.void and original.damaged
    changed_npc = next(x for x in final.world.npcs if x.id == npc.entity)
    assert changed_npc.tags[-1].label == "Void of the bones" and not hasattr(changed_npc, "assets")
    assert depth(final, actor, partner) == min(2, depth(before, actor, partner) + 1)
    assert final.sheets["2"].assets == before.sheets["2"].assets
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_mid_teaching_preserves_actual_void_and_only_records_undisclosed_risk(ledger, monkeypatch):
    game, _, _, action, _, _ = source(ledger, monkeypatch, seed_void=True)
    asset = next(x for x in state(game).sheets["3"].assets if x.void)
    answer(game, PLAYER, "mockingbird_sex_select", options=("hide",))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_sex_hide")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("asset:" + asset.id,), text="Cannot supply their act"),
        )
    answer(
        game,
        OTHER,
        "mockingbird_sex_hide",
        options=("asset:" + asset.id,),
        text="My actual altered part is concealed by this clothing",
    )
    final = state(game)
    actual = next(x for x in final.sheets["3"].assets if x.id == asset.id)
    assert actual.void and actual.concealed and actual.damaged
    assert final.mockingbird.exposures[-1].kind == "teaching"
    assert final.mockingbird.exposures[-1].disclosed_event is None
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_has_no_fabricated_autonomy_or_discovery_then_actual_witness_and_handler_tag(
    ledger, monkeypatch
):
    from girlframe.services.m3_mockingbird_discovery import DiscoveryService

    game, _, _, action, actor, target = source(ledger, monkeypatch, (1, 2), join_handler=True)
    assert is_helpless(state(game), actor) and game.inspect(PLAYER, action)["state"] == "complete"
    before = state(game)
    assert not before.sheets["3"].tags and not before.mockingbird.discoveries
    service = DiscoveryService(game)
    exposure = before.mockingbird.exposures[-1]
    handler = active_handler(before)
    case = service.report(
        PLAYER,
        str(uuid4()),
        exposure.id,
        900,
        handler,
        "Actual later disclosure to the original Handler",
    )
    with pytest.raises(WorkflowError):
        service.respond(PLAYER, str(uuid4()), case["id"], 1, True, "Cannot answer for this witness")
    service.respond(
        ADMIN, str(uuid4()), case["id"], 1, True, "The original Handler actually found this out"
    )
    assert not state(game).sheets["3"].tags
    service.respond(
        ADMIN,
        str(uuid4()),
        case["id"],
        2,
        True,
        "I apply the actual conditional Tag",
        tag="Actual revealed conduct",
    )
    final = state(game)
    tag = final.sheets["3"].tags[-1]
    assert tag.label == "Actual revealed conduct" and tag.giver_actor == handler
    assert final.mockingbird.exposures[-1].disclosed_event and game.dice.calls == 1
    assert before.sheets["2"].assets == final.sheets["2"].assets


def test_high_npc_uses_actual_handler_owned_manifestation_and_no_invented_npc_assets(
    ledger, monkeypatch
):
    game, _, _, action, actor, target = source(ledger, monkeypatch, (6, 6), target_npc=True)
    before = state(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "mockingbird_sex_npc_void")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(fields={"manifestation": "brain"}),
        )
    answer(game, ADMIN, "mockingbird_sex_npc_void", fields={"manifestation": "brain"})
    final = state(game)
    npc = next(x for x in final.world.npcs if x.id == target.entity)
    assert npc.tags[-1].label == "Void of the brain" and not hasattr(npc, "assets")
    assert final.sheets == before.sheets and game.dice.calls == 1
    assert depth(final, actor, target) == min(2, depth(before, actor, target) + 1)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_stale_unapplied_transfer_can_be_revised_without_erasing_effect_or_reroll(
    ledger, monkeypatch
):
    from girlframe.services.m3_mockingbird_revision import SexRevisionService

    game, _, _, action, actor, _ = source(ledger, monkeypatch, seed_void=True)
    asset = next(x for x in state(game).sheets["3"].assets if x.void)
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset.id, "destination": actor.token, "destination_asset": ""},
    )
    before = state(game).model_dump_json()
    receipt = game.inspect(PLAYER, action)["receipt"]
    old = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_sex_restore")
    service = SexRevisionService(game)
    view = service.get(PLAYER, action)
    with pytest.raises(WorkflowError):
        service.revise(OTHER, str(uuid4()), action, view["revision"])
    service.revise(PLAYER, str(uuid4()), action, view["revision"])
    assert (
        state(game).model_dump_json() == before
        and game.inspect(PLAYER, action)["receipt"] == receipt
    )
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            old["id"],
            old["revision"],
            ChoiceAnswer(text="Old superseded description"),
        )
    answer(
        game, PLAYER, "mockingbird_sex_select", options=("starry",), fields={"capability": "words"}
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_native_high_owned_asset_choice_and_patient_rewrite_preserve_one_receipt(
    ledger, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice

    game, _, _, action, _, _ = source(ledger, monkeypatch, (6, 6))
    original = game.inspect(PLAYER, action)["receipt"]

    async def run():
        owner = current(2, 960101)
        await owner.response.defer(ephemeral=True)
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_sex_infect")
        await open_choice(owner, game, choice["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values["asset"] = (form.fields[0].options[0][0],)
        await form.confirm.callback(current(2, 960102))
        assert form.completed
        patient = current(3, 960103)
        await patient.response.defer(ephemeral=True)
        choice = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_sex_rewrite")
        await open_choice(patient, game, choice["id"])
        form = patient.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, 960104))
        form.values["description"] = "Actual patient-authored corruption"
        await form.confirm.callback(current(3, 960105))
        assert form.completed

    asyncio.run(run())
    assert game.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_real_mid_redirect_to_handler_removes_source_void_then_waits_for_actual_treatment(
    ledger, monkeypatch
):
    from girlframe.services.m3_handler_void import HandlerVoidService

    game, _, _, action, _, _ = source(ledger, monkeypatch, seed_void=True, extra_handler=True)
    asset = next(x for x in state(game).sheets["3"].assets if x.void)
    handler = active_handler(state(game))
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset.id, "destination": handler.token, "destination_asset": ""},
    )
    answer(
        game,
        OTHER,
        "mockingbird_sex_restore",
        text="Actual source without its transferred corruption",
    )
    assert not next(x for x in state(game).sheets["3"].assets if x.id == asset.id).void
    work = state(game).handler_void[-1].work
    actual = HandlerVoidService(ledger, game)
    assert actual.get(ADMIN, work)["episode"]["actor"] == handler.model_dump(mode="json")
    assert game.inspect(PLAYER, action)["state"] != "complete"
    actual.choose(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "knife",
        "Actual removal of redirected Void",
        site="Arm",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    assert game.dice.calls == 1


def test_actual_high_new_all_girl_void_uses_real_private_source_threshold_not_ack(
    ledger, monkeypatch
):
    from girlframe.services.m3_void import VoidService

    game, _, _, action, _, target = source(ledger, monkeypatch, (6, 6), last_girl=True)
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.void)
    answer(game, PLAYER, "mockingbird_sex_infect", fields={"asset": asset.id})
    answer(game, OTHER, "mockingbird_sex_rewrite", text="Actual final Girl corruption")
    row = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_sex_void_threshold")
    import json

    work = json.loads(row["body_json"])["work_id"]
    view = VoidService(ledger).get(OTHER, work)
    assert view["actor"] == target.model_dump(mode="json") and view["source_action"] == action
    assert (
        view["stage"] == "physical_review" and game.inspect(PLAYER, action)["state"] != "complete"
    )
    with pytest.raises(WorkflowError):
        game.respond(OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(flag=True))
    with pytest.raises(WorkflowError):
        VoidService(ledger).get(PLAYER, work)
    from test_void_service import respond

    service = VoidService(ledger)
    respond(
        service,
        work,
        "propose_occupancy",
        dict(mode="outside_frame", account="My actual body was already outside my own Frame"),
        viewer=OTHER,
    )
    respond(
        service,
        work,
        "confirm_occupancy",
        dict(account="Actual independent source review confirms the original occupancy"),
        viewer=ADMIN,
    )
    assert service.get(OTHER, work)["stage"] == "allured"
    guardian = next(
        x["ref"]
        for x in service.get(OTHER, work)["guardians"]
        if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    respond(
        service,
        work,
        "protect",
        dict(guardian=guardian, account="I request actual help before entering my Frame"),
        viewer=OTHER,
    )
    respond(
        service,
        work,
        "accept_protection",
        dict(account="I actually hold the original Girl away from her Frame"),
        viewer=PLAYER,
    )
    assert service.get(OTHER, work)["stage"] == "prevented"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert all(x.void for x in state(game).sheets["3"].assets if x.family == "girl")
    assert game.dice.calls == 1


def test_high_already_void_actual_harpy_has_factual_outcome_no_fake_asset_or_second_conversion(
    ledger, monkeypatch
):
    game, _, _, action, actor, target = source(ledger, monkeypatch, (6, 6), target_harpy=True)
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert "3" in actual.sheets and actual.sheets["3"].character_id != target.incarnation
    assert len(actual.world.pilots) == 1 and not actual.harpy_states
    assert (
        len(actual.world.pilots[0].assets) == 1
        and actual.world.pilots[0].assets[0].id == "actual-void-body"
    )
    assert depth(actual, actor, target) == 1
    assert any(
        x.get("kind") == "mockingbird_already_void" and x.get("target") == target.model_dump_json()
        for x in actual.facts
    )


def test_hidden_actual_cast_npc_never_leaks_through_book_or_discovery_picker(ledger, monkeypatch):
    from test_world import initial

    from girlframe.engine.m3_mockingbird_state import PERSON
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_mockingbird_discovery import DiscoveryService
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService

    game, worker, gateway, _, actor, _ = source(ledger, monkeypatch, (1, 2), join_handler=True)
    tick(worker, gateway, 5)
    with ledger.transaction() as c:
        value = state(game)
        value.world = initial()
        game.event(c, 1, str(uuid4()), "synthetic.actual_later_world", value)
    roles = NpcRoleService(WorldService(MissionService(ledger)))
    offered = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-private-witness",
            name="PRIVATE_TRUE_WITNESS_LABEL",
            jobs=("civilian",),
            detail="PRIVATE_UNOBSERVED_STORY",
            controller=3,
            cell=(0, 0),
            revealed=False,
        ),
    )
    roles.respond(OTHER, str(uuid4()), offered["id"], state(game).revision, "accept")
    witness = ActorRef(kind="npc", entity="actual-private-witness")
    change(CastService(ActorService(MissionService(ledger))), OTHER, "join", witness)
    book = plays.MockingbirdService(game)
    discovery = DiscoveryService(game)
    exposure = state(game).mockingbird.exposures[-1]
    assert "PRIVATE_TRUE_WITNESS_LABEL" not in str(book.preview(PLAYER, 900, actor))
    assert "actual-private-witness" not in str(discovery.preview(PLAYER, exposure.id, 900))
    before = state(game)
    with pytest.raises(WorkflowError):
        book.propose(
            PLAYER, str(uuid4()), 900, actor, PERSON, (witness,), "Cannot guess a private source"
        )
    with pytest.raises(WorkflowError):
        discovery.report(
            PLAYER,
            str(uuid4()),
            exposure.id,
            900,
            witness,
            "Cannot manufacture access by guessing a hidden role",
        )
    assert state(game) == before and game.dice.calls == 1
