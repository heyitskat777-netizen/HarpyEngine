"""Real observed Handler Tags are spent once; original humans retain their own choices."""

import asyncio
import json

import pytest
from test_actor_play_service import begin, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_handler_tags as rules
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.onboarding import WorkflowError


def test_invalid_private_source_state_is_not_included_in_native_service_errors(ledger):
    service, game, girl = setup(ledger)
    view = service.view(PLAYER, 900, girl)
    with ledger.transaction() as c:
        row = t.m2["m2_state"]
        raw = json.loads(c.scalar(row.select().with_only_columns(row.c.body_json)))
        raw["handler_heat"] = "PRIVATE_INVALID_RESOURCE_VALUE"
        c.execute(
            row.update()
            .where(row.c.campaign_id == ledger.campaign_id)
            .values(body_json=json.dumps(raw))
        )
    for command in (
        lambda: service.view(PLAYER, 900, girl),
        lambda: service.actors(PLAYER, 900),
        lambda: service.use(
            PLAYER,
            "cannot-leak-invalid-private-source",
            900,
            girl,
            view["source_sha256"],
            "tag",
            "attention",
            "Actual factual request",
        ),
    ):
        with pytest.raises(WorkflowError) as failure:
            command()
        assert "PRIVATE_INVALID_RESOURCE_VALUE" not in str(failure.value)
        assert "input_value" not in str(failure.value)


