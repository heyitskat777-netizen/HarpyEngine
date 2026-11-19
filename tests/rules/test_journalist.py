"""An actual Journalist question through the native role and private Inbox."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_world_service import ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_journalist import RULES, questions
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_journalist import JournalistService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("reply", ["answer", "decline", "withdraw"])
@pytest.mark.parametrize("job", ["journalist", "family"])
def test_owned_npc_request_awards_a_real_tag_only_after_the_original_trigger(
    ledger, tmp_path, monkeypatch, reply, job
):
    world, game = ready(ledger)
    reporter = ActorRef(kind="npc", entity="original-reporter")
    world.npc(
        ADMIN,
        "reporter",
        state(game).revision,
        Npc(
            id=reporter.entity,
            name="PRIVATE_REPORTER",
            jobs=(job,),
            detail="An actual Journalist.",
            cell=(0, 0),
            controller=ADMIN.user_id,
        ),
    )
    cast = CastService(ActorService(world.missions))
    change(cast, ADMIN, "join", reporter)
    service = JournalistService(game)
    approved(ledger, game, tmp_path, monkeypatch)
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.targets(ADMIN, 900, reporter, job=job)
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULES[job],))
    cast = CastService(ActorService(MissionService(ledger)))
    assert service.targets(OTHER, 900, reporter, job=job)["targets"] == ()
    question = "PRIVATE_QUESTION"
    tag = "PRIVATE_REFUSAL_TAG"
    before = state(game).sheets["2"].tags

    async def native_ask():
        click = current(ADMIN.user_id, 89920)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        token = next(x for x, _ in menu.options if x.startswith(job + ":"))
        opening = current(ADMIN.user_id, 89921)
        await opening.response.defer(ephemeral=True)
        await menu.open_item(opening, token)
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(girl=("2",), question=question, tag=tag)
        await form.confirm.callback(current(ADMIN.user_id, 89922))
        assert form.completed

    revision = state(game).revision
    asyncio.run(native_ask())
    saved = service.ask(ADMIN, "89922", 900, revision, reporter, 2, question, tag, job=job)
    identity = saved["id"]
    assert saved["state"] == "pending" and state(game).sheets["2"].tags == before
    assert tag not in str(service.view(PLAYER, identity))
    assert not any(x.identity == identity for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="original NPC controller and Girl"):
        service.view(OTHER, identity)
    with pytest.raises(WorkflowError, match="actual addressed Girl"):
        service.respond(ADMIN, "forged-answer", identity, state(game).revision, "decline", "")
    with pytest.raises(WorkflowError, match="STALE_QUESTION"):
        service.respond(PLAYER, "stale-response", identity, revision, "decline", "")
    if reply == "withdraw":
        change(cast, ADMIN, "withdraw", reporter)
        assert not service.view(PLAYER, identity)["can_answer"]
        assert state(game).sheets["2"].tags == before
        with pytest.raises(WorkflowError, match="STALE_QUESTION"):
            service.respond(PLAYER, "revoked", identity, state(game).revision, "decline", "")
        return

    ledger.safety(OTHER, "pause-question", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(PLAYER, "paused-answer", identity, state(game).revision, "decline", "")
    ledger.safety(OTHER, "resume-question", ledger.status(OTHER)["revision"], pause=False)
    text = "PRIVATE_ACTUAL_REPLY" if reply == "answer" else ""
    revision = state(game).revision

    async def native_reply():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.identity == identity)
        assert item.task == "m3_journalist"
        assert ("Family" in item.title) == (job == "family")
        click = current(PLAYER.user_id, 89923)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert (
            isinstance(form, NativeForm)
            and clean(question) in form.instructions
            and clean(tag) not in form.instructions
        )
        form.values.update(response=(reply,), reply=text)
        await form.confirm.callback(current(PLAYER.user_id, 89924))
        assert form.completed

    asyncio.run(native_reply())
    assert service.respond(PLAYER, "89924", identity, revision, reply, text)["response"] == reply
    ledger.engine.dispose()
    current_state = state(game)
    (case,) = questions(current_state)
    assert case.reply == text and case.response == reply and case.job == job
    assert service.view(ADMIN, identity)["reply"] == text
    tags = current_state.sheets["2"].tags
    if reply == "decline":
        assert (
            len(tags) == len(before) + 1
            and tags[-1].label == tag
            and tags[-1].giver_actor == reporter
        )
    else:
        assert tags == before
    assert game.dice.calls == 0
