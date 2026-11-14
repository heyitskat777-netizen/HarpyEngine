"""Exact-cadre setup retained for a focused prerequisite check; no GM session mix.

Synthetic registry approvals and mock delivery, not production admission.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_creation import selected
from test_ledger import ADMIN, seed
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation_details import (
    InitialConditions,
)
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture
SEED = 202611130943
TRACE = []


def record(stage, **details):
    TRACE.append(dict(stage=stage, **details))
    print("SESSION_TRACE " + json.dumps(TRACE[-1], default=str))


def exact_setup(ledger, tmp_path, monkeypatch):
    specialized = True
    newgirl = True
    TRACE.clear()
    # Deliberately distinct roster, not a claim of random or exhaustive coverage.
    girls = ["AM", "CASUALTY", "NEWGIRL", "MOCKINGBIRD"]
    frames = ["PROJECT ANKOU", "DOCTORDOCTOR MK. II", "CHANGELING", "JANUS-B"]
    viewers = [GuildViewer(i, 200, True, False) for i in range(2, 6)]
    record(
        "deliberate_distinct_selection",
        scenario_id=SEED,
        characters=list(zip(range(2, 6), girls, frames, strict=False)),
    )
    ledger.policy = ledger.policy.model_copy(
        update={"owner_initial_conditions": InitialConditions()}
    )
    for viewer, girl, frame in zip(viewers, girls, frames, strict=False):
        seed(
            ledger,
            viewer,
            callsign=f"TEST_{viewer.user_id}",
            notes=f"PRIVATE_{viewer.user_id}",
            girl=girl,
            frame=frame,
        )
    ledger.join(ADMIN, "handler-join")
    handler = HandlerService(ledger)
    handler.appoint(ADMIN, "appoint", 0, 1)
    if newgirl:
        handler.mentor(
            ADMIN,
            str(uuid4()),
            handler.roster(ADMIN)["revision"],
            PilotRef(user_id=4, character_revision=1),
            PilotRef(user_id=3, character_revision=1),
        )
    bonds = BondService(ledger)
    bond_rows = {}
    for _i, viewer in enumerate(viewers):
        target = {2: viewers[1], 3: viewers[3], 4: viewers[1], 5: viewers[0]}[viewer.user_id]
        row = bonds.propose(
            viewer,
            str(uuid4()),
            1,
            1,
            BondProposal(
                target_id=target.user_id,
                prompt=0,
                context="Explicit simulated mutual connection",
            ),
        )
        bonds.decide(target, str(uuid4()), row["id"], 1, "accept")
        bond_rows[viewer.user_id] = row
    if newgirl:
        from girlframe.engine.shared_setup import CallsignChoice

        # Actual Handler assignment, followed by Mentor proposal and Newgirl
        # acceptance. No post-activation profile or dependency patch.
        shared = SharedSetupService(ledger)
        named = shared.propose(
            viewers[1],
            str(uuid4()),
            4,
            "callsign",
            shared.prepare(viewers[1], 4, "callsign"),
            CallsignChoice(callsign="TEST_NOVICE"),
        )
        shared.decide(viewers[2], str(uuid4()), named["id"], 1, "accept")
        record(
            "newgirl_mentor_and_owned_callsign",
            mentor=3,
            newgirl=4,
            callsign="TEST_NOVICE",
            authority="Handler assignment, Mentor proposal, Newgirl acceptance",
        )
    creation = CreationService(ledger)
    for viewer, girl, frame in zip(viewers, girls, frames, strict=False):
        cur = creation.get(viewer)
        data = selected(girl, frame)
        upd = {
            "shared_tokens": cur.draft.shared_tokens,
            "pair_source_token": cur.draft.pair_source_token,
        }
        if girl == "NEWGIRL":
            from girlframe.engine.cadre_history import PriorMission

            # Actual Newgirl-authored creation declaration for this synthetic
            # new Cadre: no earlier mission together, discussed with the group.
            upd["prior_missions"] = tuple(
                PriorMission(user_id=uid, character_revision=row["revision"], missions=0)
                for uid, row in creation.cadre(viewer).items()
            )
            upd["cadre_discussed"] = True
            record(
                "newgirl_cadre_history_declared",
                owner=viewer.user_id,
                prior_missions="zero for every current Cadre member",
                discussion="scripted participant discussion before this first mission",
            )
        data = data.model_copy(update=upd)
        creation.save(viewer, str(uuid4()), 0, 1, data, expected_pair_token=data.pair_source_token)
    rev = handler.roster(ADMIN)["revision"]
    handler.rank(
        ADMIN,
        str(uuid4()),
        rev,
        tuple(PilotRef(user_id=x.user_id, character_revision=1) for x in viewers),
    )
    handler.rulings(ADMIN, str(uuid4()), rev + 1, CreationRulings())
    review = CreationReviewService(ledger)
    for viewer in viewers:
        current = review.get(viewer)
        record(
            "onboarding_review",
            user=viewer.user_id,
            ready=current.sheet.ready_for_rules_review,
            issues=[x.code for x in current.sheet.issues],
        )
        assert current.sheet.ready_for_rules_review
        review.save(viewer, str(uuid4()), current.saved_revision, current.fingerprint)
    game = GameService(ledger, dice=Dice())
    with pytest.raises(WorkflowError, match="M2_REVIEW_PENDING") as exc:
        game.activate(viewers[0], str(uuid4()), review.get(viewers[0]).fingerprint)
    record("production_admission_blocked", error=str(exc.value))
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="not certification",
            ),
        }
    )
    for viewer in viewers:
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    record(
        "fixture_activation",
        sheets={uid: (s.girl, s.frame) for uid, s in state(game).sheets.items()},
    )

    from m3_policy_scenario import configure_m3_fixture
    from test_enforcer_requisitions import approved
    from test_world import initial

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_world import WorldService

    configure_m3_fixture(ledger)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=tuple(
            e["id"]
            for e in json.loads(Path("rules/registry.json").read_text())["entries"]
            if e["id"].startswith(
                (
                    "girl.am.",
                    "girl.casualty.",
                    "girl.newgirl.",
                    "girl.mockingbird.",
                    "frame.ankou.",
                    "frame.doctordoctor",
                    "frame.changeling.",
                    "frame.janus.",
                )
            )
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks", "strain"}}
            )
        }
    )
    record(
        "fixture_policy",
        description="TEST ONLY selected requested Girl/Frame rules; "
        "production admission is "
        "unsupported/subset/inventoried/pending. M2 "
        "release approval; M3 scenario approval and "
        "selected rule contracts copied from synthetic "
        "test fixture. Not certification or deployment "
        "approval.",
    )
    missions = MissionService(ledger)
    world = initial()
    WorldService(missions).initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )

    WorldService(missions)
    physical = PhysicalService(ledger)
    for viewer in viewers:
        v = physical.preview(viewer)
        proposal = physical.propose(
            viewer,
            str(uuid4()),
            v["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(v["actor"]),
                frame_instance=v["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame" if specialized else "piloting",
                account="Simulated owner states actual starting body and Frame location",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            1,
            "accept",
            "Simulated GM verifies starting placement",
        )
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in [*viewers, ADMIN]:
        game.join_scene(viewer, str(uuid4()), 900)

    class FourGateway(Gateway):
        async def actor(self, identity):
            return {v.user_id: v for v in [*viewers, ADMIN]}[identity]

    gateway = FourGateway()
    worker = GameWorker(game)

    def pass_all():
        for v in [*viewers, ADMIN]:
            for row in game.choices(v):
                if row["kind"] == "tag_window":
                    from girlframe.engine.m2 import ChoiceAnswer

                    game.respond(
                        v,
                        str(uuid4()),
                        row["id"],
                        row["revision"],
                        ChoiceAnswer(options=("pass",)),
                    )

    def play(viewer, name, faces=(4, 5), **kw):
        game.dice.faces = faces
        action = game.begin(
            viewer,
            str(uuid4()),
            900,
            state(game).sheets[str(viewer.user_id)].revision,
            PlayInput(
                play=name,
                heat=kw.pop("heat", 0),
                context="Scripted test dialogue: "
                + kw.pop("dialogue", "We must reach the relay together."),
                trigger_confirmed=True,
                **kw,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_all()
        if any(row["kind"] == "casualty_roll_push" for row in game.choices(viewer)):
            answer(game, viewer, "casualty_roll_push", options=("skip",))
            record("owner_declined_optional_push", owner=viewer.user_id)
        if any(row["kind"] == "mockingbird_risk" for row in game.choices(viewer)):
            # Actual Mockingbird owner deliberately declines the optional costly
            # replacement. Never skip the prompt or alter the rolled outcome.
            before_assets = state(game).sheets[str(viewer.user_id)].assets
            with ledger.engine.connect() as c:
                before_total = game.action(c, action)["data"]["result"]["total"]
            answer(game, viewer, "mockingbird_risk")
            with ledger.engine.connect() as c:
                resumed = game.action(c, action)
                assert resumed["data"]["risk_factor"]["state"] == "declined"
                assert resumed["data"]["result"]["total"] == before_total
            assert state(game).sheets[str(viewer.user_id)].assets == before_assets
            record(
                "owner_declined_optional_risk",
                owner=viewer.user_id,
                total=before_total,
                assets="unchanged",
                choice="Keep the rolled result without a Risk Factor cost",
            )
        return action

    return game, worker, gateway, viewers, play


def test_missing_body_fact_rejects_before_binding_and_owner_can_retry(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine import m3_newgirl_sex as rules
    from girlframe.engine.m3_actor_bonds import current_ref, depth
    from girlframe.services.m3_changeling import ChangelingService
    from girlframe.services.m3_newgirl_sex import NewgirlSexService

    game, worker, gateway, viewers, play = exact_setup(ledger, tmp_path, monkeypatch)
    am, casualty, newgirl, mockingbird = viewers
    service = NewgirlSexService(game)
    identity = service.invite(
        newgirl,
        str(uuid4()),
        900,
        (current_ref(state(game), 2),),
        state(game).revision,
        "Owned voluntary mechanical source",
    )["id"]
    service.confirm(
        am,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "AM independently confirms participation",
    )
    before = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="SOURCE_BODY_FACT_REQUIRED"):
        play(newgirl, "newgirl_sex", source_work=identity)
    assert state(game) == before
    assert game.dice.calls == calls
    assert rules.get(state(game), identity).phase == "accepted"
    assert rules.get(state(game), identity).action is None
    # Existing owner-authorized factual API remains available, with no invented
    # body, consent, replacement, or automatic answer to the pending source.
    ChangelingService(game).body_fact(
        am,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 2),
        "girl",
        "Simulated owner confirms original native Girl "
        "body from owner-proposed Handler-confirmed "
        "placement; no transformation occurred.",
    )
    action = play(newgirl, "newgirl_sex", source_work=identity)
    answer(game, newgirl, "newgirl_sex_ask", text="Do you respect me?")
    answer(game, am, "newgirl_sex_respect", options=("yes",), text="Independent affirmative answer")
    after = state(game)
    assert game.inspect(newgirl, action)["state"] == "complete"
    assert game.dice.calls == calls + 1
    assert (
        depth(after, current_ref(after, 4), current_ref(after, 2))
        == depth(before, current_ref(before, 4), current_ref(before, 2)) + 1
    )
    assert after.order.index(4) == before.order.index(4) - 1
    from girlframe.engine import m3_changeling as changing

    old_strings = {x.id for x in changing.records(before, changing.String)}
    fresh = [
        x
        for x in changing.records(after, changing.String)
        if x.id not in old_strings
        and x.origin == "deepen"
        and x.actor == current_ref(after, 4)
        and x.subject.actor == current_ref(after, 2)
    ]
    assert len(fresh) == 1
    assert fresh[0].spent_event is None
