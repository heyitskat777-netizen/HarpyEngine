"""Distinct four-character roster: eight basic Plays, scripted GM interference, Strain.

Synthetic policy approvals and mock delivery only; not live Discord/AI Director.
Deliberate cast variation; specialized coverage only in explicitly selected variants.
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
    GirlDetails,
    InitialConditions,
    StandardChoice,
)
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
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


def test_distinct_roster_eight_basic_plays_and_strain(ledger, tmp_path, monkeypatch):
    _session_mix(ledger, tmp_path, monkeypatch, specialized=False)


def test_ten_play_mix_with_native_stim_and_prince_and_strain(ledger, tmp_path, monkeypatch):
    """r269: two specialized Plays added; same roster, not new all-type coverage."""
    _session_mix(ledger, tmp_path, monkeypatch, specialized=True)


def test_ten_play_mix_high_dose_mid_prince_and_strain(ledger, tmp_path, monkeypatch):
    """r270: new high Dose and mid Prince branches, same roster, not all-type."""
    _session_mix(ledger, tmp_path, monkeypatch, specialized=True, advanced=True)


def test_ten_play_newgirl_wyvern_mix_and_strain(ledger, tmp_path, monkeypatch):
    """r271: genuine Newgirl/Wyvern onboarding joins existing three-player core."""
    _session_mix(ledger, tmp_path, monkeypatch, specialized=True, advanced=True, newgirl=True)


def _session_mix(ledger, tmp_path, monkeypatch, *, specialized, advanced=False, newgirl=False):
    TRACE.clear()
    # Deliberately distinct roster, not a claim of random or exhaustive coverage.
    girls = ["PRINCESS", "STIM-BLISSED", "MOCKINGBIRD", "ALPHA"]
    frames = ["THE PRINCE", "CHANGELING", "PROJECT ANKOU", "THE ENFORCER"]
    if newgirl:
        girls[3], frames[3] = "NEWGIRL", "WYVERN 0.4"
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
            PilotRef(user_id=5, character_revision=1),
            PilotRef(user_id=2, character_revision=1),
        )
    bonds = BondService(ledger)
    bond_rows = {}
    for i, viewer in enumerate(viewers):
        target = viewers[(i + 1) % 4]
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
            viewers[0],
            str(uuid4()),
            5,
            "callsign",
            shared.prepare(viewers[0], 5, "callsign"),
            CallsignChoice(callsign="TEST_NOVICE"),
        )
        shared.decide(viewers[3], str(uuid4()), named["id"], 1, "accept")
        record(
            "newgirl_mentor_and_owned_callsign",
            mentor=2,
            newgirl=5,
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
        if frame == "THE PRINCE":
            # Actual owner-authored creation data, not a post-activation state patch.
            upd["fanbase"] = Fanbase(
                demographics=("Young girls", "Online shippers"),
                demanded=("Kind", "Intelligent"),
                rejected=("Dangerous", "Girly"),
            )
        if girl == "PRINCESS":
            upd["girl_details"] = GirlDetails(own_standard=StandardChoice(slot=0))
            coordinated = CoordinationService(ledger)
            # Separate peer and Handler proposals, each accepted by the owner.
            for author, role in ((viewers[1], "princess_peer"), (ADMIN, "princess_handler")):
                request = coordinated.propose(
                    author,
                    str(uuid4()),
                    viewer.user_id,
                    role,
                    coordinated.prepare(author, viewer.user_id, role),
                    StandardChoice(slot=1),
                )
                coordinated.decide(viewer, str(uuid4()), request["id"], 1, "accept")
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

    from girlframe.engine.m3_actor_bonds import current_ref
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
                    "girl.princess.",
                    "girl.stim-blissed.",
                    "girl.mockingbird.",
                    "girl.alpha.",
                    "frame.prince.",
                    "frame.changeling.",
                    "frame.ankou.",
                    "frame.enforcer.",
                )
                + (("girl.newgirl.", "frame.wyvern.") if newgirl else ())
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
        description="TEST ONLY selected Stim-Blissed prefix includes "
        "malleable-me-malleable-you; production admission "
        "is unsupported/subset/inventoried/pending. M2 "
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

    def done(viewer, action, label):
        assert game.inspect(viewer, action)["state"] == "complete"
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        record(
            "play_complete",
            label=label,
            user=viewer.user_id,
            receipt=game.inspect(viewer, action)["receipt"],
            heat={uid: s.heat for uid, s in state(game).sheets.items()},
        )

    mission = missions.offer(
        ADMIN, str(uuid4()), "Repair the relay and return all four pilots", (2, 3, 4, 5)
    )
    for viewer in viewers:
        m = missions.get(viewer, mission["id"])["mission"]
        missions.respond(viewer, str(uuid4()), mission["id"], m["revision"], "accept")
    m = missions.get(ADMIN, mission["id"])["mission"]
    missions.start(ADMIN, str(uuid4()), mission["id"], m["revision"])
    record(
        "mission_started",
        dialogue=[
            "GM: The relay is silent. Can you restore it?",
            "Princess: I choose the approach; keep our route open.",
            "Stim: I will check the signal.",
            "Mockingbird: I will protect the equipment.",
            f"{girls[3]}: Tell me what you need and I will help.",
        ],
        dialogue_mode="Scripted human inputs only, not AI/Discord transport",
    )
    # A scripted Director-like proposal is accepted/applied by the real GM-owned
    # Handler API. This does not call an AI or claim actual Director-role execution.
    from girlframe.engine import m3_handler_plays as handler_rules
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService

    interference = HandlerPlayService(ledger)

    def intervene(kind, detail, stakes):
        targets = tuple(current_ref(state(game), v.user_id) for v in viewers)
        proposal = interference.start(ADMIN, str(uuid4()), state(game).revision, targets)["id"]
        before = state(game)
        effect = Effect(
            kind=kind,
            account="Scripted Director-like proposal accepted by simulated human GM",
            detail=detail,
            stakes=stakes,
        )
        with pytest.raises(WorkflowError):
            interference.submit(viewers[0], str(uuid4()), proposal, before.revision, kind, effect)
        assert state(game) == before
        args = (ADMIN, str(uuid4()), proposal, before.revision, kind, effect)
        result = interference.submit(*args)
        after = state(game)
        assert interference.submit(*args) == result and state(game) == after
        grant = handler_rules.record(after, proposal)
        assert grant.state == "complete" and grant.effect == effect
        assert {uid: s.model_dump() for uid, s in after.sheets.items()} == {
            uid: s.model_dump() for uid, s in before.sheets.items()
        }
        record(
            "scripted_interference",
            kind=kind,
            detail=detail,
            stakes=stakes,
            actual_api="HandlerPlayService",
            authority="human GM fixture, not AI Director",
            player_choice="not supplied or consumed by this proposal",
        )

    intervene(
        "escalate",
        "A second relay signal appears on the approach.",
        "The four pilots must reassess their route.",
    )

    def tier(action):
        # Read actual rolled tier; never replace dice result or consequence state.
        with ledger.engine.connect() as c:
            return game.action(c, action)["data"]["result"]["tier"]

    def keep(viewer, faces):
        action = play(
            viewer,
            "keep_your_head",
            faces=faces,
            dialogue="I hold steady while choosing my own response to the interference.",
        )
        level = tier(action)
        if level == "high":
            answer(game, viewer, "actor_keep", text="Steady at the relay")
        elif level == "mid":
            answer(
                game, viewer, "actor_keep", options=("tough", "in_control"), denied=("desperate",)
            )
        else:
            answer(game, viewer, "actor_keep", options=("tough",))
        answer(
            game,
            ADMIN,
            "handler_keep",
            flag=True,
            text="PRIVATE_HANDLER: Your chosen approach keeps the equipment steady.",
        )
        done(viewer, action, f"{girls[viewer.user_id - 2]} Keep Your Head {level}")

    def sensors(viewer, faces):
        from girlframe.engine.m2 import QUESTIONS

        action = play(
            viewer,
            "check_sensors",
            faces=faces,
            dialogue="I ask for information before deciding what to do.",
        )
        count = {"low": 1, "mid": 2, "high": 3}[tier(action)]
        selected_questions = tuple(QUESTIONS)[:count]
        answer(game, viewer, "actor_sensors", options=selected_questions)
        answer(
            game,
            ADMIN,
            "handler_sensors",
            fields={
                f"a{i + 1}": (
                    f"PRIVATE_SENSOR: Relay observation {i + 1}; the pilot chooses the response."
                )
                for i in range(count)
            },
        )
        done(viewer, action, f"{girls[viewer.user_id - 2]} Check Sensors")

    keep(viewers[0], (4, 5))
    sensors(viewers[1], (4, 5))
    # Target retains the complete response. No GM/Director can supply it.
    action = play(
        viewers[2],
        "flirt",
        faces=(2, 3),
        target=5,
        dialogue="Would you like to coordinate our approach?",
    )
    answer(
        game,
        viewers[3],
        "target_flirt",
        text="PRIVATE_REPLY: I appreciate the invitation but will choose my own route.",
    )
    done(viewers[2], action, f"Mockingbird Flirt with {girls[3]}-owned response")
    keep(viewers[3], (1, 1))
    intervene(
        "expectation",
        "Return the relay equipment intact.",
        "The GM reviews actual conduct and does not assume player compliance.",
    )
    sensors(viewers[0], (1, 1))
    keep(viewers[1], (6, 6))
    keep(viewers[2], (3, 3))
    sensors(viewers[3], (6, 6))
    assert len([x for x in TRACE if x["stage"] == "play_complete"]) == 8
    record(
        "eight_basic_plays_completed",
        dice_calls=game.dice.calls,
        exclusions="No specialized Girl/Frame Play claim; no AI or live delivery.",
    )

    if specialized:
        # New ordinary Girl/Frame branches run on this same durable session.
        # No post-activation state injection: owners/GM declared outside-Frame
        # placement at onboarding above. This is service input, not live UI.
        from test_dose_up import native_choice as native_dose_choice

        from girlframe.engine import m3_dose_up as dose_rules
        from girlframe.engine import m3_prince as prince_rules
        from girlframe.services.m3_prince import PrinceService

        stim = viewers[1]
        action = play(
            stim,
            "dose_up",
            faces=(6, 6) if advanced else (4, 4),
            dialogue="I choose my own cocktail before we return to base.",
        )
        assert tier(action) == ("high" if advanced else "mid")
        before_drug = state(game)
        native_dose_choice(game, stim, ("quick", "strong"))
        if advanced:
            # The Handler must choose the third component; the roller cannot
            # supply this separate decision or silently reuse a component.
            native_dose_choice(game, ADMIN, ("sense",))
        drug_state = state(game)
        drug = next(x for x in dose_rules.records(drug_state, dose_rules.Dose) if x.id == action)
        assert drug.actor == drug.target == current_ref(drug_state, stim.user_id)
        assert [x.role for x in drug.selections] == (
            ["roller", "handler"] if advanced else ["roller"]
        )
        assert len(dose_rules.drug_tags(drug_state, current_ref(drug_state, stim.user_id))) == (
            3 if advanced else 2
        )
        assert (
            drug_state.sheets[str(stim.user_id)].identities
            == before_drug.sheets[str(stim.user_id)].identities
        )
        record(
            "specialized_stim_self_dose",
            action=action,
            selections=drug.selections,
            delivery="mock native choice, direct values; test-only approvals",
        )
        done(
            stim,
            action,
            "Stim native Dose Up high with separate Handler third Tag"
            if advanced
            else "Stim native Dose Up mid with two actual drug Tags",
        )

        prince = PrinceService(game)
        account = "I perform a kind, intelligent public hero for my actual audience"
        audience = viewers[3] if advanced else viewers[1]
        source = prince.perform(
            viewers[0],
            str(uuid4()),
            state(game).revision,
            900,
            current_ref(state(game), audience.user_id),
            "The composed public hero",
            True,
            account,
        )["id"]
        action = play(
            viewers[0],
            prince_rules.PLAY,
            faces=(4, 4) if advanced else (1, 1),
            source_work=source,
            prince_demands="following",
            prince_demand_account=account,
            dialogue="I play the declared role; my audience chooses her own reaction.",
        )
        if advanced:
            from test_prince import native_choice as native_prince_choice

            from girlframe.engine.m3_actor_bonds import depth as bond_depth

            assert tier(action) == "mid"
            before_benefits = state(game)
            actor = current_ref(before_benefits, viewers[0].user_id)
            target = current_ref(before_benefits, audience.user_id)
            before_depth = bond_depth(before_benefits, actor, target)
            assert before_depth < 2
            native_prince_choice(
                game,
                viewers[0],
                "prince_choose_actor",
                option=("status",),
                account="My performance raises my Status",
            )
            native_prince_choice(
                game,
                audience,
                "prince_choose_target",
                75210,
                option=("bond",),
                account="I choose to deepen our Bond",
            )
            after_benefits = state(game)
            assert after_benefits.order.index(2) == max(0, before_benefits.order.index(2) - 1)
            assert bond_depth(after_benefits, actor, target) == before_depth + 1
            choices = [
                x
                for x in prince_rules.records(after_benefits, prince_rules.Selection)
                if x.performance == source
            ]
            assert [(x.controller, x.option) for x in choices] == [(2, "status"), (5, "bond")]
            record(
                "specialized_prince_mid_owned_benefits",
                performer=2,
                audience=5,
                source=source,
                benefits="Status choice (cap respected) then actual +1 Bond",
                before_depth=before_depth,
            )
            done(viewers[0], action, "Prince Performer mid with two independent owner benefits")
        else:
            assert tier(action) == "low"
            before_decline = state(game)
            answer(game, audience, "prince_falter", options=("pass",))
            after_decline = state(game)
            assert after_decline.sheets == before_decline.sheets
            assert after_decline.role_punishments == before_decline.role_punishments
            record(
                "specialized_prince_owned_decline",
                performer=2,
                audience=3,
                source=source,
                optional_choice="pass",
                fabricated_effects=False,
            )
            done(viewers[0], action, "Prince Performer low with audience-owned decline")
        assert len([x for x in TRACE if x["stage"] == "play_complete"]) == 10
        record(
            "ten_plays_completed",
            basic=8,
            specialized=2,
            roster="Newgirl/Wyvern replaces fourth slot; three prior slots retained"
            if newgirl
            else "same distinct r268 roster; not all-type coverage",
        )

    from test_punishment_service import submit

    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_punishments import PunishmentService

    m = missions.get(ADMIN, mission["id"])["mission"]
    ended = missions.end(ADMIN, str(uuid4()), mission["id"], m["revision"], True)
    work = missions.get(ADMIN, mission["id"])["work"]
    record("mission_end_pending", work=work)
    punishment = PunishmentService(ledger, missions.access.registry)
    for item in work:
        if item["kind"] == "princess_mission_end":
            from girlframe.services.m3_reactions import ReactionService

            reactions = ReactionService(missions)
            data = reactions.get(ADMIN, item["id"])
            assert len(data["standards"]) == 3
            assert sum(x["is_order"] for x in data["standards"]) == 1
            before_permissions = state(game).sheets[str(item["subject"])].permissions
            reviewed = reactions.princess(
                ADMIN,
                str(uuid4()),
                item["id"],
                data["revision"],
                data["game_revision"],
                upheld=False,
                rationale="Scripted GM review: the Princess did not report "
                "Cadre conduct during this mission, so her own "
                "chosen reporting Standard was not upheld. No "
                "bonus is awarded.",
            )
            assert reviewed["state"] == "resolved"
            assert state(game).sheets[str(item["subject"])].permissions == before_permissions
            record(
                "princess_standards_reviewed",
                authority="actual Handler service",
                upheld=False,
                bonus="none",
                reviewed_standards=data["standards"],
            )
            continue
        assert item["kind"] == "punishment", item
        submit(
            punishment,
            ADMIN,
            item["id"],
            Details(kind="stimulant_injection"),
            str(uuid4()),
        )
    ended = missions.get(ADMIN, mission["id"])["mission"]
    result = missions.complete(ADMIN, str(uuid4()), mission["id"], ended["revision"])
    if result["phase"] == "awaiting_consequences":
        # Princess review precedes mission rewards; the actual Dog consequence
        # can therefore be created only by this first completion attempt.
        current_mission = missions.get(ADMIN, mission["id"])
        followups = current_mission["work"]
        assert followups
        record("mission_post_review_followups", work=followups)
        for item in followups:
            assert item["kind"] == "punishment", item
            submit(punishment, ADMIN, item["id"], Details(kind="stimulant_injection"), str(uuid4()))
        current_mission = missions.get(ADMIN, mission["id"])
        result = missions.complete(
            ADMIN, str(uuid4()), mission["id"], current_mission["mission"]["revision"]
        )
    assert result["phase"] == "complete"
    record(
        "mission_complete",
        permissions={uid: s.permissions for uid, s in state(game).sheets.items()},
        heat={uid: s.heat for uid, s in state(game).sheets.items()},
    )
    from test_strain import facts
    from test_strain_service import D6
    from test_world import gorgon

    from girlframe.engine.m3_strain_effects import Choice
    from girlframe.engine.m3_world_state import Faction
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_strain import StrainService
    from girlframe.services.m3_strain_effects import EffectService

    strain = StrainService(OffDutyService(missions), dice=D6())
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    period = strain.periods.begin(ADMIN, str(uuid4()))
    from girlframe.engine.m3_janus_storage import effective_assets

    trigger_state = state(game)
    void_owners = tuple(
        uid
        for uid in trigger_state.order
        if any(
            asset.void for asset in effective_assets(trigger_state, current_ref(trigger_state, uid))
        )
    )
    # Review current actual Assets: the Mockingbird starts with a Void Asset.
    # This is a factual declaration, not a state edit or a forced Strain tier.
    record(
        "strain_void_trigger_review",
        void_owners=void_owners,
        total_girls=len(trigger_state.order),
        canonical_triggers=trigger_state.strain.triggers,
    )
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        period["revision"],
        trigger_state.revision,
        facts(
            no_girl_void=not void_owners,
            at_least_half_have_void=2 * len(void_owners) >= len(trigger_state.order),
        ),
    )
    effects = EffectService(strain)
    choices = (
        (
            "void",
            1,
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="Simulated next-map threat",
                gorgon=gorgon("directed", "next-threat", (10, 0)),
            ),
        ),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Simulated local dissent",
                target="city0",
                faction=Faction(
                    id="relay-dissent",
                    name="Local dissent",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Scripted recovery consequence",
                ),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2",
                account="All four explicitly share accommodation",
                rooms=((2, 3), (4, 5)),
            ),
        ),
    )
    for track, face, column, choice in choices:
        request = next(
            x
            for x in state(game).strain.requests
            if x.period_id == period["id"] and x.track == track
        )
        strain.dice.face = face
        rolled = strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(
            ADMIN,
            str(uuid4()),
            request.id,
            rolled["revision"],
            state(game).revision,
            column,
        )
        if track == "budget":
            from girlframe.engine.m3_actor_bonds import depth as bond_depth

            before_rooms = state(game)
            room_depths = {
                (first, second): bond_depth(
                    before_rooms,
                    current_ref(before_rooms, first),
                    current_ref(before_rooms, second),
                )
                for first, second in choice.rooms
            }
            # This scenario exercises a real +1 Bond, not capped overflow.
            assert all(value < 2 for value in room_depths.values())
        effect_key = str(uuid4())
        if track == "budget":
            from girlframe.engine import m3_changeling as changeling_rules
            from girlframe.services.m3_changeling import ChangelingService

            # Reproduce r267's real admission failure on the pending effect.
            # The transaction must preserve both Bonds and the pending Strain;
            # do not replace the consequence or fabricate a body in GameState.
            before_failed_apply = state(game)
            with pytest.raises(WorkflowError, match="SOURCE_BODY_FACT_REQUIRED") as rejected:
                effects.apply(
                    ADMIN,
                    effect_key,
                    request.id + ":effect",
                    1,
                    before_failed_apply.revision,
                    choice,
                )
            assert state(game) == before_failed_apply
            record(
                "budget_effect_atomically_pending",
                error=str(rejected.value),
                rooms=state(game).world.rooms,
                state_unchanged=True,
            )

            princess = current_ref(state(game), viewers[0].user_id)
            assert not any(
                x.actor == princess
                for x in changeling_rules.records(state(game), changeling_rules.BodyFact)
            )
            controls = ChangelingService(game)
            fact = controls.body_fact(
                viewers[0],
                str(uuid4()),
                state(game).revision,
                900,
                princess,
                "girl",
                "Simulated Princess owner confirms her actual original Girl body and brain "
                "in the existing owner-proposed and Handler-confirmed placement. "
                "No body transfer, replacement, or transformation has occurred.",
            )
            proved = changeling_rules.record(state(game), changeling_rules.BodyFact, fact["id"])
            assert proved.actor == princess and proved.author == princess
            assert proved.controller == viewers[0].user_id and proved.kind == "girl"
            record(
                "owner_body_fact_established",
                actor=princess.token,
                body=proved.id,
                author=proved.controller,
                actual_api="ChangelingService.body_fact",
                method="Synthetic participant testimony through real owned service; no state patch",
            )
        effect_args = (ADMIN, effect_key, request.id + ":effect", 1, state(game).revision, choice)
        applied = effects.apply(*effect_args)
        if track == "budget":
            after_rooms = state(game)
            # Replay the successful request without duplicating the Bond/String.
            assert effects.apply(*effect_args) == applied
            assert state(game) == after_rooms
            changeling = current_ref(after_rooms, viewers[1].user_id)
            deepened = [
                x
                for x in changeling_rules.records(after_rooms, changeling_rules.Deepening)
                if x.first == changeling and x.second == princess
            ]
            assert len(deepened) == 1
            strings = [
                x
                for x in changeling_rules.records(after_rooms, changeling_rules.String)
                if x.actor == changeling
                and x.origin == "deepen"
                and x.source == deepened[0].id
                and x.subject.actor == princess
            ]
            assert len(strings) == 1 and strings[0].subject.source == proved.event
            record(
                "budget_retry_with_required_psych_string",
                string=strings[0].id,
                body_source=proved.event,
                exact_replay="unchanged",
            )
            for (first, second), previous_depth in room_depths.items():
                assert (
                    bond_depth(
                        after_rooms,
                        current_ref(after_rooms, first),
                        current_ref(after_rooms, second),
                    )
                    == previous_depth + 1
                )
            record(
                "room_bond_gains_verified",
                before={f"{a}:{b}": d for (a, b), d in room_depths.items()},
                delta=1,
            )
    final = state(game)
    assert any(x.id == "next-threat" and x.gorgon_class == "directed" for x in final.world.gorgons)
    assert any(
        x.id == "relay-dissent" and x.kind == "rebel" and x.cells == ((0, 4),)
        for x in final.world.factions
    )
    assert final.world.rooms == ((2, 3), (4, 5))
    assert all(
        secret not in json.dumps(gateway.messages)
        for secret in ("PRIVATE_SENSOR", "PRIVATE_REPLY", "PRIVATE_HANDLER")
    )
    GameService(ledger).rebuild()
    assert state(game) == final
    record(
        "strain_post_state_verified",
        gorgon="next-threat",
        faction="relay-dissent",
        rooms=final.world.rooms,
        rebuild="in-process only",
        exclusions="No Off-Duty recovery, AI Director, live Discord, "
        "process restart, full privacy or backup/restore "
        "certification; only two specialized branches when "
        "enabled",
    )
