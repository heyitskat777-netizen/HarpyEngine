"""Reuse source-backed native scenarios with explicit fixture-authored GM proposals."""

import importlib
import inspect
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.ai.gm_outcomes import (
    BattleConsequences,
    CollateralOutcome,
    FactOutcome,
    GorgonJudgment,
    HandlerOutcome,
    KeepOutcome,
    OutcomeProposal,
    PandoraOutcome,
    SensorAnswers,
    WarpOutcome,
    WraithOutcome,
)
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.ai.observation import ObservationPolicy
from girlframe.engine.m3_janus_pandora import ChildProposal
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.gm_outcomes import GMOutcomeService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_plays import HandlerPlayService


def attach(game):
    observer = DirectorObservationService(game.store, synthetic=True)
    with game.store.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, str(uuid4()), scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, str(uuid4()), scene, 1, consent=True)
    return GMOutcomeService(DirectorContextService(observer)), scene


def consume(svc, scene, kind, identity, decision, owner=ADMIN, frame=None):
    request = svc.open(ADMIN, str(uuid4()), scene, kind, identity, frame)
    packet = svc.packet(ADMIN, scene, request["id"])
    proposal = OutcomeProposal(
        request_id=packet.request_id,
        decision=decision,
        cited_evidence=("source", "native"),
        private_reasoning="SYNTHETIC private reasoning, excluded from native answers",
    )
    saved = svc.propose(ADMIN, str(uuid4()), scene, request["id"], proposal)
    key = str(uuid4())
    committed = svc.confirm(owner, key, scene, saved["id"])
    assert svc.confirm(owner, key, scene, saved["id"]) == committed
    return committed


def decision(kind, answer):
    if kind == "harpy_sensor_answers":
        return SensorAnswers(answers={"a1": answer.text})
    if kind.startswith("gorgon_"):
        if kind == "gorgon_collateral":
            return CollateralOutcome(
                effects=answer.options,
                structure=answer.fields.get("structure"),
                civilians=tuple(filter(None, answer.fields.get("civilians", "").split(","))),
                account=answer.text,
            )
        if kind == "gorgon_warp":
            return WarpOutcome(
                effect=answer.options[0],
                account=answer.text,
                name=answer.fields.get("name", ""),
                description=answer.fields.get("description", ""),
            )
        return GorgonJudgment(
            verdict=("capable" if answer.flag else "incapable")
            if kind == "gorgon_asset_capability"
            else answer.options[0],
            losing_asset=answer.fields.get("asset"),
            indirect=bool(answer.flag) if kind == "gorgon_contest_judge" else False,
            account=answer.text,
        )
    if kind == "battle_handler":
        return BattleConsequences(
            choices=answer.options, account=answer.text or "Printed consequence"
        )
    if kind == "janus_pandora_child":
        return PandoraOutcome(child=ChildProposal.model_validate_json(answer.fields["child"]))
    if kind == "wyvern_wraith_rules":
        return WraithOutcome(rules=answer.text, tag=answer.fields.get("tag"))
    return FactOutcome(established=answer.flag, account=answer.text)


CASES = (
    (
        "test_contaminant_zone",
        "test_actual_group_harpy_study_warp_protection_expiry_and_private_history",
        {},
    ),
    (
        "test_harpy_sensors",
        "test_harpy_questions_have_no_roll_modifiers_heat_or_resource_award_and_private_honest_reply",
        {},
    ),
    (
        "test_gorgon_runtime",
        "test_actual_attack_response_child_uses_one_real_roll_and_actual_enough",
        {"enough": True},
    ),
    (
        "test_harpy_actor_plays",
        "test_native_harpy_keep_all_tiers_has_one_real_roll_owned_traits_and_actual_gm",
        {
            "faces": (4, 4),
            "positive": ("beautiful", "in_control"),
            "negative": ("desperate",),
            "label": "",
        },
    ),
    (
        "test_enforcer_snoop",
        "test_mid_real_bond_private_finding_and_actual_ordinary_object_transfer",
        {},
    ),
    (
        "test_gorgon_runtime",
        "test_actual_directed_collateral_no_interrupt_and_concrete_structure_loss",
        {},
    ),
    (
        "test_gorgon_runtime",
        "test_warp_actual_exposed_core_and_exact_selected_mutation",
        {"option": "evolve"},
    ),
    ("test_gorgon_runtime", "test_actual_gorgon_contest_destroys_original_losing_asset", {}),
    (
        "test_gorgon_runtime",
        "test_native_actual_owner_declines_damaged_capability_without_effect_and_replay",
        {},
    ),
    (
        "test_gorgon_runtime",
        "test_source_director_denies_nonlocal_collateral_reach_without_fabricated_travel",
        {},
    ),
    (
        "test_battle_pipeline",
        "test_actual_high_allout_handler_chooses_and_actor_pays_owned_asset",
        {},
    ),
    (
        "test_janus_pandora_low",
        "test_actual_pandora_low_birth_creates_dormant_child_at_original_birthplace",
        {},
    ),
    (
        "test_wyvern",
        "test_real_frame_wraith_tiers_actual_handler_rules_tag_and_table_play",
        {"tier": "high", "faces": (6, 6), "slot": "captain"},
    ),
)


