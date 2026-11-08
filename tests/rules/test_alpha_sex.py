"""Normal original-PC Alpha Sex outcomes use real consent, receipts and consequences."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_alpha_brutalize import ready
from test_enforcer_requisitions import approved
from test_items import carried_asset
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_alpha import conditions
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_alpha_sex import SexService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch, faces, *, native=False, item=False, extra=()):
    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, *extra))
    service = SexService(game)
    if item:
        asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
        carried_asset(game, PLAYER, asset)
    if native:
        from girlframe.discord_adapter.m2_forms import NativeForm
        from girlframe.discord_adapter.m3_alpha_sex import open_alpha

        async def source():
            owner = current(2, 98001)
            owner.channel_id = 900
            await owner.response.defer(ephemeral=True)
            await open_alpha(owner, service)
            form = owner.edit_original_response.call_args.kwargs["view"]
            form.values["action"] = ("invite",)
            chosen = current(2, 98002)
            await form.confirm.callback(chosen)
            next_form = chosen.edit_original_response.call_args.kwargs["view"]
            assert isinstance(next_form, NativeForm)
            next_form.values.update(
                target=(current_ref(state(game), 3).token,),
                account="My actual voluntary source interaction",
            )
            await next_form.confirm.callback(current(2, 98003))
            assert game.dice.calls == 0
            value = rules.sessions(state(game))[-1]
            target = current(3, 98004)
            target.channel_id = 900
            await target.response.defer(ephemeral=True)
            from girlframe.discord_adapter.inbox import InboxView

            inbox = InboxService(store)
            invitation = next(x for x in inbox.items(OTHER) if x.identity == value.id)
            assert invitation.task == "m3_alpha_consent"
            assert not any(x.identity == value.id for x in inbox.items(ADMIN))
            await InboxView(inbox, 3).route(target, invitation)
            form = target.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                accept=("yes",), account="My own voluntary actual source confirmation"
            )
            await form.confirm.callback(current(3, 98006))
            assert form.completed

        asyncio.run(source())
        identity = rules.sessions(state(game))[-1].id
    else:
        identity = service.invite(
            PLAYER,
            str(uuid4()),
            900,
            current_ref(state(game), 3),
            state(game).revision,
            "Actual voluntary source proposed by Alpha",
        )["id"]
        service.respond(
            OTHER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "The actual counterpart confirms their own voluntary source",
        )
    return game, worker, gateway, service, identity


def rolled(store, tmp_path, monkeypatch, faces, *, native=False, item=False, extra=()):
    game, worker, gateway, service, identity = setup(
        store, tmp_path, monkeypatch, faces, native=native, item=item, extra=extra
    )
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            target_actor=current_ref(state(game), 3),
            source_work=identity,
            heat=0,
            context="The actual confirmed voluntary interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, service, identity, action


def test_mid_actual_native_source_bond_broken_and_smell_without_movement(
    ledger, tmp_path, monkeypatch
):
    game, _, _, service, identity, action = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), native=True
    )
    actual = state(game)
    own, other = current_ref(actual, 2), current_ref(actual, 3)
    assert depth(actual, own, other) == 2 and conditions(actual, other, own)
    assert service.track(PLAYER, identity)["cell"] == (0, 0)
    assert not service.track(PLAYER, identity)["moved"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_high_actual_asset_damage_with_bond_broken(ledger, tmp_path, monkeypatch):
    game, _, _, _, identity, action = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)
    answer(game, PLAYER, "alpha_sex_damage", options=(asset.id,))
    actual = state(game)
    assert next(x for x in actual.sheets["3"].assets if x.id == asset.id).damaged
    assert (
        rules.get(actual, identity).condition
        and game.inspect(PLAYER, action)["state"] == "complete"
    )
    assert game.dice.calls == 1


@pytest.mark.parametrize("opportunity", ["take", "play", "punish"])
def test_low_real_sleep_and_owned_opportunity_then_actual_wake(
    ledger, tmp_path, monkeypatch, opportunity
):
    game, worker, gateway, _, identity, action = rolled(
        ledger, tmp_path, monkeypatch, (1, 1), item=opportunity == "take"
    )
    sleeping = state(game)
    actor = current_ref(sleeping, 2)
    assert rules.asleep(sleeping, actor)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    with pytest.raises(WorkflowError, match="ASLEEP"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            sleeping.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                parent=action,
                context="No reprisal while actually asleep",
                trigger_confirmed=True,
            ),
        )
    if opportunity == "take":
        data = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_low")
        detail = game.decision(OTHER, data["id"])["alpha_sex"]
        answer(
            game,
            OTHER,
            "alpha_sex_low",
            options=("take",),
            fields={"item": detail["items"][0]["id"]},
            text="I take the actual detachable apparatus",
        )
        assert state(game).item_transfers[-1].source_kind == "alpha_sex"
        assert state(game).item_transfers[-1].recipient == current_ref(state(game), 3)
    elif opportunity == "play":
        answer(game, OTHER, "alpha_sex_low", options=("play",))
        game.dice.faces = (2, 3)
        child = game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                parent=action,
                context="My actual source opportunity Keep",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, OTHER, "actor_keep", options=("sexy",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual source Keep adjudication")
        assert game.inspect(OTHER, child)["state"] == "complete"
    else:
        answer(game, OTHER, "alpha_sex_low", options=("punish",))
        case = state(game).role_punishments[-1]
        role = RolePunishmentService(game)

        def change(viewer, **kwargs):
            return role.change(
                viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **kwargs
            )

        details = Details(kind="stimulant_injection")
        change(
            OTHER,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(OTHER, scene="The actual on-scene source Punishment, not fictional consent")
        change(PLAYER, attest=True)
        change(OTHER, execute=True, account="I actually administer the instructed injection")
        assert state(game).sheets["2"].heat == sleeping.sheets["2"].heat + 7
    assert rules.asleep(state(game), actor)
    answer(
        game,
        PLAYER,
        "alpha_sex_wake",
        options=("wake",),
        text="I actually wake from the source sleep",
    )
    assert not rules.asleep(state(game), actor)
    assert rules.get(state(game), identity).wake_event
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.dice.calls == (2 if opportunity == "play" else 1)


def test_actual_sleeping_source_native_ordinary_dive_counter_keeps_receipt_and_wake(
    ledger, tmp_path, monkeypatch
):
    """A real non-Keep child uses the counterpart's own Dive and original held parent."""
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_alpha_sex import open_alpha_choice

    game, worker, gateway, _, identity, parent = rolled(
        ledger,
        tmp_path,
        monkeypatch,
        (1, 1),
        extra=(
            "play.basic.flirt",
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
            "play.basic.dive_deep",
        ),
    )
    original_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_sex_low", options=("play",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_counter_play")

    async def native():
        interaction = current(3, 98901)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_alpha_choice(interaction, game, choice["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        plays = next(x for x in form.fields if x.key == "play")
        assert "dive_deep" in dict(plays.options) and "check_sensors" in dict(plays.options)

    asyncio.run(native())
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            parent=parent,
            context="My actual communion during this one sleeping-source opportunity",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        ADMIN,
        "dive_select",
        options=("void_and_unmark_all",),
        text="The actual low Dive uses its printed Handler choice",
    )
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "frame" and not x.void)
    answer(
        game,
        OTHER,
        "dive_effect",
        fields={"asset": asset.id},
        text="Actual threads now run through this Frame feature",
    )
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert rules.asleep(state(game), current_ref(state(game), 2))
    assert rules.get(state(game), identity).phase == "waking"
    answer(game, PLAYER, "alpha_sex_wake", options=("wake",), text="I actually wake now")
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == original_receipt
    assert game.dice.calls == 2


