"""Actual donor-confirmed Wings loss creates an owned, source-proved Void consequence."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_runtime import acquire, doctor
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.m3_void import VoidService, source
from girlframe.services.onboarding import WorkflowError


def exposed_donor_void(ledger, tmp_path, monkeypatch, *, prior_defeated_gorgon=False):
    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        initial = state(game)
        if prior_defeated_gorgon:
            from test_world import gorgon
            from test_world import initial as initial_world

            from girlframe.engine.m3_world import update

            world = initial_world()
            initial.world = update(
                world,
                gorgons=world.gorgons
                + (
                    gorgon("erratic", "prior-defeated", (1, 1)).model_copy(
                        update={"alive": False, "exposed": True}
                    ),
                ),
            )
        initial.sheets["2"].heat = 3
        assets = [x for x in initial.sheets["3"].assets if x.family == "frame"]
        assert len(assets) >= 2
        for asset in assets:
            asset.void = True
        selected = assets[0]
        selected.void = False
        selected.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.prior_donor_void_and_damage", initial)
    donor = current_ref(state(game), 3)
    procedures = ProcedureService(game)
    proposal = procedures.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        donor,
        "wings",
        "PRIVATE_DOC actual graft request",
        asset=selected.id,
        heat=2,
    )
    prior = state(game)
    with pytest.raises(WorkflowError, match="actual donor"):
        procedures.confirm(
            PLAYER, str(uuid4()), proposal["id"], prior.revision, "Cannot answer for donor"
        )
    assert state(game) == prior
    args = (
        OTHER,
        str(uuid4()),
        proposal["id"],
        prior.revision,
        "PRIVATE_DONOR confirms actual removal",
    )
    result = procedures.confirm(*args)
    assert procedures.confirm(*args) == result
    after = state(game)
    assert after.sheets["2"].heat == 1
    assert selected.id not in {x.id for x in after.sheets["3"].assets}
    loan = rules.values(after, "doctor_loan", rules.Loan)[0]
    assert loan.donor == donor and loan.source_asset_json == selected.model_dump_json()
    with ledger.engine.connect() as c:
        rows = list(
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "void_threshold"
                )
            ).mappings()
        )
        matching = [r for r in rows if json.loads(r["body_json"]).get("reason") == "doctor_wings"]
        assert len(matching) == 1
        work = matching[0]["id"]
        _, body, actor = source(game, c, work)
        assert actor == donor and body["source_id"] == proposal["id"]
        assert body["source_action"] is None and body["details"] == {"family": "frame"}
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    void = VoidService(ledger)
    with pytest.raises(WorkflowError):
        void.get(PLAYER, work)
    view = void.get(OTHER, work)
    assert view["stage"] in ("resist_pending", "enclosed", "abandoned", "physical_review")
    assert any(x["id"] == work for x in void.tasks(OTHER))

    return game, void, work, loan, selected


def test_donor_confirmed_wings_exposes_full_void_as_owned_required_work(
    ledger, tmp_path, monkeypatch
):
    exposed_donor_void(ledger, tmp_path, monkeypatch)


def test_donor_wings_actual_resistance_then_next_off_duty_returns_same_hardware(
    ledger, tmp_path, monkeypatch
):
    from test_ledger import ADMIN
    from test_m2_game import Gateway, answer, pass_tags, tick
    from test_void_service import respond

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput

    game, void, work, loan, original = exposed_donor_void(
        ledger, tmp_path, monkeypatch, prior_defeated_gorgon=True
    )
    # No assumed placement: use the existing independent owner/Handler occupancy workflow.
    view = void.get(OTHER, work)
    if view["stage"] == "physical_review":
        respond(
            void,
            work,
            "propose_occupancy",
            dict(mode="inside_frame", account="Actual donor remains inside her own Frame"),
            viewer=OTHER,
        )
        respond(
            void,
            work,
            "confirm_occupancy",
            dict(account="Handler confirms original donor occupancy"),
            viewer=ADMIN,
        )
    assert void.get(OTHER, work)["stage"] == "resist_pending"
    game.dice.faces = (4, 4)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=work,
            parent=None,
            heat=0,
            context="Actual donor resists her newly corrupt Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", options=("in_control", "tough"), denied=("sexy",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="Handler judges this actual resistance sufficient",
    )
    assert void.get(OTHER, work)["stage"] == "prevented"
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert all(x["id"] != work for x in void.tasks(OTHER))
    tick(worker, gateway, 4)
    next_period_preserving_void(ledger, game)
    after = state(game)
    returned = next(x for x in rules.values(after, "doctor_loan", rules.Loan) if x.id == loan.id)
    assert returned.phase == "returned" and returned.return_event
    assert not any(x.id == loan.asset for x in after.sheets["2"].assets)
    hardware = next(x for x in after.sheets["3"].assets if x.id == original.id)
    assert not hardware.void and not hardware.damaged
    assert hardware.name == original.name
    assert void.get(OTHER, work)["stage"] == "prevented"
    # Canonical rebuild preserves both the terminal consequence and the single return.
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == after


def next_period_preserving_void(store, game):
    """Real boundary without the older generic helper's synthetic prior surgery."""
    from test_ledger import ADMIN
    from test_off_duty_cycle import activate
    from test_strain import facts
    from test_strain_service import D6

    from girlframe.engine.m3_strain_effects import Choice
    from girlframe.engine.m3_world_state import Asset, CorePlan, Faction
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService
    from girlframe.services.m3_strain import StrainService
    from girlframe.services.m3_strain_effects import EffectService

    missions = MissionService(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"strain", "world", "plays", "off_duty"}
                }
            )
        }
    )
    strain = StrainService(OffDutyService(missions), dice=D6())
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    identity = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    strain.periods.credit(
        PLAYER,
        str(uuid4()),
        identity,
        1,
        state(game).revision,
        None,
        "I did not give anyone else credit this period",
    )
    before = state(game)
    original_void = {x.id for x in before.sheets["3"].assets if x.void}
    assert original_void
    count = sum(any(x.void for x in sheet.assets) for sheet in before.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        identity,
        2,
        before.revision,
        facts(
            at_least_half_have_void=2 * count >= len(before.order),
            no_girl_void=count == 0,
            harpy_or_prevented_since_last=True,
        ),
    )
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            3,
            1,
            Choice(
                rule_id="strain.void.high.3.1",
                account="The previously defeated Gorgon returns altered",
                target="prior-defeated",
                new_type="growth",
                new_assets=tuple(
                    Asset(
                        id="returned-new:" + str(i),
                        name="Altered capability " + str(i),
                        description="A new altered capability",
                        family="gorgon",
                    )
                    for i in (1, 2)
                ),
                core_plan=CorePlan(assets=("returned-new:1",), weakness="Foundation interference"),
            ),
        ),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A real group appears",
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
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned", rooms=((2, 3),)),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    activate(CycleService(strain.periods), game, identity)
    assert {x.id for x in state(game).sheets["3"].assets if x.void} == original_void