def test_attention_notice_reaches_only_original_human_and_native_read_is_not_a_response(ledger):
    from girlframe.discord_adapter.m3_handler_tags import open_handler_tags
    from girlframe.services.inbox import InboxService

    service, game, girl = setup(ledger)
    result = use(service, girl, kind="attention")
    inbox = InboxService(ledger)
    notice = next(x for x in inbox.items(ADMIN) if x.source == "handler_tag_notice")
    assert notice.identity == result["id"] and notice.state == "pending"
    assert not any(x.source == "handler_tag_notice" for x in inbox.items(OTHER))
    assert not any(x.source == "handler_tag_notice" for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="original Handler"):
        service.read_attention(PLAYER, "cannot-read-for-handler", result["id"])
    before = state(game).model_dump_json()

    async def read():
        caller = current(1, 920001)
        await caller.response.defer(ephemeral=True)
        await open_handler_tags(caller, game, identity=result["id"])
        assert (
            "PRIVATE\\_ACTUAL\\_REQUEST"
            in caller.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(read())
    assert next(x for x in inbox.items(ADMIN) if x.key == notice.key).state == "resolved"
    service.read_attention(ADMIN, "read-again-does-not-reapply", result["id"])
    assert state(game).model_dump_json() == before and game.dice.calls == 0
    assert service.get(ADMIN, result["id"])["response"] is None
    with ledger.engine.connect() as c:
        assert not list(c.execute(t.m3["m3_required_work"].select()))
        assert (
            len(
                list(
                    c.execute(
                        t.events.select().where(t.events.c.kind == "m3.handler_tag_attention_read")
                    )
                )
            )
            == 1
        )


def test_saved_private_receipts_and_notice_reads_survive_unavailable_rules_while_writes_block(
    ledger, monkeypatch
):
    from girlframe.services import m3_access

    service, game, girl = setup(ledger)
    result = use(service, girl, kind="attention")
    before = state(game).model_dump_json()

    def missing():
        raise WorkflowError("Synthetic unavailable registry")

    monkeypatch.setattr(m3_access, "load_registry", missing)
    assert service.get(ADMIN, result["id"])["account"] == "PRIVATE_ACTUAL_REQUEST"
    assert service.get(PLAYER, result["id"])["kind"] == "attention"
    with pytest.raises(WorkflowError, match="original two"):
        service.get(OTHER, result["id"])
    service.read_attention(ADMIN, "original-handler-read-under-unavailable-rules", result["id"])
    with pytest.raises(WorkflowError):
        service.view(PLAYER, 900, girl)
    with pytest.raises(WorkflowError):
        service.respond(
            ADMIN, "no-gameplay-under-unavailable-rules", result["id"], 1, "agree", "No rule bypass"
        )
    assert state(game).model_dump_json() == before


def setup(store):
    _, game, _, _, _ = ready(store)
    service = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    return service, game, girl


def test_pre_roll_tag_removal_preserves_stale_commitment_without_spending_then_allows_redeclare(
    ledger,
):
    from test_actor_play_service import begin as begin_actor

    actor_service, game, _, handler, _ = ready(ledger)
    old = begin_actor(actor_service, handler)
    service = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    use(service, girl, kind="attention")
    before = state(game).handler_heat
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    assert game.inspect(ADMIN, old)["receipt"] is None and game.dice.calls == 0
    assert state(game).handler_heat == before
    game.abort(ADMIN, "restore-stale-unrolled-tag-source", old)
    tick(worker, gateway, 4)
    saved = next(x for x in actor_service.saved(ADMIN) if x["id"] == old)
    assert not saved["rolled"]
    actor_service.recover(
        ADMIN, "cancel-stale-unrolled-tag-source", old, saved["revision"], cancel=True
    )
    fresh = begin_actor(actor_service, handler)
    tick(worker, gateway, 3)
    assert game.inspect(ADMIN, fresh)["receipt"] is not None and game.dice.calls == 1
    assert service.get(ADMIN, rules.uses(state(game))[0].id)["kind"] == "attention"


def use(service, girl, *, kind="favour", key="spend-actual-handler-tag"):
    view = service.view(PLAYER, 900, girl)
    return service.use(
        PLAYER, key, 900, girl, view["source_sha256"], "tag", kind, "PRIVATE_ACTUAL_REQUEST"
    )


@pytest.mark.parametrize(
    "kind,response",
    [("favour", "agree"), ("favour", "decline"), ("compel", "pause"), ("compel", "give_in")],
)
def test_original_handler_owns_printed_response_and_favour_grants_no_automatic_benefit(
    ledger, kind, response
):
    service, game, girl = setup(ledger)
    before = state(game)
    offered = use(service, girl, kind=kind)
    assert offered["state"] == "pending" and not state(game).handler_tags
    with pytest.raises(WorkflowError):
        service.respond(
            PLAYER, "cannot-answer-for-handler", offered["id"], 1, response, "My answer"
        )
    with pytest.raises(WorkflowError):
        service.get(OTHER, offered["id"])
    result = service.respond(
        ADMIN,
        "real-handler-answer-once",
        offered["id"],
        1,
        response,
        "The original Handler's actual response",
    )
    assert (
        service.respond(
            ADMIN,
            "real-handler-answer-once",
            offered["id"],
            1,
            response,
            "The original Handler's actual response",
        )
        == result
    )
    final = state(game)
    assert final.sheets == before.sheets and final.handler_heat == before.handler_heat
    assert service.get(PLAYER, offered["id"])["response"] == response
    assert game.dice.calls == 0 and len(rules.uses(final)) == 1
    assert HandlerTagService(GameService(ledger)).get(ADMIN, offered["id"])["state"] == "resolved"


def test_attention_is_diceless_and_spent_tag_cannot_be_reused_or_freshened_by_retry(ledger):
    service, game, girl = setup(ledger)
    view = service.view(PLAYER, 900, girl)
    result = service.use(
        PLAYER,
        "actual-attention-once",
        900,
        girl,
        view["source_sha256"],
        "tag",
        "attention",
        "My actual request for attention",
    )
    assert result["state"] == "resolved"
    assert (
        service.use(
            PLAYER,
            "actual-attention-once",
            900,
            girl,
            view["source_sha256"],
            "tag",
            "attention",
            "My actual request for attention",
        )
        == result
    )
    with pytest.raises(WorkflowError):
        service.use(
            PLAYER,
            "cannot-spend-twice",
            900,
            girl,
            view["source_sha256"],
            "tag",
            "attention",
            "Again",
        )
    assert not state(game).handler_tags and game.dice.calls == 0


def test_unknown_tag_and_another_girls_role_fail_before_consumption(ledger):
    service, game, girl = setup(ledger)
    before = state(game)
    with pytest.raises(WorkflowError):
        service.view(OTHER, 900, girl)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags.append(
            TagState(id="unobserved", label="PRIVATE_UNKNOWN", giver=1, observers=(1,))
        )
        game.event(c, 1, "private-handler-tag-fixture", "synthetic.state", canon)
    view = service.view(PLAYER, 900, girl)
    assert "PRIVATE_UNKNOWN" not in str(view)
    with pytest.raises(WorkflowError):
        service.use(
            PLAYER,
            "cannot-use-unknown",
            900,
            girl,
            view["source_sha256"],
            "unobserved",
            "compel",
            "Unknown",
        )
    assert state(game).sheets == before.sheets and len(state(game).handler_tags) == 2


def test_anytime_tag_consumption_invalidates_pending_proposal_without_new_roll(ledger):
    plays, game, _, handler, _ = ready(ledger)
    service = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    identity = begin(plays, handler)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    decision = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    details = game.decision(PLAYER, decision["id"])
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=("tag",),
        fields={"as_actor": details["roles"][0]["token"]},
        number=1,
        text="Actual source relevance",
    )
    original_receipt = game.inspect(ADMIN, identity)["receipt"]
    use(service, girl, kind="attention")
    assert game.inspect(ADMIN, identity)["receipt"] == original_receipt
    assert any(x["kind"] == "tag_window" for x in game.choices(PLAYER))
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, ADMIN, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, OTHER, "handler_keep", flag=True, text="Actual original Director's ruling")
    assert game.inspect(ADMIN, identity)["state"] == "complete" and game.dice.calls == 1


