"""A real city appearance and actual Moderate Punishments complete Low Void 3.2."""

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_pilot_fears import native
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m3_pilot_fears import APPEARANCE, cases
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_pilot_fears import FearsService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("addressed", (True, False), ids=("normalcy", "actual-moderate"))
def test_original_public_city_appearance_keeps_both_printed_outcomes(ledger, addressed):
    strain, game, _, period, _ = strain_source(ledger, 6, column=2)

    def select(track, severity, face, column):
        request = next(
            x for x in state(game).strain.requests if x.track == track and x.severity == severity
        )
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + request.id, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + request.id, request.id, 2, state(game).revision, column)
        return request.id + ":effect"

    effects = EffectService(strain)
    for track, severity, face, column, choice in (
        (
            "void",
            "high",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The Handler states the original risk.",
                revelation_play="reveal_near_disaster",
                revelation_channel=900,
            ),
        ),
        (
            "rebellion",
            "low",
            1,
            2,
            Choice(rule_id="strain.rebellion.low.1.2", account="Original choice."),
        ),
        (
            "budget",
            "low",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Shared quarters.", rooms=((2, 3),)),
        ),
    ):
        other = select(track, severity, face, column)
        effects.apply(ADMIN, "resolve-" + track, other, 1, state(game).revision, choice)

    work = select("void", "low", 3, 2)
    assert effects.get(ADMIN, work)["rule_id"] == APPEARANCE
    build, commit, _ = effect_form(ADMIN, effects, work)
    assert ("city0", "city0") in next(x for x in build({}) if x.key == "appearance_city").options
    values = dict(appearance_city=("city0",), account="The Cadre visits the city during a fair.")
    commit(ADMIN, "call-appearance", values)
    assert effects.get(ADMIN, work)["state"] == "pending"
    with pytest.raises(WorkflowError, match="actual public appearance"):
        FearsService(strain).act(
            PLAYER, "from-base", work, state(game).revision, "respond", "Arrived", channel=900
        )
    with ledger.transaction() as connection:
        canon = state(game)
        for viewer in (PLAYER, OTHER):
            canon = place(canon, viewer.user_id, mode="outside_frame", cell=(0, 4))
        game.event(connection, ADMIN.user_id, "city-places", "synthetic.city_positions", canon)

    native(ledger, PLAYER, 88700, action=("respond",), account="I welcome the fair visitors.")
    response = cases(state(game))[0].responses[0].event
    with pytest.raises(WorkflowError, match="Every original Girl"):
        FearsService(strain).act(
            ADMIN,
            "premature",
            work,
            state(game).revision,
            "addressed",
            "One person alone cannot complete the Cadre appearance.",
            evidence=response,
        )
    native(ledger, OTHER, 88710, action=("respond",), account="I sit on the public panel.")
    saved = state(game).strain.events
    cycle = CycleService(strain.periods)
    if addressed:
        native(
            ledger,
            ADMIN,
            88720,
            action=("addressed",),
            response=(response,),
            account="The public recognizes the team.",
        )
        assert state(game).strain.levels["budget"] == "low"
    else:
        native(
            ledger,
            ADMIN,
            88720,
            action=("discipline",),
            response=(response,),
            track=("budget",),
            account="The assembled public leaves angrier than before.",
        )
        assert state(game).strain.levels["budget"] == "high"
        with pytest.raises(WorkflowError, match="Resolve actual Strain"):
            activate(cycle, game, period)
        discipline = PunishmentService(ledger)
        for viewer in (PLAYER, OTHER):
            identity = f"{work}:moderate:{viewer.user_id}"
            assert discipline.get(ADMIN, identity)["required_severity"] == "moderate"
            source = discipline.propose_scene(
                ADMIN,
                f"scene-{viewer.user_id}",
                identity,
                1,
                state(game).revision,
                "Actual regulations briefing.",
            )
            for witness in (ADMIN, viewer):
                source = discipline.attest_scene(
                    witness,
                    f"attest-{identity}-{witness.user_id}",
                    identity,
                    source["revision"],
                    state(game).revision,
                )
            discipline.apply(
                ADMIN,
                f"apply-{viewer.user_id}",
                identity,
                source["revision"],
                state(game).revision,
                Details(kind="strict_regulations", regulation="Attend a daily review."),
            )
        assert {x.subject.entity for x in state(game).regulations} == {"2", "3"}
    assert state(game).strain.events == saved
    assert effects.get(ADMIN, work)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
