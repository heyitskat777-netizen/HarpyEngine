"""A frozen scene judge's finite GM procedure is neither a global appointment nor a dead body."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state

from girlframe.database import tables as t
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_tag_setters import ooc_setter
from girlframe.services.onboarding import WorkflowError


def source(store, monkeypatch):
    from test_battle_director import director_battle_source
    from test_battle_pipeline import table

    game, worker, gateway, action, target, director = director_battle_source(store, monkeypatch)
    table(game)
    answer(game, OTHER, "battle_handler", options=("handler_play",))
    grant = next(x for x in state(game).handler_plays if x.source_action == action)
    return game, worker, gateway, target, action, grant, director


def test_actual_scene_judge_scoped_tag_survives_body_death_without_global_gm_or_fictional_giver(
    ledger, monkeypatch
):
    game, _, _, director, action, grant, director_service = source(ledger, monkeypatch)
    assert (
        grant.chooser_controller == 3
        and grant.chooser_actor is None
        and grant.adjudicator_ref == director
    )
    service = HandlerPlayService(ledger)
    victim = current_ref(state(game), 2)
    effect = Effect(
        kind="tag",
        target=victim,
        tag="Actual scoped consequence",
        account="The source episode's actual ruling",
    )
    with pytest.raises(WorkflowError):
        service.submit(ADMIN, "no-main-gm-proxy", grant.id, state(game).revision, "mess", effect)
    with ledger.engine.connect() as c:
        rows = c.execute(
            sa.select(t.m3["m3_required_work"])
            .where(t.m3["m3_required_work"].c.kind == "director_damage")
            .order_by(t.m3["m3_required_work"].c.revision)
        ).mappings()
        latest = {x["id"]: dict(x) for x in rows}
        owed = next(x for x in latest.values() if x["state"] == "pending")
    director_service.respond(
        OTHER,
        "actual-director-death",
        owed["id"],
        owed["revision"],
        "death",
        "The actual original Director dies from the source's actual Asset hit",
    )
    service.submit(OTHER, "actual-owed-scoped-tag", grant.id, state(game).revision, "mess", effect)
    canon = state(game)
    tag = next(x for x in canon.sheets["2"].tags if x.id == grant.id + ":tag")
    assert tag.giver == 3 and tag.giver_actor is None and tag.giver_character is None
    assert tag.gm_setter_grant == grant.id and tag.gm_setter_appointment == grant.appointment
    assert (
        canon.handler == 1
        and game.inspect(PLAYER, action)["state"] == "complete"
        and game.dice.calls == 1
    )
    with ledger.engine.connect() as c:
        assert ooc_setter(c, ledger, victim, tag) == 3
        with pytest.raises(WorkflowError, match="SOURCE_GM_TAG_SETTER_MISSING"):
            ooc_setter(c, ledger, victim, tag.model_copy(update={"gm_setter_grant": str(uuid4())}))
    before = canon.model_dump_json()
    with pytest.raises(WorkflowError):
        with ledger.transaction() as c:
            forged = state(game)
            forged.sheets["2"].tags.append(
                TagState(
                    id="forged-outside-scope",
                    label="Forged",
                    giver=3,
                    gm_setter_appointment=grant.appointment,
                    gm_setter_grant=grant.id,
                )
            )
            game.event(c, 3, "no-arbitrary-scoped-principal", "synthetic.forged_tag", forged)
    assert state(game).model_dump_json() == before

    # Exercise the pure birth boundary with its explicit synthetic owner choices;
    # full real-user Void dialogs are covered by the Harpy mandatory-Defeat test.
    from girlframe.engine import m3_void
    from girlframe.engine.m3_void_state import HarpyAsset
    from girlframe.services.m3_actors import profiles

    birth = str(uuid4())
    with ledger.transaction() as c:
        original = state(game)
        patient = current_ref(original, 2)
        sheet = original.sheets["2"]
        # Isolate this pure retention boundary from Mockingbird's separately
        # tested optional resistance workflow with an explicit ALPHA fixture.
        sheet.girl = "ALPHA"
        for asset in sheet.assets:
            if asset.family == "girl":
                asset.void = True
        evolving, threshold = m3_void.start_threshold(
            original,
            profiles(c, ledger.campaign_id),
            patient,
            "girl",
            "synthetic-threshold-source",
            "synthetic-threshold-work",
        )
        evolving = m3_void.begin_questions(
            evolving,
            profiles(c, ledger.campaign_id),
            threshold.id,
            sheet.identities[0].id,
            "synthetic-owned-entry",
            "Explicit synthetic original-owner entry",
        )
        for index in range(5):
            evolving = m3_void.answer_question(
                evolving,
                threshold.id,
                2,
                False,
                "synthetic-owned-answer-" + str(index),
                honest=True,
            )
        born = m3_void.rebirth(
            evolving,
            profiles(c, ledger.campaign_id),
            threshold.id,
            birth,
            harpy_id="source-scope-retained-harpy",
            new_vessel="actual-different-body",
            archive_id=str(uuid4()),
            profile_id=sheet.character_id,
            profile_revision=sheet.source_profile_revision,
            retained_identities=(),
            new_identities=(),
            retained_tags=(tag.id,),
            retained_plays=(),
            owned_plays=(),
            discarded_bonds=(),
            assets=tuple(
                HarpyAsset(
                    **x.model_dump()
                    | {
                        "void": True,
                        "description": "Explicit synthetic original-owner rewritten Asset",
                    }
                )
                for x in sheet.assets
            ),
            account="Explicit synthetic owner chooses this same-person new body",
        )
        game.event(
            c,
            2,
            "synthetic-actual-tag-retention",
            "synthetic.actual_harpy_birth",
            born,
            event_id=birth,
        )
    harpy = state(game).harpy_states[-1]
    retained = next(x for x in harpy.tags if x.id == tag.id)
    assert retained.gm_setter_grant == grant.id and retained.gm_setter_event == tag.gm_setter_event
    with ledger.engine.connect() as c:
        assert (
            ooc_setter(c, ledger, ActorRef(kind="external_pilot", entity=harpy.id), retained) == 3
        )


def test_new_and_old_ordinary_forms_cannot_jump_a_pending_owned_play(ledger):
    from test_handler_plays import begin, ready
    from test_m2_game import start

    service, game = ready(ledger)
    original = begin(service, game)
    pending = start(game)
    before = state(game).model_dump_json()
    effect = Effect(
        kind="status",
        target=current_ref(state(game), 2),
        status=-1,
        account="An old ordinary form cannot interrupt this held Play",
    )
    with pytest.raises(WorkflowError, match="pending Play"):
        service.submit(
            ADMIN, "old-form-cannot-jump", original, state(game).revision, "mess", effect
        )
    with pytest.raises(WorkflowError, match="pending Play"):
        service.start(
            ADMIN, "new-form-cannot-jump", state(game).revision, (current_ref(state(game), 2),)
        )
    assert state(game).model_dump_json() == before and game.dice.calls == 0
    assert game.inspect(PLAYER, pending)["state"] == "acquiring"


def test_system_audit_can_preserve_state_but_cannot_authenticate_a_new_scoped_tag(
    ledger, monkeypatch
):
    from girlframe.engine import m3_handler_plays as rules

    game, _, _, _, _, grant, _ = source(ledger, monkeypatch)
    with ledger.transaction() as c:
        current = state(game)
        game.event(
            c, "maintenance-system", "actual-maintenance-audit", "system.maintenance", current
        )
    preserved = state(game)
    assert next(x for x in preserved.handler_plays if x.id == grant.id).state == "pending"
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.command_key == "actual-maintenance-audit"
                )
            )
            == "maintenance-system"
        )
    before = preserved.model_dump_json()
    event = str(uuid4())
    effect = Effect(
        kind="tag",
        target=current_ref(preserved, 2),
        tag="Not a system principal",
        account="A maintenance actor cannot impersonate this actual source judge",
    )
    staged = rules.select(preserved, grant.id, "mess", effect, event)
    staged = rules.direct(staged, grant.id, event)
    staged = rules.complete(staged, grant.id, event)
    with pytest.raises(WorkflowError, match="actual human judge"):
        with ledger.transaction() as c:
            game.event(
                c,
                "maintenance-system",
                "cannot-sign-as-the-judge",
                "m3.handler_play_applied",
                staged,
                event_id=event,
                grant_id=grant.id,
                play="mess",
            )
    assert state(game).model_dump_json() == before
