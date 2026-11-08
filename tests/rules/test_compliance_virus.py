"""Actual source-owned Compliance Virus acceptance traces."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcement_initiative import ready as enforcement_ready
from test_enforcer_requisitions import approved, buy
from test_handler_items import director
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_compliance_virus import open_purge
from girlframe.engine import m3_compliance_virus as rules
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_compliance_virus_state import (
    InfectedPerson,
    PainRestraint,
    PastLinkExposure,
    Purge,
    Strain,
)
from girlframe.engine.m3_enforcer_requisitions import VIRUS
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_compliance_virus import VirusService, prove_person, prove_strain
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_virus_exposure import ExposureService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch, *, self_frame=False, faces=(4, 5), unknown_host=False):
    game, worker, gateway = enforcement_ready(store, tmp_path, monkeypatch, faces)
    acquisition = approved(store, game, tmp_path, monkeypatch)
    buy(acquisition, VIRUS)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    if unknown_host:
        from girlframe.engine.m3_physical_state import Placement

        with store.transaction() as c:
            canon = state(game)
            own, other = current_ref(canon, 2), current_ref(canon, 3)
            proposed = str(uuid4())
            game.event(
                c,
                2,
                str(uuid4()),
                "synthetic.actual_existing_unknown_cockpit_proposal",
                canon,
                event_id=proposed,
            )
            reviewed = str(uuid4())
            canon.placements.append(
                Placement(
                    actor=own,
                    vessel_id="actual-existing-original-body",
                    frame_instance="initial:" + own.incarnation,
                    girl_cell=None,
                    frame_cell=None,
                    mode="inside_frame",
                    occupied_frame_owner=other,
                    occupied_frame_instance="initial:" + other.incarnation,
                    proposed_event=proposed,
                    source_event=reviewed,
                    account=(
                        "Actual owned original cockpit relation; "
                        "positions and other Pilot's link remain unknown"
                    ),
                )
            )
            game.event(
                c,
                1,
                str(uuid4()),
                "synthetic.actual_existing_unknown_cockpit_review",
                canon,
                event_id=reviewed,
            )
    else:
        service = PhysicalService(store)
        for viewer in (PLAYER, OTHER):
            data = service.preview(viewer)
            proposal = InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting" if self_frame or viewer == OTHER else "outside_frame",
                account="Actual original prior physical facts",
                facts_confirmed=True,
            )
            work = service.propose(viewer, str(uuid4()), data["game_revision"], proposal)["id"]
            service.decide(
                ADMIN,
                str(uuid4()),
                work,
                1,
                "accept",
                "Actual source review of original same-cell physical facts",
            )
        own, other = current_ref(state(game), 2), current_ref(state(game), 3)
        if not self_frame:
            # Existing real same-cell original rescue pose, not a Virus-granted transport.
            with store.transaction() as c:
                event = str(uuid4())
                changed = physical.rescue_to_cockpit(
                    state(game),
                    profiles(c, store.campaign_id),
                    own,
                    other,
                    event,
                    "Actual earlier original rescue into existing available Frame",
                )
                game.event(
                    c, 3, str(uuid4()), "synthetic.actual_prior_rescue", changed, event_id=event
                )
    virus = VirusService(game)
    preview = virus.preview(PLAYER, 900, own)
    from girlframe.engine.m3_compliance_virus_state import FrameRef

    infection = virus.infect(
        PLAYER,
        str(uuid4()),
        900,
        own,
        FrameRef.model_validate(preview["cockpit"]),
        preview["source_sha256"],
        "Actual original cockpit infection",
    )["id"]
    return game, worker, gateway, virus, own, other, infection


def _begin(game, worker, gateway, virus, *args):
    result = virus.begin_purge(*args)
    before = state(game)
    value = rules.record(before, Purge, result["id"])
    assert value.phase == "queued" and value.effect_event is None and value.role_case is None
    strain = rules.record(before, Strain, value.strain)
    assert strain.purged_event is None
    tick(worker, gateway, 3)
    return result


def change_case(service, viewer, case, **kwargs):
    data = service.get(viewer, case)
    return service.change(viewer, str(uuid4()), case, data["revision"], **kwargs)


def punish(game, purge, *, self_case=False):
    value = rules.record(state(game), Purge, purge)
    service = RolePunishmentService(game)
    details = Details(kind="stimulant_injection")
    change_case(
        service,
        ADMIN,
        value.role_case,
        instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
    )
    change_case(
        service,
        PLAYER,
        value.role_case,
        scene="Actual original source instruction and real injection",
    )
    if not self_case:
        change_case(service, OTHER, value.role_case, attest=True)
    change_case(
        service,
        PLAYER,
        value.role_case,
        execute=True,
        account="Actual instructed source Stimulant Injection performed",
    )


def test_actual_owned_cockpit_infection_and_real_remote_fixed11_punishment_without_rng(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, other, infection = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    with ledger.engine.connect() as c:
        prove_strain(c, game, before, infection)
        person = next(x for x in rules.records(before, InfectedPerson) if x.actor == other)
        assert prove_person(c, game, before, person.id) == person
    old_heat = before.sheets["3"].heat
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        infection,
        "frame",
        "Actual remote source pain purge",
    )["id"]
    during = state(game)
    assert game.dice.calls == 0
    assert is_helpless(during, other, own)
    assert rules.record(during, Purge, purge).role_case
    assert rules.records(during, PainRestraint)[-1].active
    assert during.enforcer_grasps == before.enforcer_grasps
    assert during.placements == before.placements
    punish(game, purge)
    after = state(game)
    assert rules.record(after, Purge, purge).phase == "complete"
    assert after.sheets["3"].heat == old_heat + 7
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert is_helpless(after, other, own) and not rules.records(after, PainRestraint)[-1].active
    assert rules.record(after, Strain, infection).purged_event
    assert rules.record(after, InfectedPerson, person.id).purged_event is None
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 0


def test_actual_self_frame_purge_has_real_self_punishment_no_self_helpless_or_fake_foe(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, _, infection = ready(
        ledger, tmp_path, monkeypatch, self_frame=True
    )
    before = state(game)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        infection,
        "frame",
        "Actual own Frame purge and printed own pain",
    )["id"]
    during = state(game)
    case = during.role_punishments[-1]
    assert case.executor == case.subject == own
    assert not is_helpless(during, own, own)
    assert during.helpless_conditions == before.helpless_conditions
    assert rules.records(during, PainRestraint)[-1].active
    punish(game, purge, self_case=True)
    after = state(game)
    assert rules.record(after, Purge, purge).phase == "complete"
    assert after.sheets["2"].heat == before.sheets["2"].heat + 7
    assert after.helpless_conditions == before.helpless_conditions
    assert not rules.records(after, PainRestraint)[-1].active and game.dice.calls == 0


def test_real_touch_review_and_one_shot_order_preserve_status_and_actual_human_replies(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, other, infection = ready(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = tuple(reversed(canon.order))
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_status", canon)
    initial = state(game)
    person = next(x for x in rules.records(initial, InfectedPerson) if x.actor == other)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual original touch purge",
    )["id"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        virus.review_contact(
            OTHER,
            str(uuid4()),
            purge,
            virus.get(PLAYER, purge)["revision"],
            True,
            "Cannot choose as another actual human",
        )
    assert state(game).model_dump_json() == before
    virus.review_contact(
        ADMIN,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual source touching confirmed",
    )
    data = virus.get(PLAYER, purge)
    key = str(uuid4())
    args = (
        PLAYER,
        key,
        purge,
        data["revision"],
        "Actual direct order despite lower printed Status",
    )
    issued = virus.issue_order(*args)
    assert virus.issue_order(*args) == issued
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    tick(worker, gateway, 4)
    after = state(game)
    assert rules.record(after, Purge, purge).phase == "complete"
    assert after.order == initial.order
    assert rules.record(after, Strain, infection).purged_event is None
    assert rules.record(after, InfectedPerson, person.id).purged_event
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete" and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert len([x for x in game.choices(OTHER) if x["kind"] == "order_response"]) == 0
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_responses"])) == 1


def test_real_lower_status_virus_order_allows_only_original_pc_disobey_one_roll(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, other, _ = ready(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_status", canon)
    person = next(x for x in rules.records(state(game), InfectedPerson) if x.actor == other)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual source touching",
    )["id"]
    virus.review_contact(
        ADMIN,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual touched original Girl",
    )
    issued = virus.issue_order(
        PLAYER, str(uuid4()), purge, virus.get(PLAYER, purge)["revision"], "One actual direct order"
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("disobey",))
    canon = state(game)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        canon.sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            parent=issued["action_id"],
            order_id=issued["order_id"],
            trigger_confirmed=True,
            context="Actual original refusal",
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=1, text="Actual refusal Tag")
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 4)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    assert state(game).order == (3, 2) and game.dice.calls == 1
    assert rules.record(state(game), Purge, purge).phase == "complete"


def handler_exposure(game, virus, own, infection, *, complete=True):
    ref = director(game)
    casts = CastService(ActorService(MissionService(game.store)))
    judge = ActorRef(kind="npc", entity="director")
    for viewer, role in ((ADMIN, ref), (OTHER, judge)):
        data = casts.view(viewer, 900)
        casts.change(
            viewer, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", role
        )
    data = casts.view(OTHER, 900)
    casts.change(
        OTHER, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "adjudicate", judge
    )
    with game.store.engine.connect() as c:
        history = t.m2["m2_state_history"]
        prior = c.scalar(
            sa.select(history.c.event_id)
            .where(history.c.campaign_id == game.store.campaign_id)
            .order_by(history.c.revision.desc())
            .limit(1)
        )
    exposure = ExposureService(game)
    work = exposure.propose(
        ADMIN,
        str(uuid4()),
        900,
        ref,
        infection,
        prior,
        "Actual prior source episode: this original Girl linked the already infected Frame",
    )["id"]
    if not complete:
        return ref, None, work
    exposure.decide(
        OTHER,
        str(uuid4()),
        work,
        1,
        True,
        "Actual authenticated original Frame owner's factual confirmation",
    )
    exposure.decide(
        OTHER,
        str(uuid4()),
        work,
        2,
        True,
        "Actual frozen Director factual review; no current control granted",
    )
    canon = state(game)
    person = next(x for x in rules.records(canon, InfectedPerson) if x.actor.kind == "handler")
    return ref, person, work


@pytest.mark.parametrize("faces", [(1, 1), (4, 5), (6, 6)])
def test_actual_handler_girl_exposure_and_disobey_use_real_heat_tags_no_rank_or_proxy(
    ledger, tmp_path, monkeypatch, faces
):
    game, worker, gateway, virus, own, _, infection = ready(
        ledger, tmp_path, monkeypatch, faces=faces
    )
    before_exposure = state(game)
    ref, person, exposure = handler_exposure(game, virus, own, infection)
    after_exposure = state(game)
    assert after_exposure.placements == before_exposure.placements
    assert after_exposure.handler_heat == before_exposure.handler_heat
    assert "1" not in after_exposure.sheets
    with ledger.engine.connect() as c:
        assert prove_person(c, game, after_exposure, person.id) == person
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual touching of original HandlerGirl",
    )["id"]
    virus.review_contact(
        OTHER,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual source Director confirms touching facts",
    )
    issued = virus.issue_order(
        PLAYER,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        "Actual source one-shot order",
    )
    tick(worker, gateway, 3)
    answer(game, ADMIN, "order_response", options=("disobey",))
    service = ActorPlayService(game)
    preview = service.preview(ADMIN, 900, ref)
    child = service.begin(
        ADMIN,
        str(uuid4()),
        900,
        ref,
        preview["actor"]["source_sha256"],
        ActorRef.model_validate(preview["adjudicator"]["ref"]),
        preview["cast_revision"],
        PlayInput(
            play="disobey_orders",
            parent=issued["action_id"],
            order_id=issued["order_id"],
            trigger_confirmed=True,
            context="Actual original HandlerGirl refusal",
            heat=0,
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if faces == (4, 5):
        answer(
            game,
            ADMIN,
            "virus_disobey_outcome",
            options=("tag_heat",),
            number=1,
            text="Actual original Girl refusal",
        )
    elif faces == (6, 6):
        answer(game, ADMIN, "virus_disobey_outcome", flag=True)
    answer(game, OTHER, "virus_disobey_discovery", flag=False)
    tick(worker, gateway, 4)
    after = state(game)
    assert "1" not in after.sheets and after.order == after_exposure.order
    assert after.handler_heat == after_exposure.handler_heat + (
        1 if faces == (4, 5) else 2 if faces == (6, 6) else 0
    )
    assert game.inspect(ADMIN, child)["result"]["status_change"] is None
    assert game.inspect(ADMIN, issued["action_id"])["state"] == "complete"
    assert rules.record(after, Purge, purge).phase == "complete" and game.dice.calls == 1
    assert after.placements == after_exposure.placements
    assert rules.record(after, PastLinkExposure, exposure).phase == "approved"


def test_native_real_contact_review_uses_dropdown_owned_judge_and_pause(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, other, _ = ready(ledger, tmp_path, monkeypatch)
    person = next(x for x in rules.records(state(game), InfectedPerson) if x.actor == other)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual original source touch",
    )["id"]

    async def submit():
        interaction = current(1, 88301)
        await interaction.response.defer(ephemeral=True)
        await open_purge(interaction, virus, purge)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(3))
        form.values.update(confirmed=("yes",), account="Actual original touching fact")
        await form.confirm.callback(current(1, 88302))
        assert form.completed

    asyncio.run(submit())
    assert rules.record(state(game), Purge, purge).phase == "order"
    ledger.safety(OTHER, "pause-virus", ledger.status(OTHER)["revision"], pause=True)
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        virus.issue_order(
            PLAYER,
            str(uuid4()),
            purge,
            virus.get(PLAYER, purge)["revision"],
            "No mutation while paused",
        )
    assert state(game).model_dump_json() == snapshot and game.dice.calls == 0


def test_true_retained_harpy_frame_transmission_keeps_original_strain_no_proxy_and_orders_exemption(
    ledger, tmp_path, monkeypatch
):
    from test_retained_tag_permissions import reborn_with_lock

    from girlframe.engine.m3_compliance_virus_state import FrameRef
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_physical_state import Placement

    sources = {}

    def configure(game):
        acquisition = approved(ledger, game, tmp_path, monkeypatch)
        with ledger.transaction() as c:
            canon = state(game)
            canon.sheets["2"].permissions = 4
            canon.sheets["3"].permissions = 4
            game.event(c, 1, str(uuid4()), "synthetic.actual_prior_earned_permissions", canon)
        buy(acquisition, VIRUS)
        data = acquisition.acquisition_view(OTHER, "frame_grafting")
        acquisition.buy_rule(
            OTHER,
            str(uuid4()),
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            "frame_grafting",
            VIRUS,
            "Actual acquired donor rule on this original Frame",
        )
        # An actual existing guest cockpit fact has two distinct original human sources.
        with ledger.transaction() as c:
            canon = state(game)
            guest, host = current_ref(canon, 3), current_ref(canon, 2)
            proposal = str(uuid4())
            game.event(
                c,
                3,
                str(uuid4()),
                "synthetic.actual_prior_guest_facts_proposed",
                canon,
                event_id=proposal,
            )
            review = str(uuid4())
            canon.placements.append(
                Placement(
                    actor=guest,
                    vessel_id="actual-original-guest-body",
                    frame_instance="initial:" + guest.incarnation,
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    mode="inside_frame",
                    occupied_frame_owner=host,
                    occupied_frame_instance="initial:" + host.incarnation,
                    proposed_event=proposal,
                    source_event=review,
                    account=(
                        "Actual earlier original guest in this Frame; no current control inferred"
                    ),
                )
            )
            game.event(
                c,
                1,
                str(uuid4()),
                "synthetic.actual_prior_guest_facts_reviewed",
                canon,
                event_id=review,
            )
        virus = VirusService(game)
        preview = virus.preview(OTHER, 900, guest)
        sources["strain"] = virus.infect(
            OTHER,
            str(uuid4()),
            900,
            guest,
            FrameRef.model_validate(preview["cockpit"]),
            preview["source_sha256"],
            "Actual original guest infects the occupied existing Frame",
        )["id"]

    game, worker, gateway, ref, _, _ = reborn_with_lock(
        ledger, frame="THE ENFORCER", configure=configure, retained_plays=(VIRUS,)
    )
    # Same physical Frame, actual new Harpy actor: origin binding is proved by real birth.
    canon = state(game)
    strain = rules.record(canon, Strain, sources["strain"])
    assert strain.target.owner.kind == "pilot" and rules.frame_actor(canon, strain.target) == ref
    person = next(
        x for x in rules.records(canon, InfectedPerson) if x.actor == ref and x.strain == strain.id
    )
    with ledger.engine.connect() as c:
        assert prove_person(c, game, canon, person.id) == person
    creator = current_ref(canon, 3)
    virus = VirusService(game)
    calls = game.dice.calls
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        OTHER,
        str(uuid4()),
        900,
        creator,
        person.id,
        "girl",
        "Actual touch of actual reborn Harpy",
    )["id"]
    virus.review_contact(
        ADMIN,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual touching confirmed",
    )
    issued = virus.issue_order(
        OTHER,
        str(uuid4()),
        purge,
        virus.get(OTHER, purge)["revision"],
        "Actual words cannot compel a Harpy",
    )
    assert issued["immune"] and "action_id" not in issued
    assert rules.record(state(game), Purge, purge).phase == "complete"
    assert game.dice.calls == calls and "2" not in state(game).sheets
    assert harpy(state(game), ref).heat == harpy(canon, ref).heat
    tick(worker, gateway, 5)
    # Owner's real remote Frame purge still inflicts fixed11/typed Harpy Helpless.
    frame_purge = _begin(
        game,
        worker,
        gateway,
        virus,
        OTHER,
        str(uuid4()),
        900,
        creator,
        strain.id,
        "frame",
        "Actual remote source Frame pain",
    )["id"]
    actual = state(game)
    assert is_helpless(actual, ref, creator)
    assert rules.record(actual, Purge, frame_purge).target == ref
    assert game.dice.calls == calls and "2" not in actual.sheets


def test_actual_girl_self_contact_purge_grants_no_order_or_rank_bonus(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, _, _ = ready(ledger, tmp_path, monkeypatch, self_frame=True)
    before = state(game)
    person = next(x for x in rules.records(before, InfectedPerson) if x.actor == own)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual self-contact purge",
    )["id"]
    virus.review_contact(
        ADMIN,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual original self-contact occurred",
    )
    after = state(game)
    value = rules.record(after, Purge, purge)
    assert value.phase == "complete" and value.order_action is None and not value.order_text
    assert after.order == before.order and after.sheets == before.sheets
    assert rules.record(after, InfectedPerson, person.id).purged_event
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_orders"])) == 0


def test_saved_actual_source_read_only_after_release_withdrawal_and_no_factual_time_rewrite(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, other, infection = ready(ledger, tmp_path, monkeypatch)
    ref, person, _ = handler_exposure(game, virus, own, infection)
    exposure = ExposureService(game)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        exposure.propose(
            ADMIN,
            str(uuid4()),
            900,
            ref,
            infection,
            "not-an-actual-source-event",
            "No invented past link",
        )
    assert state(game).model_dump_json() == before
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual pending original touch source",
    )["id"]
    original = state(game).model_dump_json()
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    saved = virus.get(ADMIN, purge)
    assert saved["id"] == purge and saved["can_act"] is False
    with pytest.raises(WorkflowError):
        virus.review_contact(
            OTHER,
            str(uuid4()),
            purge,
            saved["revision"],
            True,
            "Cannot write under withdrawn release",
        )
    assert state(game).model_dump_json() == original


@pytest.mark.parametrize("failure", ["snapshot", "lock", "publish"])
def test_actual_operation_lock_failure_prevents_purge_and_safe_cancel_restores_without_rng(
    ledger, tmp_path, monkeypatch, failure
):
    game, worker, gateway, virus, own, _, infection = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    gateway.fail = failure
    queued = virus.begin_purge(
        PLAYER, str(uuid4()), 900, own, infection, "frame", "Actual confirmed remote purge request"
    )
    tick(worker, gateway, 3)
    actual = state(game)
    assert rules.record(actual, Purge, queued["id"]).phase == "queued"
    assert rules.record(actual, Strain, infection).purged_event is None
    assert (
        actual.sheets == before.sheets and actual.helpless_conditions == before.helpless_conditions
    )
    assert not actual.role_punishments and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "review"
    key = str(uuid4())
    result = game.abort(ADMIN, key, queued["action_id"])
    assert game.abort(ADMIN, key, queued["action_id"]) == result
    gateway.fail = None
    tick(worker, gateway, 5)
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    ended = rules.record(state(game), Purge, queued["id"])
    assert ended.end_reason == "cancelled_before_effect" and ended.effect_event is None
    assert rules.record(state(game), Strain, infection).purged_event is None
    assert game.dice.calls == 0


def test_actual_purge_restart_replay_keeps_one_fixed11_and_owned_case_until_real_completion(
    ledger, tmp_path, monkeypatch
):
    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.services.m2_game import GameService

    game, worker, gateway, virus, own, _, infection = ready(ledger, tmp_path, monkeypatch)
    key = str(uuid4())
    args = (PLAYER, key, 900, own, infection, "frame", "Actual confirmed source request")
    queued = virus.begin_purge(*args)
    assert virus.begin_purge(*args) == queued
    restarted = GameService(ledger, dice=game.dice)
    resumed_worker = GameWorker(restarted)
    tick(resumed_worker, gateway, 3)
    during = state(restarted)
    value = rules.record(during, Purge, queued["id"])
    assert value.phase == "punishment" and len(during.role_punishments) == 1
    assert restarted.inspect(PLAYER, queued["action_id"])["receipt"] is None
    before = during.model_dump_json()
    with pytest.raises(WorkflowError):
        restarted.abort(ADMIN, str(uuid4()), queued["action_id"])
    assert state(restarted).model_dump_json() == before
    punish(restarted, queued["id"])
    tick(resumed_worker, gateway, 5)
    assert rules.record(state(restarted), Purge, queued["id"]).phase == "complete"
    assert len(state(restarted).role_punishments) == 1 and game.dice.calls == 0
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original


def test_unknown_link_is_never_assumed_vacant_real_owner_and_judge_facts_precede_fixed11(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_virus_operations import OperationService

    game, worker, gateway, virus, own, other, infection = ready(
        ledger, tmp_path, monkeypatch, unknown_host=True
    )
    before = state(game)
    queued = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        infection,
        "frame",
        "Actual remote Frame purge, original link unknown",
    )
    value = rules.record(state(game), Purge, queued["id"])
    assert value.phase == "vacancy_proposal" and value.target is None
    assert value.role_case is None and value.effect_event is None
    assert rules.record(state(game), Strain, infection).purged_event is None
    ops = OperationService(game)
    ops.occupancy(
        OTHER,
        str(uuid4()),
        value.id,
        value.revision,
        "owner_linked",
        "Actual original Frame owner confirms her own already-existing link",
    )
    review = rules.record(state(game), Purge, value.id)
    assert review.phase == "vacancy_review" and review.target is None
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        ops.occupancy(
            PLAYER,
            str(uuid4()),
            value.id,
            review.revision,
            "confirm",
            "Cannot impersonate original judge",
        )
    assert state(game).model_dump_json() == snapshot
    ops.occupancy(
        ADMIN,
        str(uuid4()),
        value.id,
        review.revision,
        "confirm",
        "Actual frozen judge reviews real original link; no coordinates assigned",
    )
    after = state(game)
    applied = rules.record(after, Purge, value.id)
    assert applied.phase == "punishment" and applied.target == other
    assert is_helpless(after, other, own) and game.dice.calls == 0
    assert after.sheets == before.sheets
    place = next(x for x in after.placements if x.actor == other)
    assert place.mode == "piloting" and place.girl_cell is None and place.frame_cell is None
    assert len(after.placements) == len(before.placements) + 1
    assert next(x for x in after.placements if x.actor == own) == before.placements[0]


def test_reviewed_no_linked_pilot_cures_actual_frame_without_inventing_pain_role_or_resources(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_virus_operations import OperationService

    game, worker, gateway, virus, own, other, infection = ready(ledger, tmp_path, monkeypatch)
    physical_service = PhysicalService(ledger)
    for viewer, actor in ((PLAYER, own), (OTHER, other)):
        data = physical_service.preview(viewer)
        physical_service.operate(
            viewer,
            str(uuid4()),
            data["game_revision"],
            CockpitAction(
                actor=actor,
                operation="exit",
                expected_position=data["position_sha256"],
                account="Actual original body leaves its current cockpit",
                confirmed=True,
            ),
        )
    before = state(game)
    queued = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        infection,
        "frame",
        "Actual no-linked-Pilot source purge",
    )
    value = rules.record(state(game), Purge, queued["id"])
    ops = OperationService(game)
    ops.occupancy(
        OTHER,
        str(uuid4()),
        value.id,
        value.revision,
        "vacant",
        "Actual original Frame owner confirms there is no linked Pilot",
    )
    value = rules.record(state(game), Purge, value.id)
    ops.occupancy(
        ADMIN,
        str(uuid4()),
        value.id,
        value.revision,
        "confirm",
        "Actual frozen judge confirms no linked Pilot",
    )
    tick(worker, gateway, 5)
    after = state(game)
    value = rules.record(after, Purge, value.id)
    assert value.phase == "complete" and value.target is None and value.role_case is None
    assert rules.record(after, Strain, infection).purged_event
    assert after.sheets == before.sheets and after.placements == before.placements
    assert after.helpless_conditions == before.helpless_conditions and not rules.records(
        after, PainRestraint
    )
    assert not after.role_punishments and game.dice.calls == 0


def test_actual_handler_girl_discovery_waits_for_real_director_punishment_before_root_release(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, virus, own, _, infection = ready(
        ledger, tmp_path, monkeypatch, faces=(6, 6)
    )
    ref, person, _ = handler_exposure(game, virus, own, infection)
    purge = _begin(
        game,
        worker,
        gateway,
        virus,
        PLAYER,
        str(uuid4()),
        900,
        own,
        person.id,
        "girl",
        "Actual HandlerGirl source touch",
    )["id"]
    virus.review_contact(
        OTHER,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        True,
        "Actual source Director confirms original contact",
    )
    issued = virus.issue_order(
        PLAYER,
        str(uuid4()),
        purge,
        virus.get(PLAYER, purge)["revision"],
        "Actual original one-shot order",
    )
    answer(game, ADMIN, "order_response", options=("disobey",))
    actor_service = ActorPlayService(game)
    data = actor_service.preview(ADMIN, 900, ref)
    child = actor_service.begin(
        ADMIN,
        str(uuid4()),
        900,
        ref,
        data["actor"]["source_sha256"],
        ActorRef.model_validate(data["adjudicator"]["ref"]),
        data["cast_revision"],
        PlayInput(
            play="disobey_orders",
            parent=issued["action_id"],
            order_id=issued["order_id"],
            heat=0,
            trigger_confirmed=True,
            context="Actual original immediate refusal",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "virus_disobey_outcome", flag=True)
    answer(game, OTHER, "virus_disobey_discovery", flag=True)
    value = rules.record(state(game), Purge, purge)
    assert value.phase == "punishment" and value.role_case
    case = state(game).role_punishments[-1]
    assert case.executor == ActorRef(kind="npc", entity="director")
    assert case.subject.kind == "handler" and case.subject_controller == 1
    assert game.inspect(ADMIN, child)["state"] != "complete"
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
    service = RolePunishmentService(game)
    details = Details(kind="quality_time", tag="Actual original Director-instructed Tag")
    change_case(
        service,
        OTHER,
        case.id,
        instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
    )
    change_case(service, OTHER, case.id, scene="Actual original Director and HandlerGirl scene")
    change_case(service, ADMIN, case.id, attest=True)
    change_case(
        service,
        OTHER,
        case.id,
        execute=True,
        account="Actual original Director performs instructed Quality Time",
    )
    tick(worker, gateway, 5)
    after = state(game)
    assert "1" not in after.sheets and after.handler_tags[-1].giver_actor == case.executor
    assert game.inspect(ADMIN, child)["state"] == "complete"
    assert game.inspect(ADMIN, issued["action_id"])["state"] == "complete"
    assert rules.record(after, Purge, purge).phase == "complete"
    assert game.dice.calls == 1
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original


def test_actual_public_hub_and_pending_source_inbox_use_owned_native_dropdowns(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_compliance_virus import open_virus_hub
    from girlframe.discord_adapter.m3_punishments import Picker
    from girlframe.services.inbox import InboxService

    game, worker, gateway, virus, own, _, infection = ready(ledger, tmp_path, monkeypatch)

    async def hub():
        caller = current(2, 88350)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_virus_hub(caller, game)
        picker = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        assert not await picker.interaction_check(current(3))
        follow = current(2, 88351)
        follow.channel_id = 900
        await follow.response.defer(ephemeral=True)
        await picker.open_item(follow, "virus:" + own.token)
        form = follow.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            operation=("frame:" + infection,), account="Actual source request from owned dropdown"
        )
        await form.confirm.callback(current(2, 88352))
        assert form.completed

    asyncio.run(hub())
    value = rules.records(state(game), Purge)[-1]
    assert value.phase == "queued"
    tick(worker, gateway, 3)
    items = InboxService(ledger).items(ADMIN)
    actual = [
        x
        for x in items
        if x.task == "m2_choice" and game.decision(ADMIN, x.identity).get("virus_purge")
    ]
    assert len(actual) == 1 and actual[0].incoming
    assert not any(x.task == "m3_work" and x.identity == value.id for x in items)


def test_pending_past_link_inbox_preserves_actual_chooser_and_outgoing_read_only(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.inbox import InboxService

    game, _, _, virus, own, _, infection = ready(ledger, tmp_path, monkeypatch)
    _, _, identity = handler_exposure(game, virus, own, infection, complete=False)
    exposure = ExposureService(game)
    assert not exposure.get(ADMIN, identity)["can_act"]
    assert exposure.get(OTHER, identity)["can_act"]
    incoming = [x for x in InboxService(ledger).items(OTHER) if x.identity == identity]
    outgoing = [x for x in InboxService(ledger).items(ADMIN) if x.identity == identity]
    assert len(incoming) == len(outgoing) == 1
    assert incoming[0].task == outgoing[0].task == "m3_virus_exposure"
    assert incoming[0].incoming and not outgoing[0].incoming
    assert not any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
