"""Dogrunner rank changes and native mission discipline use the original Dogs."""

import asyncio

import pytest
from m3_policy_scenario import configure_m3_fixture
from test_enforcer_requisitions import approved
from test_handler_creation import complete, save
from test_intracadre_marriage import FOUR, setup_three
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_service import launched
from test_mission_ui import current
from test_punishment_service import submit
from test_role_punishments import change

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine import m3_handler_plays as handler_plays
from girlframe.engine.m2 import PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_dogrunner import owners
from girlframe.engine.m3_handler_advancements import PermissionGrant, awards
from girlframe.engine.m3_handler_ordinary import RULE as ordinary_rule
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_intracadre_marriage import is_dog
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def dogrunner_ready(ledger):
    game, worker, gateway, _ = setup_three(ledger)
    registry = configure_m3_fixture(ledger)
    approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"playbooks", "plays"})
            ),
            owner_m3_rulings=rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing"),
            ),
        )
    )
    creation = HandlerCreationService(ledger)
    draft = complete(creation, "Dogrunner")
    dog = draft.starting[1].model_copy(update=dict(pilot=current_ref(state(game), 4)))
    save(creation, draft.model_copy(update=dict(starting=(draft.starting[0], dog))))
    invitations = creation.propose(ADMIN, "dogrunner-propose", creation.view(ADMIN)["revision"])
    for identity, viewer in zip(invitations["ids"], (PLAYER, FOUR), strict=True):
        data = creation.get_agreement(viewer, identity)
        creation.answer(viewer, "dogrunner-accept:" + identity, identity, data["revision"], True)
    preview = creation.view(ADMIN)
    creation.activate(
        ADMIN, "dogrunner-activate", preview["revision"], preview["game_revision"], True
    )
    assert state(game).order == (2, 3, 4)
    assert owners(state(game)) == (4,)
    return game, worker, gateway, registry


