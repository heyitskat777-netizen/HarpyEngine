"""Real earned lesson, original group, separate consent and one primary printed outcome."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_physical_operations import place
from test_vatgrown_plays import _learn_daily_source, _learned_sex_interaction, ready

from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_learned_mockingbird_group_partial_refusal_fresh_consent_primary_and_once_use(
    ledger, tmp_path, monkeypatch
):
    import test_m2_game as game_fixture

    from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
    from girlframe.discord_adapter.m3_mockingbird_plays import open_request
    from girlframe.discord_adapter.m3_mockingbird_sex import open_sex
    from girlframe.engine import m3_mockingbird as mockingbird
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_learned_play_state import learned_sex_links
    from girlframe.engine.m3_mockingbird_state import SEX
    from girlframe.services.m3_learned_sex import lessons, prove, source_id
    from girlframe.services.m3_mockingbird_effects import source_trigger
    from girlframe.services.m3_mockingbird_plays import MockingbirdService

    original_ready = game_fixture.ready

    def ready_with_original_third(store, *args, **kwargs):
        review, creation, extra = original_ready(store, *args, **kwargs)
        third_draft(store)
        return review, creation, extra

    monkeypatch.setattr(game_fixture, "ready", ready_with_original_third)
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, mockingbird.SEX),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, mockingbird.SEX)
    learner, target = current_ref(state(game), 2), current_ref(state(game), 3)
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
    service = MockingbirdService(game)

    def native_invitation():
        async def invite():
            opened = _learned_sex_interaction()
            await opened.response.defer(ephemeral=True)
            await open_learned_sex(opened, game, identity=lesson.id)
            form = opened.edit_original_response.call_args.kwargs["view"]
            assert dict(next(x for x in form.fields if x.key == "play").options) == {
                SEX: "Sex Play"
            }
            assert not await form.interaction_check(_learned_sex_interaction(3))
            form.values.update(
                play=(SEX,),
                targets=(target.token, fourth.token),
                primary=(target.token,),
                account="PRIVATE_LEARNED_MOCK Our own actual voluntary physical source",
            )
            sent = _learned_sex_interaction()
            await form.confirm.callback(sent)
            assert form.completed, (
                sent.response.events,
                sent.edit_original_response.call_args_list,
            )
            saved = state(game)
            await form.confirm.callback(sent)
            assert state(game) == saved

        asyncio.run(invite())
        return learned_sex_links(state(game))[-1]

    first = native_invitation()
    with pytest.raises(WorkflowError):
        service.get(ADMIN, first.session)
    service.attest(OTHER, str(uuid4()), first.session, target, True)
    partial = state(game)
    with ledger.engine.connect() as c:
        pending = prove(game, c, partial, first.id)
        assert pending.accepted is None and pending.consent_event is None
        assert not lessons(game, c, partial, learner, mockingbird.SEX)
    assert (
        next(x for x in partial.mockingbird.triggers if x.id == first.session).state == "proposed"
    )
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            partial.sheets["2"].revision,
            PlayInput(
                play=SEX,
                source_work=first.session,
                heat=1,
                trigger_confirmed=True,
                context="One answer is not group consent",
            ),
        )
    assert state(game) == partial
    service.attest(FOUR, str(uuid4()), first.session, fourth, False)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), first.id).released_kind == "declined"
        assert lessons(game, c, state(game), learner, mockingbird.SEX)[0]["id"] == lesson.id
    link = native_invitation()
    assert link.id != first.id
    with pytest.raises(WorkflowError):
        service.attest(PLAYER, str(uuid4()), link.session, fourth, True)
    service.attest(OTHER, str(uuid4()), link.session, target, True)
    key = str(uuid4())
    response = service.attest(FOUR, key, link.session, fourth, True)
    assert service.attest(FOUR, key, link.session, fourth, True) == response
    trigger = next(x for x in state(game).mockingbird.triggers if x.id == link.session)
    assert trigger.state == "ready" and trigger.parties[0].event
    assert trigger.learned_source is None and trigger.learned_sex_source == link.id
    before = state(game)
    heat, calls = before.sheets["2"].heat, game.dice.calls
    bond = depth(before, learner, target)
    game.dice.faces = (3, 4)

    async def start_native():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_request(opened, service, link.session, continue_source=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("1",), gain=("0",))
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.events,
            sent.edit_original_response.call_args_list,
        )

    asyncio.run(start_native())
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
        actual_action = game.action(c, action)
        assert source_id(actual_action) == link.id
        assert "learned_source" not in actual_action["data"]["mockingbird"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    raw = game.inspect(PLAYER, action)["receipt"]

    async def choose_starry():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_sex_select")
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_sex(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(option=("starry",), capability=("deception",))
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.events,
            sent.edit_original_response.call_args_list,
        )

    asyncio.run(choose_starry())
    actual = state(game)
    tag = next(x for x in actual.sheets["3"].tags if x.label == "Starry-Eyed")
    assert tag.giver_actor == learner and tag.giver == 2
    assert not any(x.label == "Starry-Eyed" for x in actual.sheets["4"].tags)
    assert actual.sheets["4"].assets == before.sheets["4"].assets
    assert mockingbird.starry_capabilities(actual, learner, target) == ("deception",)
    assert depth(actual, learner, target) == min(3, bond + 1)
    assert actual.sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert actual.sheets["3"].assets == before.sheets["3"].assets
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == raw
    with ledger.engine.connect() as c:
        used = prove(game, c, actual, link.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        assert not lessons(game, c, actual, learner, mockingbird.SEX)
        assert source_trigger(game, c, game.action(c, action), actual)[0].kind == "handler"
    assert service.get(PLAYER, link.session)["body"]["account"].startswith("PRIVATE_LEARNED_MOCK")
    with pytest.raises(WorkflowError):
        service.get(ADMIN, link.session)
    assert actual.sheets["2"].girl == "VATGROWN"
    assert not has_rule(actual.sheets["2"], mockingbird.SEX, "MOCKINGBIRD")
    assert not has_rule(actual.sheets["2"], mockingbird.PERSON, "MOCKINGBIRD")
    assert "PRIVATE_LEARNED_MOCK" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)
