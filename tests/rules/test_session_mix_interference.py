"""Eight player Plays and scripted Director-like interference through GM services.

Not actual AI Director, live Discord or release approval. Same seeded roster as r265
keeps the added interference/Frame consequence scenario comparable.
"""

import json
import random
from pathlib import Path
from uuid import uuid4

import pytest
from test_creation import selected
from test_ledger import ADMIN, seed
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import AssetChoice
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import (
    DesireChoice,
    GirlDetails,
    InitialConditions,
    NpcInvestor,
)
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.pair_assets import PairNames
from girlframe.engine.shared_setup import CourtChoice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture
SEED = 202611130754
TRACE = []


def record(stage, **details):
    TRACE.append(dict(stage=stage, **details))
    print("SESSION_TRACE " + json.dumps(TRACE[-1], default=str))


def test_eight_play_mix_with_scripted_interference(ledger, tmp_path, monkeypatch):
    rng = random.Random(SEED)
    girls = rng.sample([k for k, v in CATALOG.items() if v["family"] == "girl"], 4)
    frames = rng.sample([k for k, v in CATALOG.items() if v["family"] == "frame"], 4)
    viewers = [GuildViewer(i, 200, True, False) for i in range(2, 6)]
    record(
        "random_selection",
        seed=SEED,
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
    # Pair owns names; neither the GM nor generation chooses them for the real user.
    bonded = viewers[girls.index("BONDED")]
    partner = viewers[(girls.index("BONDED") + 1) % 4]
    PairService(ledger).choose(
        partner,
        str(uuid4()),
        bond_rows[bonded.user_id]["id"],
        2,
        0,
        PairNames(names=tuple(CATALOG["BONDED"]["assets"][:2])),
    )
    shared = SharedSetupService(ledger)
    queen = viewers[frames.index("THE RED QUEEN")]
    target = viewers[(frames.index("THE RED QUEEN") + 1) % 4]
    req = shared.propose(
        queen,
        str(uuid4()),
        target.user_id,
        "court",
        shared.prepare(queen, target.user_id, "court"),
        CourtChoice(role="The Knight"),
    )
    shared.decide(target, str(uuid4()), req["id"], 1, "accept")
    creation = CreationService(ledger)
    for viewer, girl, frame in zip(viewers, girls, frames, strict=False):
        cur = creation.get(viewer)
        data = selected(girl, frame)
        upd = {
            "shared_tokens": cur.draft.shared_tokens,
            "pair_source_token": cur.draft.pair_source_token,
        }
        if cur.pair_choice:
            upd["pair_asset_descriptions"] = tuple(
                AssetChoice(name=x, description="Simulated player choice")
                for x in cur.pair_choice.names
            )
        if girl == "OLDGEN":
            upd["girl_details"] = GirlDetails(maxims=(0, 1))
        if girl == "VATGROWN":
            upd["girl_details"] = GirlDetails(
                investors=tuple(
                    NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                    for x in data.npc_bonds
                )
            )
            coord = CoordinationService(ledger)
            req = coord.propose(
                ADMIN,
                str(uuid4()),
                viewer.user_id,
                "vatgrown_handler",
                coord.prepare(ADMIN, viewer.user_id, "vatgrown_handler"),
                DesireChoice(slots=(1,)),
            )
            coord.decide(viewer, str(uuid4()), req["id"], 1, "accept")
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
    with pytest.raises(WorkflowError) as exc:
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

    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.engine import m3_red_queen as queen_rules
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_red_queen import RedQueenService
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
                    "girl.oldgen.",
                    "girl.alpha.",
                    "girl.bonded.",
                    "girl.vatgrown.",
                    "frame.consume.",
                    "frame.janus.",
                    "frame.red-queen.",
                    "frame.wyvern.",
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
        description="TEST ONLY M2 release approval; M3 scenario "
        "approval and selected rule contracts copied from "
        "synthetic test fixture. Not certification or "
        "deployment approval.",
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
    from girlframe.engine.m3_world_state import Npc

    world_service = WorldService(missions)
    vatgrown = viewers[girls.index("VATGROWN")]
    for bond in state(game).sheets[str(vatgrown.user_id)].review.creation.npc_bonds:
        npc = Npc(
            id=f"initial-investor-{bond.slot}",
            name=f"Scripted starting Investor {bond.slot}",
            jobs=("scientist",),
            detail="Explicitly created initial Investor NPC",
            controller=1,
            cell=(0, 0),
            revealed=True,
        )
        world_service.npc(ADMIN, str(uuid4()), state(game).revision, npc)
        world_service.import_starting_npc(
            vatgrown, str(uuid4()), state(game).revision, bond.slot, npc.id
        )
    record("starting_investors_bound", owner=vatgrown.user_id)
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
                mode="piloting",
                account="Simulated owner states actual starting cockpit location",
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
            "Oldgen: Stay together; I will watch the approaches.",
            "Alpha: I will check the signal.",
            "Bonded: My partner and I can protect the equipment.",
            "Vatgrown: Tell me what you need and I will help.",
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
    a = play(
        viewers[0],
        "keep_your_head",
        dialogue="I hold the line as warning lights flare.",
    )
    answer(
        game,
        viewers[0],
        "actor_keep",
        options=("tough", "in_control"),
        denied=("desperate",),
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="PRIVATE_HANDLER: You remain steady enough to reach the panel.",
    )
    done(viewers[0], a, "Keep Your Head")
    a = play(
        viewers[1],
        "check_sensors",
        dialogue="Where should we go, and what should we avoid?",
    )
    answer(
        game,
        viewers[1],
        "actor_sensors",
        fields={
            "q1": "Where does the Foundation want us to go?",
            "q2": "What does the Foundation want us to avoid?",
        },
    )
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={
            "a1": "PRIVATE_SENSOR: The relay at the eastern gate.",
            "a2": "PRIVATE_SENSOR: The unstable approach tunnel.",
        },
    )
    done(viewers[1], a, "Check Sensors exact printed text")
    a = play(
        viewers[2],
        "flirt",
        faces=(2, 3),
        target=5,
        dialogue="You did well keeping your head. What do you think of my approach?",
    )
    answer(
        game,
        viewers[3],
        "target_flirt",
        text="PRIVATE_REPLY: I appreciate the support, but I want to choose my own route.",
    )
    done(viewers[2], a, "Flirt with target-owned response")
    a = play(
        viewers[3],
        "keep_your_head",
        faces=(2, 3),
        dialogue="I steady my hands and carry the replacement relay module.",
    )
    answer(game, viewers[3], "actor_keep", options=("tough",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="PRIVATE_HANDLER: You carry it safely despite the pressure.",
    )
    done(viewers[3], a, "Keep Your Head low")
    # Genuine Oldgen source, separate original recipient choice, actual effect.
    a = play(
        viewers[0],
        oldgen.PLAY,
        faces=(4, 4),
        target=3,
        heat=0,
        dialogue="Follow the marked cable; it will lead to the safer route.",
    )
    answer(
        game,
        viewers[0],
        "oldgen_write_maxim",
        text="Follow the marked cable when visibility fails.",
    )
    answer(
        game,
        viewers[1],
        "oldgen_listen",
        text="I listen to the advice and consider the marked cable route.",
    )
    done(viewers[0], a, "Oldgen Advice")
    # Court initialization derives the actual original starting Court allocation.
    queen = RedQueenService(game)
    queen.initialize(viewers[2], str(uuid4()), state(game).revision)
    original_queen = next(
        x for x in queen_rules.records(state(game), queen_rules.CourtAM) if x.role == "The Queen"
    )
    queen.mark(
        viewers[2],
        str(uuid4()),
        900,
        state(game).revision,
        original_queen.id,
        "status",
        amount=1,
    )
    a = play(
        viewers[2],
        "red_queen_consult",
        faces=(4, 4),
        heat=0,
        dialogue="I consult the Court about keeping the relay secure.",
    )
    answer(
        game,
        viewers[2],
        "red_queen_consult",
        options=(original_queen.id,),
        text="Do not deliberately damage the relay equipment.",
    )
    done(viewers[2], a, "Red Queen Consult and real Decree")
    intervene(
        "expectation",
        "Return with the relay equipment intact.",
        "The Handler will review actual performance, not assume obedience.",
    )
    # Different chooser/tier than the original Alpha mid Sensors.
    a = play(
        viewers[2],
        "check_sensors",
        faces=(1, 1),
        dialogue="I ask the Foundation what it wants us to avoid before deciding my route.",
    )
    answer(
        game,
        viewers[2],
        "actor_sensors",
        fields={"q1": "What does the Foundation want us to avoid?"},
    )
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={"a1": "PRIVATE_SENSOR: The second signal leads toward unstable ground."},
    )
    done(viewers[2], a, "Bonded low Check Sensors after interference")
    # Real additional active Frame Play, with its mandatory low identity cost.
    from girlframe.engine import m3_wyvern as wyvern_rules
    from girlframe.engine.m3_physical_state import CockpitAction

    wyvern_actor = current_ref(state(game), 5)
    identity_before = {x.id for x in state(game).sheets["5"].identities}
    order_before = state(game).order
    # Earlier Plays do not mint spendable Heat: use the actual available balance.
    # This low-tier scenario deliberately spends none, rather than inventing Heat.
    assert state(game).sheets["5"].heat < 5
    record("wyvern_rouse_input", available_heat=state(game).sheets["5"].heat, spent_heat=0)
    a = play(
        viewers[3],
        "wyvern_rouse",
        faces=(1, 1),
        heat=0,
        dialogue="I rouse the Wyvern while retaining my own choice to disengage.",
    )
    row = next(x for x in game.choices(viewers[3]) if x["kind"] == "wyvern_rouse_cost")
    chosen = game.decision(viewers[3], row["id"])["detail"]["identities"][0][0]
    answer(game, viewers[3], "wyvern_rouse_cost", denied=(chosen,))
    assert identity_before - {x.id for x in state(game).sheets["5"].identities} == {chosen}
    assert wyvern_rules.acts_last(state(game), wyvern_actor) and state(game).order == order_before
    done(viewers[3], a, "Wyvern low Rouse and actual identity erasure")
    position = physical.preview(viewers[3])
    physical.operate(
        viewers[3],
        str(uuid4()),
        position["game_revision"],
        CockpitAction(
            actor=wyvern_actor,
            operation="exit",
            expected_position=position["position_sha256"],
            account="Simulated owner chooses to unlink and leave the cockpit",
            confirmed=True,
        ),
    )
    assert not wyvern_rules.acts_last(state(game), wyvern_actor)
    assert len([x for x in TRACE if x["stage"] == "play_complete"]) == 8
    record(
        "session_state",
        dice_calls=game.dice.calls,
        status_order=state(game).order,
        obligations=[o.model_dump(mode="json") for o in state(game).obligations],
    )

    assert any(
        x.text == "Do not deliberately damage the relay equipment."
        for x in queen_rules.records(state(game), queen_rules.Decree)
    )
    assert any(
        x.subject == current_ref(state(game), 3) for x in oldgen.records(state(game), oldgen.Maxim)
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
        assert item["kind"] == "punishment"
        submit(
            punishment,
            ADMIN,
            item["id"],
            Details(kind="stimulant_injection"),
            str(uuid4()),
        )
    ended = missions.get(ADMIN, mission["id"])["mission"]
    result = missions.complete(ADMIN, str(uuid4()), mission["id"], ended["revision"])
    assert result["phase"] == "complete"
    record(
        "mission_complete",
        permissions={uid: s.permissions for uid, s in state(game).sheets.items()},
        heat={uid: s.heat for uid, s in state(game).sheets.items()},
    )
    from test_off_duty_cycle import call, movement
    from test_strain import facts
    from test_strain_service import D6
    from test_world import gorgon

    from girlframe.engine.m3_off_duty import RecoveryChoice
    from girlframe.engine.m3_strain_effects import Choice
    from girlframe.engine.m3_world_state import Faction
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService
    from girlframe.services.m3_strain import StrainService
    from girlframe.services.m3_strain_effects import EffectService

    strain = StrainService(OffDutyService(missions), dice=D6())
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    period = strain.periods.begin(ADMIN, str(uuid4()))
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        period["revision"],
        state(game).revision,
        facts(no_girl_void=True),
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
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    cycle = CycleService(strain.periods)
    call(cycle, game, ADMIN, period["id"], "activate")
    from girlframe.engine.m3_frame_rewards import Claim
    from girlframe.services.m3_frame_rewards import RewardService

    for viewer in viewers:
        a = play(
            viewer,
            "go_off_duty",
            faces=(3, 3),
            off_duty_id=period["id"],
            dialogue="I return to base and rest after repairing the relay.",
        )
        tick(worker, gateway, 5)
        rewards = RewardService(strain.periods)
        for item in strain.periods.get(viewer, period["id"])["work"]:
            if item["kind"] == "frame_off_duty_reward":
                data = rewards.get(viewer, item["id"])
                if data["owner_id"] == str(viewer.user_id) and data["mode"] == "conditional":
                    rewards.apply(
                        viewer,
                        str(uuid4()),
                        item["id"],
                        data["revision"],
                        data["game_revision"],
                        Claim(
                            fulfilled=False,
                            account="No qualifying frame reward occurred in this scripted mission.",
                        ),
                    )
                elif data["owner_id"] == str(viewer.user_id) and data["mode"] == "queen":
                    rewards.apply(
                        viewer,
                        str(uuid4()),
                        item["id"],
                        data["revision"],
                        data["game_revision"],
                        recipient=5,
                        account="The Queen holder recognizes the Vatgrown pilot "
                        "for carrying the replacement module.",
                    )
        if viewer.user_id == 5:
            from girlframe.engine import m3_vatgrown_plays as investment_rules
            from girlframe.engine.creation_details import DESIRES
            from girlframe.engine.m3_actor_bonds import current_ref
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            vatgrown = viewers[girls.index("VATGROWN")]
            investment = investment_rules.identity(
                "investment",
                period["id"],
                current_ref(state(game), vatgrown.user_id).token,
            )
            investor_controls = VatgrownPlaysService(game)
            investor_controls.low_investor(
                vatgrown,
                str(uuid4()),
                investment,
                state(game).revision,
                current_ref(state(game), 1),
                DESIRES[1],
                "The simulated Vatgrown chooses the actual Handler Investor whose desire waned.",
            )
            investor_controls.low_tag(
                ADMIN,
                str(uuid4()),
                investment,
                state(game).revision,
                "Investor interest waned",
            )
            assert investor_controls.view(vatgrown, investment)["investment"]["completed_event"]
            record(
                "prime_investment_completed",
                owner=vatgrown.user_id,
                investor=1,
                removed_desire=DESIRES[1],
                tag="Investor interest waned",
            )
        if cycle.review(viewer, period["id"])["own"]["roll"]["total"] < 8:
            call(
                cycle,
                game,
                viewer,
                period["id"],
                "scene",
                "other_unwanted",
                (viewer.user_id, 2),
                "PRIVATE_SCENE: Oldgen: We are assigned an "
                "unwanted late repair shift. Vatgrown: I will help "
                "but need clearer instructions. Oldgen: Tell me "
                "which module is uncertain. Vatgrown: The relay "
                "coupler.",
            )
            for participant in (viewer, viewers[0]):
                call(
                    cycle,
                    game,
                    participant,
                    period["id"],
                    "acknowledge",
                    viewer.user_id,
                )
        else:
            call(cycle, game, viewer, period["id"], "scene", None, (), "")
        call(cycle, game, viewer, period["id"], "recover", RecoveryChoice())
        record(
            "pilot_recovered",
            user=viewer.user_id,
            own=cycle.review(viewer, period["id"])["own"],
        )
    call(
        cycle,
        game,
        ADMIN,
        period["id"],
        "handler_scene",
        "routine",
        (1, 2, 3, 4, 5),
        "PRIVATE_ROUTINE: Debrief at base.",
    )
    for v in [ADMIN, *viewers]:
        call(cycle, game, v, period["id"], "acknowledge", None)
    call(
        cycle,
        game,
        ADMIN,
        period["id"],
        "review_status",
        state(game).order,
        "PRIVATE_PERFORMANCE: All four completed assigned tasks.",
    )
    assert call(cycle, game, ADMIN, period["id"], "finish", movement(game))["phase"] == "complete"
    record(
        "off_duty_complete",
        order=state(game).order,
        heat={uid: s.heat for uid, s in state(game).sheets.items()},
    )
    second = missions.offer(ADMIN, str(uuid4()), "Next relay patrol", (2, 3, 4, 5))
    for v in viewers:
        m = missions.get(v, second["id"])["mission"]
        missions.respond(v, str(uuid4()), second["id"], m["revision"], "accept")
    m = missions.get(ADMIN, second["id"])["mission"]
    assert missions.start(ADMIN, str(uuid4()), second["id"], m["revision"])["phase"] == "active"
    final = state(game)
    GameService(ledger).rebuild()
    assert state(game) == final
    assert all(
        secret not in json.dumps(gateway.messages)
        for secret in ("PRIVATE_SENSOR", "PRIVATE_REPLY", "PRIVATE_HANDLER")
    )
    record(
        "next_mission_started_and_rebuild",
        players=len(final.sheets),
        dice_calls=game.dice.calls,
        privacy="chosen response canaries absent from mock public deliveries",
        scope="service-level temporary DB, no real Discord or process restart",
    )