def witnessed_refusal(game, worker, gateway):
    order = game.issue_order(ADMIN, "dogrunner-actual-order", 900, 3, "Stay by the entrance.")
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("disobey",))
    refusal = game.begin(
        OTHER,
        "dogrunner-witnessed-refusal",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            context="I ignore the order in front of the other Girls.",
            trigger_confirmed=True,
            heat=0,
            order_id=order["order_id"],
            parent=order["action_id"],
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    answer(game, FOUR, "tag_window", options=("pass",))
    answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(OTHER, refusal)["result"]["can_disobey"]
    tick(worker, gateway, 4)


def test_dogrunner_keeps_raised_dogs_and_mission_punishes_each_original_once(ledger):
    game, worker, gateway, registry = dogrunner_ready(ledger)
    witnessed_refusal(game, worker, gateway)
    assert state(game).order == (2, 4, 3)
    assert owners(state(game)) == (4, 3)
    assert is_dog(state(game), 4) and is_dog(state(game), 3)
    ascended = state(game)
    shift_status(ascended, 4, 1)
    assert ascended.order == (4, 2, 3) and owners(ascended) == (3,)

    missions = MissionService(ledger, registry)
    mission, revision = launched(missions)
    ended = missions.end(ADMIN, "mission-end-two-dogs", mission, revision, True)
    original = {row["subject"]: row["id"] for row in missions.get(ADMIN, mission)["work"]}
    assert set(original) == {3, 4}
    other_inbox = {row.identity for row in InboxService(ledger).items(OTHER)}
    assert {original[3], original[4]} & other_inbox == {original[3]}
    assert original[4] in {row.identity for row in InboxService(ledger).items(FOUR)}
    ledger.engine.dispose()
    assert owners(state(game)) == (4, 3)
    assert (
        MissionService(ledger, registry).end(ADMIN, "mission-end-two-dogs", mission, revision, True)
        == ended
    )

    discipline = PunishmentService(ledger, registry)
    drug = Details(kind="stimulant_injection")
    with pytest.raises(WorkflowError, match="decision owner"):
        submit(discipline, FOUR, original[4], drug, "dog-punishes-self")
    ledger.safety(OTHER, "dogrunner-table-pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        submit(discipline, ADMIN, original[4], drug, "dog-punishment-paused")
    ledger.safety(OTHER, "dogrunner-table-resume", ledger.status(OTHER)["revision"], pause=False)
    assert owners(state(game)) == (4, 3)
    old = discipline.get(ADMIN, original[4])
    result = submit(discipline, ADMIN, original[4], drug, "dog-four-punishment")
    assert (
        discipline.apply(
            ADMIN, "dog-four-punishment", original[4], old["revision"], old["game_revision"], drug
        )
        == result
    )
    assert owners(state(game)) == (3,)
    assert state(game).sheets["4"].heat == 7
    assert missions.get(ADMIN, mission)["pending_count"] == 1
    submit(discipline, ADMIN, original[3], drug, "dog-three-punishment")
    assert owners(state(game)) == ()
    assert not is_dog(state(game), 3)
    assert (
        missions.complete(ADMIN, "all-current-dogs-resolved", mission, ended["revision"])["phase"]
        == "complete"
    )


@pytest.mark.parametrize(
    "ending",
    ("dog", "punishment", "dismissal", "demeaning"),
    ids=("tag-only", "proper-punishment", "dismissal", "demeaning"),
)
def test_dress_them_down_native_play_reduces_for_each_choice_and_tags_the_new_dog(ledger, ending):
    game, worker, gateway, _ = dogrunner_ready(ledger)
    service = HandlerPlayService(ledger)
    original = state(game)
    actor = current_ref(original, 2)
    with pytest.raises(WorkflowError, match="scene"):
        service.start(ADMIN, "unbound-dressing", original.revision, (actor,), dress_scene=901)

    async def begin():
        invoked = current(1, 47000)
        invoked.channel_id = 900
        await invoked.response.defer(ephemeral=True)
        await open_handler_plays(invoked, service)
        hub = invoked.edit_original_response.call_args.kwargs["view"]
        assert "dress" in dict(hub.options)
        await hub.open_item(invoked, "dress")
        form = invoked.edit_original_response.call_args.kwargs["view"]
        form.values.update(targets=(actor.token,))
        await form.confirm.callback(current(1, 47001))
        assert form.completed

    asyncio.run(begin())
    (task,) = service.tasks(ADMIN)
    identity = task["id"]
    inbox = InboxService(ledger)
    assert all(x.identity != identity for x in inbox.items(OTHER))
    effect = Effect(
        kind="dress_them_down",
        target=actor,
        account="PRIVATE_ACTUAL_DRESSING",
        dress_steps=("competency", ending),
        tag="PRIVATE_NEW_DOG_TAG",
        detail={"dismissal": "Get out of my sight.", "demeaning": "Scrub my boots."}.get(
            ending, ""
        ),
    )
    information = service.get(ADMIN, identity)
    revision = information["game_revision"]
    with pytest.raises(WorkflowError):
        service.submit(OTHER, "forged-dressing", identity, revision, "dress_them_down", effect)
    with pytest.raises(WorkflowError, match="Tag exactly"):
        service.submit(
            ADMIN,
            "without-required-tag",
            identity,
            revision,
            "dress_them_down",
            effect.model_copy(update=dict(tag="")),
        )
    ledger.safety(OTHER, "dressing-paused", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.submit(ADMIN, "try-paused-dress", identity, revision, "dress_them_down", effect)
    ledger.safety(OTHER, "dressing-resume", ledger.status(OTHER)["revision"], pause=False)
    ledger.engine.dispose()
    assert state(game).order == original.order
    assert not state(game).sheets["2"].tags

    async def submit_via_inbox():
        click = current(1, 47010)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, "dress_them_down")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(actor.token,),
            dress_steps=tuple(reversed(effect.dress_steps))
            if ending in ("punishment", "dismissal")
            else effect.dress_steps,
            account=effect.account,
            tag=effect.tag,
            detail=effect.detail,
        )
        sent = current(1, 47011)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(submit_via_inbox())
    assert service.submit(ADMIN, "47011", identity, revision, "dress_them_down", effect)[
        "state"
    ] == ("awaiting_effect" if effect.opens_punishment else "complete")
    with pytest.raises(WorkflowError):
        service.submit(ADMIN, "stale-dress", identity, revision, "dress_them_down", effect)
    canonical = state(game)
    assert canonical.order == (3, 4, 2) and owners(canonical) == (4, 2)
    (tag,) = canonical.sheets["2"].tags
    assert tag.label == effect.tag and tag.giver_actor == current_ref(canonical, 1)
    assert set(tag.observers) == {1, 2}
    assert service.notice(PLAYER, identity)["account"] == effect.account
    with pytest.raises(WorkflowError):
        service.notice(OTHER, identity)
    if effect.opens_punishment:
        (case_id,) = handler_plays.record(canonical, identity).followups
        (case,) = canonical.role_punishments
        assert case.id == case_id and case.executor == current_ref(canonical, 1)
        assert case.subject == actor and canonical.sheets["2"].heat == original.sheets["2"].heat
        role = RolePunishmentService(game)
        with pytest.raises(WorkflowError):
            role.get(OTHER, case_id)
        details = Details(kind="stimulant_injection")
        change(
            role,
            ADMIN,
            case_id,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(role, ADMIN, case_id, scene="The original Handler performs the Punishment.")
        with pytest.raises(WorkflowError):
            change(role, ADMIN, case_id, execute=True, account="Cannot invent attendance.")
        change(role, PLAYER, case_id, attest=True)
        change(role, ADMIN, case_id, execute=True, account="The chosen Punishment occurred.")
        completed = state(game)
        grant = handler_plays.record(completed, identity)
        assert grant.state == "complete"
        assert grant.completed_event == completed.role_punishments[-1].completion_event
        assert completed.sheets["2"].heat == 7 and owners(completed) == (4,)
    if effect.dress_order:
        assert not canonical.role_punishments
        assert not game.choices(PLAYER)
        tick(worker, gateway, 3)
        (choice,) = [x for x in game.choices(PLAYER) if x["kind"] == "order_response"]
        assert game.decision(PLAYER, choice["id"])["order_text"] == effect.detail
        with pytest.raises(WorkflowError):
            game.decision(OTHER, choice["id"])
        answer(game, PLAYER, "order_response", options=("disobey",))
        assert handler_plays.record(state(game), identity).state == "complete"
    if ending == "demeaning":
        decision = game.decision(
            PLAYER, next(x["id"] for x in game.choices(PLAYER) if x["kind"] == "order_disobey")
        )
        refusal = game.begin(
            PLAYER,
            "refuse-original-demeaning-order",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="disobey_orders",
                context="I refuse the original demeaning demand.",
                trigger_confirmed=True,
                heat=0,
                order_id=decision["body"]["order_id"],
                parent=decision["parent"],
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, FOUR, "tag_window", options=("pass",))
        answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Defiant")
        answer(game, ADMIN, "handler_disobey", flag=True)
        assert game.inspect(PLAYER, refusal)["result"]["can_disobey"]
        assert any(
            ob.kind == "punishment" and ob.owner == 2 and ob.action == refusal
            for ob in state(game).obligations
        )


def test_dress_them_down_waits_for_the_delegate_and_contact_then_creates_its_order(ledger):
    from test_harpy_flirt import submit_form

    from girlframe.services.m3_dogrunner_dress import DressPerformanceService

    game, worker, gateway, _ = dogrunner_ready(ledger)
    service = HandlerPlayService(ledger)
    inbox = InboxService(ledger)
    perform = DressPerformanceService(game)
    original = state(game)
    girl, delegate = current_ref(original, 2), current_ref(original, 3)
    proposal = service.start(
        ADMIN, "prepare-physical-dress", original.revision, (girl,), dress_scene=900
    )
    identity = proposal["id"]

    async def propose(click):
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, "dress_them_down")

    asyncio.run(
        submit_form(
            ADMIN,
            propose,
            dict(
                target=(girl.token,),
                dress_steps=("physical", "delegate", "demeaning"),
                dress_contact=("grab",),
                dress_delegate=(delegate.token,),
                account="The Dogrunner proposes these steps.",
                tag="The new original Dog",
                detail="Attend to the equipment.",
            ),
            47500,
        )
    )
    assert state(game).order == original.order
    assert perform.get(OTHER, identity)["phase"] == "delegate"
    with pytest.raises(WorkflowError):
        perform.get(PLAYER, identity)
    with pytest.raises(WorkflowError):
        perform.get(FOUR, identity)

    def step(owner, i, selection, text=""):
        async def route(click):
            item = next(
                x
                for x in inbox.items(owner)
                if x.identity == identity and x.task == "m3_dress_performance"
            )
            await InboxView(inbox, owner.user_id).route(click, item)

        return asyncio.run(submit_form(owner, route, dict(step=(selection,), account=text), i))

    step(OTHER, 47510, "competency", "I choose an insult about the previous sortie.")
    contact = perform.get(PLAYER, identity)
    assert (contact["phase"], contact["contacts"]) == ("contact", ("grab",))
    ledger.safety(PLAYER, "pause-physical-dressing", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        perform.respond(
            PLAYER,
            "paused-contact",
            identity,
            contact["revision"],
            "performed",
            "The grab occurred.",
        )
    ledger.safety(
        PLAYER, "resume-physical-dressing", ledger.status(PLAYER)["revision"], pause=False
    )
    ledger.engine.dispose()
    step(PLAYER, 47520, "performed", "The grab occurred.")
    assert state(game).order == original.order
    assert perform.get(ADMIN, identity)["phase"] == "ready"
    ready_revision = state(game).revision
    key = step(ADMIN, 47530, "finish")
    completed = state(game)
    replay = perform.finish(ADMIN, key, identity, ready_revision)
    assert replay["state"] == "complete"
    assert state(game) == completed and completed.order == (3, 4, 2)
    assert (
        len([tag for tag in completed.sheets["2"].tags if tag.label == "The new original Dog"]) == 1
    )
    tick(worker, gateway, 3)
    order = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
    assert "Attend to the equipment." in game.decision(PLAYER, order["id"])["order_text"]


def test_demeaning_dress_order_finishes_before_its_selected_proper_punishment(ledger):
    game, worker, gateway, _ = dogrunner_ready(ledger)
    service = HandlerPlayService(ledger)
    role = RolePunishmentService(game)
    original = state(game)
    girl = current_ref(original, 2)
    grant = service.start(
        ADMIN, "prepare-ordered-discipline", original.revision, (girl,), dress_scene=900
    )["id"]
    effect = Effect(
        kind="dress_them_down",
        target=girl,
        dress_steps=("demeaning", "punishment"),
        tag="Newly the Dog",
        detail="Put away the tools.",
        account="I order her to put away the tools, then set discipline.",
    )
    issued = service.submit(
        ADMIN, "ordered-discipline", grant, state(game).revision, "dress_them_down", effect
    )
    assert issued["state"] == "awaiting_effect"
    (case,) = handler_plays.record(state(game), grant).followups
    details = Details(kind="stimulant_injection")
    instruction = Instruction(kind=details.kind, details_json=details.model_dump_json())
    with pytest.raises(WorkflowError, match="demeaning Order"):
        change(role, ADMIN, case, instruction=instruction)
    assert state(game).sheets["2"].heat == original.sheets["2"].heat
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 4)
    ledger.engine.dispose()
    change(role, ADMIN, case, instruction=instruction)
    change(role, ADMIN, case, scene="The actual discipline follows the answered Order.")
    change(role, PLAYER, case, attest=True)
    change(role, ADMIN, case, execute=True, account="The original Handler applies the discipline.")
    assert handler_plays.record(state(game), grant).state == "complete"
    assert state(game).sheets["2"].heat == 7 and game.dice.calls == 0


def test_dogrunner_issues_the_recorded_dismissal_after_the_demeaning_order(ledger):
    from test_harpy_flirt import submit_form

    game, worker, gateway, _ = dogrunner_ready(ledger)
    service = HandlerPlayService(ledger)
    original = state(game)
    girl = current_ref(original, 2)
    grant = service.start(
        ADMIN, "prepare-two-actual-orders", original.revision, (girl,), dress_scene=900
    )["id"]
    effect = Effect(
        kind="dress_them_down",
        target=girl,
        dress_steps=("demeaning", "dismissal"),
        tag="The original Girl becomes a Dog",
        detail="Clean the oil pan.",
        dress_dismissal="Leave now.",
        account="Two separate orders are selected.",
    )
    first = service.submit(
        ADMIN, "first-dress-order", grant, state(game).revision, "dress_them_down", effect
    )
    assert first["state"] == "awaiting_effect"
    assert not service.get(ADMIN, grant)["dress_final_pending"]
    with pytest.raises(WorkflowError):
        service.finish_dress_order(ADMIN, "too-early-dismissal", grant, state(game).revision)
    tick(worker, gateway, 3)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
    assert game.decision(PLAYER, choice["id"])["order_text"] == "Clean the oil pan."
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 4)
    ledger.engine.dispose()
    inbox = InboxService(ledger)

    async def final(click):
        item = next(
            x for x in inbox.items(ADMIN) if x.identity == grant and x.task == "m3_handler_play"
        )
        await InboxView(inbox, 1).route(click, item)

    before_final = state(game)
    with pytest.raises(WorkflowError):
        service.finish_dress_order(OTHER, "wrong-owner-dismissal", grant, before_final.revision)
    key = asyncio.run(submit_form(ADMIN, final, dict(choice=("send",)), 47550))
    assert (
        service.finish_dress_order(ADMIN, key, grant, before_final.revision)["state"] == "complete"
    )
    actual = state(game)
    assert (
        actual.order == before_final.order
        and actual.sheets["2"].tags == before_final.sheets["2"].tags
    )
    tick(worker, gateway, 3)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "order_response")
    assert game.decision(PLAYER, choice["id"])["order_text"] == "Leave now."
    answer(game, PLAYER, "order_response", options=("obedient",))
    assert game.dice.calls == 0


