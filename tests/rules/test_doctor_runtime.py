"""Native Doctor normal source workflows; no graft/actor matrix or release claim."""

import asyncio
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor import open_choice, open_roll
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_doctor_requisitions import DoctorRequisitionService


def doctor(store, tmp_path, monkeypatch):
    _, game = service(store, frame=rules.BOOK)
    approved(
        store, game, tmp_path, monkeypatch, extra=(rules.NANO, rules.TRACK, *rules.REQUISITIONS)
    )
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks", "world", "off_duty"}}
            )
        }
    )
    return DoctorService(game), game


def acquire(game, *abilities):
    with game.store.transaction() as c:
        value = state(game)
        value.sheets["2"].permissions += 2 * len(abilities)
        game.event(c, 1, str(uuid4()), "synthetic.prior_doctor_permissions", value)
    service = DoctorRequisitionService(game)
    for ability in abilities:
        service.buy(
            PLAYER, str(uuid4()), state(game).revision, ability, "Actual native Doctor acquisition"
        )


def next_period(store, game, monkeypatch):
    import test_strain_service
    from test_off_duty_cycle import activate, prepared

    from girlframe.services.m3_missions import MissionService

    monkeypatch.setattr(
        test_strain_service, "service", lambda store, frame=None: (MissionService(store), game)
    )

    def with_credit(strain, actual, high=frozenset()):
        from test_strain import facts

        strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", high)
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
        current = state(game)
        void_count = sum(any(x.void for x in s.assets) for s in current.sheets.values())
        return strain.prepare(
            ADMIN,
            str(uuid4()),
            identity,
            2,
            current.revision,
            facts(
                at_least_half_have_void=2 * void_count >= len(current.order),
                no_girl_void=void_count == 0,
            ),
        )["id"]

    monkeypatch.setattr(test_strain_service, "prepared", with_credit)
    cycle, actual, identity = prepared(store)
    assert actual is game
    activate(cycle, game, identity)
    return identity


def test_actual_nanobot_native_roll_marks_once_gives_heat_and_patient_repairs_and_unmarks(
    ledger, tmp_path, monkeypatch
):
    source, game = doctor(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["2"].heat = 2
        patient = value.sheets["3"]
        damaged = tuple(x.id for x in patient.assets[:2])
        for asset in patient.assets[:2]:
            asset.damaged = True
        patient.identities[0].marked = True
        identity = patient.identities[0].id
        game.event(c, 1, str(uuid4()), "synthetic.actual_medical_resources", value)
    game.dice.faces = (3, 4)

    async def prepare():
        interaction = current(2, 997001)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_roll(interaction, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("nanobot_injection",),
            target=(current_ref(state(game), 3).token,),
            heat=("2",),
            account="I actually stab the patient with my nanobots",
        )
        await form.confirm.callback(current(2, 997002))
        assert form.completed and game.dice.calls == 0

    asyncio.run(prepare())
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    assert state(game).sheets["2"].obsolescence_marked == 1
    assert state(game).sheets["2"].heat == 0 and state(game).sheets["3"].heat == 2
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")

    async def benefits():
        own = current(2, 997003)
        await own.response.defer(ephemeral=True)
        await open_choice(own, source, choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("repair", "identity"))
        await form.confirm.callback(current(2, 997004))
        assert form.completed
        row = next(x for x in game.choices(OTHER) if x["kind"] == "doctor_patient")
        patient = current(3, 997005)
        await patient.response.defer(ephemeral=True)
        await open_choice(patient, source, row["id"])
        form = patient.edit_original_response.call_args.kwargs["view"]
        form.values.update(assets=damaged, identity=(identity,))
        await form.confirm.callback(current(3, 997006))
        assert form.completed

    asyncio.run(benefits())
    actual = state(game)
    assert all(not x.damaged for x in actual.sheets["3"].assets if x.id in damaged)
    assert not actual.sheets["3"].identities[0].marked
    assert actual.sheets["2"].obsolescence_marked == 1 and game.dice.calls == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_paid_cute_nurse_native_patient_confirm_deepens_actual_bond(ledger, tmp_path, monkeypatch):
    from girlframe.discord_adapter.m3_doctor import open_care, open_procedure
    from girlframe.engine.m3_actor_bonds import depth
    from girlframe.services.m3_doctor_care import CareService

    source, game = doctor(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["2"].permissions = 2
        value.sheets["2"].obsolescence_marked = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_resources", value)

    async def workflow():
        own = current(2, 997101)
        await own.response.defer(ephemeral=True)
        await open_procedure(own, source, source.menu(PLAYER, 900), "buy")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(rule=(rules.NURSE,), account="Actual native Cute Nurse acquisition")
        await form.confirm.callback(current(2, 997102))
        assert form.completed
        own = current(2, 997103)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_procedure(own, source, source.menu(PLAYER, 900), "nurse")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(current_ref(state(game), 3).token,), account="Actual hands-on medical care"
        )
        await form.confirm.callback(current(2, 997104))
        care = rules.values(state(game), "doctor_care", rules.Care)[-1]
        patient = current(3, 997105)
        await patient.response.defer(ephemeral=True)
        await open_care(patient, source, care.id)
        form = patient.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="I confirm the actual medical care I received")
        await form.confirm.callback(current(3, 997106))
        assert (
            form.completed and CareService(game).get(OTHER, care.id)["care"]["phase"] == "complete"
        )

    before = depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3))
    asyncio.run(workflow())
    assert depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3)) == min(
        2, before + 1
    )
    assert state(game).sheets["2"].permissions == 0
    assert state(game).sheets["2"].obsolescence_marked == 1


