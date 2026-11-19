"""The original qualified Harpy Play opens a new private consent decision."""

import asyncio

import pytest
from test_harpy_flirt import native_answer, prepared, start_native, submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_harpy_intimacy import open_intimacy_choice
from girlframe.discord_adapter.m3_harpy_kiss import open_surprise
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine.m3_harpy_advancements import KISS
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.services.inbox import InboxService
from girlframe.services.m3_harpy_advancements import HarpyAdvancementService
from girlframe.services.m3_harpy_intimacy import RULE as INTIMACY
from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService
from girlframe.services.m3_harpy_intimacy import records as encounters
from girlframe.services.m3_harpy_kiss import KissService, records
from girlframe.services.onboarding import WorkflowError


def test_outside_harpy_original_surprise_play_requires_private_gm_and_girl_decisions(ledger):
    _, game, cast, actor, worker, gateway = prepared(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    activity_specialist_rules=policy.activity_specialist_rules | {KISS, INTIMACY}
                )
            )
        )
    )
    HarpyAdvancementService(ledger).select(
        PLAYER, "learn-actual-kiss", actor.entity, state(game).revision, KISS
    )
    with ledger.transaction() as c:
        canon = update(state(game), actor, linked=False)
        game.event(c, PLAYER.user_id, "actually-outside-frame", "synthetic.harpy_position", canon)
    action = start_native(game, actor, worker, gateway)
    owned_id = harpy(state(game), actor).identities[0].id
    target_id = state(game).sheets["3"].identities[0].id
    native_answer(
        game, PLAYER, "harpy_flirt_actor", dict(options=("name",), denied=(owned_id,)), 93572
    )
    native_answer(
        game,
        OTHER,
        "harpy_flirt_target",
        dict(options=("fears",), denied=(target_id,), text="Her actual response."),
        93576,
    )
    native_answer(
        game, PLAYER, "harpy_flirt_answer", dict(text="Original Harpy’s factual answer."), 93580
    )
    tick(worker, gateway, 5)
    service = KissService(game)
    assert action in service.menu(PLAYER, 900, actor)["actions"]

    async def open_choice(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "kiss:" + actor.token)

    asyncio.run(
        submit_form(
            PLAYER,
            open_choice,
            dict(action=(action,), choice=("kiss",), account="The original Play surprised her."),
            93584,
        )
    )
    (review,) = records(state(game))
    assert review.action == action and not encounters(state(game))
    inbox = InboxService(ledger)
    assert any(x.identity == review.id and x.task == "m3_harpy_kiss" for x in inbox.items(ADMIN))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, review.id)
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_surprise(click, service, review.id),
            dict(choice=("yes",)),
            93588,
        )
    )
    ledger.engine.dispose()
    (actual,) = encounters(state(game))
    assert actual.kiss == review.id and actual.phase == "consent"
    assert not actual.consent
    intimacy = HarpyIntimacyService(game)
    assert any(
        x.identity == actual.id and x.task == "m3_harpy_intimacy" for x in inbox.items(OTHER)
    )
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_intimacy_choice(click, intimacy, actual.id),
            dict(choice=("decline",)),
            93592,
        )
    )
    assert encounters(state(game))[0].phase == "complete" and not encounters(state(game))[0].consent
    assert action not in service.menu(PLAYER, 900, actor)["actions"]