def test_native_actual_tag_and_original_handler_reply_dropdowns_complete_whole_flow(ledger):
    from girlframe.discord_adapter.m3_handler_tags import open_handler_tags

    service, game, girl = setup(ledger)

    async def send():
        caller = current(2, 311001)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_handler_tags(caller, game, actor=girl)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(tag=("tag",), kind=("compel",), account="Act on the actual Tag")
        await form.confirm.callback(current(2, 311002))
        assert form.completed

    asyncio.run(send())
    case = rules.uses(state(game))[0]

    async def respond():
        caller = current(1, 311003)
        await caller.response.defer(ephemeral=True)
        await open_handler_tags(caller, game, identity=case.id)
        form = caller.edit_original_response.call_args.kwargs["view"]
        form.values.update(response=("pause",), account="I pause and control myself")
        await form.confirm.callback(current(1, 311004))
        assert form.completed

    asyncio.run(respond())
    assert service.get(PLAYER, case.id)["response"] == "pause" and game.dice.calls == 0


def test_safety_pause_blocks_use_and_reply_without_losing_the_original_tag(ledger):
    service, game, girl = setup(ledger)
    view = service.view(PLAYER, 900, girl)
    ledger.safety(OTHER, "pause-tag-use", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError):
        service.use(
            PLAYER, "paused-use", 900, girl, view["source_sha256"], "tag", "compel", "A request"
        )
    assert any(x.id == "tag" for x in state(game).handler_tags)
    ledger.safety(OTHER, "resume-tag-use", ledger.status(OTHER)["revision"], pause=False)
    case = use(service, girl, kind="compel")
    ledger.safety(OTHER, "pause-tag-reply", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError):
        service.respond(ADMIN, "paused-reply", case["id"], 1, "pause", "My response")
    assert service.get(ADMIN, case["id"])["state"] == "pending"


