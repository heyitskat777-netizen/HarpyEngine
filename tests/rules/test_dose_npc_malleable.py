"""Actual NPC cocktail qualifies only later genuine Malleable births and survives expiry."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_disposable_psyche import real_period
from test_dose_up import native_choice, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_off_duty_cycle import call

from girlframe.engine import m3_dose_up as rules
from girlframe.engine import m3_malleable as malleable
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_off_duty import HandlerContext
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_dose_up import prove
from girlframe.services.m3_malleable import MalleableService, prove_birth
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_dose_birth_expiry_and_foundation_deprogramming_protection(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    # Explicit initial fixture, before any NPC, Dose or Malleable source exists.
    # The imported real-period helper chooses the genuine low-Void table.
    with ledger.transaction() as c:
        initial = state(game)
        for sheet in initial.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.initial_no_void_assets", initial)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-dose-recipient")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            cell=(0, 0),
            revealed=True,
            detail="Actual ordinary human source recipient",
            employment="foundation",
        ),
    )
    casts = CastService(ActorService(missions))
    cast_change(casts, ADMIN, "join", npc)
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.record_contact(
            PLAYER, str(uuid4()), 900, npc, before.revision, "A name alone is not actual anatomy"
        )
    assert state(game) == before
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "Actual witnessed human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in controls.menu(PLAYER, 900)["targets"]
    )
    malleable_controls = MalleableService(ledger, game)
    early = malleable_controls.give_npc_tag(
        PLAYER, str(uuid4()), 900, npc, "Actual pre-dose work Tag", state(game).revision
    )
    assert not early["eligible"]
    contact = controls.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_NPC_VEIN My hand actually reaches this original body's exposed vein here",
    )["id"]
    game.dice.faces = (6, 6)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            target_actor=npc,
            source_work=contact,
            heat=1,
            context="Actual original recipient dosing",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(game, PLAYER, ("quick", "calm"))
    native_choice(game, ADMIN, ("sense",))
    final = state(game)
    with ledger.engine.connect() as c:
        source = prove(game, c, final, action)
    assert source.target == npc and source.target_controller == 1
    assert source.total >= 11 and len(source.selections) == 2
    assert source.selections[0].chooser == 2 and source.selections[1].chooser == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1 and game.dice.calls == 1
    drugs = [x for x in rules.records(final, rules.NpcDrugTag) if x.dose == action]
    assert {x.component for x in drugs} == {"quick", "calm", "sense"}
    assert all(x.tag in actor_tags(final, npc) for x in drugs)
    assert not any(x.dose == action for x in rules.records(final, rules.DrugTag))
    assert controls.view(ADMIN, action)["phase"] == "active"
    with pytest.raises(WorkflowError):
        controls.view(OTHER, action)
    tick(worker, gateway, 8)
    qualified = malleable_controls.give_npc_tag(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        "Actual work Tag during the real cocktail",
        state(game).revision,
    )
    assert qualified["eligible"]
    birth = next(
        x for x in malleable.records(state(game), malleable.Birth) if x.id == qualified["id"]
    )
    assert birth.altered_kind == "dose" and birth.altered_id in {x.id for x in drugs}
    assert birth.recipient == npc and birth.event
    with ledger.engine.connect() as c:
        assert prove_birth(game, c, state(game), birth.id) == birth
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        assert (
            len([x for x in rules.records(state(game), rules.SceneEnd) if x.dose == action])
            == number
        )
        if number == 1:
            assert all(x.tag in actor_tags(state(game), npc) for x in drugs)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (PLAYER, OTHER, ADMIN):
                game.join_scene(human, str(uuid4()), 900)
            cast_change(casts, ADMIN, "join", npc)
    final = state(game)
    assert rules.expired(final, action)
    assert not any(x.id in {d.id for d in drugs} for x in actor_tags(final, npc))
    assert controls.view(ADMIN, action)["phase"] == "expired"
    with ledger.engine.connect() as c:
        assert prove(game, c, final, action) == source
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)
    cast_change(casts, ADMIN, "join", npc)
    later = malleable_controls.give_npc_tag(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        "Actual later work Tag after drugs wore off",
        state(game).revision,
    )
    assert not later["eligible"]
    assert malleable.protected_npc(state(game), npc)
    with ledger.engine.connect() as c:
        assert prove_birth(game, c, state(game), birth.id) == birth
    cycle, period = real_period(missions, game)
    assert any(
        event.period_id == period and event.rule_id == "strain.void.low.1.1"
        for event in state(game).strain.events
    )
    before_procedure = state(game)
    review = cycle.review(ADMIN, period)
    context = HandlerContext(
        entity="npc:" + npc.entity, operation="deprogram", deprogram_tags=(later["id"],)
    )
    cycle.handler_scene(
        ADMIN,
        str(uuid4()),
        period,
        review["revision"],
        before_procedure.revision,
        "npc_employment",
        (1, 2),
        "These actual work-affecting Tags impair duties; Foundation staff perform deprogramming",
        context=context,
    )
    # This genuine NPC is controlled by ADMIN, already included in (1, 2).
    # OTHER is not a participant and must not attest to this procedure.
    for viewer in (ADMIN, PLAYER):
        call(cycle, game, viewer, period, "acknowledge", None)
    final = state(game)
    receipt = malleable.records(final, malleable.Deprogramming)[-1]
    assert receipt.subject == npc and receipt.tags == (later["id"],) and receipt.blocked
    assert actor_tags(final, npc) == actor_tags(before_procedure, npc)
    assert not any(x.id.startswith("dose-up:") for x in actor_tags(final, npc))
    assert game.dice.calls == 1
    assert "PRIVATE_NPC_VEIN" not in str(gateway.messages)