def test_borrowed_wings_spends_actual_heat_moves_one_asset_then_returns_at_real_off_duty(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m2 import AssetState
    from girlframe.services.m3_doctor_procedures import ProcedureService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["2"].heat = 2
        host = value.sheets["2"]
        for index in range(4 - sum(x.family == "frame" for x in host.assets)):
            host.assets.append(
                AssetState(
                    id="prior-frame:" + str(index),
                    family="frame",
                    name="Previously acquired Frame hardware " + str(index),
                )
            )
        assert sum(x.family == "frame" for x in host.assets) == 4
        asset = next(x for x in value.sheets["3"].assets if x.family == "frame")
        asset.damaged = True
        original = asset.model_copy(deep=True)
        game.event(c, 1, str(uuid4()), "synthetic.actual_damaged_donor", value)
    source = ProcedureService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "wings",
        "I actually tear off the damaged Frame hardware",
        asset=original.id,
        heat=2,
    )["id"]
    source.confirm(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        "Actual donor confirms the performed transfer",
    )
    loan = rules.values(state(game), "doctor_loan", rules.Loan)[-1]
    assert state(game).sheets["2"].heat == 0
    assert not any(x.id == original.id for x in state(game).sheets["3"].assets)
    assert not next(x for x in state(game).sheets["2"].assets if x.id == loan.asset).damaged
    assert sum(x.family == "frame" for x in state(game).sheets["2"].assets) == 5
    next_period(ledger, game, monkeypatch)
    assert rules.values(state(game), "doctor_loan", rules.Loan)[-1].phase == "returned"
    assert not any(x.id == loan.asset for x in state(game).sheets["2"].assets)
    assert sum(x.family == "frame" for x in state(game).sheets["2"].assets) == 4
    assert (
        next(x for x in state(game).sheets["3"].assets if x.id == original.id).void == original.void
    )