@pytest.mark.parametrize("module,name,extra", CASES, ids=[x[1] for x in CASES])
def test_actual_native_consumers_through_typed_proposals(
    ledger, tmp_path, monkeypatch, module, name, extra
):
    native = importlib.import_module(module)
    if module == "test_gorgon_runtime":
        native.candidate_source_gate.__wrapped__(monkeypatch)
    original = GameService.respond
    adapters, seen, operations = {}, {}, []
    supported = {
        "gorgon_asset_capability",
        "gorgon_contest_judge",
        "gorgon_attack_judge",
        "gorgon_collateral_reach",
        "gorgon_collateral",
        "gorgon_warp",
        "battle_handler",
        "janus_pandora_child",
        "wyvern_wraith_rules",
        "snoop_object_fact",
        "harpy_sensor_answers",
        "handler_keep",
    }

    def routed(game, viewer, key, identity, revision, answer, **kwargs):
        if key.startswith("gm-outcome:"):
            return original(game, viewer, key, identity, revision, answer, **kwargs)
        row = next((r for r in game.choices(viewer) if r["id"] == identity), None)
        if (
            row
            and row["kind"] == "harpy_sensor_answers"
            and (answer.flag is not True or answer.options or answer.denied or answer.fields)
        ):
            return original(game, viewer, key, identity, revision, answer, **kwargs)
        if not row or row["kind"] not in supported:
            return original(game, viewer, key, identity, revision, answer, **kwargs)
        if key in seen:
            return seen[key]
        if id(game.store) not in adapters:
            adapters[id(game.store)] = attach(game)
        svc, scene = adapters[id(game.store)]
        operations.append(row["kind"])
        frame = None
        if row["kind"] == "handler_keep":
            with game.store.engine.connect() as c:
                result = game.action(c, row["action_id"])["data"]["result"]
            traits = tuple(
                TraitClaim(trait=x, polarity=polarity)
                for key, polarity in (("positive", "are"), ("negative", "are_not"))
                for x in result[key]
            )
            frame = TaskFrame(
                stakes="Actual source response succeeds or fails",
                demands=(Demand(id="goal", question="Does this actual response suffice?"),),
            )
            outcome = KeepOutcome(
                verdict="enough" if answer.flag else "not_enough",
                assessments=(
                    Assessment(
                        demand_id="goal",
                        sufficient=answer.flag,
                        evidence_ids=("traits", "source", "native"),
                        traits=traits,
                        private_reason="Explicit fixture-authored interpretation",
                    ),
                ),
                narration=answer.text,
            )
        else:
            outcome = decision(row["kind"], answer)
        result = consume(svc, scene, "choice", identity, outcome, owner=viewer, frame=frame)
        seen[key] = result
        return result

    original_submit = HandlerPlayService.submit

    def handler_routed(handler, viewer, key, identity, revision, play, effect):
        if key.startswith("gm-outcome:") or play != "contaminant_warp":
            return original_submit(handler, viewer, key, identity, revision, play, effect)
        if key in seen:
            return seen[key]
        if id(handler.store) not in adapters:
            adapters[id(handler.store)] = attach(handler.game)
        svc, scene = adapters[id(handler.store)]
        operations.append("contaminant_warp")
        result = consume(
            svc,
            scene,
            "handler_grant",
            identity,
            HandlerOutcome(play=play, effect=effect),
            owner=viewer,
        )
        seen[key] = result
        return result

    monkeypatch.setattr(HandlerPlayService, "submit", handler_routed)
    monkeypatch.setattr(GameService, "respond", routed)
    function = getattr(native, name)
    values = dict(ledger=ledger, tmp_path=tmp_path, monkeypatch=monkeypatch, **extra)
    function(**{k: values[k] for k in inspect.signature(function).parameters})
    assert operations, "Scenario must exercise a real typed adapter consumer"


