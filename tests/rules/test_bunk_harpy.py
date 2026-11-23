"""Private saved High Void bunk draw and original authored notice."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_void_leave import native
from test_world import initial

from girlframe.discord_adapter.m3_strain_effects import DependentForm, open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_bunk_harpy import RULE, encounters
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot
from girlframe.services.inbox import InboxService
from girlframe.services.m3_bunk_harpy import BunkService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

HARPY = GuildViewer(4, 200, True, False)


class SecondGirl:
    def __init__(self):
        self.population_sizes = []

    def choose(self, size):
        self.population_sizes.append(size)
        return 1


@pytest.mark.parametrize("method", ("contact", "late"))
def test_high_void_bunk_keeps_draw_and_arrival_private_until_actual_notice(ledger, method):
    strain, game = ready(ledger, face=2)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            ),
        }
    )
    ledger.join(HARPY, "harpy-controller-joins")
    actor = ActorRef(kind="external_pilot", entity="bunk-harpy")
    entry = AdversaryPilot(
        id=actor.entity,
        name="Unlinked Harpy",
        kind="harpy",
        girl="HARPY",
        frame="HARPY",
        controller=HARPY.user_id,
        cell=(2, 0),
        assets=(),
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial().model_copy(update={"pilots": (entry,)})
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        # Keep High Void from dropping to Low at the printed check.
        canon.sheets["2"].assets[0].void = True
        game.event(c, 1, "bunk-positions", "synthetic.original_bunk_actors", canon)
    harpy = HarpyDefeatService(ledger, game)
    draft = harpy.propose_runtime(
        HARPY,
        "bunk-harpy-setup",
        state(game).revision,
        NativeHarpyFacts(
            actor=actor,
            linked=False,
            girl_cell=(0, 0),
            frame_cell=(2, 0),
            heat=0,
            body_incapacitated=False,
            frame_shutdown=False,
            custody="free",
            identities=(),
            tags=(),
            account="The Harpy's actual body is at the base. Her Frame is parked elsewhere.",
            facts_confirmed=True,
        ),
    )
    harpy.review_setup(
        ADMIN,
        "bunk-harpy-approved",
        draft["id"],
        state(game).revision,
        True,
        "Verified separate body and original Frame",
    )
    period = prepared(strain, game, high=frozenset({"void"}))
    selector = SecondGirl()
    effects = EffectService(strain, selector=selector)
    for track, face, column, choice in (
        ("rebellion", 1, 2, Choice(rule_id="strain.rebellion.low.1.2", account="Control slips.")),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", rooms=((2, 3),), account="Rooms reassigned."),
        ),
        ("void", 2, 2, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        assert (
            strain.roll(ADMIN, "bunk-die-" + track, request.id, 1, state(game).revision)["face"]
            == face
        )
        selected = strain.choose(
            ADMIN, "bunk-column-" + track, request.id, 2, state(game).revision, column
        )
        work = request.id + ":effect"
        if choice is not None:
            assert selected["rule_id"] == choice.rule_id
            effects.apply(ADMIN, "bunk-other-" + track, work, 1, state(game).revision, choice)
    assert selected["rule_id"] == RULE

    async def prepare_native():
        click = current(1, 40200)
        await click.response.defer(ephemeral=True)
        await open_effect(click, effects, work)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm)
        form.values.update(bunk_harpy=(actor.entity,), account="An unexpected bunk encounter.")
        submit = current(1, 40201)
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args

    revision = state(game).revision
    choice = Choice(rule_id=RULE, account="An unexpected bunk encounter.", target=actor.entity)
    asyncio.run(prepare_native())
    assert effects.apply(ADMIN, "40201", work, 1, revision, choice)["state"] == "pending"
    (case,) = encounters(state(game))
    assert (
        selector.population_sizes == [2]
        and case.girl.entity == "3"
        and case.rng_source == "test_injected"
    )
    assert effects.get(ADMIN, work)["awaiting_bunk_harpy"] and work not in {
        x.identity for x in InboxService(ledger).items(OTHER) if x.task == "m3_bunk_harpy"
    }
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Strain"):
        activate(cycle, game, period)
    service = BunkService(strain)
    with pytest.raises(WorkflowError, match="original audience"):
        service.get(ADMIN, work)
    native(
        ledger,
        HARPY,
        work,
        "m3_bunk_harpy",
        40210,
        choice=("appear",),
        account="PRIVATE_APPEARANCE",
    )
    assert service.get(OTHER, work)["appearance"] == "PRIVATE_APPEARANCE"
    assert effects.get(ADMIN, work)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
    with pytest.raises(WorkflowError, match="original audience"):
        service.get(ADMIN, work)
    with pytest.raises(WorkflowError, match="original audience"):
        service.get(PLAYER, work)
    with pytest.raises(WorkflowError, match="original performer"):
        service.respond(
            HARPY, "pretend-pilot-contact", work, state(game).revision, "contact", "Unauthorized"
        )
    controller = OTHER if method == "contact" else HARPY
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.respond(controller, "stale-disclosure", work, revision - 1, method, "Notice")
    ledger.safety(PLAYER, "pause-bunk", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(controller, "paused-disclosure", work, revision, method, "Notice")
    ledger.safety(PLAYER, "resume-bunk", ledger.status(PLAYER)["revision"], pause=False)
    ledger.engine.dispose()
    revision = state(game).revision
    native(
        ledger, controller, work, "m3_bunk_harpy", 40220, choice=(method,), account="ACTUAL_NOTICE"
    )
    assert (
        service.respond(controller, "40221", work, revision, method, "ACTUAL_NOTICE")["stage"]
        == method
    )
    notice = service.get(ADMIN, work)
    assert notice["method"] == method and notice["disclosure"] == "ACTUAL_NOTICE"
    assert not notice["harpy"] and bool(notice["girl"]) == (method == "contact")
    assert notice["appearance"] == "" and "PRIVATE_APPEARANCE" not in str(
        InboxService(ledger).items(ADMIN)
    )
    body = resolve(state(game), actor, ())
    assert body.cell == (0, 0) and body.frame_cell == (2, 0) and not body.inside_frame
