"""Native bot-owned setup, private ownership and full owner activation."""

from uuid import uuid4

import mission_lab as mission_lab
import pytest
import sqlalchemy as sa
from bot_enrollment import BotEnrollment
from test_creation import selected
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation_details import InitialConditions
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.m2 import ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.shared_setup import CallsignChoice
from girlframe.services.activity_session_zero import SessionZeroDesk
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.session_zero import SessionZeroService
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture


def count(store, table):
    with store.engine.connect() as c:
        return c.scalar(sa.select(sa.func.count()).select_from(table))


def prepare(store, girl="MOCKINGBIRD", frame="JANUS"):
    store.policy = store.policy.model_copy(
        update={
            "owner_initial_conditions": InitialConditions(),
            "owner_creation_rulings": CreationRulings(provenance="owner_approved_campaign_ruling"),
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic bot enrollment test",
                reference="isolated test only",
            ),
        }
    )
    seed(store, PLAYER, girl=girl, frame=frame)
    seed(store, OTHER)
    store.join(ADMIN, "join-setup-owner")
    bot = GuildViewer(store.policy.application_id, store.policy.guild_id, True, False)
    store.join(bot, "join-handler-bot")
    HandlerService(store).appoint(ADMIN, "appoint-handler-bot", 0, bot.user_id)
    return BotEnrollment(store, bot)


def tasks(store, owner=PLAYER):
    with store.engine.connect() as c:
        return CoordinationService(store)._latest(c, owner.user_id)


def request(bot, owner=PLAYER, retry=False, key=None):
    view = bot.view(owner)
    data = {"character_revision": view["character_revision"], "context": view["context"]}
    if retry:
        data["retry_declined"] = True
    return bot.request(owner, key or str(uuid4()), data), data


