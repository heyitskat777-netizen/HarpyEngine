"""Actual Handler token, paid native/graft source and printed social consequences."""

import asyncio
import copy
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_special_girl import open_special_girl, open_token
from girlframe.engine import m3_privileges as privileges
from girlframe.engine import m3_special_girl as rules
from girlframe.engine.m2 import AssetState, ChoiceAnswer, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_appearance_matrix import damages
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_special_girl import SpecialGirlService, entitlement
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, frame="THE ENFORCER", *, cap=False):
    _, game = service(store, frame=frame)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update={
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        sheet.permissions = 6
        if cap:
            while sum(x.family == "girl" for x in sheet.assets) < 4:
                sheet.assets.append(
                    AssetState(
                        id="prior:" + str(len(sheet.assets)),
                        family="girl",
                        name="Actual prior gear",
                    )
                )
            next(x for x in sheet.assets if x.family == "girl").void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_class_resources", actual)
    return game, SpecialGirlService(game)


def acquire_token(game, source, *, donor=None, number=995100):
    data = source.menu(PLAYER)
    before = state(game)
    args = (
        PLAYER,
        str(number + 1),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual paid Special Girl source",
        donor,
    )

    async def actual_purchase():
        own = current(2, number)
        await own.response.defer(ephemeral=True)
        await open_special_girl(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual paid Special Girl source")
        if donor:
            form.values.update(donor=(donor,))
        await form.confirm.callback(current(2, number + 1))
        assert form.completed

    asyncio.run(actual_purchase())
    paid = source.buy(*args)
    assert source.buy(*args) == paid
    actual = state(game)
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions - paid["cost"]
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert rules.held(actual, current_ref(actual, 2)) is None
    assert source.get(ADMIN, paid["id"])["token"]["phase"] == "handler"
    with pytest.raises(WorkflowError):
        source.get(OTHER, paid["id"])
    view = source.get(PLAYER, paid["id"])
    with pytest.raises(WorkflowError, match="original owned token"):
        source.respond(
            PLAYER,
            str(uuid4()),
            paid["id"],
            view["revision"],
            view["game_revision"],
            name="Cannot invent Handler authorship",
            description="Cannot fabricate a gift",
        )
    return paid


def complete_token(game, source, paid, *, number=995110):
    async def actual_human_steps():
        handler = current(1, number)
        handler.channel_id = 901
        await handler.response.defer(ephemeral=True)
        inbox = InboxService(game.store)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_special_girl" and x.identity == paid["id"]
        )
        await InboxView(inbox, 1).route(handler, item)
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            name="Actual Handler's keepsake",
            description="A token named and described by its actual Handler",
        )
        await form.confirm.callback(current(1, number + 1))
        assert form.completed
        waiting = state(game)
        assert not any(x.id == "special-token:" + paid["id"] for x in waiting.sheets["2"].assets)
        view = source.get(PLAYER, paid["id"])
        if view["needs_replace"]:
            forbidden = next(
                x.id for x in waiting.sheets["2"].assets if x.family == "girl" and x.void
            )
            with pytest.raises(ValueError, match="non-Void"):
                source.respond(
                    PLAYER,
                    str(uuid4()),
                    paid["id"],
                    view["revision"],
                    view["game_revision"],
                    replace=forbidden,
                )
            assert state(game) == waiting
        owner = current(2, number + 2)
        await owner.response.defer(ephemeral=True)
        await open_token(owner, source, paid["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert "Actual Handler's keepsake" in form.text()
        replacement = view["replacements"][-1]["id"] if view["needs_replace"] else None
        if replacement:
            form.values.update(replace=(replacement,))
        else:
            form.values.update(receive=("yes",))
        await form.confirm.callback(current(2, number + 3))
        assert form.completed
        result = source.respond(
            PLAYER,
            str(number + 3),
            paid["id"],
            view["revision"],
            view["game_revision"],
            replace=replacement,
        )
        assert result["phase"] == "complete"
        return replacement

    return asyncio.run(actual_human_steps())


def begin_beneath(game, faces):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual source social confrontation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    pass_tags(game)
    return identity, raw, worker, gateway


def test_native_special_girl_real_handler_token_cap_bonus_all_printed_counters_and_punishment(
    ledger, tmp_path, monkeypatch
):
    game, source = ready(ledger, tmp_path, monkeypatch, cap=True)
    before = state(game)
    paid = acquire_token(game, source)
    assert paid["cost"] == 2
    with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="put_someone_beneath_you",
                target=3,
                heat=0,
                context="Wait for the real token",
                trigger_confirmed=True,
            ),
        )
    replaced = complete_token(game, source, paid)
    actual = state(game)
    actor = current_ref(actual, 2)
    token = next(x for x in actual.sheets["2"].assets if x.id == "special-token:" + paid["id"])
    assert token.family == "girl" and token.name == "Actual Handler's keepsake"
    assert sum(x.family == "girl" for x in actual.sheets["2"].assets) == 4
    assert replaced not in {x.id for x in actual.sheets["2"].assets}
    assert sum(x.void for x in actual.sheets["2"].assets) == sum(
        x.void for x in before.sheets["2"].assets
    )
    assert rules.held(actual, actor).id == paid["id"] and game.dice.calls == 0

    # Higher Status supplies the actual +1 before normal mid-result choices.
    identity, raw, worker, gateway = begin_beneath(game, (3, 4))
    assert raw["pre_total"] == 8 and raw["special_girl_purchase"] == paid["id"]
    assert raw["pre_modifiers"] == [{"source": "Handler's Special Girl", "amount": 1}]
    assert game.roll(PLAYER, str(uuid4()), identity)["receipt"] == raw
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "Actual source Tag"},
        text="Actual result",
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 5)

    # A low counter without damage does not invent a Handler Punishment.
    identity, raw, worker, gateway = begin_beneath(game, (1, 2))
    assert raw["pre_total"] == 4
    answer(
        game, OTHER, "beneath_select", options=("status",), text="Actual counter lowers her Status"
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).order == (3, 2)
    assert not game.inspect(PLAYER, identity)["result"].get("punishment_work")
    tick(worker, gateway, 5)

    # At lower Status there is no +1; actual damage still causes the printed Handler duty.
    identity, raw, worker, gateway = begin_beneath(game, (1, 2))
    assert raw["pre_total"] == 3 and raw["pre_modifiers"] == []
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("damage",),
        text="Actual counterattack on her equipment",
    )
    selected = next(
        x.id
        for x in state(game).sheets["2"].assets
        if x.family == "girl" and not x.void and x.id != token.id
    )
    answer(game, PLAYER, "beneath_details", denied=(selected,))
    assert next(x for x in state(game).sheets["2"].assets if x.id == selected).damaged
    with ledger.engine.connect() as c:
        original_action = game.action(c, identity)
    attribution = next(
        x for x in damages(state(game)) if x.action == identity and x.asset == selected
    )
    assert attribution.damager == current_ref(state(game), 3) and attribution.target == actor
    assert attribution.event == original_action["data"]["response_event"]
    assert attribution.scene == original_action["scene_id"]
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "beneath_punishment")
    work = game.decision(ADMIN, choice["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    view = discipline.get(ADMIN, work)
    assert view["owner_id"] == "1" and view["subject_id"] == "3"
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    with pytest.raises(WorkflowError, match="source-backed resolver"):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(flag=True, text="No fake acknowledgment"),
        )
    delegated = Details(kind="passing_responsibility", delegate=2)
    delegation_args = (
        ADMIN,
        "actual-handler-delegation",
        work,
        view["revision"],
        view["game_revision"],
        delegated,
    )
    delegation_result = discipline.apply(*delegation_args)
    delegated_state = state(game)
    with pytest.raises(WorkflowError, match="other participants"):
        discipline.apply(*delegation_args)
    assert state(game) == delegated_state
    assert delegation_result["state"] == "delegated"
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    view = discipline.get(PLAYER, work)
    assert view["owner_id"] == "2" and view["subject_id"] == "3"
    before = state(game)
    details = Details(kind="stimulant_injection")
    args = (
        PLAYER,
        "actual-special-girl-punishment",
        work,
        view["revision"],
        view["game_revision"],
        details,
    )
    result = discipline.apply(*args)
    assert discipline.apply(*args) == result
    final = state(game)
    assert final.sheets["3"].heat == before.sheets["3"].heat + 7
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["receipt"] == raw and game.dice.calls == 3
    assert game.inspect(PLAYER, identity)["result"]["punishment_work"] == work
    assert len([x for x in final.sheets["2"].assets if x.id == token.id]) == 1
    assert len([x for x in damages(final) if x.action == identity and x.asset == selected]) == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_grafted_special_girl_source_suspension_preserves_token_and_status_rechecks_before_rng(
    ledger, tmp_path, monkeypatch
):
    game, source = ready(ledger, tmp_path, monkeypatch, frame="CONSUME")
    paid = acquire_token(game, source, donor="THE ENFORCER", number=995200)
    assert paid["cost"] == 3
    complete_token(game, source, paid, number=995210)
    actual = state(game)
    actor = current_ref(actual, 2)
    receipt = rules.held(actual, actor)
    token = next(x for x in actual.sheets["2"].assets if x.id == "special-token:" + paid["id"])
    assert receipt.kind == "frame_grafting" and receipt.donor_frame == "THE ENFORCER"
    removed = privileges.revoke(
        actual,
        2,
        1,
        receipt.id,
        "Actual original restoration condition",
        str(uuid4()),
        str(uuid4()),
        {int(uid): s.character_id for uid, s in actual.sheets.items()},
    )
    assert (
        rules.held(removed, actor) is None
        and removed.sheets["2"].assets == actual.sheets["2"].assets
    )
    with ledger.engine.connect() as c:
        assert entitlement(game, c, removed, actor) is None
    gate = removed.obligations[-1]
    gate.details["restoration_allowed"] = "true"
    restored = privileges.restore(removed, gate.id, actor.incarnation, None)
    assert rules.held(restored, actor) == receipt
    assert rules.token(restored, paid["id"]) == rules.token(actual, paid["id"])
    assert next(x for x in restored.sheets["2"].assets if x.id == token.id) == token
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].heat = 1
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_heat", actual)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=1,
            context="Actual source before Status changes",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    with ledger.transaction() as c:
        changed = state(game)
        shift_status(changed, 2, -1)
        game.event(c, 1, str(uuid4()), "synthetic.actual_status_change_before_rng", changed)
    with pytest.raises(WorkflowError, match="original unrolled Special Girl"):
        game.roll(PLAYER, "actual-stale-special-roll", identity)
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == 1
    assert game.inspect(PLAYER, identity)["receipt"] is None
