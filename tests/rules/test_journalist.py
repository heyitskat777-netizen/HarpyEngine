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
@pytest.mark.parametrize("job", ["journalist", "family", "public_relations"])
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
            detail="An actual NPC with a scene role.",
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
    explanation = "PRIVATE_ACTUAL_REPLY" if reply == "answer" or job == "public_relations" else ""
    unmark = None
    locked = None
    if job == "public_relations":
        with ledger.transaction() as c:
            canon = state(game)
            sheet = canon.sheets["2"]
            sheet.identities[0].marked = sheet.identities[1].marked = True
            locked = sheet.identities[1].id
            sheet.sedation_locked = (locked,)
            if reply == "answer":
                unmark = sheet.identities[0].id
            game.event(c, 1, "original-marks", "synthetic.existing_marks", canon)
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
    assert service.view(ADMIN, identity)["marked_identities"] == ()
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
    revision = state(game).revision
    if job == "public_relations" and reply == "answer":
        with pytest.raises(WorkflowError, match="eligible marked Identity"):
            service.respond(
                PLAYER, "locked", identity, revision, "answer", explanation, unmark=locked
            )
        with pytest.raises(WorkflowError, match="eligible marked Identity"):
            service.respond(PLAYER, "no-owned-effect", identity, revision, "answer", explanation)
        assert questions(state(game))[0].response is None

    async def native_reply():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.identity == identity)
        assert item.task == "m3_journalist"
        assert ("Family" in item.title) == (job == "family")
        assert ("Public Relations" in item.title) == (job == "public_relations")
        click = current(PLAYER.user_id, 89923)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert (
            isinstance(form, NativeForm)
            and clean(question) in form.instructions
            and clean(tag) not in form.instructions
        )
        form.values.update(response=(reply,), reply=explanation)
        if unmark is not None:
            assert next(field for field in form.fields if field.key == "unmark").options == (
                (unmark, state(game).sheets["2"].identities[0].name),
            )
            form.values["unmark"] = (unmark,)
        await form.confirm.callback(current(PLAYER.user_id, 89924))
        assert form.completed

    asyncio.run(native_reply())
    assert (
        service.respond(PLAYER, "89924", identity, revision, reply, explanation, unmark=unmark)[
            "response"
        ]
        == reply
    )
    ledger.engine.dispose()
    current_state = state(game)
    (case,) = questions(current_state)
    assert case.reply == explanation and case.response == reply and case.job == job
    assert case.unmarked_identity == unmark
    assert service.view(ADMIN, identity)["reply"] == explanation
    if job == "public_relations":
        assert current_state.sheets["2"].identities[0].marked == (reply != "answer")
        assert current_state.sheets["2"].identities[1].marked
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
