"""Source-owned private Harpy encounter, native escape and actual transformation paths."""

import asyncio

import pytest
from test_harpy_actor_plays import ready
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_physical_operations import bindings, place
from test_privacy_game_delivery import PrivateGateway
from test_void_service import respond

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_harpy_intimacy import open_intimacy_choice
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m3_harpy_intimacy import RULE, HarpyIntimacyService, records
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("intense", [False, True])
def test_harpy_private_consent_escape_and_actual_consequences(ledger, intense):
    _, game, cast, harpy = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(activity_specialist_rules=policy.activity_specialist_rules | {RULE})
            )
        )
    )
    with ledger.transaction() as c:
        canon = place(state(game), OTHER.user_id, mode="outside_frame")
        recipient = current_ref(canon, OTHER.user_id)
        canon.sheets["3"].girl = "PRINCESS"
        canon.sheets["3"].girl_runtime = None
        if intense:
            canon = set_depth(canon, harpy, recipient, 2, "actual-intense-bond")
        else:
            family = [x for x in canon.sheets["3"].assets if x.family == "girl"]
            for x in family[:-1]:
                x.void = True
        game.event(c, ADMIN.user_id, "original-role-positions", "synthetic.position", canon)

    async def invite(click):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "intimacy:" + harpy.token)

    asyncio.run(submit_form(PLAYER, invite, dict(person=(recipient.token,)), 93532))
    (case,) = records(state(game))
    service = HarpyIntimacyService(game)
    inbox = InboxService(ledger)
    assert any(x.identity == case.id for x in inbox.items(OTHER))
    assert not any(x.identity == case.id for x in inbox.items(ADMIN))

    def native(choice, sequence, **values):
        asyncio.run(
            submit_form(
                OTHER,
                lambda click: open_intimacy_choice(click, service, case.id),
                dict(choice=(choice,)) | values,
                sequence,
            )
        )

    native("accept", 93536)
    if intense:
        native("stay", 93540)
        native("begin", 93544)
    else:
        worker, gateway = GameWorker(game), PrivateGateway()
        action = game.begin(
            OTHER,
            "harpy-private-escape",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                source_work=case.id,
                context="I try to escape this private encounter.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 5)
        for participant in (OTHER, PLAYER, ADMIN):
            answer(game, participant, "tag_window", options=("pass",))
        answer(game, OTHER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=False, text="The attempt does not get her out.")
        tick(worker, gateway, 5)
        (decided,) = records(state(game))
        assert decided.action == action and decided.escaped is False and decided.phase == "void"
        assert game.dice.calls == 1
        assert depth(state(game), harpy, recipient) == 1
        data = service.get(OTHER, case.id)
        asset = next(iter(data["assets"]))
        native(asset, 93544, account="The original Asset changes after the failed escape.")
        assert next(x for x in state(game).sheets["3"].assets if x.id == asset).void

    ledger.engine.dispose()
    (threshold,) = records(state(game))
    assert threshold.phase == "threshold" and threshold.work
    resolver = VoidService(ledger)
    view = resolver.get(OTHER, threshold.work)
    assert view["stage"] == "allured"
    with pytest.raises(WorkflowError):
        resolver.get(PLAYER, threshold.work)
    if intense:
        respond(
            resolver,
            threshold.work,
            "begin",
            dict(identity=view["identities"][0]["id"], account="I enter my original Frame."),
            viewer=OTHER,
        )
        assert resolver.get(OTHER, threshold.work)["stage"] == "questions"
        canon = state(game)
        assert resolve(canon, recipient, bindings(canon)).occupied_frame_instance == case.frame
        for _ in range(5):
            respond(
                resolver,
                threshold.work,
                "answer",
                dict(answer=False, honest=True, account="I choose this answer."),
                viewer=OTHER,
            )
        actual = resolver.get(OTHER, threshold.work)
        description = "I confirm my original character’s transformation."
        respond(
            resolver,
            threshold.work,
            "rebirth",
            dict(
                choice=actual["rebirth_choice"]
                | dict(new_identities=["Free to decide"], account=description),
                account=description,
            ),
            viewer=OTHER,
        )
        assert records(state(game))[0].phase == "complete"
