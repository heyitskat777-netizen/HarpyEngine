"""Real recursive Strain → selected Endgame → actual owned persistent Tag uses."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_budget_tags import open_gift
from girlframe.engine import m3_budget_tags as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_tags import BudgetTagService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.onboarding import WorkflowError


def source(store, *, option=5):
    strain, game = ready(store, face=6)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    period = prepared(strain, game, high=frozenset({"budget"}))
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "budget" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(
        ADMIN,
        "actual-budget-persistent-endgame",
        request.id,
        1,
        state(game).revision,
        option,
        endgame=True,
    )
    return BudgetTagService(store), game, strain, request.id + ":effect", period


def nominate(service, game, identity):
    data = service.view(ADMIN, identity)
    girl = current_ref(state(game), 2)
    result = service.nominate(
        ADMIN,
        "actual-girl-selected",
        identity,
        data["revision"],
        data["game_revision"],
        girl,
        "An actual source Endgame selects this Girl to give the Tag",
    )
    return result["id"], girl


def test_real_recursive_source_native_owned_gift_persists_through_repeated_real_uses(ledger):
    service, game, strain, identity, _ = source(ledger)
    original = state(game)
    inbox = InboxService(ledger)
    parent_card = next(x for x in inbox.items(ADMIN) if x.identity == identity)
    assert parent_card.task == "m3_budget_tag"
    assert strain.dice.calls == 4 and game.dice.calls == 0

    async def run():
        handler = current(1, 810)
        await handler.response.defer(ephemeral=True)
        await open_gift(handler, service, identity)
        selection = handler.edit_original_response.call_args.kwargs["view"]
        assert isinstance(selection, NativeForm) and state(game) == original
        girl = current_ref(state(game), 2)
        selection.values.update(girl=(girl.token,), account="The actual Endgame choice")
        await selection.confirm.callback(current(1, 811))
        card = next(x for x in inbox.items(PLAYER) if x.task == "m3_budget_tag")
        assert not any(x.task == "m3_budget_tag" for x in inbox.items(OTHER))
        player = current(2, 812)
        await player.response.defer(ephemeral=True)
        await open_gift(player, service, card.identity)
        form = player.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 813))
        form.values.update(
            tag="PRIVATE_GIRL_GIFT", account="The Girl gives her own actual descriptor"
        )
        await form.confirm.callback(current(2, 814))
        return card.identity, girl

    gift_id, girl = asyncio.run(run())
    current_state = state(game)
    tag = current_state.handler_tags[-1]
    assert tag.label == "PRIVATE_GIRL_GIFT" and tag.giver_actor == girl
    assert service.view(ADMIN, identity)["gift"]["stage"] == "given"
    assert "PRIVATE_GIRL_GIFT" not in str(inbox.items(OTHER))
    uses = HandlerTagService(game)
    for i in range(2):
        data = uses.view(PLAYER, 900, girl)
        assert next(x for x in data["tags"] if x["id"] == tag.id)["persistent"]
        key = "actual-persistent-use-" + str(i)
        result = uses.use(
            PLAYER,
            key,
            900,
            girl,
            data["source_sha256"],
            tag.id,
            "attention",
            "Actual source request " + str(i),
        )
        assert (
            uses.use(
                PLAYER,
                key,
                900,
                girl,
                data["source_sha256"],
                tag.id,
                "attention",
                "Actual source request " + str(i),
            )
            == result
        )
        assert result["persistent"] and any(x.id == tag.id for x in state(game).handler_tags)
    assert game.dice.calls == 0 and strain.dice.calls == 4
    assert service.view(PLAYER, gift_id)["state"] == "resolved"


def test_original_owner_pause_stale_and_replay_cannot_duplicate_or_forge_gift(ledger):
    service, game, _, identity, _ = source(ledger)
    with pytest.raises(WorkflowError):
        service.view(OTHER, identity)
    with pytest.raises(WorkflowError, match="original Handler"):
        service.nominate(
            PLAYER,
            "wrong-nominator",
            identity,
            1,
            state(game).revision,
            current_ref(state(game), 2),
            "Cannot choose for Handler",
        )
    gift, girl = nominate(service, game, identity)
    with pytest.raises(WorkflowError, match="selected original Girl"):
        service.give(
            ADMIN, "wrong-giver", gift, state(game).revision, "FORGED", "Cannot write her choice"
        )
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE"):
        service.give(PLAYER, "stale-giver", gift, before.revision - 1, "STALE", "Old source")
    ledger.safety(OTHER, "pause-gift", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.give(PLAYER, "paused-giver", gift, before.revision, "PAUSED", "Paused choice")
    ledger.safety(OTHER, "resume-gift", ledger.status(OTHER)["revision"], pause=False)
    result = service.give(
        PLAYER,
        "actual-given-once",
        gift,
        before.revision,
        "Actual gift",
        "The actual Girl's descriptor",
    )
    assert (
        service.give(
            PLAYER,
            "actual-given-once",
            gift,
            before.revision,
            "Actual gift",
            "The actual Girl's descriptor",
        )
        == result
    )
    assert len([x for x in state(game).handler_tags if x.id == result["tag"]]) == 1


def test_failure_after_canonical_gift_rolls_back_tag_work_and_history_then_retries(
    ledger, monkeypatch
):
    service, game, _, identity, _ = source(ledger)
    gift, girl = nominate(service, game, identity)
    before = state(game)
    real_event = service.game.event

    def failure(*args, **kwargs):
        real_event(*args, **kwargs)
        raise RuntimeError("Synthetic post-event failure")

    monkeypatch.setattr(service.game, "event", failure)
    with pytest.raises(RuntimeError):
        service.give(
            PLAYER, "retry-real-gift", gift, before.revision, "Actual gift", "Actual descriptor"
        )
    assert state(game) == before and service.view(PLAYER, gift)["state"] == "pending"
    monkeypatch.setattr(service.game, "event", real_event)
    service.give(
        PLAYER, "retry-real-gift", gift, before.revision, "Actual gift", "Actual descriptor"
    )
    assert service.view(PLAYER, gift)["state"] == "resolved"


def test_current_marker_or_tag_tampering_cannot_forge_persistence(ledger):
    service, game, _, identity, _ = source(ledger)
    gift, girl = nominate(service, game, identity)
    result = service.give(
        PLAYER, "actual-gift", gift, state(game).revision, "Actual descriptor", "Actual Gift"
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags[-1].label = "Forged descriptor"
        game.event(c, 1, str(uuid4()), "synthetic.source_tamper", canon)
    handler_tags = HandlerTagService(game)
    view = handler_tags.view(PLAYER, 900, girl)
    before = state(game)
    with pytest.raises(WorkflowError, match="immutable persistent"):
        handler_tags.use(
            PLAYER,
            "cannot-forge-source",
            900,
            girl,
            view["source_sha256"],
            result["tag"],
            "attention",
            "Actual attempted use",
        )
    assert state(game) == before


@pytest.mark.parametrize("ended", ["handler", "girl"])
def test_only_real_original_ending_closes_pending_gift_without_giving_successor_tag(ledger, ended):
    from girlframe.engine import m3_handler_consequences as handler_rules
    from girlframe.services.m3_careers import end_in_transaction

    service, game, _, identity, _ = source(ledger)
    gift, girl = nominate(service, game, identity)
    with pytest.raises(WorkflowError, match="Prove the actual"):
        service.close_original(ADMIN, "cannot-close-living-source", gift, state(game).revision)
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        if ended == "handler":
            canon, required = handler_rules.require(
                canon,
                handler_rules.active_handler(canon),
                trigger="asset_damage",
                source_action=None,
                source_work=identity,
                source_event="synthetic-established-damage",
                opponent=girl,
                appointment="synthetic-source-appointment",
            )
            canon = handler_rules.apply(
                canon, required, "death", "The actual original Handler dies", event
            )
        else:
            canon = end_in_transaction(
                c,
                game,
                canon,
                girl,
                reason="death",
                source_event=event,
                account="The actual selected Girl dies",
                archive_id="actual-gift-girl-death",
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_ending", canon, event_id=event)
    before = state(game)
    result = service.close_original(ADMIN, "close-real-original", gift, before.revision)
    assert result["state"] == "original_ended" and not state(game).handler_tags
    assert rules.gifts(state(game))[-1].stage == "original_ended"
    assert service.view(ADMIN, identity)["state"] == "resolved"


def test_original_retired_girl_can_give_without_spending_any_successor_resources(ledger):
    from girlframe.services.m3_careers import end_in_transaction

    service, game, _, identity, _ = source(ledger)
    gift, girl = nominate(service, game, identity)
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon = end_in_transaction(
            c,
            game,
            canon,
            girl,
            reason="retirement",
            source_event=event,
            account="Actual original living retirement",
            archive_id="actual-retired-gift-girl",
        )
        game.event(
            c, 2, str(uuid4()), "synthetic.actual_original_retirement", canon, event_id=event
        )
    before = state(game)
    service.give(
        PLAYER,
        "retired-original-gives",
        gift,
        before.revision,
        "Her actual descriptor",
        "The retired original Girl gives this Tag",
    )
    assert state(game).sheets == before.sheets
    assert state(game).handler_tags[-1].giver_actor == girl