def test_actual_handler_ending_closes_only_old_request_without_acting_for_new_body(ledger):
    from uuid import uuid4

    from test_beneath_service import ready as base

    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.services.m3_handler_consequences import HandlerConsequenceService, require

    game, _, _ = base(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags.append(
            TagState(id="tag", label="Actual old Handler Tag", giver=2, observers=(1, 2))
        )
        game.event(c, 2, "old-handler-tag-source", "synthetic.state", canon)
    service, girl = HandlerTagService(game), current_ref(state(game), 2)
    case = use(service, girl, kind="compel")
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon, consequence = require(
            game,
            c,
            canon,
            active_handler(canon),
            trigger="asset_damage",
            source_action=None,
            source_event=event,
            opponent=girl,
        )
        game.event(c, 2, "actual-handler-damage", "synthetic.state", canon, event_id=event)
    HandlerConsequenceService(ledger).respond(
        ADMIN,
        "actual-handler-original-death",
        consequence,
        state(game).revision,
        "death",
        "This original Handler dies from the actual injury",
    )
    before = state(game)
    with pytest.raises(WorkflowError):
        service.respond(
            ADMIN,
            "cannot-act-as-ended-body",
            case["id"],
            1,
            "give_in",
            "A new body cannot inherit this",
        )
    service.respond(
        ADMIN,
        "close-actual-ended-handler-request",
        case["id"],
        1,
        "original_handler_ended",
        "The original Handler role has actually ended",
    )
    assert state(game).handler_archives == before.handler_archives
    assert state(game).sheets == before.sheets
    assert service.get(PLAYER, case["id"])["response"] == "original_handler_ended"


def test_consuming_already_committed_tag_keeps_modifier_and_closes_only_removed_tag_resolution(
    ledger,
):
    plays, game, _, handler, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags[0].marked = True
        game.event(c, 2, "actual-marked-handler-tag", "synthetic.state", canon)
    identity = begin(plays, handler)
    tick(GameWorker(game), Gateway(), 3)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    data = game.decision(PLAYER, choice["id"])
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=("tag",),
        fields={"as_actor": data["roles"][0]["token"]},
        number=1,
        text="Actually mark this already marked Tag",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("pass",))
    assert any(x["kind"] == "tag_resolution" for x in game.choices(ADMIN))
    use(HandlerTagService(game), current_ref(state(game), 2), kind="attention")
    assert not any(x["kind"] == "tag_resolution" for x in game.choices(ADMIN))
    answer(game, ADMIN, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, OTHER, "handler_keep", flag=True, text="The actual original Director rules")
    assert game.inspect(ADMIN, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_consumption_resolves_only_original_handlers_already_owed_rejection(ledger):
    plays, game, _, handler, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags[0].marked = True
        game.event(c, 2, "original-repeated-handler-tag", "synthetic.state", canon)
    identity = begin(plays, handler)
    tick(GameWorker(game), Gateway(), 3)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    data = game.decision(PLAYER, choice["id"])
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=("tag",),
        fields={"as_actor": data["roles"][0]["token"]},
        number=1,
        text="Actual repeated relevance",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_resolution", options=("reject",))
    obligation = next(x for x in state(game).obligations if x.kind == "actor_reject_tag")
    assert obligation.state == "pending"
    use(HandlerTagService(game), current_ref(state(game), 2), kind="attention")
    resolved = next(x for x in state(game).obligations if x.id == obligation.id)
    assert resolved.state == "fulfilled" and resolved.details["resolved_by_handler_tag_use"]
    assert not state(game).handler_tags and game.dice.calls == 1
    assert game.inspect(ADMIN, identity)["state"] != "complete"


def test_actual_harpy_uses_handler_tag_without_borrowing_controllers_other_girl(ledger):
    from test_harpy_actor_plays import ready as harpy_ready

    _, game, _, harpy = harpy_ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags.append(
            TagState(id="tag", label="Observed actual Handler Tag", giver=3, observers=(1, 2, 3))
        )
        game.event(c, 3, "actual-native-harpy-observed-tag", "synthetic.state", canon)
    before = state(game)
    service = HandlerTagService(game)
    case = use(service, harpy, kind="favour")
    service.respond(
        ADMIN,
        "actual-harpy-handler-declines",
        case["id"],
        1,
        "decline",
        "The actual Handler declines this favour",
    )
    assert rules.uses(state(game))[0].girl == harpy
    assert (
        state(game).sheets == before.sheets and state(game).native_harpies == before.native_harpies
    )
    assert game.dice.calls == 0


def test_concurrent_distinct_commands_cannot_spend_one_handler_tag_twice(ledger):
    from concurrent.futures import ThreadPoolExecutor

    service, game, girl = setup(ledger)
    source = service.view(PLAYER, 900, girl)["source_sha256"]

    def attempt(key):
        try:
            return service.use(
                PLAYER, key, 900, girl, source, "tag", "attention", "Actual concurrent request"
            )
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, ("first-real-tag-use", "second-real-tag-use")))
    assert sum(value is not None for value in results) == 1
    assert len(rules.uses(state(game))) == 1 and not state(game).handler_tags


