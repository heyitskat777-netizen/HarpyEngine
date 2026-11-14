"""PANDORA low ordinary birth and source-bound birthplace constraint."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.services.m3_janus_requisitions import JanusRequisitionService


def test_unplaced_pandora_rejects_before_roll_then_actual_placement_allows_birth(
    ledger, tmp_path, monkeypatch
):
    from test_ledger import ADMIN
    from test_m2_game import Gateway, answer, pass_tags, tick
    from test_off_duty_cycle import activate, prepared

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actors import owned_refs
    from girlframe.engine.m3_janus_pandora import ChildProposal, pregnancies
    from girlframe.engine.m3_janus_requisitions import PANDORA
    from girlframe.services.m3_actors import profiles

    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(PANDORA,))
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_pandora_funds", current)
    service = JanusRequisitionService(game)
    data = service.menu(PLAYER)
    service.buy_rule(
        PLAYER,
        str(uuid4()),
        data["source_sha256"],
        PANDORA,
        "Actual PANDORA implanted womb acquisition",
    )
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService

    cycle = CycleService(OffDutyService(MissionService(ledger)))
    activate(cycle, game, period)
    assert pregnancies(state(game))[-1].phase == "inseminated"
    from girlframe.services.onboarding import WorkflowError

    before = state(game).model_dump_json()
    pending_pregnancy = pregnancies(state(game))[-1].id
    with pytest.raises(WorkflowError, match="Establish the original Frame's actual birthplace"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="pandora_birth",
                heat=0,
                trigger_confirmed=True,
                context="Actual unplaced birth must not consume a roll",
            ),
        )
    assert state(game).model_dump_json() == before
    assert game.dice.calls == 0
    # Establish the original Frame's location through the owner's factual
    # proposal and the separately authorized Handler review, before any birth.
    from test_physical_service import decide, propose

    from girlframe.services.m3_physical import PhysicalService

    physical = PhysicalService(ledger)
    placement = propose(physical)
    decide(physical, placement["id"])

    assert pregnancies(state(game))[-1].id == pending_pregnancy
    assert pregnancies(state(game))[-1].phase == "inseminated"
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="pandora_birth",
            heat=0,
            trigger_confirmed=True,
            context="Birth the actual child from this original Inseminated Frame",
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    proposal = ChildProposal(
        name="Actual source newborn",
        gorgon_type="growth",
        gorgon_class="dormant",
        assets=("Overgrown Musculature",),
        descriptions=("Actual newborn muscle",),
        core_assets=(0,),
        weakness="Actual Handler-written vulnerable Core",
        account="Handler writes actual dormant child",
    )
    answer(game, ADMIN, "janus_pandora_child", fields={"child": proposal.model_dump_json()})
    actual = state(game)
    child = pregnancies(actual)[-1].child
    assert child is not None and child.kind == "gorgon"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    body = next(x for x in actual.world.gorgons if x.id == child.entity)
    assert len(body.assets) == 1 and body.gorgon_class == "dormant"
    assert body.cell == pregnancies(actual)[-1].birth_cell
    with ledger.engine.connect() as c:
        assert child not in owned_refs(actual, 2, profiles(c, ledger.campaign_id))

    from girlframe.engine.m3_janus_pandora import require_can_move

    birthplace = pregnancies(actual)[-1].birth_cell
    assert birthplace is not None
    before = actual.model_dump_json()
    require_can_move(actual, child, birthplace)
    other_cell = (birthplace[0] + 1, birthplace[1])
    with pytest.raises(ValueError, match="stays at its original birthplace"):
        require_can_move(actual, child, other_cell)
    assert actual.model_dump_json() == before
    assert pregnancies(actual)[-1].tier == "low"
    assert pregnancies(actual)[-1].phase == "born"
    from girlframe.services.m3_janus_pandora import menu

    assert menu(game, PLAYER)["can_birth"] is False
    assert game.dice.calls == 1