def test_actual_native_stim_self_dose_counter_keeps_sleep_parent_receipt_and_owned_wake(
    ledger, tmp_path, monkeypatch
):
    """Deferred: actual native own Play; it need not target the sleeping Alpha."""
    from m3_policy_scenario import configure_m3_fixture
    from test_creation import selected
    from test_creation_review import ready as creation_ready
    from test_m2_game import Dice, Gateway
    from test_physical_operations import place
    from test_world import initial

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m3_alpha_sex import open_alpha_choice, open_consent
    from girlframe.discord_adapter.m3_dose_up import open_choice as dose_choice
    from girlframe.engine import m3_dose_up as dose
    from girlframe.engine.m2 import ChoiceAnswer, ReleaseApproval
    from girlframe.engine.m2_registry import registry_digest
    from girlframe.services.creation_review import CreationReviewService
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_alpha_sex import counter_plays, self_dose_counter
    from girlframe.services.m3_dose_up import DoseUpService
    from girlframe.services.m3_dose_up import prove as prove_dose

    review, creation, _ = creation_ready(
        ledger, girl="ALPHA", frame="THE ENFORCER", other_girl="STIM-BLISSED"
    )
    current_draft = creation.get(OTHER)
    draft = selected("STIM-BLISSED", "JANUS-B").model_copy(
        update={"shared_tokens": current_draft.draft.shared_tokens}
    )
    creation.save(OTHER, "actual-alpha-counter-stim-build", current_draft.revision, 1, draft)
    other_review = CreationReviewService(ledger)
    incoming = next(x for x in other_review.get(OTHER).sheet.bonds if not x.outgoing)
    current_draft = creation.get(OTHER)
    other_review.select_bond(
        OTHER,
        "actual-alpha-counter-stim-bond",
        current_draft.revision,
        1,
        current_draft.draft,
        incoming.id,
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    game = GameService(ledger, dice=Dice((1, 1)))
    for viewer in (PLAYER, OTHER):
        saved = review.get(viewer)
        review.save(
            viewer,
            "actual-counter-review-" + str(viewer.user_id),
            saved.saved_revision,
            saved.fingerprint,
        )
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review
        game.activate(viewer, "actual-counter-active-" + str(viewer.user_id), saved.fingerprint)
    configure_m3_fixture(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE, dose.RULE))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        original = state(game)
        original.world = initial()
        original = place(place(original, 2, mode="outside_frame"), 3, mode="outside_frame")
        original.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.original_alpha_stim_counter_bodies", original)
    game.bind_scene(ADMIN, "actual-alpha-self-dose-scene", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, "actual-alpha-self-dose-join-" + str(viewer.user_id), 900)
    worker, gateway, service = GameWorker(game), Gateway(), SexService(game)
    alpha, stim = current_ref(state(game), 2), current_ref(state(game), 3)
    assert state(game).sheets["2"].girl == "ALPHA"
    assert state(game).sheets["3"].girl == "STIM-BLISSED"
    session = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        stim,
        state(game).revision,
        "My actual original voluntary Alpha interaction",
    )["id"]

    def interaction(user=3, channel=900):
        value = current(user, uuid4().int % 1000000000)
        value.channel_id = channel
        return value

    async def native_consent():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_consent(opened, service, session)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(accept=("yes",), account="My actual Stim confirms only her own source")
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(native_consent())
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=session,
            target_actor=stim,
            heat=0,
            context="Our actually confirmed original source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert rules.asleep(state(game), alpha)
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    consent_event = rules.get(state(game), session).consent_event

    async def choose_counter():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_low")
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["opportunity"] = ("play",)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(choose_counter())
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_counter_play")
    with ledger.engine.connect() as c:
        actual_parent = game.action(c, parent)
        assert dose.PLAY in counter_plays(game, c, state(game), actual_parent, stim)
        with pytest.raises(WorkflowError):
            self_dose_counter(
                game,
                c,
                state(game),
                PLAYER,
                PlayInput(
                    play=dose.PLAY,
                    parent=parent,
                    heat=0,
                    context="Not the actual counterpart",
                    trigger_confirmed=True,
                ),
                900,
            )
    before = state(game)
    calls = game.dice.calls

    async def prepare_counter_native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert dose.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(
            play=(dose.PLAY,),
            heat=("1",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="I actually self-inject my own combat cocktail while she sleeps",
            trigger=("yes",),
            disposable_heat=("0",),
        )
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(prepare_counter_native())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = game.action(
            c,
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == ledger.campaign_id,
                    actions.c.parent_id == parent,
                    actions.c.actor_id == "3",
                )
            ),
        )
    child_id = child["id"]
    assert child_id != parent and child["parent_id"] == parent and child["actor_id"] == "3"
    assert child["data"]["prepared"]["source_work"] is None
    assert child["data"]["dose_up"]["actor"] == stim.model_dump(mode="json")
    assert child["data"]["dose_up"]["target"] == stim.model_dump(mode="json")
    assert child["data"]["dose_up"]["contact"] is None
    assert child["data"]["dose_up"]["order"] is None
    assert "princess_direction" not in child["data"]["dose_up"]
    assert child["data"]["alpha_sex_counter_source"]["choice"] == choice["id"]
    assert game.dice.calls == calls and state(game).sheets["3"].heat == before.sheets["3"].heat
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert rules.asleep(state(game), alpha)
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    row = next(x for x in game.choices(OTHER) if x["kind"] == "dose_up_components")
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, row["id"])

    async def real_stim_components():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await dose_choice(opened, game, game.decision(OTHER, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["components"] = ("quick", "strong")
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(real_stim_components())
    actual = state(game)
    assert game.inspect(OTHER, child_id)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert rules.asleep(actual, alpha) and rules.get(actual, session).phase == "waking"
    assert rules.get(actual, session).wake_event is None
    assert rules.get(actual, session).consent_event == consent_event
    with ledger.engine.connect() as c:
        value = prove_dose(game, c, actual, child_id)
        assert value.actor == value.target == stim and value.caster == 3
        assert value.total == 8 and value.heat == 1 and value.contact is None
        assert value.duration == 2 and len(value.selections) == 1
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == value.roll_event)) == "3"
        )
        assert game.action(c, child_id)["data"].get("alpha_sex_counter_done")
    assert len(dose.drug_tags(actual, stim)) == 2
    assert not dose.drug_tags(actual, alpha)
    assert not dose.records(actual, dose.Contact)
    wake = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_sex_wake")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            wake["id"],
            wake["revision"],
            ChoiceAnswer(options=("wake",), text="Not my original source wake"),
        )

    async def original_alpha_wakes():
        opened = interaction(2)
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, wake["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = "I actually wake from my original source sleep"
        submitted = interaction(2)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(original_alpha_wakes())
    assert not rules.asleep(state(game), alpha) and rules.get(state(game), session).wake_event
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.dice.calls == calls + 1
    assert DoseUpService(ledger, game).view(OTHER, child_id)["components"] == [
        "Upper:Quick",
        "Upper:Strong",
    ]
    with pytest.raises(WorkflowError):
        DoseUpService(ledger, game).view(PLAYER, child_id)
    tick(worker, gateway, 5)