def test_dogrunner_all_dogs_uses_actual_status_and_the_ordinary_award_slot(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = dogrunner_ready(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary_rule,))
    ordinary = HandlerOrdinaryService(ledger)
    session = ordinary.record_session(
        ADMIN, "dogs-session", state(game).revision, "Actual synthetic session", "Session starts."
    )["id"]
    assert not ordinary.menu(ADMIN, session)["dogrunner_award"]
    with pytest.raises(WorkflowError, match="actual Dogs"):
        ordinary.claim_all_dogs(ADMIN, "before-dogs", session, state(game).revision, "Too early.")
    witnessed_refusal(game, worker, gateway)
    assert ordinary.menu(ADMIN, session)["dogrunner_award"]
    expected = state(game).revision
    with pytest.raises(WorkflowError):
        ordinary.claim_all_dogs(OTHER, "wrong-dog-award", session, expected, "Wrong controller.")
    ledger.engine.dispose()

    async def claim():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == session)
        click = current(1, 47700)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert "dogrunner_award" in dict(form.fields[0].options)
        form.values.update(operation=("dogrunner_award",), account="The Ace and two actual Dogs.")
        sent = current(1, 47701)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(claim())
    (value,) = awards(state(game))
    assert (
        value.ordinary_source.session == session
        and value.ordinary_source.trigger == "dogrunner_all_dogs"
    )
    assert ordinary.claim_all_dogs(
        ADMIN, "47701", session, expected, "The Ace and two actual Dogs."
    ) == dict(id=value.id, phase="held")
    assert not ordinary.menu(ADMIN, session)["dogrunner_award"]
    assert (
        HandlerAdvancementService(ledger).spend_permissions(
            ADMIN,
            "spend-dog-award",
            value.id,
            state(game).revision,
            (PermissionGrant(actor=current_ref(state(game), 3), amount=2),),
            "Actual spend.",
        )["phase"]
        == "spent"
    )
    assert state(game).sheets["3"].permissions == 2
    ordinary.end_session(ADMIN, "close-dogs", session, state(game).revision, "Session ends.")
    next_session = ordinary.record_session(
        ADMIN,
        "another-dogs-session",
        state(game).revision,
        "Next session",
        "Next actual session starts.",
    )["id"]
    with pytest.raises(WorkflowError, match="once"):
        ordinary.claim_all_dogs(
            ADMIN, "repeat-dog-award", next_session, state(game).revision, "Already marked."
        )
