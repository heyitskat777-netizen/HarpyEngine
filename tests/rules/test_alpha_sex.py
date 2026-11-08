"""Normal original-PC Alpha Sex outcomes use real consent, receipts and consequences."""

import asyncio
from uuid import uuid4

import pytest
from test_alpha_brutalize import ready
from test_enforcer_requisitions import approved
from test_items import carried_asset
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

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
