"""PANDORA mid ordinary birth, real maternal ownership and scene admission."""

from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.services.m3_janus_requisitions import JanusRequisitionService


def test_actual_pandora_mid_birth_grants_original_mother_child_control(
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
    # Establish the original Frame's location through the owner's factual
    # proposal and the separately authorized Handler review, before any birth.
    from test_physical_service import decide, propose

    from girlframe.services.m3_physical import PhysicalService

    physical = PhysicalService(ledger)
    placement = propose(physical)
    decide(physical, placement["id"])

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
    game.dice.faces = (4, 5)
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
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    assert pregnancies(state(game))[-1].tier == "mid"
    proposal = ChildProposal(
        name="Actual source newborn",
        gorgon_type="growth",
        gorgon_class="benevolent",
        assets=("Overgrown Musculature", "Infectious Flagella"),
        descriptions=("Actual newborn muscle", "Actual newborn flagella"),
        core_assets=(0,),
        weakness="Actual Handler-written vulnerable Core",
        account="Handler writes actual obedient and vicious child",
    )
    answer(game, ADMIN, "janus_pandora_child", fields={"child": proposal.model_dump_json()})
    actual = state(game)
    child = pregnancies(actual)[-1].child
    assert child is not None and child.kind == "gorgon"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    body = next(x for x in actual.world.gorgons if x.id == child.entity)
    assert len(body.assets) == 2 and body.gorgon_class == "benevolent"
    assert body.cell == pregnancies(actual)[-1].birth_cell
    with ledger.engine.connect() as c:
        bindings = profiles(c, ledger.campaign_id)
        assert child in owned_refs(actual, PLAYER.user_id, bindings)
        assert child not in owned_refs(actual, ADMIN.user_id, bindings)

    from test_cast_service import change

    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_janus_pandora import vicious
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService

    assert resolve(actual, child, bindings).controller == PLAYER.user_id
    assert vicious(actual, child)
    assert pregnancies(actual)[-1].tier == "mid"
    assert pregnancies(actual)[-1].phase == "born"
    # Release actual source delivery before the original mother admits her child.
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert not game.pending_actions(c)
    change(CastService(ActorService(MissionService(ledger))), PLAYER, "join", child)
    actual = state(game)
    scene = next(x for x in actual.scene_casts if x.channel == 900)
    role = next(x for x in scene.roles if x.actor == child)
    assert role.controller == PLAYER.user_id
    from girlframe.services.m3_janus_pandora import menu

    assert menu(game, PLAYER)["can_birth"] is False
    assert game.dice.calls == 1
