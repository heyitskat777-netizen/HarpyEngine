"""Explicit prompt-reference retirement preserves provenance and survives long sessions."""

import pytest
import sqlalchemy as sa
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.onboarding import WorkflowError


def test_archival_retains_history_and_dependencies_and_allows_more_than_100_references(observed):
    observer, scene, _, game, *_ = observed
    context = DirectorContextService(observer)
    before = state(game).model_dump_json()
    with observer.store.engine.connect() as c:
        _, _, pilot = observer._authorize_input(c, PLAYER, scene, "pilot")
        _, _, handler = observer._authorize_input(c, ADMIN, scene, "handler")
    ids = []
    for i in range(100):
        _, source = send(observer, scene, f"source:{i}", text=f"Actual synthetic observation {i}")
        ids.append(
            context.record(
                ADMIN,
                f"ref:{i}",
                scene,
                source.source_id,
                i,
                known_by=(pilot,),
                dependencies=(ids[0],) if i == 1 else (),
            )["id"]
        )
    current = context.build(ADMIN, scene)
    with pytest.raises(WorkflowError):
        context.archive(PLAYER, "not-gm", scene, current.revision, (ids[0],), "My selection")
    with pytest.raises(WorkflowError, match="ACTIVE_DEPENDENCY"):
        context.archive(ADMIN, "dependent", scene, current.revision, (ids[0],), "Retire old detail")
    archived = context.archive(
        ADMIN, "archive", scene, current.revision, tuple(ids[:50]), "Prior test chapter"
    )
    assert (
        context.archive(
            ADMIN, "archive", scene, current.revision, tuple(ids[:50]), "Prior test chapter"
        )
        == archived
    )
    for i in range(100, 125):
        _, source = send(observer, scene, f"source:{i}", text=f"Later synthetic observation {i}")
        context.record(ADMIN, f"ref:{i}", scene, source.source_id, i, known_by=(pilot,))
    reopened = DirectorContextService(observer)
    assert len(reopened.build(ADMIN, scene).references) == 75
    assert len(reopened.build(PLAYER, scene, actor=pilot).references) == 75
    assert not reopened.build(ADMIN, scene, actor=handler).references
    with observer.store.engine.connect() as c:
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.director_context["knowledge"])) == 125
        )
        assert len(context._references(c, scene)) == 125
    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        reopened.archive(ADMIN, "stale", scene, current.revision, (ids[60],), "Old selection")
    assert state(game).model_dump_json() == before
    assert 'Actual synthetic observation 1"' not in reopened.build(ADMIN, scene).model_dump_json()