def test_running_ragged_caller_marks_own_tag_and_actual_doctor_arrives(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m2 import TagState
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_doctor_procedures import ProcedureService
    from girlframe.services.m3_physical import PhysicalService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.RAGGED)
    # Actual owner proposals and Handler reviews establish both current bodies.
    physical = PhysicalService(ledger)
    from test_world import initial

    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    world = initial()
    WorldService(MissionService(ledger)).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    for viewer, cell in ((PLAYER, (0, 0)), (OTHER, (1, 0))):
        data = physical.preview(viewer)
        identity = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=current_ref(state(game), viewer.user_id),
                frame_instance=data["frame_instance"],
                girl_cell=cell,
                frame_cell=cell,
                mode="piloting",
                account="Actual original body position",
                facts_confirmed=True,
            ),
        )["id"]
        physical.decide(ADMIN, str(uuid4()), identity, 1, "accept", "Actual source position review")
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["3"].tags.append(TagState(id="caller-tag", label="Calls for help", giver=3))
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_tag", value)
    source = ProcedureService(game)
    identity = source.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "ragged",
        "The actual caller calls out for me",
    )["id"]
    source.confirm(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        "I actually called; Doctor arrives",
        tag="caller-tag",
    )
    doc = next(x for x in state(game).placements if x.actor == current_ref(state(game), 2))
    assert doc.girl_cell == doc.frame_cell == (1, 0)
    assert next(x for x in state(game).sheets["3"].tags if x.id == "caller-tag").marked


def test_here_for_support_real_roll_owned_protector_and_actual_damage_guard(
    ledger, tmp_path, monkeypatch
):
    import pytest
    from test_m2_game import answer, start

    from girlframe.engine.m3_battle import damage
    from girlframe.services.m3_actors import profiles

    source, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.SUPPORT)
    game.dice.faces = (4, 5)
    identity = start(game, play="doctor_support", target_actor=current_ref(state(game), 3))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "doctor_support_response", options=("protect",), fields={"bond": "yes"})
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        actual = state(game)
        actor = current_ref(actual, 2)
        with pytest.raises(ValueError, match="protector"):
            damage(
                actual,
                actor,
                actual.sheets["2"].assets[0].id,
                profiles(c, ledger.campaign_id),
                str(uuid4()),
                opponent=current_ref(actual, 1),
            )


def test_metal_angel_prevents_real_career_fallout_and_next_off_duty_care_recovers(
    ledger, tmp_path, monkeypatch
):
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_careers import end
    from girlframe.services.m3_doctor_care import CareService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.ANGEL)
    care = CareService(game)
    patient = current_ref(state(game), 3)
    identity = care.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        patient,
        "Actual ongoing life-saving care",
        angel=True,
    )["id"]
    care.confirm(
        OTHER, str(uuid4()), identity, state(game).revision, "Actual original patient confirms care"
    )
    with ledger.transaction() as c:
        actual = state(game)
        profile = c.execute(
            sa.select(t.characters.c.id, t.characters.c.revision).where(
                t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "3"
            )
        ).one()
        event = str(uuid4())
        changed = end(
            actual,
            patient,
            reason="death",
            source_event=event,
            account="Actual otherwise lethal source consequence",
            archive_id=str(uuid4()),
            profile_id=profile.id,
            profile_revision=profile.revision,
        )
        changed.sheets["3"].medical_state = "unconscious_injured"
        game.event(
            c, 3, str(uuid4()), "synthetic.actual_lethal_consequence", changed, event_id=event
        )
    assert not state(game).career_archives and "3" in state(game).sheets
    period = next_period(ledger, game, monkeypatch)
    assert care.get(OTHER, identity)["care"]["period"] == period
    for viewer in (PLAYER, OTHER):
        care.recover(
            viewer,
            str(uuid4()),
            identity,
            state(game).revision,
            "I confirm actual care throughout this Off-Duty",
        )
    assert care.get(OTHER, identity)["care"]["phase"] == "complete"
    assert state(game).sheets["3"].medical_state == "fit"