@pytest.mark.parametrize("session_zero", [False, True])
def test_bot_assigns_status_and_both_owners_activate_and_reopen(ledger, session_zero):
    bot = prepare(ledger)
    before = count(ledger, tables.creation_drafts)
    bot.reconcile()
    assert count(ledger, tables.creation_drafts) == before
    handler = HandlerService(ledger)
    with ledger.engine.connect() as c:
        order = handler.current(c)[1].status_order
        assert [ref.user_id for ref in order] == [PLAYER.user_id, OTHER.user_id]
        assert not load_state(c, ledger.campaign_id).sheets
    events = count(ledger, tables.events)
    assert bot.reconcile()["actions"] == []
    assert count(ledger, tables.events) == events
    bonds = BondService(ledger)
    row = bonds.propose(
        PLAYER,
        "pilot-bond-offer",
        1,
        1,
        BondProposal(target_id=OTHER.user_id, prompt=0, context="A synthetic shared assignment."),
    )
    assert row["state"] == "pending"
    bot.reconcile()
    assert bonds.get(PLAYER, row["id"])["state"] == "pending"
    bonds.decide(OTHER, "target-accepts-own-bond", row["id"], 1, "accept")
    creation = CreationService(ledger)
    review = CreationReviewService(ledger)
    for owner in (PLAYER, OTHER):
        creation.save(
            owner, "owner-build-" + str(owner.user_id), 0, 1, selected("MOCKINGBIRD", "JANUS")
        )
    current = creation.get(OTHER)
    review.select_bond(
        OTHER, "other-selects-own-primary", current.revision, 1, current.draft, row["id"]
    )
    if session_zero:
        desk = SessionZeroDesk(
            SessionZeroService(ledger, group_owner=bot.bot.user_id, setup_organizer=ADMIN.user_id),
            None,
        )
        group = desk.write(
            ADMIN,
            "status-group",
            "session-zero-group",
            {"revision": 0, "members": ["1", "2", "3"]},
        )
        view = desk.read(ADMIN, "session-zero")
        assert {x["owner"] for x in view["status_recommendation"]} == {"2", "3"}
        plan = {
            "revision": group["revision"],
            "goals": "Find the relay.",
            "difficulty": "normal",
            "facilitator": "1",
            "facilitator_only": True,
            "seats": {"player_count": 2, "ai_pilots": []},
            "starting_status": {"ace": "3", "dog": "2"},
        }
        with pytest.raises(WorkflowError, match="distinct"):
            desk.write(
                ADMIN,
                "ineligible-status",
                "session-zero-plan",
                plan | {"starting_status": {"ace": "1", "dog": "2"}},
            )
        desk.write(ADMIN, "manual-status-plan", "session-zero-plan", plan)
        proposal = desk.read(ADMIN, "session-zero")["plan_proposal"]
        assert not review.get(OTHER).sheet.ready_for_rules_review
        for participant in (ADMIN, OTHER, PLAYER):
            desk.write(
                participant,
                "approve-status:" + str(participant.user_id),
                "session-zero-plan-vote",
                {"proposal": proposal, "approve": True},
            )
        assert desk.read(OTHER, "session-zero")["starting_status"] == {"ace": "3", "dog": "2"}
        assert review.get(OTHER).sheet.status == "Ace"
        assert review.get(PLAYER).sheet.status == "Dog"
    bot.reconcile()
    game = GameService(ledger)
    with pytest.raises(WorkflowError):
        review.get(bot.bot)
    for owner in (PLAYER, OTHER):
        view = review.get(owner)
        assert view.sheet.ready_for_rules_review
        assert not view.saved_current
        review.save(
            owner, "owner-reviews-" + str(owner.user_id), view.saved_revision, view.fingerprint
        )
        game.activate(owner, "owner-activates-" + str(owner.user_id), view.fingerprint)
    ledger.engine.dispose()
    reopened = GameService(ledger)
    assert reopened.sheet(PLAYER)["callsign"] == ledger.draft(PLAYER)["callsign"]
    assert reopened.sheet(OTHER)["callsign"] == ledger.draft(OTHER)["callsign"]
    with ledger.engine.connect() as c:
        state = load_state(c, ledger.campaign_id)
        assert state.handler == bot.bot.user_id and set(state.sheets) == {
            str(PLAYER.user_id),
            str(OTHER.user_id),
        }
        frozen = state.order
        assert frozen == (
            (OTHER.user_id, PLAYER.user_id) if session_zero else (PLAYER.user_id, OTHER.user_id)
        )
    before = count(ledger, tables.events)
    bot.reconcile()
    assert count(ledger, tables.events) == before
    with ledger.engine.connect() as c:
        assert load_state(c, ledger.campaign_id).order == frozen

    late = GuildViewer(4, ledger.policy.guild_id, True, False)
    peer = GuildViewer(5, ledger.policy.guild_id, True, False)
    seed(ledger, late, callsign="Synthetic late pilot")
    seed(ledger, peer, callsign="Synthetic late peer")
    requests = handler.late_wing_requests(bot.bot)
    assert {item["owner"] for item in requests} == {"4", "5"}
    assert bot.reconcile(owner=late.user_id)["actions"] == ["WING PLACEMENT FILED"]
    with ledger.engine.connect() as c:
        assert load_state(c, ledger.campaign_id).order == frozen
    assert bot.reconcile(owner=late.user_id)["actions"] == []
    pending = bonds.propose(
        late,
        "late-starting-bond",
        1,
        1,
        BondProposal(target_id=peer.user_id, prompt=0, context="Filed together after launch."),
    )
    bonds.decide(peer, "late-peer-accepts", pending["id"], 1, "accept")
    creation.save(late, "late-pilot-build", 0, 1, selected("MOCKINGBIRD", "JANUS"))
    draft = review.get(late)
    assert draft.sheet.status == "Wings" and draft.sheet.ready_for_rules_review
    review.save(late, "late-pilot-approves-review", draft.saved_revision, draft.fingerprint)
    game.activate(late, "late-pilot-activates-own-sheet", draft.fingerprint)
    ledger.engine.dispose()
    with ledger.engine.connect() as c:
        assert load_state(c, ledger.campaign_id).order == (frozen[0], late.user_id, frozen[-1])


def test_status_recommendation_weights_both_playbooks_and_keeps_princess_first():
    from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
    from girlframe.engine.starting_status import FRAME_WEIGHTS, GIRL_WEIGHTS, recommendation

    assert GIRL_WEIGHTS.keys() == GIRL_TYPES.keys() and FRAME_WEIGHTS.keys() == FRAME_TYPES.keys()
    ranked = recommendation(
        {
            3: ("Model Pilot", "OLDGEN", "THE PRINCE"),
            4: ("Foundation Prototype", "AM", "PROJECT ANKOU"),
            5: ("Model Pilot with Void equipment", "OLDGEN", "CHANGELING"),
            6: ("Public face", "PRINCESS", "JANUS"),
        }
    )
    assert [row["owner"] for row in ranked] == ["6", "3", "5", "4"]
    assert ranked[1]["score"] == ranked[1]["girl_weight"] + ranked[1]["frame_weight"]