@pytest.mark.parametrize("source_kind", ["choice", "table"])
def test_gm_discretion_overrides_shared_assault_outcome_without_player_responses(
    ledger, monkeypatch, source_kind
):
    import sqlalchemy as sa
    from test_battle_pipeline import rolled
    from test_m2_game import answer, state

    from girlframe.ai.gm_outcomes import TableOutcome
    from girlframe.database import tables as t
    from girlframe.services.onboarding import WorkflowError

    if source_kind == "choice":
        ledger.policy = ledger.policy.model_copy(update={"owner_table_outcomes": "gm_discretion"})
    game, _, _, action, declaration = rolled(ledger, monkeypatch)
    if source_kind == "table":
        # An actual participant's contribution survives a transition to GM discretion.
        answer(game, PLAYER, "battle_assault_table", flag=False, text="My actual assessment")
        ledger.policy = ledger.policy.model_copy(update={"owner_table_outcomes": "gm_discretion"})
    svc, scene = attach(game)
    with ledger.engine.connect() as c:
        before = list(c.execute(sa.select(t.m2["m2_responses"])))
    if source_kind == "choice":
        identity = next(x["id"] for x in game.choices(ADMIN) if x["kind"] == "battle_gm_table")
    else:
        identity = action
    request = svc.open(ADMIN, str(uuid4()), scene, source_kind, identity)
    packet = svc.packet(ADMIN, scene, request["id"])
    saved = svc.propose(
        ADMIN,
        str(uuid4()),
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=TableOutcome(
                vast_advantage=True,
                account="GM establishes overwhelming advantage despite "
                "the participant's contrary assessment",
            ),
            cited_evidence=("source", "native"),
            private_reasoning="Fixture GM decision",
        ),
    )
    with pytest.raises(WorkflowError, match="NOT_OWNED"):
        svc.confirm(PLAYER, str(uuid4()), scene, saved["id"])
    if source_kind == "table":
        approved_policy = ledger.policy
        ledger.policy = approved_policy.model_copy(
            update={
                "m3_approval": approved_policy.m3_approval.model_copy(
                    update={"subsystems": approved_policy.m3_approval.subsystems - {"plays"}}
                )
            }
        )
        with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
            svc.confirm(ADMIN, str(uuid4()), scene, saved["id"])
        ledger.policy = approved_policy
    key = str(uuid4())
    committed = svc.confirm(ADMIN, key, scene, saved["id"])
    assert svc.confirm(ADMIN, key, scene, saved["id"]) == committed
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert not next(
        x for x in state(game).sheets["3"].assets if x.id == declaration.target_asset
    ).damaged
    with ledger.engine.connect() as c:
        after = list(c.execute(sa.select(t.m2["m2_responses"])))
        assert all(row in after for row in before)
        assert all(row.actor_id == "1" for row in after if row not in before)
        meta = game.action(c, action)["data"]["battle"]
        assert meta["gm_table_outcome"]["vast_advantage"] is True
        if source_kind == "table":
            assert meta["votes"]["2"]["vast"] is False


