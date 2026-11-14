"""One earned lesson, original group source, every independent consent and real Mentors."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_newgirl_sex import choose
from test_physical_operations import place
from test_vatgrown_plays import (
    _actual_newgirl_teacher_vatgrown_sex_learner,
    _learned_sex_interaction,
    native_choice,
)

from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.engine.m3_mentorship import active_mentors, current_set
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_newgirl_sex import NewgirlSexService, prove_mentor_set
from girlframe.services.onboarding import WorkflowError


def test_earned_newgirl_group_independent_decline_reoffer_all_consent_and_once_use(
    ledger, tmp_path, monkeypatch
):
    import test_creation_review as creation_fixture

    original_ready = creation_fixture.ready

    def ready_with_original_third(store, *args, **kwargs):
        review, creation, extra = original_ready(store, *args, **kwargs)
        third_draft(store)
        own = creation.get(PLAYER)
        draft = own.draft.model_copy(
            update={
                "prior_missions": tuple(
                    PriorMission(user_id=uid, character_revision=row["revision"], missions=0)
                    for uid, row in creation.cadre(PLAYER).items()
                ),
                "cadre_discussed": True,
            }
        )
        creation.save(PLAYER, str(uuid4()), own.revision, store.draft(PLAYER)["revision"], draft)
        return review, creation, extra

    monkeypatch.setattr(creation_fixture, "ready", ready_with_original_third)
    game, worker, gateway, controls = _actual_newgirl_teacher_vatgrown_sex_learner(
        ledger, tmp_path, monkeypatch
    )
    teacher, learner = current_ref(state(game), 2), current_ref(state(game), 3)
    source = controls.invite(
        OTHER, str(uuid4()), 900, teacher, state(game).revision, "Actual original learning source"
    )["id"]
    controls.respond(
        PLAYER, str(uuid4()), source, state(game).revision, True, "My own participation"
    )
    taught = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=source,
            heat=1,
            trigger_confirmed=True,
            context="Actual Newgirl teaches her own Play",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    original = state(game)
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        identities=(original.sheets["2"].identities[1].id,),
        replacements=(original.sheets["3"].identities[0].id,),
        play=(newgirl.RULE,),
        account="Actual native Newgirl lesson",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert lesson.actor == learner and game.inspect(OTHER, taught)["state"] == "complete"
    controls.send_away(
        PLAYER, str(uuid4()), source, state(game).revision, "Release the actual learner"
    )
    tick(worker, gateway, 6)

    # Real third character creation/review/activation, not a copied synthetic partner.
    review = CreationReviewService(ledger)
    checked = review.get(FOUR)
    assert checked.sheet.ready_for_rules_review, checked.sheet.issues
    review.save(FOUR, str(uuid4()), checked.saved_revision, checked.fingerprint)
    game.activate(FOUR, str(uuid4()), review.get(FOUR).fingerprint)
    with ledger.transaction() as connection:
        placed = place(state(game), 4, mode="outside_frame")
        game.event(connection, 1, str(uuid4()), "synthetic.original_third_body_position", placed)
    fourth = current_ref(state(game), 4)
    cast = CastService(ActorService(MissionService(ledger)))
    available_cast = cast.view(FOUR, 900)
    cast.change(
        FOUR,
        str(uuid4()),
        900,
        available_cast["game_revision"],
        available_cast["cast_revision"],
        "join",
        fourth,
    )
    service = NewgirlSexService(game)

    async def invite():
        opened = _learned_sex_interaction(3)
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("invite",)
        response = _learned_sex_interaction(3)
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(_learned_sex_interaction(1))
        form.values.update(
            partners=(teacher.token, fourth.token),
            lesson=(lesson.id,),
            account="PRIVATE actual learned group proposal",
        )
        sent = _learned_sex_interaction(3)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        return learned_sex_links(state(game))[-1]

    first = asyncio.run(invite())
    assert newgirl.get(state(game), first.session).partners == (teacher, fourth)
    service.confirm(
        PLAYER, str(uuid4()), first.session, state(game).revision, True, "Only my consent"
    )
    partial = state(game)
    assert newgirl.get(partial, first.session).phase == "invited"
    with ledger.engine.connect() as connection:
        link = prove(game, connection, partial, first.id)
        assert link.accepted is None and link.consent_event is None and link.roll_event is None
        assert not lessons(game, connection, partial, learner, newgirl.RULE)
    with pytest.raises(WorkflowError):
        game.begin(
            OTHER,
            str(uuid4()),
            900,
            partial.sheets["3"].revision,
            PlayInput(
                play=newgirl.PLAY,
                source_work=first.session,
                heat=0,
                context="Missing fourth person's consent",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == partial
    service.confirm(
        FOUR, str(uuid4()), first.session, state(game).revision, False, "My own refusal"
    )
    with ledger.engine.connect() as connection:
        assert prove(game, connection, state(game), first.id).released_kind == "declined"
        assert lessons(game, connection, state(game), learner, newgirl.RULE)[0]["id"] == lesson.id
    second = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.confirm(
            OTHER,
            str(uuid4()),
            second.session,
            state(game).revision,
            True,
            "Cannot consent for partners",
        )
    service.confirm(
        PLAYER, str(uuid4()), second.session, state(game).revision, True, "My fresh consent"
    )
    key, revision = str(uuid4()), state(game).revision
    confirmed = service.confirm(
        FOUR, key, second.session, revision, True, "My separate fresh consent"
    )
    assert (
        service.confirm(FOUR, key, second.session, revision, True, "My separate fresh consent")
        == confirmed
    )
    before, calls = state(game), game.dice.calls
    game.dice.faces = (3, 4)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        before.sheets["3"].revision,
        PlayInput(
            play=newgirl.PLAY,
            source_work=second.session,
            heat=1,
            context="PRIVATE actually confirmed group",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    for owner, human in ((2, PLAYER), (4, FOUR)):
        choose(game, OTHER, "newgirl_sex_ask", owner, text="Do you respect me?", native=True)
        choose(
            game,
            human,
            "newgirl_sex_respect",
            owner,
            options=("no",),
            text="My own actual answer",
            native=True,
        )
    final = state(game)
    assert newgirl.get(final, second.session).phase == "complete"
    assert game.inspect(OTHER, action)["state"] == "complete" and game.dice.calls == calls + 1
    assert final.sheets["3"].heat == before.sheets["3"].heat - 1
    assert active_mentors(final, learner) == (teacher, fourth)
    relation = current_set(final, learner)
    assert relation and relation.session == second.session
    with ledger.engine.connect() as connection:
        prove_mentor_set(game, connection, final, relation)
        used = prove(game, connection, final, second.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        assert not lessons(game, connection, final, learner, newgirl.RULE)
        assert prove(game, connection, final, first.id).released_kind == "declined"
    assert service.view(OTHER, second.session)["phase"] == "complete"
    with pytest.raises(WorkflowError):
        service.view(ADMIN, second.session)
    assert "PRIVATE" not in json.dumps(gateway.messages)