@pytest.mark.parametrize(
    "girl,role", [("PRINCESS", "princess_handler"), ("VATGROWN", "vatgrown_handler")]
)
def test_only_bot_owned_offers_are_proposed_and_owner_decides(ledger, girl, role):
    bot = prepare(ledger, girl)
    bot.reconcile()
    rows = tasks(ledger)
    assert len(rows) == 1 and rows[0]["role"] == role
    row = rows[0]
    assert row["author_id"] == str(bot.bot.user_id) and row["owner_id"] == str(PLAYER.user_id)
    assert row["state"] == "pending"
    service = CoordinationService(ledger)
    for wrong in (OTHER, bot.bot):
        with pytest.raises(WorkflowError):
            service.decide(wrong, str(uuid4()), row["id"], row["revision"], "accept")
    with pytest.raises(ValueError):
        bot.request(OTHER, str(uuid4()), {"owner": str(PLAYER.user_id), "answer": "accept"})
    service.decide(PLAYER, "owner-declines", row["id"], row["revision"], "decline")
    before = count(ledger, tables.events)
    bot.reconcile()
    assert count(ledger, tables.events) == before
    key = str(uuid4())
    receipt, data = request(bot, retry=True, key=key)
    offered = [row for row in tasks(ledger) if row["state"] == "pending"]
    assert len(offered) == 1 and offered[0]["choice_json"] != row["choice_json"]
    new = offered[0]
    service.decide(PLAYER, "owner-declines-second", new["id"], new["revision"], "decline")
    assert bot.request(PLAYER, key, data) == receipt
    assert not any(row["state"] == "pending" for row in tasks(ledger))
    _, new_data = request(bot, retry=True)
    pending = next(row for row in tasks(ledger) if row["state"] == "pending")
    service.decide(PLAYER, "owner-accepts-third", pending["id"], pending["revision"], "accept")
    bot.reconcile()
    accepted = service.accepted
    with ledger.engine.connect() as c:
        assert {item.role for item in accepted(c, PLAYER.user_id)} == {role}
    ledger.engine.dispose()
    assert CoordinationService(ledger).get(PLAYER, pending["id"])["state"] == "accepted"


def test_newgirl_mentor_is_bot_owned_callsign_remains_player_owned(ledger):
    bot = prepare(ledger, "NEWGIRL")
    bot.reconcile()
    handler = HandlerService(ledger)
    with ledger.engine.connect() as c:
        mentor = handler.mentor_for(c, PLAYER.user_id)
        assert mentor and mentor.mentor.user_id == OTHER.user_id
    shared = SharedSetupService(ledger)
    assert shared.list(PLAYER) == []
    bonds = BondService(ledger)
    bond = bonds.propose(
        PLAYER,
        "newgirl-proposes-own-mentor-bond",
        1,
        1,
        BondProposal(target_id=OTHER.user_id, prompt=0, context="A synthetic Mentor agreement."),
    )
    bot.reconcile()
    assert bonds.get(PLAYER, bond["id"])["state"] == "pending"
    bonds.decide(OTHER, "mentor-accepts-own-bond", bond["id"], 1, "accept")
    context = shared.prepare(OTHER, PLAYER.user_id, "callsign")
    row = shared.propose(
        OTHER,
        "mentor-chooses-own-callsign",
        PLAYER.user_id,
        "callsign",
        context,
        CallsignChoice(callsign="MENTOR CHOICE"),
    )
    bot.reconcile()
    assert shared.get(PLAYER, row["id"])["state"] == "pending"
    with pytest.raises(WorkflowError):
        shared.decide(bot.bot, "bot-cannot-answer-callsign", row["id"], 1, "accept")
    shared.decide(PLAYER, "newgirl-countersigns", row["id"], 1, "accept")
    assert shared.get(PLAYER, row["id"])["state"] == "accepted"
    assert count(ledger, tables.creation_drafts) == 0


def test_frame_court_and_missing_owner_approval_are_not_fabricated(ledger):
    bot = prepare(ledger, frame="THE RED QUEEN")
    ledger.policy = ledger.policy.model_copy(
        update={"owner_initial_conditions": None, "owner_creation_rulings": None}
    )
    result = bot.reconcile()
    assert any("campaign-owner" in text for text in result["blocked"])
    assert SharedSetupService(ledger).list(PLAYER) == []
    assert count(ledger, tables.creation_drafts) == 0
    assert count(ledger, tables.creation_reviews) == 0
    with ledger.engine.connect() as c:
        assert not load_state(c, ledger.campaign_id).sheets


