"""High Void contact preserves the exact random fallback and its actual ownership."""

import asyncio

import pytest
from test_budget_cleanup import Draw
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_signal import RULE, signals
from girlframe.engine.m3_world import introduce_gorgon
from girlframe.services import m3_void_signal as signal_service
from girlframe.services.inbox import InboxService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void import VoidService
from girlframe.services.m3_void_signal import SignalService
from girlframe.services.onboarding import WorkflowError


def source(ledger, threshold=False, prior=False, cascades=0):
    strain, game = ready(ledger, face=5)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(
                    subsystems=approval.subsystems | {"world", "plays"},
                )
            ),
        )
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = introduce_gorgon(initial(), gorgon("directed", "contact", (0, 0))).world
        for sheet in canon.sheets.values():
            for item in sheet.assets:
                item.void = False
        sheet = canon.sheets["2"]
        frame_assets = [x for x in sheet.assets if x.family == "frame"]
        if threshold:
            sheet.assets = [x for x in sheet.assets if x.family != "frame"] + frame_assets[:1]
        if prior:
            frame_assets[0].void = True
        canon = place(canon, 2, mode="piloting" if threshold else "outside_frame")
        game.event(c, ADMIN.user_id, "world-and-positions", "synthetic.strain_signal", canon)
    period = prepared(strain, game, high=frozenset({"void"}))
    request = next(x for x in state(game).strain.requests if x.track == "void")
    assert request.severity == "high"
    for depth in range(cascades):
        strain.dice.face = 6
        strain.roll(ADMIN, f"cascade-roll-{depth}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"cascade-choice-{depth}", request.id, 2, state(game).revision, 2)
        request = next(
            x
            for x in state(game).strain.requests
            if x.parent == request.id and x.severity == "high"
        )
    strain.dice.face = 5
    strain.roll(ADMIN, "signal-roll", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "signal-column", request.id, 2, state(game).revision, 2)
    return strain, game, period, request.id + ":effect", frame_assets[0].id


@pytest.mark.parametrize(
    ("threshold", "cascades", "legacy"),
    [(False, 0, False), (True, 0, False), (True, 3, False), (True, 0, True)],
    ids=["ordinary", "full-family", "nested-cascade", "legacy-work-id"],
)
def test_high_void_draw_and_original_inbox_gain_resolve_only_after_actual_effect(
    ledger, threshold, cascades, legacy, monkeypatch
):
    strain, game, period, identity, asset = source(ledger, threshold=threshold, cascades=cascades)
    draw = Draw()
    effects = EffectService(strain, selector=draw)
    start_revision = state(game).revision
    before = state(game).strain.events
    build, commit, _ = effect_form(ADMIN, effects, identity)
    assert ("contact", "contact") in next(x for x in build({}) if x.key == "signal").options
    description = "The Gorgon reaches across Voidspace."
    assert "original recipient" in commit(
        ADMIN,
        "stage",
        dict(signal=("contact",), account=description),
    )
    staged = effects.apply(
        ADMIN,
        "stage",
        identity,
        1,
        start_revision,
        Choice(rule_id=RULE, target="contact", account=description),
    )
    assert staged["state"] == "pending" and draw.calls == 1
    assert effects.get(ADMIN, identity)["awaiting_void_signal"]
    assert strain.periods.get(ADMIN, period)["phase"] == "preparing"

    service = SignalService(strain)
    inbox = InboxService(ledger)
    revision = state(game).revision
    for viewer in (ADMIN, OTHER):
        assert not any(x.task == "m3_strain_void_signal" for x in inbox.items(viewer))
        with pytest.raises(WorkflowError, match="originally drawn Girl"):
            service.gain(viewer, "wrong", identity, revision, asset, "No")
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.gain(PLAYER, "stale", identity, revision - 1, asset, "Old draft")
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.gain(PLAYER, "paused", identity, revision, asset, "Paused draft")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)

    account = "The Void alters the look of the original owned hardware."

    async def gain_from_inbox():
        item = next(x for x in inbox.items(PLAYER) if x.task == "m3_strain_void_signal")
        click = current(PLAYER.user_id, 96300)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(asset=(asset,), account=account)
        await form.confirm.callback(current(PLAYER.user_id, 96301))
        assert form.completed

    revision = state(game).revision
    with monkeypatch.context() as old_writer:
        if legacy:
            old_writer.setattr(
                signal_service, "_threshold_id", lambda parent, family: f"{parent}:signal:{family}"
            )
        asyncio.run(gain_from_inbox())
    expected = "pending" if threshold else "resolved"
    assert (
        SignalService(strain).gain(PLAYER, "96301", identity, revision, asset, account)["state"]
        == expected
    )
    (saved,) = signals(state(game))
    assert saved.actor.entity == "2" and saved.asset == asset and saved.gain_event
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
    assert effects.get(ADMIN, identity)["state"] == expected
    if threshold:
        (required,) = saved.thresholds
        if legacy:
            assert required == f"{identity}:signal:frame"
        assert len(required) <= 100
        assert VoidService(ledger).get(PLAYER, required)["stage"] == "resist_pending"
        worker, gateway = GameWorker(game), Gateway()
        game.dice.faces = (1, 1)
        action = game.begin(
            PLAYER,
            "resist",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                source_work=required,
                heat=state(game).sheets["2"].heat,
                context="Resist the full Void alteration",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The actual resistance holds.")
        tick(worker, gateway, 4)
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert VoidService(ledger).get(PLAYER, required)["stage"] == "prevented"
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    assert state(game).strain.events == before and draw.calls == 1


def test_existing_void_requires_the_gorgon_linked_play_without_using_random_fallback(ledger):
    strain, game, _, identity, _ = source(ledger, prior=True)
    draw = Draw()
    effects = EffectService(strain, selector=draw)
    before = state(game)
    with pytest.raises(WorkflowError, match="actual Gorgon-linked Dive"):
        effects.apply(
            ADMIN,
            "cannot-substitute",
            identity,
            1,
            before.revision,
            Choice(rule_id=RULE, target="contact", account="Attempted contact"),
        )
    assert effects.get(ADMIN, identity)["state"] == "pending"
    assert state(game) == before and draw.calls == 0
