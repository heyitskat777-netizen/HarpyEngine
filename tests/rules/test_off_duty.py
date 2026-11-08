import pytest
from pydantic import ValidationError
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state

from girlframe.engine.m3_core import Recovery
from girlframe.engine.m3_off_duty import (
    Period,
    acknowledge_scene,
    activate,
    choose_scene,
    doctor_credit,
    finish,
    ordinary_roll,
    recovery,
)
from girlframe.engine.m3_punishments import Details, apply

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    return state(game)


def active(canon):
    return activate(
        Period(id="period-A", handler=1, pilots=canon.order), 1, pending_preparation=frozenset()
    )


@pytest.mark.parametrize(
    "actor,faces,total", [(2, (1, 1), 6), (2, (2, 2), 8), (2, (6, 6), 16), (3, (4, 4), 8)]
)
def test_off_duty_uses_status_not_heat_and_retains_one_roll(canon, actor, faces, total):
    canon.sheets[str(actor)].heat = 999
    period = active(canon)
    saved = ordinary_roll(period, 2, actor, canon, faces)
    assert saved.progress[str(actor)].roll.total == total
    assert not period.progress
    with pytest.raises(ValueError, match="saved roll"):
        ordinary_roll(saved, 3, actor, canon, (1, 1))
    restored = Period.model_validate_json(saved.model_dump_json())
    assert restored == saved
    with pytest.raises(ValueError, match="STALE"):
        ordinary_roll(restored, 2, actor, canon, faces)
    with pytest.raises(ValidationError):
        ordinary_roll(period, 2, actor, canon, (0, 7))


def test_preparation_void_observation_and_scrapped_frames_cannot_be_skipped(canon):
    from girlframe.engine.m2 import Obligation

    period = Period(id="period-A", handler=1, pilots=canon.order)
    with pytest.raises(ValueError, match="Strain"):
        activate(period, 1, pending_preparation=frozenset({"strain-start"}))
    with pytest.raises(ValueError, match="preparation"):
        ordinary_roll(period, 1, 2, canon, (4, 4))
    canon.obligations.append(
        Obligation(id="observation", kind="void_observation", owner=2, action="source-trigger")
    )
    with pytest.raises(ValueError, match="Void Observation"):
        ordinary_roll(active(canon), 2, 2, canon, (4, 4))
    canon.obligations.clear()
    canon.sheets["2"].frame_scrapped = True
    with pytest.raises(ValueError, match="replacement"):
        ordinary_roll(active(canon), 2, 2, canon, (4, 4))


@pytest.mark.parametrize("faces,kind", [((1, 1), "cell"), ((6, 6), "handler_office")])
def test_required_scenes_need_actual_other_participants_and_own_confirmation(canon, faces, kind):
    period = ordinary_roll(active(canon), 2, 2, canon, faces)
    with pytest.raises(ValueError, match="optional"):
        choose_scene(period, 3, 2, kind=None)
    for participants in ((2,), (2, 4), (1,)):
        with pytest.raises(ValueError):
            choose_scene(period, 3, 2, kind=kind, participants=participants, summary="A scene")
    period = choose_scene(period, 3, 2, kind=kind, participants=(2, 1), summary="Played scene")
    with pytest.raises(ValueError, match="on-screen"):
        recovery(period, 4, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset())
    with pytest.raises(ValueError, match="themselves"):
        acknowledge_scene(period, 4, 3, 2)
    period = acknowledge_scene(period, 4, 2, 2)
    with pytest.raises(ValueError, match="on-screen"):
        recovery(period, 5, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset())
    period = acknowledge_scene(period, 5, 1, 2)
    with pytest.raises(ValueError, match="mandatory effects"):
        recovery(
            period,
            6,
            2,
            canon.sheets["2"],
            Recovery(),
            pending_effects=frozenset({"punishment-on-screen"}),
        )
    saved, _ = recovery(period, 6, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset())
    with pytest.raises(ValueError, match="once"):
        recovery(saved, 7, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset())


