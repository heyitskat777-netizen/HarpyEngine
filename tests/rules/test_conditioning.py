"""Actual private native Conditioning, with the printed roles and owned consequences."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_mission_ui import current
from test_scientist_lab import create_scientist
from test_world_service import ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine import m3_conditioning as rules
from girlframe.engine.m2 import AssetState, IdentityState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_conditioning import ConditioningService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def setup(ledger, tmp_path, monkeypatch, role, faces, count):
    world, game = ready(ledger)
    game.dice = Dice(faces)
    cast = CastService(ActorService(world.missions))
    if role == "girl":
        game.leave_scene(ADMIN, "facilitator-leaves", 900)
        trainer = OTHER
        ref = current_ref(state(game), trainer.user_id)
    elif role == "handler":
        game.leave_scene(OTHER, "third-person-leaves", 900)
        create_scientist(ledger)
        trainer, ref = ADMIN, current_ref(state(game), ADMIN.user_id)
        change(cast, trainer, "join", ref)
    else:
        game.leave_scene(OTHER, "third-person-leaves", 900)
        trainer, ref = ADMIN, ActorRef(kind="npc", entity="real-trainer")
        world.npc(
            ADMIN,
            "create-trainer",
            state(game).revision,
            Npc(
                id=ref.entity,
                name="Synthetic trainer",
                jobs=("doctor",),
                detail="Original NPC instructor",
                cell=(0, 0),
                controller=trainer.user_id,
                revealed=True,
            ),
        )
        change(cast, trainer, "join", ref)

    with ledger.transaction() as c:
        canon = state(game)
        patient = canon.sheets["2"]
        patient.identities = [
            IdentityState(id=f"trait-{i}", name=f"Trait {i}", slot=i) for i in range(count)
        ]
        patient.tags.append(
            TagState(id="actual-old-tag", label="Old Tag", giver=trainer.user_id, observers=(1, 2))
        )
        patient.assets.append(
            AssetState(id="own-ordinary-asset", family="girl", name="Old equipment")
        )
        if role == "handler":
            canon = set_depth(
                canon, current_ref(canon, 2), current_ref(canon, 3), 2, "existing-bond"
            )
        game.event(c, 2, "original-resources", "synthetic.conditioning_fixture", canon)

    service = ConditioningService(game)
    assert not service.enabled()
    with pytest.raises(WorkflowError, match="scoped .*approval"):
        service.menu(trainer, 900)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    return (
        ConditioningService(game),
        CastService(ActorService(MissionService(ledger))),
        trainer,
        ref,
    )


def step(service, viewer, identity, stage, **kwargs):
    return service.advance(viewer, stage, identity, state(service.game).revision, stage, **kwargs)


async def native_request(store, viewer, identity, sequence, option, **values):
    inbox = InboxService(store)
    item = next(x for x in inbox.items(viewer) if x.identity == identity)
    assert item.task == "m3_conditioning"
    click = current(viewer.user_id, sequence)
    await click.response.defer(ephemeral=True)
    await InboxView(inbox, viewer.user_id).route(click, item)
    menu = click.edit_original_response.call_args.kwargs["view"]
    assert option in dict(menu.options)
    opening = current(viewer.user_id, sequence + 1)
    await opening.response.defer(ephemeral=True)
    await menu.open_item(opening, option)
    form = opening.edit_original_response.call_args.kwargs["view"]
    assert isinstance(form, NativeForm)
    form.values.update(values)
    sent = current(viewer.user_id, sequence + 2)
    await form.confirm.callback(sent)
    assert form.completed, sent.followup.send.call_args


@pytest.mark.parametrize(
    "role,faces,count,bonus,total",
    [("npc", (2, 3), 4, 1, 6), ("girl", (2, 3), 3, 2, 8), ("handler", (4, 4), 4, 3, 11)],
)
def test_conditioning_private_native_roll_and_real_owned_effects(
    ledger, tmp_path, monkeypatch, role, faces, count, bonus, total
):
    service, cast, trainer, ref = setup(ledger, tmp_path, monkeypatch, role, faces, count)
    game = service.game
    before = state(game)
    other = ADMIN if role == "girl" else OTHER

    async def invite():
        click = current(trainer.user_id, 91011)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        opening = current(trainer.user_id, 91012)
        await opening.response.defer(ephemeral=True)
        await menu.open_item(opening, "conditioning")
        form = opening.edit_original_response.call_args.kwargs["view"]
        form.values["decision"] = ("request",)
        sent = current(trainer.user_id, 91013)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    opening = service.menu(trainer, 900)
    asyncio.run(invite())
    offer = service.invite(
        trainer, "91013", opening["revision"], 900, opening["scene"], opening["cast"]
    )
    identity = offer["id"]
    assert service.get(trainer, identity)["resources"] is None
    assert not any(x.identity == identity for x in InboxService(ledger).items(other))
    with pytest.raises(WorkflowError, match="original two participants"):
        service.get(other, identity)
    with pytest.raises(WorkflowError, match="actual participant"):
        step(service, trainer, identity, "consent")
    asyncio.run(native_request(ledger, PLAYER, identity, 91020, "consent", sharing=("share",)))

    rolled_at = state(game).revision
    step(service, PLAYER, identity, "roll")
    restarted = ConditioningService(GameService(ledger, dice=game.dice))
    assert restarted.advance(PLAYER, "roll", identity, rolled_at, "roll") == service.advance(
        PLAYER, "roll", identity, rolled_at, "roll"
    )
    assert game.dice.calls == 1
    value = rules.find(state(game), identity)
    assert value.roll.total == total
    assert value.roll.trainer_bonus == bonus
    assert value.roll.identity_bonus == int(count < 4)
    assert value.trainer == ref
    assert service.get(PLAYER, identity)["resources"] is None
    assert service.get(trainer, identity)["resources"]["vacancies"] == 4 - count
    with pytest.raises(WorkflowError, match="stale"):
        service.advance(
            trainer,
            "stale",
            identity,
            rolled_at,
            "choose",
            choice=rules.Tag(account="Stale", label="Bogus"),
        )

    def plan(key, effect):
        revision = state(game).revision
        return service.advance(trainer, key, identity, revision, "choose", choice=effect)

    with pytest.raises(WorkflowError, match="actual participant"):
        step(
            service,
            PLAYER,
            identity,
            "choose",
            choice=rules.Tag(account="My retelling", label="False"),
        )

    low = None
    if role == "npc":
        asyncio.run(
            native_request(
                ledger,
                trainer,
                identity,
                91030,
                "tag",
                label="Tutor's Tag",
                account="My part of the Conversation.",
            )
        )
        low = rules.IdentityChoice(name="I am still here", replace="trait-0")
    elif role == "girl":
        plan("erase", rules.Erase(account="Trainer retells", identities=("trait-0", "trait-1")))
        plan(
            "teach", rules.Teach(account="Trainer explains", labels=("Learned one", "Learned two"))
        )
    else:
        plan(
            "replace",
            rules.Replace(account="Trainer retells", identity="trait-0", label="Replaced"),
        )
        plan(
            "embrace",
            rules.Embrace(
                account="Trainer shows",
                choices=(rules.TagChoice(tag="actual-old-tag", replace="trait-1"),),
            ),
        )
        asset = next(x for x in before.sheets["2"].assets if x.id == "own-ordinary-asset")
        plan(
            "excise",
            rules.Excise(account="Trainer offers", asset=asset.id, replacement="New equipment"),
        )
    assert state(game).sheets["2"] == before.sheets["2"]
    ledger.safety(other, "pause-conditioning", ledger.status(other)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        step(service, PLAYER, identity, "confirm", account="My own response", new_identity=low)
    ledger.safety(other, "resume-conditioning", ledger.status(other)["revision"], pause=False)
    assert restarted.get(PLAYER, identity)["changes"]
    revision = state(game).revision
    receipt = restarted.advance(
        PLAYER, "finish", identity, revision, "confirm", account="My own response", new_identity=low
    )
    assert (
        service.advance(
            PLAYER,
            "finish",
            identity,
            revision,
            "confirm",
            account="My own response",
            new_identity=low,
        )
        == receipt
    )
    final = state(game)
    assert rules.find(final, identity).phase == "complete"
    assert final.sheets["2"].heat == before.sheets["2"].heat
    assert final.sheets["3"] == before.sheets["3"]
    assert not any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    sheet = final.sheets["2"]
    names = {x.name for x in sheet.identities}
    if role == "npc":
        tag = next(x for x in sheet.tags if x.label == "Tutor's Tag")
        assert tag.giver_actor == ref and set(tag.observers) == {trainer.user_id, PLAYER.user_id}
        assert "I am still here" in names and "Trait 0" not in names
    elif role == "girl":
        assert names == {"Trait 2", "Learned one", "Learned two"}
    else:
        assert names == {"Replaced", "Old Tag", "Trait 2", "Trait 3"}
        assert not any(x.id == asset.id for x in sheet.assets)
        assert any(x.name == "New equipment" for x in sheet.assets)
        assert not sheet.tags


def test_private_consent_withdrawal_and_shared_bond_effect(ledger, tmp_path, monkeypatch):
    service, cast, trainer, ref = setup(ledger, tmp_path, monkeypatch, "handler", (4, 4), 4)
    game = service.game
    original = state(game)
    choice = rules.Bond(
        account="Trainer accounts for the conversation", weaken=(current_ref(original, 3),)
    )

    def offer(key):
        menu = service.menu(trainer, 900)
        return service.invite(trainer, key, menu["revision"], 900, menu["scene"], menu["cast"])[
            "id"
        ]

    canceled = offer("first-offer")
    step(service, PLAYER, canceled, "consent", share_bonds=True)
    step(service, PLAYER, canceled, "roll")
    service.advance(
        trainer, "first-choice", canceled, state(game).revision, "choose", choice=choice
    )
    change(cast, trainer, "withdraw", ref)
    change(cast, trainer, "join", ref)
    assert service.get(trainer, canceled)["resources"] is None
    with pytest.raises(WorkflowError, match="original private scene"):
        service.advance(
            trainer, "new-cast", canceled, state(game).revision, "choose", choice=choice
        )
    ledger.safety(OTHER, "pause-to-withdraw", ledger.status(OTHER)["revision"], pause=True)
    outcome = step(service, PLAYER, canceled, "withdraw")
    assert outcome["phase"] == "withdrawn"
    assert state(game).actor_bonds == original.actor_bonds
    ledger.safety(OTHER, "resume-after-withdrawal", ledger.status(OTHER)["revision"], pause=False)

    identity = offer("second-offer")
    service.advance(
        PLAYER, "new-consent", identity, state(game).revision, "consent", share_bonds=True
    )
    service.advance(PLAYER, "new-roll", identity, state(game).revision, "roll")
    for i, effect in enumerate(
        (
            choice,
            rules.Tag(account="Second choice", label="First Tag"),
            rules.Tag(account="Repeat a choice", label="Second Tag"),
        )
    ):
        service.advance(
            trainer, f"pick-{i}", identity, state(game).revision, "choose", choice=effect
        )
    asyncio.run(
        native_request(ledger, PLAYER, identity, 91300, "confirm", account="My own account.")
    )
    final = state(game)
    actual = current_ref(final, 2)
    assert depth(final, actual, ref) == 2
    assert depth(final, actual, current_ref(final, 3)) == 1
    assert {"First Tag", "Second Tag"} <= {tag.label for tag in final.sheets["2"].tags}


def test_spoken_word_only_lifts_after_actual_success_against_its_trainer(
    ledger, tmp_path, monkeypatch
):
    service, cast, trainer, ref = setup(ledger, tmp_path, monkeypatch, "handler", (1, 2), 4)
    game = service.game
    menu = service.menu(trainer, 900)
    offer = service.invite(
        trainer, "word-training", menu["revision"], 900, menu["scene"], menu["cast"]
    )
    identity = offer["id"]
    step(service, PLAYER, identity, "consent")
    step(service, PLAYER, identity, "roll")
    asyncio.run(
        native_request(
            ledger, trainer, identity, 91400, "word", label="Quiet", account="Trainer rehearses."
        )
    )
    assert not game.helpless_status(PLAYER)
    assert service.speech(trainer, 900)["sources"] == []
    asyncio.run(
        native_request(ledger, PLAYER, identity, 91410, "confirm", account="I heard the word.")
    )
    speech = service.speech(trainer, 900)
    assert speech["sources"] == [(identity, 0, "Quiet")]
    assert not service.speech(PLAYER, 900)["sources"]
    with pytest.raises(WorkflowError, match="original two participants"):
        service.speak(OTHER, "steal-word", 900, speech["scene"], speech["revision"], identity, 0)

    async def speak():
        click = current(trainer.user_id, 91420)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        assert "conditioning-word" in dict(menu.options)
        opening = current(trainer.user_id, 91421)
        await opening.response.defer(ephemeral=True)
        await menu.open_item(opening, "conditioning-word")
        form = opening.edit_original_response.call_args.kwargs["view"]
        form.values["source"] = (identity + ":0",)
        sent = current(trainer.user_id, 91422)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(speak())
    receipt = service.speak(trainer, "91422", 900, speech["scene"], speech["revision"], identity, 0)
    assert receipt["phase"] == "word_spoken"
    assert game.helpless_status(PLAYER)
    assert not game.helpless_status(PLAYER, ordinary_recovery=True)
    with pytest.raises(WorkflowError, match="no matching Helpless recovery"):
        game.recover_helpless(
            PLAYER, "bypass-word", state(game).sheets["2"].revision, "Alone.", None
        )
    change(cast, trainer, "withdraw", ref)
    with pytest.raises(WorkflowError, match="recover from Helplessness"):
        game.begin(
            PLAYER,
            "bypass-order",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head", context="I keep my head.", trigger_confirmed=True, heat=0
            ),
        )
    worker, gateway = GameWorker(game), Gateway()
    for number, faces in enumerate(((1, 2), (6, 6))):
        game.dice.faces = faces
        root = game.issue_order(trainer, f"direct-{number}", 900, 2, "Stay where you are.")
        tick(worker, gateway)
        answer(game, PLAYER, "order_response", options=("disobey",))
        child = game.begin(
            PLAYER,
            f"refuse-{number}",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="disobey_orders",
                context="I step forward.",
                trigger_confirmed=True,
                heat=0,
                order_id=root["order_id"],
                parent=root["action_id"],
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway)
        for participant in (PLAYER, trainer):
            if any(x["kind"] == "tag_window" for x in game.choices(participant)):
                answer(game, participant, "tag_window", options=("pass",))
        if number:
            answer(game, PLAYER, "actor_disobey", flag=True)
        assert game.helpless_status(PLAYER)
        answer(game, trainer, "handler_disobey", flag=False)
        assert game.inspect(PLAYER, child)["result"]["can_disobey"] is bool(number)
        assert game.helpless_status(PLAYER) is (not number)
        tick(worker, gateway, 4)
    (utterance,) = rules.find(state(game), identity).utterances
    assert utterance.event == receipt["event"]
    assert utterance.released and utterance.released != utterance.event
    assert game.dice.calls == 3