def test_grafted_void_at_doctor_cap_creates_owned_consequence_and_real_escape(
    ledger, tmp_path, monkeypatch
):
    from test_ledger import ADMIN
    from test_void_service import respond
    from test_world import initial as initial_world

    from girlframe.engine.m2 import AssetState
    from girlframe.engine.m3_assets import frame_capacity
    from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        initial = state(game)
        # Explicit prior campaign world; no invented post-transfer position.
        initial.world = initial.world or initial_world()
        host = initial.sheets["2"]
        host.heat = 3
        for index in range(
            frame_capacity(host, initial) - sum(x.family == "frame" for x in host.assets)
        ):
            host.assets.append(
                AssetState(
                    id=f"prior-doctor-cap:{index}", family="frame", name=f"Prior hardware {index}"
                )
            )
        hardware = [x for x in host.assets if x.family == "frame"]
        for item in hardware:
            item.void = True
            if not item.description:
                item.description = "Prior physical Doctor hardware: " + item.name
        replace = hardware[0]
        replace.void = False
        donor_asset = next(x for x in initial.sheets["3"].assets if x.family == "frame")
        if not donor_asset.description:
            donor_asset.description = "Prior physical donor component: " + donor_asset.name
        donor_asset.void = True
        donor_asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.prior_doctor_cap_void_and_donor_damage", initial)
    procedures = ProcedureService(game)
    request = procedures.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "wings",
        "PRIVATE original Doctor chooses the corrupt graft",
        asset=donor_asset.id,
        heat=2,
        replace=replace.id,
    )["id"]
    args = (OTHER, str(uuid4()), request, state(game).revision, "PRIVATE donor confirms transfer")
    outcome = procedures.confirm(*args)
    assert procedures.confirm(*args) == outcome
    after = state(game)
    assert after.sheets["2"].heat == 1
    assert all(x.void for x in after.sheets["2"].assets if x.family == "frame")
    assert replace.id not in {x.id for x in after.sheets["2"].assets}
    void = VoidService(ledger)
    work = next(x["id"] for x in void.tasks(PLAYER))
    with ledger.engine.connect() as c:
        _, body, actor = source(game, c, work)
        assert actor == current_ref(after, 2) and body["source_id"] == request
        assert body["reason"] == "doctor_wings"
        assert "PRIVATE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        void.get(OTHER, work)
    view = void.get(PLAYER, work)
    if view["stage"] == "physical_review":
        respond(
            void,
            work,
            "propose_occupancy",
            dict(mode="inside_frame", account="Original Doctor is inside her own Frame"),
        )
        respond(
            void,
            work,
            "confirm_occupancy",
            dict(account="Handler confirms the original Doctor occupancy"),
            viewer=ADMIN,
        )
    # The native fixture is a Mockingbird: its real owned resistance must happen
    # before Frame enclosure. Failure is a Handler decision, not a skipped child.
    if void.get(PLAYER, work)["stage"] == "resist_pending":
        from test_m2_game import Gateway, answer, pass_tags, tick

        from girlframe.delivery.m2_worker import GameWorker
        from girlframe.engine.m2 import PlayInput

        game.dice.faces = (4, 4)
        child = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                source_work=work,
                parent=None,
                heat=0,
                context="Doctor actually resists the grafted corruption",
                trigger_confirmed=True,
            ),
        )["action_id"]
        worker, gateway = GameWorker(game), Gateway()
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("sexy",))
        answer(
            game,
            ADMIN,
            "handler_keep",
            flag=False,
            text="Handler judges this actual resistance insufficient",
        )
        assert game.inspect(PLAYER, child)["state"] == "awaiting_choices"
    assert void.get(PLAYER, work)["stage"] == "enclosed"
    before_escape = state(game)
    cost = next(x for x in before_escape.sheets["2"].assets if x.family == "girl" and not x.damaged)
    respond(
        void,
        work,
        "choose_escape",
        dict(asset=cost.id, account="Doctor chooses actual escape cost"),
    )
    frame = [x for x in before_escape.sheets["2"].assets if x.family == "frame"]
    gorgon = Gorgon(
        id="wings-doctor-abandoned",
        name="Original Doctor Frame",
        cell=next(
            x.frame_cell
            for x in before_escape.placements
            if x.actor == current_ref(before_escape, 2)
        ),
        gorgon_class="aggressive",
        types=("sentinel",),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                void=x.void,
                damaged=x.damaged,
            )
            for x in frame
        ),
        core_plan=CorePlan(assets=(frame[0].id,), weakness="Actual exposed access"),
    )
    respond(
        void,
        work,
        "escape",
        dict(
            gorgon=gorgon.model_dump(mode="json"),
            account="Handler records the actual abandoned Doctor Frame",
        ),
        viewer=ADMIN,
    )
    final = state(game)
    assert void.get(PLAYER, work)["stage"] == "escaped"
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert final.sheets["2"].frame_scrapped
    assert next(x for x in final.sheets["2"].assets if x.id == cost.id).damaged
    converted = next(x for x in final.world.gorgons if x.id == gorgon.id)
    loan = next(x for x in rules.values(final, "doctor_loan", rules.Loan) if x.id == request)
    assert loan.asset == "doctor-loan:" + request
    borrowed = next(x for x in converted.assets if x.id == loan.asset)
    assert borrowed.void and not borrowed.damaged
    assert loan.phase == "borrowed"  # Conversion is not a fictional hardware return.
    assert all(x["id"] != work for x in void.tasks(PLAYER))
    # Transformed/scrapped donor or Doctor loan return is a separate unresolved lifecycle.
    # This test does not claim that later Off-Duty return has happened.