def test_adrenal_ends_actual_helplessness_and_replaces_death_before_archive(
    ledger, tmp_path, monkeypatch
):
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_actor_bonds import is_helpless
    from girlframe.engine.m3_careers import end
    from girlframe.services.m3_doctor_procedures import ProcedureService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.ADRENAL)
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].helpless_against = (3,)
        game.event(c, 1, str(uuid4()), "synthetic.actual_helplessness", actual)
    source = ProcedureService(game)
    source.adrenal(
        PLAYER, str(uuid4()), state(game).revision, "Actual Adrenal activation while Helpless"
    )
    assert not is_helpless(state(game), current_ref(state(game), 2))
    with ledger.transaction() as c:
        actual = state(game)
        actor = current_ref(actual, 2)
        profile = c.execute(
            sa.select(t.characters.c.id, t.characters.c.revision).where(
                t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
            )
        ).one()
        event = str(uuid4())
        changed = end(
            actual,
            actor,
            reason="death",
            source_event=event,
            account="Actual otherwise lethal consequence",
            archive_id=str(uuid4()),
            profile_id=profile.id,
            profile_revision=profile.revision,
        )
        game.event(
            c, 2, str(uuid4()), "synthetic.actual_lethal_consequence", changed, event_id=event
        )
    assert not state(game).career_archives and state(game).sheets["2"].obsolescence_marked == 2


def test_low_support_holds_for_real_handler_play_then_releases_original(
    ledger, tmp_path, monkeypatch
):
    from test_m2_game import start

    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService

    source, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.SUPPORT)
    game.dice.faces = (1, 2)
    identity = start(game, play="doctor_support", target_actor=current_ref(state(game), 3))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_handler")

    async def native():
        own = current(1, 997201)
        await own.response.defer(ephemeral=True)
        await open_choice(own, source, choice["id"])
        assert own.edit_original_response.call_args.kwargs["view"] is not None

    asyncio.run(native())
    grant = next(x for x in state(game).handler_plays if x.source_action == identity)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    handler = HandlerPlayService(ledger)
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        state(game).revision,
        "escalate",
        Effect(
            kind="escalate",
            account="Actual newly revealed danger reaches Doctor",
            detail="The original hiding place is exposed",
            stakes="Doctor is in more danger",
        ),
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_real_cadre_death_marks_eighth_box_and_creates_existing_compulsory_replacement(
    ledger, tmp_path, monkeypatch
):
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_careers import end
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_replacement import ReplacementService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].obsolescence_marked = 7
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_track", actual)
        patient = current_ref(actual, 3)
        profile = c.execute(
            sa.select(t.characters.c.id, t.characters.c.revision).where(
                t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "3"
            )
        ).one()
        event = str(uuid4())
        changed = end(
            actual,
            patient,
            reason="death",
            source_event=event,
            account="Actual unprevented Cadre death",
            archive_id=str(uuid4()),
            profile_id=profile.id,
            profile_revision=profile.revision,
        )
        game.event(c, 3, str(uuid4()), "synthetic.actual_cadre_death", changed, event_id=event)
    assert state(game).sheets["2"].frame_scrapped
    with ledger.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                t.m3["m3_required_work"].c.kind == "doctor_frame_replacement",
            )
        )
    assert (
        work
        and ReplacementService(MissionService(ledger)).get(PLAYER, work)["current_frame"]
        == rules.BOOK
    )


def test_nanobot_patient_can_decline_optional_unmark_and_caster_cannot_remove_locked_tag(
    ledger, tmp_path, monkeypatch
):
    from test_m2_game import answer, start

    from girlframe.engine.m2 import Obligation, TagState
    from girlframe.services.m3_doctor import effects

    _, game = doctor(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        actual = state(game)
        patient = actual.sheets["3"]
        patient.identities[0].marked = True
        patient.tags.append(
            TagState(
                id="actual-locked-tag", label="Existing restricted Tag", giver=2, observers=(2, 3)
            )
        )
        actual.obligations.append(
            Obligation(
                id="actual-lock",
                kind="tag_rejection_permission",
                owner=2,
                target=3,
                action="prior-actual-source",
                details={"tag": "actual-locked-tag", "target_character": patient.character_id},
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.existing_source_locked_tag", actual)
    assert "tag:actual-locked-tag" not in {
        x["id"] for x in effects(state(game), current_ref(state(game), 3), 2)
    }
    game.dice.faces = (4, 5)
    identity = start(game, play="nanobot_injection", target_actor=current_ref(state(game), 3))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "doctor_nanobot_benefits", options=("identity",))
    answer(game, OTHER, "doctor_patient")
    assert state(game).sheets["3"].identities[0].marked
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
