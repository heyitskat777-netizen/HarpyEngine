"""An actual Speak installation binds private answers and the printed high refusal."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.m3_trainer_control import CHOICE
from girlframe.services.m3_trainer_phrases import HEAR, SPEAK
from girlframe.services.onboarding import WorkflowError


def create_trainer(ledger, *, start_with_speak, dog_prompt=None):
    creation = HandlerCreationService(ledger)
    approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"plays", "playbooks"})
            ),
            owner_m3_rulings=rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    draft = complete(creation, "Trainer")
    if start_with_speak or dog_prompt is not None:
        ace, dog = draft.starting
        prompt = 2 if start_with_speak else dog_prompt
        draft = draft.model_copy(
            update=dict(starting=(ace, dog.model_copy(update=dict(prompt=prompt))))
        )
    save(creation, draft)
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "speak-trainer", preview["revision"], preview["game_revision"], True)


@pytest.mark.parametrize("character_answer", ("trainer_yes", "trainer_understands"))
def test_private_trainer_source_installs_speak_or_erases_only_the_owned_identity(
    ledger, character_answer
):
    from girlframe.engine.m3_handler_private_scene import records

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False)
    game.leave_scene(PLAYER, "private-trainer-scene", 900)
    service = HandlerPrivateSceneService(ledger, game)
    inbox = InboxService(ledger)

    async def offer():
        click = current(1, 49300)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "trainer_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49301)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(offer())
    (value,) = records(state(game))
    assert value.playbook == "Trainer"
    assert not any(x.identity == value.id for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError):
        service.menu(PLAYER, value.id)

    async def native(viewer, number, step, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == value.id)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=(step,), **values)
        sent = current(viewer.user_id, number + 1)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(native(OTHER, 49310, "consent"))
    asyncio.run(native(ADMIN, 49312, "attest"))
    asyncio.run(native(OTHER, 49314, "attest"))
    asyncio.run(native(ADMIN, 49316, "trainer_ask"))
    before = state(game)
    identities = tuple(before.sheets["3"].identities)
    assert not service.menu(ADMIN, value.id)["identities"] and identities
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN, "cannot-answer-for-girl", value.id, before.revision, character_answer
        )
    with pytest.raises(WorkflowError, match="current private choice"):
        service.respond(OTHER, "old-answer", value.id, before.revision - 1, character_answer)
    selector = {}
    if character_answer == "trainer_understands":
        with pytest.raises(WorkflowError, match="SOURCE_IDENTITY_REQUIRED"):
            service.respond(
                OTHER, "fake-id", value.id, before.revision, character_answer, text="different-body"
            )
        selector["identity"] = (identities[0].id,)
    asyncio.run(native(OTHER, 49320, character_answer, **selector))
    if selector:
        assert service.menu(OTHER, value.id)["outcome"] == "identity_erased"
        assert state(game).sheets["3"].identities == list(identities[1:])
        assert state(game).handler_persona.conditioning == before.handler_persona.conditioning
        return

    assert service.menu(ADMIN, value.id)["phase"] == "trainer_install"
    assert state(game).sheets["3"].identities == list(identities)
    ledger.engine.dispose()
    revision = state(game).revision
    asyncio.run(native(ADMIN, 49322, "install_speak"))
    assert (
        service.respond(ADMIN, "49323", value.id, revision, "install_speak")["phase"] == "complete"
    )
    (finished,) = records(state(game))
    assert finished.outcome == "speak_installed"
    worker, gateway = GameWorker(game), Gateway()
    made = game.issue_order(
        ADMIN,
        "private-trained-speak",
        900,
        3,
        "What happened in the briefing?",
        conditioning_phrase="speak",
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    answer(game, OTHER, SPEAK, text="I wrote this account myself.")
    answer(game, ADMIN, HEAR, flag=True)
    tick(worker, gateway, 4)
    assert game.inspect(OTHER, made["action_id"])["state"] == "complete"


@pytest.mark.parametrize("reaction", ("obeyed", "high", "mid"))
def test_original_speak_order_uses_its_own_phrasing_and_saved_refusal(ledger, reaction):
    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=True)
    game.dice = Dice((6, 5) if reaction == "high" else (4, 5))
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)
    issuer = PLAYER if reaction == "obeyed" else ADMIN
    uninvolved = ADMIN if issuer == PLAYER else PLAYER
    with pytest.raises(WorkflowError, match="installed Speak"):
        game.issue_order(
            ADMIN, "unconditioned", 900, 2, "Uninstalled.", conditioning_phrase="speak"
        )
    order = game.issue_order(
        issuer, "owned-speak", 900, 3, "PRIVATE_QUESTION", conditioning_phrase="speak"
    )
    tick(worker, gateway, 3)
    play = order["action_id"]
    if reaction == "obeyed":
        answer(game, OTHER, "order_response", options=("obedient",))
    else:
        answer(game, OTHER, "order_response", options=("disobey",))
        play = game.begin(
            OTHER,
            "refuse-speak",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="disobey_orders",
                context="I attempt to refuse the spoken question.",
                trigger_confirmed=True,
                heat=0,
                order_id=order["order_id"],
                parent=order["action_id"],
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        if reaction == "mid":
            answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
            answer(game, OTHER, CHOICE, options=("pass",))
        else:
            assert not any(x["kind"] == "actor_disobey" for x in game.choices(OTHER))
            assert state(game).order == (3, 2) and state(game).sheets["3"].heat == 2
        answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.dice.calls == int(reaction != "obeyed")
    if reaction == "mid":
        assert game.inspect(OTHER, play)["result"]["can_disobey"]
        assert not any(x["kind"] == SPEAK for x in game.choices(OTHER))
        assert state(game).order == (2, 3)
        return
    (asked,) = (x for x in game.choices(OTHER) if x["kind"] == SPEAK)
    assert "PRIVATE_QUESTION" in game.decision(OTHER, asked["id"])["conditioning_text"]
    with pytest.raises(WorkflowError):
        game.respond(
            issuer, "forge-speak", asked["id"], asked["revision"], ChoiceAnswer(text="Fake")
        )
    ledger.engine.dispose()

    async def native(viewer, work, sequence, **values):
        click = current(viewer.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == work["id"])
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        sent = current(viewer.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(native(OTHER, asked, 47200, text="PRIVATE_ORIGINAL_ANSWER"))
    (heard,) = (x for x in game.choices(issuer) if x["kind"] == HEAR)
    assert "PRIVATE_ORIGINAL_ANSWER" not in heard["body_json"]
    assert game.decision(issuer, heard["id"])["conditioning_text"] == "PRIVATE_ORIGINAL_ANSWER"
    for outsider in (OTHER, uninvolved):
        with pytest.raises(WorkflowError):
            game.decision(outsider, heard["id"])
    assert game.inspect(OTHER, play)["state"] != "complete"
    asyncio.run(native(issuer, heard, 47210, flag=("yes",)))
    receipt = game.respond(issuer, "47211", heard["id"], heard["revision"], ChoiceAnswer(flag=True))
    assert receipt["state"] == "complete"
    with pytest.raises(WorkflowError):
        game.respond(
            issuer, "stale-hearing", heard["id"], heard["revision"], ChoiceAnswer(flag=True)
        )
    assert game.inspect(OTHER, play)["state"] == "complete"
    if reaction == "high":
        result = game.inspect(OTHER, play)["result"]
        assert result["total"] == 11 and result["conditioning"] and not result["can_disobey"]
    with ledger.engine.connect() as c:
        saved = game.action(c, play)["data"]
        assert (
            saved["trainer_heard_event"]
            and saved["trainer_spoken"]["answer"] == "PRIVATE_ORIGINAL_ANSWER"
        )


@pytest.mark.parametrize("phrase", ("speak", "sit", "play_rough"))
def test_actual_off_duty_speak_installation_needs_both_originals_and_can_trigger(ledger, phrase):
    from test_physical_operations import place

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_trainer_phrases import sitting
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_trainer_phrases import SIT, grant_leave

    def before_period(game):
        create_trainer(ledger, start_with_speak=False)
        if phrase == "sit":
            with ledger.transaction() as c:
                actual = place(state(game), 3, mode="outside_frame")
                game.event(c, 1, "original-sit-placement", "synthetic.placement", actual)

    cycle, game, period = prepared(
        ledger,
        before_period=before_period,
    )
    activate(cycle, game, period)

    async def arrange():
        click = current(1, 47300)
        await click.response.defer(ephemeral=True)
        await open_action(click, cycle, period, "handler_scene")
        form = click.edit_original_response.call_args.kwargs["view"]
        assert "trainer_conditioning" in dict(form.fields[0].options)
        form.values.update(
            kind=("trainer_conditioning",),
            participants=("3",),
            summary="PRIVATE_TRAINING_SCENE",
        )
        if phrase != "speak":
            form.values["phrase"] = (phrase,)
        form.controls()
        sent = current(1, 47301)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(arrange())
    assert cycle.review(PLAYER, period)["handler_scene"] is None
    assert cycle.review(OTHER, period)["handler_scene"]["conditioning_phrase"] == phrase
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, period, "acknowledge", None)
    call(cycle, game, ADMIN, period, "acknowledge", None)
    assert not any(
        x.pilot.entity == "3" and phrase in x.phrases
        for x in state(game).handler_persona.conditioning
    )
    with pytest.raises(WorkflowError, match=f"installed {phrase.replace('_', ' ').title()}"):
        game.issue_order(
            ADMIN,
            "premature-speak-command",
            900,
            3,
            "Test",
            conditioning_phrase=phrase,
            phrase_target=2 if phrase == "play_rough" else None,
        )
    ledger.engine.dispose()
    pending = cycle.review(OTHER, period)

    async def attest():
        click = current(3, 47310)
        await click.response.defer(ephemeral=True)
        await open_action(click, cycle, period, "ack:handler")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        sent = current(3, 47311)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(attest())
    cycle.acknowledge(OTHER, "47311", period, pending["revision"], pending["game_revision"], None)
    spell = [
        x
        for x in state(game).handler_persona.conditioning
        if x.pilot.entity == "3" and phrase in x.phrases
    ]
    assert len(spell) == 1 and spell[0].pilot.entity == "3"
    assert spell[0].source_event != state(game).handler_persona.source_event
    worker, gateway = GameWorker(game), Gateway()
    issued = game.issue_order(
        ADMIN,
        "later-valid-speak",
        900,
        3,
        "PRIVATE_FOLLOWUP",
        conditioning_phrase=phrase,
        phrase_target=2 if phrase == "play_rough" else None,
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("immediate",))
    if phrase == "speak":
        answer(game, OTHER, SPEAK, text="Yes.")
        answer(game, ADMIN, HEAR, flag=True)
    elif phrase == "sit":
        girl = current_ref(state(game), 3)
        assert sitting(state(game), girl) is None
        choice = next(x["id"] for x in game.choices(OTHER) if x["kind"] == SIT)
        item = next(x for x in InboxService(ledger).items(OTHER) if x.identity == choice)

        async def sit_from_inbox():
            click = current(3, 47320)
            await click.response.defer(ephemeral=True)
            await InboxView(InboxService(ledger), 3).route(click, item)
            form = click.edit_original_response.call_args.kwargs["view"]
            form.values["text"] = "I sit where I stand."
            sent = current(3, 47321)
            await form.confirm.callback(sent)
            assert form.completed, sent.followup.send.call_args

        asyncio.run(sit_from_inbox())
        tick(worker, gateway, 4)
        ledger.engine.dispose()
        active = state(game)
        assert sitting(active, girl).order == issued["order_id"]
        movement = MovementService(game)
        with pytest.raises(WorkflowError, match="requires leave"):
            movement.move(
                OTHER, "while-seated", active.revision, 900, girl, (1, 0), account="I move."
            )
        with pytest.raises(WorkflowError, match="original Sit issuer"):
            grant_leave(game, PLAYER, "wrong-leave", 900, 3)
        grant_leave(game, ADMIN, "actual-leave", 900, 3)
        assert sitting(state(game), girl) is None
        assert movement.move(
            OTHER, "after-leave", state(game).revision, 900, girl, (1, 0), account="I move."
        )["destination"] == [1, 0]
    else:
        from test_harpy_flirt import submit_form

        from girlframe.services.m3_trainer_phrases import ROUGH_HEARD, ROUGH_OFFER, ROUGH_REPLY

        original = state(game)
        inbox = InboxService(ledger)

        def native(viewer, kind, answer_flag, number):
            (pending,) = (x for x in game.choices(viewer) if x["kind"] == kind)
            with pytest.raises(WorkflowError):
                game.decision(ADMIN, pending["id"])

            async def route(click):
                item = next(x for x in inbox.items(viewer) if x.identity == pending["id"])
                await InboxView(inbox, viewer.user_id).route(click, item)

            return asyncio.run(submit_form(viewer, route, dict(flag=(answer_flag,)), number))

        assert not any(x["kind"] == ROUGH_REPLY for x in game.choices(PLAYER))
        native(OTHER, ROUGH_OFFER, "yes", 47360)
        ledger.engine.dispose()
        native(PLAYER, ROUGH_REPLY, "no", 47364)
        (receipt,) = (x for x in game.choices(OTHER) if x["kind"] == ROUGH_HEARD)
        assert "declined" in game.decision(OTHER, receipt["id"])["conditioning_text"]
        native(OTHER, ROUGH_HEARD, "yes", 47368)
        actual = state(game)
        assert actual.sheets == original.sheets and actual.bonds == original.bonds
        assert game.dice.calls == 0
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"


def test_play_gentle_requires_the_original_girls_flirt_with_the_issued_target(ledger):
    from girlframe.services.m3_trainer_phrases import FLIRT

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=True)
    worker, gateway = GameWorker(game), Gateway()
    issued = game.issue_order(
        ADMIN,
        "gentle",
        900,
        3,
        "Approach the nominated Girl.",
        conditioning_phrase="play_gentle",
        phrase_target=2,
    )
    parent = issued["action_id"]
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    (choice,) = (x for x in game.choices(OTHER) if x["kind"] == FLIRT)
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, choice["id"])
    with pytest.raises(WorkflowError, match="original Play Gentle Flirt"):
        game.begin(
            OTHER,
            "replacement-play",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                context="I try something else.",
                trigger_confirmed=True,
                heat=0,
                parent=parent,
            ),
        )
    assert game.inspect(OTHER, parent)["state"] != "complete" and game.dice.calls == 0
    ledger.engine.dispose()

    async def start_from_inbox():
        click = current(3, 47340)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(OTHER) if x.identity == choice["id"])
        await InboxView(inbox, 3).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert tuple(key for key, _ in fields["play"].options) == ("flirt",)
        assert tuple(key for key, _ in fields["target"].options) == ("2",)
        form.values.update(
            play=("flirt",),
            gain=("0",),
            pair_share=("0",),
            heat=("0",),
            piloting=("no",),
            trigger=("yes",),
            context="I actually Flirt.",
        )
        sent = current(3, 47341)
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args,
            sent.followup.send.call_args,
            sent.edit_original_response.call_args,
        )

    asyncio.run(start_from_inbox())
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_flirt", options=("name",))
    assert game.inspect(OTHER, parent)["state"] != "complete"
    answer(game, PLAYER, "target_flirt", text="My actual reply.")
    assert game.inspect(OTHER, parent)["state"] == "complete" and game.dice.calls == 1
    assert any(
        x.kind == "flirt_followthrough" and x.owner == 3 and x.target == 2
        for x in state(game).obligations
    )


def test_heel_ends_the_prior_sit_and_waits_for_real_movement_to_the_issuer(ledger):
    from test_harpy_flirt import submit_form
    from test_physical_operations import place

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_trainer_phrases import pending_heel, sitting
    from girlframe.services.m3_trainer_phrases import HEEL, SIT

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False, dog_prompt=0)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    with ledger.transaction() as c:
        placed = place(
            place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame", cell=(1, 0)
        )
        game.event(c, 1, "heel-original-positions", "synthetic.placement", placed)
    girl = current_ref(state(game), 3)
    worker, gateway = GameWorker(game), Gateway()
    game.issue_order(ADMIN, "prior-sit", 900, 3, "Sit here.", conditioning_phrase="sit")
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    answer(game, OTHER, SIT, text="I sit here.")
    tick(worker, gateway, 4)
    assert sitting(state(game), girl) is not None
    issued = game.issue_order(
        PLAYER, "heel-order", 900, 3, "Come to my side.", conditioning_phrase="heel"
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("immediate",))
    before = state(game).placements
    answer(game, OTHER, HEEL, text="I get up to come over.")
    tick(worker, gateway, 4)
    ledger.engine.dispose()
    held = state(game)
    assert sitting(held, girl) is None and held.placements == before
    work = pending_heel(held, girl)
    assert work.order == issued["order_id"]
    inbox = InboxService(ledger)
    assert not any(item.task == "trainer_heel" for item in inbox.items(PLAYER))

    async def route(click):
        item = next(item for item in inbox.items(OTHER) if item.task == "trainer_heel")
        await InboxView(inbox, 3).route(click, item)

    asyncio.run(
        submit_form(
            OTHER,
            route,
            dict(
                actor=(girl.token,),
                mode=("body",),
                x=("0",),
                y=("0",),
                account="I walk to her side.",
            ),
            47380,
        )
    )
    after = state(game)
    assert pending_heel(after, girl) is None
    original = next(x for x in before if x.actor == girl)
    actual = next(x for x in after.placements if x.actor == girl)
    assert actual.girl_cell == (0, 0) and actual.frame_cell == original.frame_cell
    assert game.dice.calls == 0


def test_hunt_requires_its_exact_assault_and_earns_one_engage_maneuver(ledger):
    from test_physical_operations import place

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_trainer_phrases import HUNT

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False, dog_prompt=1)
    game.dice.faces = (4, 5)
    with ledger.transaction() as c:
        game.event(
            c, 1, "hunt-original-positions", "synthetic.placement", place(place(state(game), 2), 3)
        )
    target = current_ref(state(game), 2)
    worker, gateway = GameWorker(game), Gateway()
    parent = game.issue_order(
        ADMIN,
        "hunt-order",
        900,
        3,
        "Assault this target.",
        conditioning_phrase="hunt",
        phrase_actor=target.token,
    )["action_id"]
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    (choice,) = (x for x in game.choices(OTHER) if x["kind"] == HUNT)
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, choice["id"])
    inbox = InboxService(ledger)
    ledger.engine.dispose()

    async def open_hunt():
        click = current(3, 47390)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(OTHER) if x.identity == choice["id"])
        await InboxView(inbox, 3).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert tuple(key for key, _ in fields["play"].options) == ("all_out_assault",)
        assert tuple(key for key, _ in fields["target"].options) == (target.token,)

    asyncio.run(open_hunt())
    battle = BattleService(ledger)
    data = battle.preview(OTHER, 900)
    by_entity = {x["ref"]["entity"]: x for x in data["actors"]}
    attacker, opponent = by_entity["3"], by_entity["2"]
    declaration = Declaration(
        play="all_out_assault",
        actor=current_ref(state(game), 3),
        target=target,
        attacking_asset=attacker["assets"][0]["id"],
        target_asset=opponent["assets"][0]["id"],
        actor_sha256=attacker["sha256"],
        target_sha256=opponent["sha256"],
        account="I open with the declared Asset against the exact target.",
    )
    context = battle.propose(
        OTHER, "hunt-declare", data["revision"], 900, declaration, parent=parent
    )["id"]
    battle.confirm(
        ADMIN,
        "hunt-reach",
        state(game).revision,
        context,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="The opening and reach are established.",
    )
    child = game.begin(
        OTHER,
        "hunt-roll",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=target,
            parent=parent,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 5)
    pass_tags(game)
    assert game.inspect(OTHER, parent)["state"] != "complete"
    answer(
        game,
        OTHER,
        "engage_assault_extra",
        options=("protect",),
        fields={"protect": declaration.attacking_asset},
        text="I cover the withdrawal route.",
    )
    for member in (ADMIN, PLAYER, OTHER):
        answer(
            game, member, "battle_assault_table", flag=False, text="The defender stays in reach."
        )
    actual = state(game)
    assert next(x for x in actual.sheets["2"].assets if x.id == declaration.target_asset).damaged
    assert sum(x.get("kind") == "engage_maneuver" for x in actual.facts) == 1
    assert game.inspect(OTHER, parent)["state"] == game.inspect(OTHER, child)["state"] == "complete"
    assert game.dice.calls == 1


def test_protect_keeps_its_position_and_redirects_actual_damage_to_its_owners_asset(
    ledger, monkeypatch
):
    import test_mission_service
    from test_harpy_flirt import submit_form
    from test_intracadre_marriage import FOUR, setup_three
    from test_physical_operations import place

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_trainer_phrases import PROTECT
    from girlframe.services.m3_trainer_protect import CHOICE

    monkeypatch.setattr(test_mission_service, "setup_game", setup_three)
    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    game.leave_scene(PLAYER, "private-protect-scene-primary", 900)
    game.leave_scene(FOUR, "private-protect-scene-fourth", 900)
    private = HandlerPrivateSceneService(ledger, game)
    case = private.invite(
        ADMIN, "invite-protect-install", state(game).revision, 900, playbook="Trainer"
    )["id"]
    for owner, step in (
        (OTHER, "consent"),
        (ADMIN, "attest"),
        (OTHER, "attest"),
        (ADMIN, "trainer_ask"),
        (OTHER, "trainer_yes"),
    ):
        private.respond(
            owner, "protect-training-" + step + str(owner.user_id), case, state(game).revision, step
        )

    inbox = InboxService(ledger)

    async def install(click):
        item = next(x for x in inbox.items(ADMIN) if x.identity == case)
        await InboxView(inbox, 1).route(click, item)

    asyncio.run(submit_form(ADMIN, install, dict(choice=("install_protect",)), 47400))
    for owner in (PLAYER, FOUR):
        game.join_scene(owner, "join-protect-cast-" + str(owner.user_id), 900)
    with ledger.transaction() as c:
        positioned = place(place(place(state(game), 2), 3, mode="outside_frame"), 4)
        game.event(c, 1, "protect-positions", "synthetic.placement", positioned)
    girl, target, attacker = (current_ref(state(game), owner) for owner in (3, 2, 4))

    class FourPersonGateway(Gateway):
        async def actor(self, identity):
            return FOUR if identity == 4 else await super().actor(identity)

    worker, gateway = GameWorker(game), FourPersonGateway()
    game.issue_order(
        ADMIN,
        "protect-order",
        900,
        3,
        "Stay beside your counterpart.",
        conditioning_phrase="protect",
        phrase_actor=target.token,
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    answer(game, OTHER, PROTECT, text="I take position at her side.")
    tick(worker, gateway, 4)
    with pytest.raises(WorkflowError, match="staying at their side"):
        MovementService(game).move(
            OTHER,
            "leave-protected-actor",
            state(game).revision,
            900,
            girl,
            (1, 0),
            account="I leave her square.",
        )

    battle = BattleService(ledger)
    data = battle.preview(FOUR, 900)
    by_entity = {x["ref"]["entity"]: x for x in data["actors"]}
    own, opponent = by_entity["4"], by_entity["2"]
    declaration = Declaration(
        play="all_out_assault",
        actor=attacker,
        target=target,
        attacking_asset=own["assets"][0]["id"],
        target_asset=opponent["assets"][0]["id"],
        actor_sha256=own["sha256"],
        target_sha256=opponent["sha256"],
        account="An actual strike is incoming.",
    )
    context = battle.propose(FOUR, "strike-protected", data["revision"], 900, declaration)["id"]
    battle.confirm(
        ADMIN,
        "strike-reach",
        state(game).revision,
        context,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual reach and opening.",
    )
    assault = game.begin(
        FOUR,
        "strike-roll",
        900,
        state(game).sheets["4"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    for owner in (ADMIN, PLAYER, OTHER, FOUR):
        answer(game, owner, "tag_window", options=("pass",))
    for owner in (ADMIN, PLAYER, OTHER, FOUR):
        answer(game, owner, "battle_assault_table", flag=False, text="The hit connects.")
    pending = state(game)
    choice = next(x for x in game.choices(OTHER) if x["kind"] == CHOICE)
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, choice["id"])
    assert game.inspect(FOUR, assault)["state"] != "complete"
    with pytest.raises(WorkflowError):
        answer(game, OTHER, CHOICE, fields={"asset": "not-owned-by-this-protector"})

    ledger.engine.dispose()
    payment = next(x.id for x in pending.sheets["3"].assets if x.family == "girl" and not x.damaged)

    async def intercept(click):
        item = next(x for x in inbox.items(OTHER) if x.identity == choice["id"])
        await InboxView(inbox, 3).route(click, item)

    asyncio.run(submit_form(OTHER, intercept, dict(asset=(payment,)), 47410))
    actual = state(game)
    assert actual.sheets["2"].assets == pending.sheets["2"].assets
    assert next(x for x in actual.sheets["3"].assets if x.id == payment).damaged
    assert game.inspect(FOUR, assault)["state"] == "complete" and game.dice.calls == 1


def test_trainer_installs_one_uninstalled_phrase_during_actual_punishment(ledger):
    from test_harpy_flirt import submit_form

    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_punishments import PunishmentService

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False)
    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, "training-punishment-mission", "Synthetic test mission", (2, 3))
    identity = offered["id"]
    missions.respond(PLAYER, "training-mission-yes-2", identity, 1, "accept")
    missions.respond(OTHER, "training-mission-yes-3", identity, 2, "accept")
    missions.start(ADMIN, "training-mission-start", identity, 3)
    missions.end(ADMIN, "training-mission-end", identity, 4, False)
    work = next(x["id"] for x in missions.get(ADMIN, identity)["work"] if x["subject"] == 3)
    service = PunishmentService(ledger)
    before = service.get(ADMIN, work)
    assert set(dict(before["conditioning_phrases"])) >= {"speak", "protect"}
    assert "conditioning_phrases" not in service.get(OTHER, work)
    with pytest.raises(WorkflowError):
        service.apply(
            OTHER,
            "not-the-trainer",
            work,
            before["revision"],
            before["game_revision"],
            Details(kind="stimulant_injection"),
            conditioning_phrase="speak",
        )

    inbox = InboxService(ledger)

    async def select(click):
        item = next(x for x in inbox.items(ADMIN) if x.identity == work)
        await InboxView(inbox, 1).route(click, item)
        view = click.edit_original_response.call_args.kwargs["view"]
        await view.open_item(click, "stimulant_injection")

    key = asyncio.run(
        submit_form(ADMIN, select, dict(confirm=("yes",), conditioning_phrase=("speak",)), 47420)
    )
    ledger.engine.dispose()
    applied = service.apply(
        ADMIN,
        key,
        work,
        before["revision"],
        before["game_revision"],
        Details(kind="stimulant_injection"),
        conditioning_phrase="speak",
    )
    assert applied["state"] == "resolved" and state(game).sheets["3"].heat == 7
    installations = [
        entry for entry in state(game).handler_persona.conditioning if "speak" in entry.phrases
    ]
    assert len(installations) == 1 and installations[0].pilot.entity == "3"
    made = game.issue_order(
        ADMIN, "punishment-speak-order", 900, 3, "Report.", conditioning_phrase="speak"
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    answer(game, OTHER, SPEAK, text="This is the original Girl's answer.")
    answer(game, ADMIN, HEAR, flag=True)
    assert game.inspect(OTHER, made["action_id"])["state"] == "complete"


@pytest.mark.parametrize("heard", (True, False))
def test_trainer_npc_order_requires_both_sight_and_hearing_for_compulsion(
    ledger, heard, tmp_path, monkeypatch
):
    from test_cast_service import change
    from test_enforcer_requisitions import approved
    from test_harpy_flirt import submit_form

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.engine.m3_succubus import TRAINER_ORDER_RULE
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_succubus import SuccubusService
    from girlframe.services.m3_world import WorldService

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False)
    assert not HandlerPlayService(ledger).options(ADMIN)["trainer_npc_order"]
    approved(ledger, game, tmp_path, monkeypatch, extra=(TRAINER_ORDER_RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    missions = MissionService(ledger)
    roles = NpcRoleService(WorldService(missions))
    guard = Npc(
        id="trainer-guard",
        name="Original guard",
        jobs=("guard",),
        controller=3,
        detail="The ordinary guard.",
        cell=(0, 0),
        revealed=True,
    )
    offered = roles.offer(ADMIN, "trainer-guard-offered", state(game).revision, guard)
    roles.respond(OTHER, "trainer-guard-accepted", offered["id"], state(game).revision, "accept")
    npc = ActorRef(kind="npc", entity=guard.id)
    cast = CastService(ActorService(missions))
    change(cast, OTHER, "join", npc)
    change(cast, ADMIN, "join", active_handler(state(game)))
    orders = SuccubusService(game)
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)

    async def issue(click):
        await open_handler_plays(click, HandlerPlayService(ledger))
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, "trainer_npc_order")

    asyncio.run(
        submit_form(ADMIN, issue, dict(target=(npc.token,), instruction="Open the door."), 47440)
    )
    with ledger.engine.connect() as c:
        (pending,) = orders._tasks(c, OTHER)
    identity = pending["id"]
    with pytest.raises(WorkflowError):
        orders.inspect(PLAYER, identity)
    tick(worker, gateway, 3)

    async def route(click):
        item = next(x for x in inbox.items(OTHER) if x.identity == identity)
        await InboxView(inbox, 3).route(click, item)

    asyncio.run(
        submit_form(
            OTHER,
            route,
            dict(
                option=("perception",),
                saw_eyes=("yes",),
                heard_voice=("yes" if heard else "no",),
                account="PRIVATE_NPC_PERCEPTION",
            ),
            47450,
        )
    )
    ledger.engine.dispose()
    data = orders.inspect(OTHER, identity)
    assert data["trainer_compelled"] is heard and "PRIVATE_NPC_PERCEPTION" not in str(data)
    if heard:
        with pytest.raises(WorkflowError):
            orders.choose(
                OTHER, "compelled-no-refusal", identity, data["revision"], "disobey", "I refuse."
            )
        asyncio.run(
            submit_form(
                OTHER, route, dict(option=("hesitant",), account="The NPC obeys hesitantly."), 47460
            )
        )
        assert orders.inspect(ADMIN, identity)["result"]["response"] == "hesitant"
        assert game.dice.calls == 0
    else:
        game.dice.faces = (1, 1)
        orders.choose(
            OTHER, "ordinary-npc-refuses", identity, data["revision"], "disobey", "The NPC refuses."
        )
        result = orders.choose(
            OTHER,
            "ordinary-npc-roll",
            identity,
            orders.inspect(OTHER, identity)["revision"],
            "roll",
            "Roll the original NPC's refusal.",
        )
        assert result["receipt"]["faces"] == [1, 1] and game.dice.calls == 1
        orders.choose(
            OTHER,
            "low-npc-follows",
            identity,
            orders.inspect(OTHER, identity)["revision"],
            "obedient",
            "The NPC follows after all.",
        )
        orders.choose(
            ADMIN,
            "no-npc-notice",
            identity,
            orders.inspect(ADMIN, identity)["revision"],
            "review",
            "Nobody notices the aborted refusal.",
            knows=False,
            punish=False,
        )
        assert orders.inspect(ADMIN, identity)["phase"] == "complete"