def test_two_discord_pilots_complete_bot_enrollment_and_reopen_after_server_restart(tmp_path):
    from player_setup import OWNER_CREATION_FIELDS
    from test_campaign_role_access import CONFIG, request, role_activity
    from test_handler_pilot_view import login

    with role_activity(tmp_path, bot_handler=True) as host:
        first = login(host, "role-pilot")
        second = login(host, "invited")
        campaign = request(host, "/api/campaigns", first)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        for token, callsign in ((first, "BOT ZERO"), (second, "BOT ONE")):
            current = request(host, "/api/player-setup" + query, token)
            request(
                host,
                "/api/player-setup/profile" + query,
                token,
                {"revision": current["revision"], "callsign": callsign},
            )
        for token in (first, second):
            state = request(host, "/api/player-setup" + query, token)
            assert len(state["bot_enrollment"]["status_order"]) == 2
            assert state["bot_enrollment"]["status"] == "BOT HANDLER ON DUTY"
            source = selected("MOCKINGBIRD", "JANUS").model_dump(mode="json")
            request(
                host,
                "/api/player-setup/build" + query,
                token,
                {
                    "revision": state["revision"],
                    "character_revision": state["character_revision"],
                    "draft": {
                        key: value for key, value in source.items() if key in OWNER_CREATION_FIELDS
                    },
                },
            )
        a = request(host, "/api/player-setup" + query, first)
        target = next(
            row for row in a["bond_setup"]["targets"] if row["id"] == CONFIG.invited_user_id
        )
        bond = request(
            host,
            "/api/player-setup/bond" + query,
            first,
            {
                "target": target["id"],
                "source_revision": a["bond_setup"]["source_revision"],
                "target_revision": target["revision"],
                "prompt": 0,
                "context": "A synthetic API agreement.",
            },
        )
        peer = request(host, "/api/player-setup" + query, second)
        incoming = next(row for row in peer["bonds"] if row["id"] == bond["id"])
        assert incoming["state"] == "pending"
        request(
            host,
            "/api/player-setup/bond-decision" + query,
            second,
            {
                "id": incoming["id"],
                "revision": incoming["revision"],
                "decision": "accept",
            },
        )
        peer = request(host, "/api/player-setup" + query, second)
        request(
            host,
            "/api/player-setup/select-bond" + query,
            second,
            {
                "id": bond["id"],
                "revision": peer["revision"],
                "character_revision": peer["character_revision"],
            },
        )
        for token in (first, second):
            state = request(host, "/api/player-setup" + query, token)
            assert state["review"]["ready"] and not state["review"]["saved"]
            request(
                host,
                "/api/player-setup/review" + query,
                token,
                {
                    "revision": state["review"]["revision"],
                    "fingerprint": state["review"]["fingerprint"],
                },
            )
            state = request(host, "/api/player-setup" + query, token)
            request(
                host,
                "/api/player-setup/activate" + query,
                token,
                {"fingerprint": state["review"]["fingerprint"]},
            )
        assert request(host, "/api/player-setup" + query, first)["callsign"] == "BOT ZERO"
        assert request(host, "/api/player-setup" + query, second)["callsign"] == "BOT ONE"
    with role_activity(tmp_path, bot_handler=True) as reopened:
        for code, callsign in (("role-pilot", "BOT ZERO"), ("invited", "BOT ONE")):
            token = login(reopened, code)
            record = request(reopened, "/api/player-setup" + query, token)
            assert record["stage"] == "active" and record["callsign"] == callsign
            own = next(pilot for pilot in record["cadre"] if pilot["own"])
            assert (own["frame"], own["frame_class"]) == ("JANUS", "priestess")
            assert not record["bot_enrollment"]["can_request"]


def test_native_princess_priority_and_conflict_are_preserved(ledger):
    bot = prepare(ledger)
    bot.reconcile()
    from girlframe.engine.drafts import DraftInput

    ledger.save_draft(
        OTHER,
        "owner-chooses-princess",
        1,
        DraftInput(callsign="PRINCESS OWNER", girl_playbook="PRINCESS", frame_playbook="JANUS"),
    )
    bot.reconcile()
    with ledger.engine.connect() as c:
        assert HandlerService(ledger).current(c)[1].status_order[0].user_id == OTHER.user_id
    ledger.save_draft(
        PLAYER,
        "second-owner-chooses-princess",
        1,
        DraftInput(callsign="SECOND PRINCESS", girl_playbook="PRINCESS", frame_playbook="JANUS"),
    )
    report = bot.reconcile()
    assert (
        "Starting Ace assignment requires a ruling on the competing Princess files."
        in report["blocked"]
    )
    assert "STARTING STATUS FILED" not in report["actions"]


def test_context_is_owner_bound_and_human_handler_is_not_automated(ledger):
    bot = prepare(ledger)
    bot.reconcile()
    a = bot.view(PLAYER)
    b = bot.view(OTHER)
    assert a["context"] != b["context"]
    before = count(ledger, tables.events)
    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        bot.request(
            PLAYER,
            str(uuid4()),
            {"character_revision": a["character_revision"], "context": b["context"]},
        )
    assert count(ledger, tables.events) == before
    with ledger.engine.connect() as c:
        revision = HandlerService(ledger).current(c)[0]
    HandlerService(ledger).appoint(ADMIN, "human-handler-restored", revision, ADMIN.user_id)
    before = count(ledger, tables.events)
    assert bot.reconcile()["enabled"] is False
    assert bot.view(PLAYER) is None
    assert count(ledger, tables.events) == before