def test_optional_routine_scene_requires_other_girls_but_can_be_declined(canon):
    period = ordinary_roll(active(canon), 2, 2, canon, (2, 2))
    with pytest.raises(ValueError, match="other Girls"):
        choose_scene(period, 3, 2, kind="barracks", participants=(2, 1), summary="Routine")
    selected = choose_scene(period, 3, 2, kind="barracks", participants=(2, 3), summary="Routine")
    assert selected.progress["2"].scene.participants == (2, 3)
    declined = choose_scene(period, 3, 2, kind=None)
    assert (
        recovery(declined, 4, 2, canon.sheets["2"], Recovery(), pending_effects=frozenset())[0]
        .progress["2"]
        .recovered
    )


def test_sedation_survives_restart_and_recovery_then_only_explicit_end_clears_it(canon):
    period = active(canon)
    canon = apply(
        canon,
        2,
        1,
        Details(kind="sedation", identities=("identity:0", "identity:1")),
        entity_id="sedation",
        off_duty=True,
        off_duty_period=period.id,
    ).state
    for actor, faces in ((2, (2, 2)), (3, (4, 4))):
        period = ordinary_roll(period, period.revision, actor, canon, faces)
        period = choose_scene(period, period.revision, actor, kind=None)
        if actor == 2:
            with pytest.raises(ValueError, match="Sedation"):
                recovery(
                    period,
                    period.revision,
                    actor,
                    canon.sheets[str(actor)],
                    Recovery(unmark_identity="identity:0"),
                    pending_effects=frozenset(),
                )
        period, canon.sheets[str(actor)] = recovery(
            period,
            period.revision,
            actor,
            canon.sheets[str(actor)],
            Recovery(),
            pending_effects=frozenset(),
        )
    period = Period.model_validate_json(period.model_dump_json())
    assert canon.sheets["2"].sedation_locked
    for work, scene, status in (
        (frozenset({"required"}), True, True),
        (frozenset(), False, True),
        (frozenset(), True, False),
    ):
        with pytest.raises(ValueError, match="ends only"):
            finish(
                period,
                period.revision,
                canon,
                pending_work=work,
                handler_scene_complete=scene,
                status_review_complete=status,
            )
    ended, updated = finish(
        period,
        period.revision,
        canon,
        pending_work=frozenset(),
        handler_scene_complete=True,
        status_review_complete=True,
    )
    assert ended.phase == "complete"
    assert updated.sheets["2"].sedation_locked == ()
    assert updated.sheets["2"].identities[0].marked
    assert canon.sheets["2"].sedation_locked  # Input and historical marks are untouched.
    canon.sheets["2"].sedation_period = "another-period"
    with pytest.raises(ValueError, match="legacy"):
        finish(
            period,
            period.revision,
            canon,
            pending_work=frozenset(),
            handler_scene_complete=True,
            status_review_complete=True,
        )


def test_doctor_credit_is_current_pilot_only_and_once_per_start(canon):
    canon.sheets["2"].frame = "DOCTORDOCTOR MK. II"
    period = Period(id="period-A", handler=1, pilots=canon.order)
    for recipient in (1, 2, 4):
        with pytest.raises(ValueError, match="another current"):
            doctor_credit(period, 1, 2, canon, recipient, "Their contribution")
    saved, updated = doctor_credit(period, 1, 2, canon, 3, "Another Pilot gets credit")
    assert updated.sheets["3"].permissions == 1 and canon.sheets["3"].permissions == 0
    with pytest.raises(ValueError, match="once"):
        doctor_credit(saved, 2, 2, updated, 3, "Again")
    declined, unchanged = doctor_credit(period, 1, 2, canon, None, "No credit-sharing trigger")
    assert unchanged == canon and declined.credit_recorded == (2,)