def test_gm_exploration_preserves_contributions_and_closes_actual_questions(
    ledger, tmp_path, monkeypatch
):
    from test_m2_game import answer, state
    from test_wyvern import declare_party, ready, roll

    from girlframe.ai.gm_outcomes import TableOutcome
    from girlframe.engine import m3_wyvern as rules

    ledger.policy = ledger.policy.model_copy(update={"owner_table_outcomes": "gm_discretion"})
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    party = declare_party(game, controls)
    action = roll(game, worker, gateway, play="wyvern_explore", source_work=party)
    answer(game, PLAYER, "wyvern_questions", options=("engine",))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "wyvern_unmark")
    detail = game.decision(PLAYER, row["id"])["detail"]
    answer(
        game,
        PLAYER,
        "wyvern_unmark",
        denied=tuple(x[0] for x in detail["identities"][: detail["count"]]),
    )
    question = rules.records(state(game), rules.Question)[-1]
    controls.answer(
        PLAYER,
        str(uuid4()),
        question.id,
        state(game).revision,
        "My character thinks this is a furnace",
    )
    originals = rules.records(state(game), rules.Answer)
    svc, scene = attach(game)
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "wyvern_gm_outcome")
    consume(
        svc,
        scene,
        "choice",
        choice["id"],
        TableOutcome(
            answers={question.id: "GM establishes a coolant chamber"},
            account="Final shared exploration outcome",
        ),
    )
    final = rules.records(state(game), rules.Answer)
    assert all(x in final for x in originals)
    assert final[-1].author == 1 and final[-1].text == "GM establishes a coolant chamber"
    assert rules.records(state(game), rules.Question)[-1].closed_event
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_battle_facts_use_actual_source_without_dice(ledger):
    from test_battle_service import prepared
    from test_m2_game import state

    from girlframe.ai.gm_outcomes import BattleFacts

    game, _, _, battle, data, declaration = prepared(ledger)
    proposed = battle.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    svc, scene = attach(game)
    consume(
        svc,
        scene,
        "battle",
        proposed["id"],
        BattleFacts(opening=True, reach=True, evidence="Actual observed range and opening"),
    )
    context = battle.context(ADMIN, proposed["id"])
    assert context and game.dice.calls == 0
    assert any(x.get("kind") == "battle_context" for x in state(game).facts)


@pytest.mark.parametrize("play", ["escalate", "support"])
def test_world_proposal_uses_actual_handler_grant(ledger, play):
    from test_handler_plays import begin, ready
    from test_m2_game import state

    from girlframe.ai.gm_outcomes import HandlerOutcome
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.engine.m3_world_state import Npc

    handler, game = ready(ledger)
    grant = begin(handler, game)
    svc, scene = attach(game)
    extra = (
        dict(detail="A signal approaches", stakes="The relay may fail")
        if play == "escalate"
        else dict(
            npc=Npc(
                id="support",
                name="Technician",
                jobs=("mechanic",),
                detail="Regular employee",
                controller=1,
                cell=state(game).world.locations[0].cell,
                revealed=True,
                employment="foundation",
            )
        )
    )
    consume(
        svc,
        scene,
        "handler_grant",
        grant,
        HandlerOutcome(
            play=play, effect=Effect(kind=play, account="Actual scene support", **extra)
        ),
    )
    assert next(x for x in state(game).handler_plays if x.id == grant).state == "complete"


def test_engage_response_narration_and_gorgon_final_judgment(ledger, monkeypatch):
    from test_gorgon_runtime import candidate_source_gate, gorgon_source
    from test_m2_game import answer, pass_tags, state, tick

    from girlframe.ai.gm_outcomes import OutcomeNarration
    from girlframe.engine.m2 import PlayInput

    candidate_source_gate.__wrapped__(monkeypatch)
    game, worker, gateway, parent, declaration = gorgon_source(ledger)
    answer(game, PLAYER, "gorgon_defend", options=("play",), text="I respond to the actual attack")
    game.dice.faces = (4, 5)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            piloting=True,
            parent=parent,
            target_actor=declaration.actor,
            context="I pin the claw and advance out of its path",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("pin", "advance"),
        fields={"pin": asset.id, "advance": asset.id},
        text="Actual claw pinned by the chosen Asset",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    svc, scene = attach(game)
    judgment = next(x for x in game.choices(ADMIN) if x["kind"] == "gorgon_attack_judge")
    consume(
        svc,
        scene,
        "choice",
        judgment["id"],
        GorgonJudgment(verdict="averted", account="The actual pin and advance divert this attack"),
    )
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    before = state(game).model_dump_json()
    result = consume(
        svc,
        scene,
        "completed",
        child,
        OutcomeNarration(
            text="The pilot pins the claw and advances; the GM rules the attack averted.",
            effect_refs=("tier",),
        ),
    )
    assert svc.contribution(PLAYER, scene, result["id"])["canon_effects"] is False
    assert state(game).model_dump_json() == before and game.dice.calls == 1
