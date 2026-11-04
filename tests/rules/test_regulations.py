import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.engine.m3_punishments import Details, apply
from girlframe.engine.m3_regulations import breach

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    _, game = service(ledger)
    return state(game)


def impose(canon, **kwargs):
    return apply(
        canon,
        3,
        1,
        Details(kind="strict_regulations", regulation="PRIVATE_RULE", **kwargs),
        entity_id="rule",
        source_event="actual-imposition-event",
        off_duty=False,
    ).state


def test_regulation_is_a_private_character_bound_rule_not_a_sheet_tag_or_resource_change(canon):
    changed = impose(canon, disclosed=False)
    rule = changed.regulations[0]
    assert rule.subject.incarnation == canon.sheets["3"].character_id
    assert rule.inflictor == rule.knowing_handler
    assert rule.source_event == "actual-imposition-event" and not rule.disclosed
    assert changed.sheets["3"].model_dump(exclude={"revision"}) == canon.sheets["3"].model_dump(
        exclude={"revision"}
    )
    assert not canon.regulations and "PRIVATE_RULE" not in changed.sheets["3"].model_dump_json()


def test_moderate_regulation_needs_exact_handler_consultation_and_no_unrelated_fields(canon):
    details = Details(kind="strict_regulations", regulation="A factual rule")
    with pytest.raises(ValueError, match="CONSULT_REQUIRED"):
        apply(canon, 3, 2, details, entity_id="rule", source_event="event", off_duty=False)
    changed = apply(
        canon,
        3,
        2,
        details,
        entity_id="rule",
        source_event="event",
        off_duty=False,
        handler_consulted=True,
    ).state
    assert changed.regulations[0].inflictor.incarnation == canon.sheets["2"].character_id
    with pytest.raises(ValueError, match="unrelated"):
        apply(
            canon,
            3,
            1,
            details.model_copy(update={"tag": "Extra effect"}),
            entity_id="rule",
            source_event="event",
            off_duty=False,
        )


@pytest.mark.parametrize("text,source", [("", "event"), (" ", "event"), ("Rule", None)])
def test_empty_or_unsourced_rule_is_not_an_applied_punishment(canon, text, source):
    with pytest.raises(ValueError):
        apply(
            canon,
            3,
            1,
            Details(kind="strict_regulations", regulation=text),
            entity_id="rule",
            source_event=source,
            off_duty=False,
        )


def test_actual_breaches_create_distinct_unfulfilled_causes_without_picking_punishments(canon):
    changed = impose(canon)
    first = breach(changed, "rule", 1, "First actual occurrence", "breach-one", "debt-one")
    second = breach(first, "rule", 1, "Second actual occurrence", "breach-two", "debt-two")
    assert len(second.regulations[0].breaches) == 2 and len(second.obligations) == 2
    assert all(x.kind == "punishment" and x.state == "pending" for x in second.obligations)
    assert second.sheets == changed.sheets and not changed.obligations
    assert second.obligations[0].details["character_id"] == canon.sheets["3"].character_id
    with pytest.raises(ValueError, match="already"):
        breach(first, "rule", 1, "Duplicate event", "breach-one", "new-debt")
    with pytest.raises(ValueError):
        breach(first, "rule", 2, "Not the Handler", "other", "other")


def test_regulation_does_not_punish_a_new_character_or_reveal_knowledge_to_a_new_handler(canon):
    changed = impose(canon)
    changed.sheets["3"].character_id = "different-character"
    with pytest.raises(ValueError, match="STALE_CHARACTER"):
        breach(changed, "rule", 1, "Old body's rule", "event", "debt")
    changed = impose(canon)
    changed.handler = 4
    with pytest.raises(ValueError, match="informed Handler"):
        breach(changed, "rule", 4, "Unknown rule", "event", "debt")