@pytest.mark.parametrize("kind", ["attention", "compel", "favour"])
def test_actual_director_uses_own_handler_tags_and_human_without_touching_cadre_handler(
    ledger, kind
):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import WorldTag

    service, game, girl = setup(ledger)
    target = ActorRef(kind="npc", entity="director")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    npc.model_copy(
                        update={
                            "revealed": True,
                            "tags": (
                                WorldTag(
                                    id="actual-director-tag",
                                    label="Actual Director descriptor",
                                    giver_entity="pilot:2",
                                ),
                            ),
                        }
                    )
                    if npc.id == target.entity
                    else npc
                    for npc in canon.world.npcs
                )
            }
        )
        game.event(c, 3, "known-director-observed-tag", "synthetic.state", canon)
    before = state(game)
    view = service.view(PLAYER, 900, girl, target)
    case = service.use(
        PLAYER,
        "actual-director-tag-use",
        900,
        girl,
        view["source_sha256"],
        "actual-director-tag",
        kind,
        "Actual request to this specific Director",
        handler_ref=target,
    )
    assert service.get(OTHER, case["id"])["handler"] == target.model_dump(mode="json")
    if kind == "compel":
        with pytest.raises(WorkflowError):
            service.respond(
                ADMIN,
                "gm-cannot-choose-director-response",
                case["id"],
                1,
                "give_in",
                "Not this human's fictional body",
            )
        service.respond(
            OTHER,
            "actual-director-controls-self",
            case["id"],
            1,
            "pause",
            "The original Director pauses to control himself",
        )
    elif kind == "favour":
        service.respond(
            OTHER,
            "actual-director-declines-favour",
            case["id"],
            1,
            "decline",
            "The actual Director declines",
        )
    canon = state(game)
    assert canon.handler_tags == before.handler_tags and canon.handler_heat == before.handler_heat
    assert canon.sheets == before.sheets and game.dice.calls == 0
    assert not next(npc for npc in canon.world.npcs if npc.id == target.entity).tags


def test_actual_handler_under_girl_rules_can_use_director_tag_without_a_proxy_pilot(ledger):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import WorldTag

    _, game, _, girl_role, _ = ready(ledger)
    target = ActorRef(kind="npc", entity="director")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    npc.model_copy(
                        update={
                            "revealed": True,
                            "tags": (
                                WorldTag(
                                    id="director-observed-tag",
                                    label="Actual Director Tag",
                                    giver_entity="handler:1",
                                ),
                            ),
                        }
                    )
                    if npc.id == target.entity
                    else npc
                    for npc in canon.world.npcs
                )
            }
        )
        game.event(c, 3, "actual-known-director-tag", "synthetic.state", canon)
    service = HandlerTagService(game)
    actors = service.actors(ADMIN, 900)
    assert any(item["ref"] == girl_role.model_dump(mode="json") for item in actors)
    view = service.view(ADMIN, 900, girl_role)
    assert all(item["ref"]["kind"] != "handler" for item in view["targets"])
    before = state(game)
    service.use(
        ADMIN,
        "actual-handler-girl-tag-use",
        900,
        girl_role,
        view["source_sha256"],
        "director-observed-tag",
        "attention",
        "The actual Handler under Girl rules addresses the actual Director",
        handler_ref=target,
    )
    assert state(game).sheets == before.sheets and "1" not in state(game).sheets
    assert state(game).handler_heat == before.handler_heat and game.dice.calls == 0
