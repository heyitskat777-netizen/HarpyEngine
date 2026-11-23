"""Crisis choices arise from actual Tag effects and preserve an already saved die."""

import asyncio
import json

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_punishment_service import submit
from test_strain_effect_service import pending

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_frantic_crisis import ImmediateBreakdown, SiteRuin
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_bonds import depth as bond_depth
from girlframe.engine.m3_frantic_breakdown import records as breakdowns
from girlframe.engine.m3_frantic_crisis import records
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_handler_private_scene import records as private_scenes
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_frantic_crisis import CrisisService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_quadrant_loss import require_aftermath_clear
from girlframe.services.onboarding import WorkflowError


def create_frantic(ledger):
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
    save(creation, complete(creation, "Frantic"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(
        ADMIN, "frantic-crisis-source", preview["revision"], preview["game_revision"], True
    )


def gain_tag(game, plays, number):
    canonical = state(game)
    actor = active_handler(canonical)
    grant = plays.start(ADMIN, "frantic-tag-grant:" + str(number), canonical.revision, (actor,))
    effect = Effect(
        kind="tag",
        target=actor,
        tag="PRIVATE_FRANTIC_TAG_" + str(number),
        account="An actual synthetic Tag effect",
    )
    key = "frantic-tag-effect:" + str(number)
    saved = plays.submit(ADMIN, key, grant["id"], grant["game_revision"], "mess", effect)
    assert plays.submit(ADMIN, key, grant["id"], grant["game_revision"], "mess", effect) == saved
    value = next(x for x in records(state(game)) if x.tag == grant["id"] + ":tag")
    assert value.slot is None
    return value


def test_actual_frantic_tag_opens_one_crisis_and_each_raise_is_finite(ledger):
    effects, game, _, _ = pending(ledger, before_period=lambda _: create_frantic(ledger))
    strain = effects.strain
    before = {x.track: x for x in state(game).strain.requests if x.kind == "roll"}
    budget = before["budget"]
    strain.dice.face = 5
    roll_revision = state(game).revision
    dice = strain.roll(ADMIN, "budget-already-rolled", budget.id, 1, roll_revision)
    assert dice["face"] == 5
    with ledger.engine.connect() as c:
        initial = strain._row(c, budget.id)
    assert json.loads(initial["body_json"])["severity"] == "low"
    service, inbox = CrisisService(ledger), InboxService(ledger)
    plays = HandlerPlayService(ledger)

    async def choose(identity, slot, track, sequence):
        click = current(1, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(slot=(slot,), track=(track,))
        sent = current(1, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    first = gain_tag(game, plays, 1)
    assert len(records(state(game))) == 1
    for other in (PLAYER, OTHER):
        assert not any(x.identity == first.id for x in inbox.items(other))
        with pytest.raises(WorkflowError):
            service.get(other, first.id)
    ledger.safety(OTHER, "pause-crisis", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.raise_track(
            ADMIN, "paused-crisis", first.id, state(game).revision, "raise_first", "rebellion"
        )
    ledger.safety(OTHER, "resume-crisis", ledger.status(OTHER)["revision"], pause=False)
    ledger.engine.dispose()
    revision = state(game).revision
    asyncio.run(choose(first.id, "raise_first", "rebellion", 47600))
    service.raise_track(ADMIN, "47601", first.id, revision, "raise_first", "rebellion")
    state1 = state(game)
    assert state1.strain.levels["rebellion"] == "high"
    assert (
        next(x for x in state1.strain.requests if x.id == before["rebellion"].id).severity == "high"
    )
    second = gain_tag(game, plays, 2)
    with pytest.raises(WorkflowError, match="unused"):
        service.raise_track(
            ADMIN, "first-used", second.id, state(game).revision, "raise_first", "budget"
        )
    asyncio.run(choose(second.id, "raise_second", "budget", 47610))
    state2 = state(game)
    assert state2.strain.levels["budget"] == "high"
    with ledger.engine.connect() as c:
        assert strain._row(c, budget.id) == initial
    assert strain.roll(ADMIN, "budget-already-rolled", budget.id, 1, roll_revision) == dice
    third = gain_tag(game, plays, 3)
    assert service.get(ADMIN, third.id)["available"] == ()
    assert len(records(state(game))) == 3 and records(state(game))[-1].slot is None


def test_each_immediate_crisis_roll_is_native_and_saved_once(ledger, monkeypatch):
    cycle, game, period = prepared(ledger, before_period=lambda _: create_frantic(ledger))
    activate(cycle, game, period)
    game.dice = Dice((4, 4))
    # The Inbox constructs its own service. Keep its rolling source deterministic in this test.
    monkeypatch.setattr("girlframe.services.m3_frantic_crisis.GameService", lambda _: game)
    service, inbox, plays = CrisisService(ledger), InboxService(ledger), HandlerPlayService(ledger)
    breakdown = FranticBreakdownService(ledger, game)
    discipline = PunishmentService(ledger)

    async def roll(identity, slot, number):
        click = current(1, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in form.children if isinstance(x, ImmediateBreakdown))
        select = current(1, number + 1)
        await select.response.defer(ephemeral=True)
        await button.callback(select)
        immediate = select.edit_original_response.call_args.kwargs["view"]
        immediate.values.update(slot=(slot,), account="Actual original breakdown.")
        sent = current(1, number + 2)
        await immediate.confirm.callback(sent)
        assert immediate.completed, sent.followup.send.call_args

    first = gain_tag(game, plays, 10)
    opening = state(game).revision
    with pytest.raises(WorkflowError, match="original Frantic"):
        service.break_now(PLAYER, "wrong-roller", first.id, opening, "break_first", 900, "Wrong")
    ledger.safety(OTHER, "pause-before-immediate", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.break_now(ADMIN, "paused-roll", first.id, opening, "break_first", 900, "Paused")
    ledger.safety(OTHER, "resume-before-immediate", ledger.status(OTHER)["revision"], pause=False)
    assert not breakdowns(state(game)) and game.dice.calls == 0
    asyncio.run(roll(first.id, "break_first", 48900))
    actual = service.break_now(
        ADMIN, "48902", first.id, opening, "break_first", 900, "Actual original breakdown."
    )
    (saved,) = breakdowns(state(game))
    assert actual["breakdown"] == saved.id and game.dice.calls == 1
    assert saved.faces == (4, 4) and saved.total == 11
    assert service.get(ADMIN, first.id)["breakdown"] == saved.id
    assert breakdown.get(ADMIN, saved.id)["phase"] == "choice"
    second = gain_tag(game, plays, 11)
    current_revision = state(game).revision
    with pytest.raises(WorkflowError, match="unused"):
        service.break_now(
            ADMIN, "used-slot", second.id, current_revision, "break_first", 900, "Used"
        )
    with pytest.raises(WorkflowError, match="existing Frantic breakdown"):
        service.break_now(
            ADMIN, "existing-roll", second.id, current_revision, "break_second", 900, "Pending"
        )
    ledger.engine.dispose()
    target = current_ref(state(game), 3)
    breakdown.select(
        ADMIN, "first-choices", saved.id, state(game).revision, ("office",), office=target
    )
    breakdown.select(PLAYER, "ace-choices", saved.id, state(game).revision, ("minor_all",))
    breakdown.discover(OTHER, "actual-office", saved.id, state(game).revision, "Find the Handler.")
    for work in cycle.periods.get(ADMIN, period)["work"]:
        if work["kind"] != "punishment":
            continue
        identity = work["id"]
        data = discipline.get(ADMIN, identity)
        subject = PLAYER if data["subject_id"] == "2" else OTHER
        discipline.propose_scene(
            ADMIN,
            "propose:" + identity,
            identity,
            data["revision"],
            data["game_revision"],
            "Actual scene.",
        )
        for viewer in (ADMIN, subject):
            data = discipline.get(viewer, identity)
            discipline.attest_scene(
                viewer,
                f"attest:{viewer.user_id}:{identity}",
                identity,
                data["revision"],
                data["game_revision"],
            )
        submit(
            discipline, ADMIN, identity, Details(kind="stimulant_injection"), "perform:" + identity
        )
    assert breakdown.get(ADMIN, saved.id)["phase"] == "complete"
    asyncio.run(roll(second.id, "break_second", 48910))
    assert game.dice.calls == 2 and len(breakdowns(state(game))) == 2
    assert service.get(ADMIN, second.id)["immediate"] == ()


def test_each_printed_city_and_base_ruin_applies_and_keeps_aftermath(ledger):
    cycle, game, period = prepared(ledger, before_period=lambda _: create_frantic(ledger))
    activate(cycle, game, period)
    service, inbox, plays = CrisisService(ledger), InboxService(ledger), HandlerPlayService(ledger)
    first = gain_tag(game, plays, 21)
    before = state(game)
    with pytest.raises(WorkflowError, match="suitable original site"):
        service.ruin(ADMIN, "not-a-city", first.id, before.revision, "city", "base1", "Wrong kind")
    with pytest.raises(WorkflowError, match="original Frantic"):
        service.ruin(OTHER, "wrong-ruin-owner", first.id, before.revision, "city", "city1", "Wrong")
    assert state(game) == before

    async def ruin(identity, label, number):
        click = current(1, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in form.children if isinstance(x, SiteRuin))
        select = current(1, number + 1)
        await select.response.defer(ephemeral=True)
        await button.callback(select)
        decision = select.edit_original_response.call_args.kwargs["view"]
        option = next(key for key, title in decision.fields[0].options if title == label)
        decision.values.update(choice=(option,), account="PRIVATE_ACTUAL_RUIN")
        sent = current(1, number + 2)
        await decision.confirm.callback(sent)
        assert decision.completed, sent.followup.send.call_args

    asyncio.run(ruin(first.id, "City — city1", 48930))
    assert (
        service.ruin(
            ADMIN, "48932", first.id, before.revision, "city", "city1", "PRIVATE_ACTUAL_RUIN"
        )["location"]
        == "city1"
    )
    for index, slot in enumerate(("base_first", "base_second", "base_third")):
        case = gain_tag(game, plays, 22 + index)
        canon = state(game)
        if index:
            with pytest.raises(WorkflowError, match="unused printed ruin"):
                service.ruin(
                    ADMIN,
                    "used-base-slot:" + str(index),
                    case.id,
                    canon.revision,
                    "base_first",
                    "base" + str(index),
                    "Already used.",
                )
        if index == 1:
            ledger.engine.dispose()
        selected = service.ruin(
            ADMIN,
            "actual-base:" + slot,
            case.id,
            canon.revision,
            slot,
            "base" + str(index),
            "Actual ruin.",
        )
        assert selected["state"] == "complete"
    after = state(game)
    destroyed = {x.id for x in after.world.locations if x.condition == "destroyed"}
    assert destroyed == {"city1", "base0", "base1", "base2"}
    assert after.world.territory == before.world.territory
    assert {x.entity for x in after.strain.triggers if x.kind == "structure_destroyed"} == destroyed
    assert sum(x.get("kind") == "quadrant_loss" for x in after.facts) == 1
    with pytest.raises(WorkflowError, match="quadrant-loss aftermath"):
        require_aftermath_clear(after)


@pytest.mark.parametrize(
    "branch,faces,subject,modifier",
    (
        ("comfort", (4, 5), PLAYER, -1),
        ("mutual", (2, 3), OTHER, 3),
        ("high", (4, 4), OTHER, 3),
        ("believe", (1, 1), OTHER, 3),
        ("doubt", (1, 1), OTHER, 3),
    ),
)
def test_frantic_private_roll_keeps_printed_effects_owned(
    ledger, monkeypatch, branch, faces, subject, modifier
):
    cycle, game, period = prepared(ledger, before_period=lambda _: create_frantic(ledger))
    activate(cycle, game, period)
    outsider = OTHER if subject == PLAYER else PLAYER
    game.leave_scene(outsider, "private-frantic-roll-scene", 900)
    if branch == "high":
        with ledger.transaction() as c:
            canon = state(game)
            canon.sheets[str(subject.user_id)].identities[0].marked = True
            game.event(c, subject.user_id, "synthetic-identity-mark", "synthetic.fixture", canon)
    game.dice = Dice(faces)
    monkeypatch.setattr("girlframe.services.m3_handler_private_scene.GameService", lambda _: game)
    service, inbox = HandlerPrivateSceneService(ledger), InboxService(ledger)
    identity = service.invite(
        ADMIN,
        "private-frantic-invitation",
        state(game).revision,
        900,
        playbook="Frantic",
    )["id"]
    assert not any(x.identity == identity for x in inbox.items(outsider))

    def respond(viewer, choice, *, text="", effects=()):
        return service.respond(
            viewer,
            "actual-private:" + choice + ":" + str(viewer.user_id),
            identity,
            state(game).revision,
            choice,
            text=text,
            effects=effects,
        )

    respond(subject, "consent")
    respond(ADMIN, "attest")
    respond(subject, "attest")
    before = state(game)
    assert not game.dice.calls

    async def owned_roll():
        own = current(1, 49700)
        await own.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=("frantic_roll",))
        sent = current(1, 49701)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(owned_roll())
    (saved,) = private_scenes(state(game))
    assert (saved.roll.faces, saved.roll.modifier, saved.roll.total) == (
        faces,
        modifier,
        sum(faces) + modifier,
    )
    service.respond(ADMIN, "49701", identity, before.revision, "frantic_roll")
    assert game.dice.calls == 1
    ledger.engine.dispose()
    if branch == "comfort":
        with pytest.raises(WorkflowError, match="your own"):
            respond(ADMIN, "frantic_comfort")
        respond(subject, "frantic_comfort")
        assert state(game).order == (3, 2)
        assert state(game).sheets["2"].permissions == before.sheets["2"].permissions + 1
    elif branch == "mutual":
        respond(subject, "frantic_decline_comfort")
        respond(subject, "frantic_girl_tag", text="An actual Girl-authored Tag")
        assert service.menu(ADMIN, identity)["phase"] == "frantic_handler_tag"
        respond(ADMIN, "frantic_handler_tag", text="An actual Handler-authored Tag")
        (actual,) = private_scenes(state(game))
        assert any(
            x.id == actual.tag and x.giver_actor == saved.handler
            for x in state(game).sheets["3"].tags
        )
        assert any(
            x.id == actual.handler_tag and x.giver_actor == saved.girl
            for x in state(game).handler_tags
        )
    elif branch == "high":
        assert (
            bond_depth(state(game), saved.handler, saved.girl)
            == bond_depth(before, saved.handler, saved.girl) + 1
        )
        assert any(x.marked for x in state(game).sheets["3"].identities)
        respond(subject, "frantic_high", effects=("unmark", "printed_tag"))
        assert not any(x.marked for x in state(game).sheets["3"].identities)
        (actual,) = private_scenes(state(game))
        assert any(
            x.id == actual.handler_tag and x.giver_actor == saved.girl
            for x in state(game).handler_tags
        )
    else:
        respond(subject, "frantic_care", text="My original Girl's own answer.")
        if branch == "believe":
            respond(ADMIN, "frantic_believe")
            respond(subject, "frantic_no_tag")
            assert (
                bond_depth(state(game), saved.handler, saved.girl)
                == bond_depth(before, saved.handler, saved.girl) + 1
            )
        else:
            respond(ADMIN, "frantic_doubt")
            (actual,) = private_scenes(state(game))
            assert service.menu(subject, identity)["phase"] == "frantic_discipline"
            assert any(
                x.id == actual.discipline and x.state == "pending" for x in state(game).obligations
            )
            assert bond_depth(state(game), saved.handler, saved.girl) == bond_depth(
                before, saved.handler, saved.girl
            )
            return
    assert service.menu(subject, identity)["phase"] == "complete" and game.dice.calls == 1
