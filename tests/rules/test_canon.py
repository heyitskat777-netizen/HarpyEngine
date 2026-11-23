"""An actual introduction, scoped knowledge, and a Pilot-owned report."""

from uuid import uuid4

import pytest
from test_campaign_opening import complete, ready_plan
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_session_zero import FACILITATOR, OUTSIDE, reviewed_sheets

from girlframe.scenes.canon import KnowledgeGrant
from girlframe.services import campaign_time_history as calendar
from girlframe.services.canon import FACT, GRANT, CanonService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

SECRET = "The west relay is receiving a hidden test signal."
UNSHARED = "The courier buried a spare receiver outside the village."


@pytest.fixture
def introduction(ledger):
    reviewed_sheets(ledger)
    for viewer in (FACILITATOR, OUTSIDE):
        ledger.join(viewer, f"join-{viewer.user_id}")
    session = ready_plan(ledger, "narrative")
    complete(session)
    ledger.policy = ledger.policy.model_copy(update={"canon_facilitator_id": FACILITATOR.user_id})
    return session


def test_private_native_witness_report_survives_restart(ledger, introduction):
    with ledger.engine.connect() as c:
        original = load_state(c, ledger.campaign_id)

    canon = CanonService(ledger)
    window = canon.window(FACILITATOR, 901, facilitator=True)
    fact_id = canon.establish(FACILITATOR, "1001", window, SECRET)
    canon.establish(FACILITATOR, "1002", window, UNSHARED)
    assert [fact.statement for fact in canon.world(FACILITATOR)] == [SECRET, UNSHARED]
    assert canon.known(ADMIN) == canon.known(PLAYER) == canon.known(OTHER) == ()
    canon.witness(FACILITATOR, "1003", window, fact_id, PLAYER.user_id)
    assert [fact.statement for fact in canon.known(PLAYER)] == [SECRET]
    assert not canon.known(ADMIN)

    day_one = introduction.view(ADMIN)["opening_anchor"]
    introduction.advance_opening(ADMIN, "next-day", day_one)
    window = canon.window(PLAYER, 901, facilitator=False)
    canon.report(PLAYER, "1006", window, fact_id)
    assert [fact.statement for fact in canon.known(ADMIN)] == [SECRET]

    ledger.engine.dispose()
    canon = CanonService(ledger)
    (learned,) = canon.known(ADMIN)
    assert (
        learned.statement == SECRET and learned.method == "reported" and learned.learned_at.day == 2
    )
    (witnessed,) = canon.known(PLAYER)
    assert witnessed.method == "witnessed" and witnessed.learned_at.day == 1
    assert canon.report(PLAYER, "1006", window, fact_id) == learned.grant_id
    assert canon.known(OTHER) == ()
    with ledger.engine.connect() as c:
        assert load_state(c, ledger.campaign_id) == original
        [(witness, _), (report, payload)] = calendar.history(c, ledger.campaign_id, GRANT)
        assert witness["id"] == witnessed.grant_id and report["id"] == learned.grant_id
        assert report["actor_id"] == str(PLAYER.user_id)
        assert KnowledgeGrant.model_validate(payload).source_grant_id == witnessed.grant_id
        assert all(
            row["visibility"] == "private"
            for row, _ in calendar.history(c, ledger.campaign_id, FACT, GRANT)
        )
    assert SECRET not in str(ledger.public_export()) and UNSHARED not in str(ledger.public_export())


def test_report_checks_witness_opening_revision_and_safety(ledger, introduction):
    canon = CanonService(ledger)
    window = canon.window(FACILITATOR, 901, facilitator=True)
    fact_id = canon.establish(FACILITATOR, "establish", window, SECRET)
    with pytest.raises(WorkflowError, match="designated canon facilitator"):
        canon.world(ADMIN)
    with pytest.raises(WorkflowError, match="unavailable"):
        canon.known(OUTSIDE)
    with pytest.raises(WorkflowError, match="unavailable"):
        canon.known(GuildViewer(PLAYER.user_id, 999, True, False))
    with pytest.raises(WorkflowError, match="Introduction channel"):
        canon.window(PLAYER, 900, facilitator=False)
    with pytest.raises(WorkflowError, match="participating Pilot"):
        canon.witness(FACILITATOR, "handler-witness", window, fact_id, ADMIN.user_id)
    for identity in (fact_id, str(uuid4())):
        with pytest.raises(WorkflowError, match="do not have a witness record"):
            canon.report(OTHER, "guessed-id", window, identity)
    canon.witness(FACILITATOR, "witness", window, fact_id, PLAYER.user_id)
    assert canon.known(ADMIN) == ()

    day_one = introduction.view(ADMIN)["opening_anchor"]
    introduction.advance_opening(ADMIN, "next-day", day_one)
    with pytest.raises(WorkflowError, match="STALE_CANON"):
        canon.report(PLAYER, "stale-report", window, fact_id)
    current = canon.window(PLAYER, 901, facilitator=False)
    ledger.safety(OTHER, "pause", 0, pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        canon.report(PLAYER, "valid-report", current, fact_id)
    assert canon.known(ADMIN) == ()
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    canon.report(PLAYER, "valid-report", current, fact_id)
    with pytest.raises(WorkflowError, match="already knows"):
        canon.report(PLAYER, "repeat-report", current, fact_id)
    assert [fact.statement for fact in canon.known(ADMIN)] == [SECRET]

    for day in (2, 3):
        anchor = introduction.view(ADMIN)["opening_anchor"]
        introduction.advance_opening(ADMIN, f"advance-{day}", anchor)
    with pytest.raises(WorkflowError, match="open|closed"):
        canon.window(FACILITATOR, 901, facilitator=True)
    assert [fact.statement for fact in canon.known(ADMIN)] == [SECRET]
