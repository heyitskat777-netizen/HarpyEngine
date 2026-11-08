"""Actual selected source roles own Tag modifiers independently of Discord controller IDs."""

import asyncio

import pytest
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current as interaction

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_tag_markers import bind_answer, marker_field, open_discussion
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Board, Npc, World
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

FOUR = GuildViewer(4, 200, True, False)


def mixed(store, *, controller=3, depth=0, observers=(2, 3, 4), faces=(3, 3)):
    game, worker, gateway = ready(store, faces)
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    if controller == 4:
        store.join(FOUR, "actual-npc-controller-join")
    with store.transaction() as c:
        canon = state(game)
        canon.bonds["2:3"] = 2  # The controller's own Girl has a different actual relationship.
        canon.world = World(
            board=Board(minimum=(-2, -2), maximum=(2, 2)),
            locations=(),
            npcs=(
                Npc(
                    id="3",
                    name="PRIVATE_NPC_ROLE",
                    cell=(0, 0),
                    jobs=("guard",),
                    detail="Actual original NPC",
                    controller=controller,
                    bonds={"pilot:2": depth} if depth else {},
                ),
            ),
        )
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-private-tag", label="PRIVATE_TAG_LABEL", giver=3, observers=observers
            )
        )
        game.event(c, 1, "actual-role-context", "synthetic.state", canon)
    casts = CastService(ActorService(MissionService(store)))
    viewer = OTHER if controller == 3 else FOUR
    view = casts.view(viewer, 900)
    casts.change(
        viewer,
        "actual-controlled-npc-role",
        900,
        view["game_revision"],
        view["cast_revision"],
        "join",
        ActorRef(kind="npc", entity="3"),
    )
    identity = game.begin(
        PLAYER,
        "actual-mixed-role-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep", heat=0, context="Actual mixed source table", trigger_confirmed=True
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    return game, worker, gateway, identity


def tag_data(game, viewer):
    row = next(x for x in game.choices(viewer) if x["kind"] == "tag_window")
    return game.decision(viewer, row["id"])


def tag(game, viewer, marker=None):
    kwargs = dict(
        options=("tag",), denied=("actual-private-tag",), number=1, text="PRIVATE_TAG_RELEVANCE"
    )
    if marker:
        kwargs["fields"] = {"marker": marker}
    return answer(game, viewer, "tag_window", **kwargs)


@pytest.mark.parametrize("depth,expected", [(0, 1), (1, 2), (2, 2)])
def test_exact_selected_npc_bond_controls_bonus_without_numeric_or_controller_alias(
    ledger, depth, expected
):
    game, worker, gateway, identity = mixed(ledger, depth=depth)
    data = tag_data(game, OTHER)
    token = next(x["token"] for x in data["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE")
    assert marker_field(data) is not None
    with pytest.raises(WorkflowError, match="actual original roles"):
        tag(game, OTHER)
    answer(game, PLAYER, "tag_window", options=("pass",))
    tag(game, OTHER, token)
    answer(game, ADMIN, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
    assert action["data"]["tag_marker_applied"]["actor"] == dict(
        kind="npc", entity="3", incarnation=None
    )
    assert action["data"]["modifiers"][-1]["amount"] == expected
    assert action["data"]["result"]["total"] == 6 + expected and game.dice.calls == 1
    assert "actor_ref" not in action["data"]["modifiers"][-1]


def test_new_human_with_only_npc_gets_owned_window_and_implicit_single_role_is_actual_source(
    ledger,
):
    game, worker, gateway, identity = mixed(ledger, controller=4)
    data = tag_data(game, FOUR)
    assert len(data["tag_markers"]) == 1 and marker_field(data) is None and data["own"] is None
    with pytest.raises(WorkflowError):
        tag(game, FOUR, "invented-role")
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    tag(game, FOUR)  # Public Game.respond stays compatible when one role is proved.
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
    assert action["data"]["participants"] == [1, 2, 3, 4]
    assert action["data"]["tag_marker_applied"]["controller"] == 4
    assert action["data"]["modifiers"][-1]["amount"] == 1
    answer(
        game,
        ADMIN,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual painful connection",
    )
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"identity": state(game).sheets["2"].identities[0].id},
        text="Every original human answers",
    )
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "dive_table_answer", text="Actual table answer")
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(game, FOUR, "dive_table_answer", text="Actual NPC-controller human answer")
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_native_multiple_role_picker_and_single_role_hidden_hash_preserve_exact_choice(ledger):
    game, worker, gateway, identity = mixed(ledger)
    data = tag_data(game, OTHER)
    npc = next(x["token"] for x in data["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE")

    async def run():
        current = interaction(3, 31301)
        await current.response.defer(ephemeral=True)
        await open_choice(current, game, data["id"])
        form = current.edit_original_response.call_args.kwargs["view"]
        assert any(x.key == "fields.marker" for x in form.fields)
        assert not await form.interaction_check(interaction(4, 31302))
        form.values.update(
            options=("tag",),
            denied=("actual-private-tag",),
            number=("1",),
            text="Actual native proposal",
            **{"fields.marker": (npc,)},
        )
        await form.confirm.callback(interaction(3, 31303))
        assert form.completed

    asyncio.run(run())
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
    assert action["data"]["tag_marker_applied"]["actor"]["kind"] == "npc"
    plain = (
        tag_data
        if False
        else bind_answer(
            dict(kind="tag_window", tag_markers=[dict(token="actual-reviewed-source")]),
            ChoiceAnswer(options=("tag",), denied=("actual",), number=1, text="Actual"),
        )
    )
    assert plain.fields["marker"] == "actual-reviewed-source"


def test_stale_reviewed_actor_hash_cannot_mark_then_original_human_can_refresh(ledger):
    game, worker, gateway, identity = mixed(ledger)
    data = tag_data(game, OTHER)
    old = next(x["token"] for x in data["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE")
    with ledger.transaction() as c:
        canon = state(game)
        npc = canon.world.npcs[0]
        canon.world = canon.world.model_copy(
            update={"npcs": (npc.model_copy(update={"detail": "Actual changed role resources"}),)}
        )
        game.event(c, 1, "actual-npc-resource-change", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_TAG_MARKER"):
        tag(game, OTHER, old)
    fresh = next(
        x["token"] for x in tag_data(game, OTHER)["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE"
    )
    assert fresh != old and game.dice.calls == 1
    tag(game, OTHER, fresh)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert state(game).sheets["2"].tags[-1].marked


def competing(store, *, private_text="PRIVATE_TAG_RELEVANCE"):
    game, worker, gateway, identity = mixed(store, controller=4, observers=(2, 4))
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(id="public-tag", label="Public observed Tag", giver=3, observers=(1, 2, 3, 4))
        )
        game.event(c, 1, "actual-public-tag-context", "synthetic.state", canon)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("public-tag",),
        number=1,
        text="Public actual relevance",
    )
    answer(
        game,
        FOUR,
        "tag_window",
        options=("tag",),
        denied=("actual-private-tag",),
        number=1,
        text=private_text,
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    data = game.decision(
        ADMIN, next(x["id"] for x in game.choices(ADMIN) if x["kind"] == "tag_marker_selection")
    )
    return game, worker, gateway, identity, data["tag_marker_discussion"]["proposals"]


def test_real_mixed_competing_proposals_need_each_actual_human_and_keep_nonwitness_details_private(
    ledger,
):
    game, worker, gateway, identity, proposals = competing(ledger)
    assert "PRIVATE_NPC_ROLE" not in str(proposals)
    assert "PRIVATE_TAG_LABEL" not in str(proposals) and "PRIVATE_TAG_RELEVANCE" not in str(
        proposals
    )
    private = next(x["id"] for x in proposals if x["amount"] == 1)
    answer(game, ADMIN, "tag_marker_selection", options=(private,))
    outsider = GuildViewer(5, 200, True, True)
    ledger.join(outsider, "actual-outsider-member")
    own = next(x for x in game.choices(FOUR) if x["kind"] == "tag_marker_agreement")
    with pytest.raises(WorkflowError):
        game.decision(outsider, own["id"])
    visible = game.decision(FOUR, own["id"])["tag_marker_discussion"]
    assert "PRIVATE_NPC_ROLE" in str(visible) and "PRIVATE_TAG_LABEL" in str(visible)
    hidden = game.decision(
        OTHER, next(x["id"] for x in game.choices(OTHER) if x["kind"] == "tag_marker_agreement")
    )["tag_marker_discussion"]
    assert "PRIVATE_TAG_LABEL" not in str(hidden) and "PRIVATE_TAG_RELEVANCE" not in str(hidden)
    for viewer, accepted in ((PLAYER, True), (OTHER, False), (FOUR, True), (ADMIN, True)):
        answer(game, viewer, "tag_marker_agreement", flag=accepted)
    assert not any(x.marked for x in state(game).sheets["2"].tags)
    public = next(x["id"] for x in proposals if x["amount"] == 2)
    answer(game, ADMIN, "tag_marker_selection", options=(public,))
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "tag_marker_agreement", flag=True)
    assert not any(x.marked for x in state(game).sheets["2"].tags)
    answer(game, FOUR, "tag_marker_agreement", flag=True)
    canon = state(game)
    assert next(x for x in canon.sheets["2"].tags if x.id == "public-tag").marked
    assert not next(x for x in canon.sheets["2"].tags if x.id == "actual-private-tag").marked
    with ledger.engine.connect() as c:
        source = game.action(c, identity)["data"]["tag_marker_applied"]
    assert source["actor"]["kind"] == "pilot" and source["amount"] == 2


def test_native_source_discussion_presents_full_owned_proposal_without_fabricated_votes(ledger):
    game, worker, gateway, identity, proposals = competing(ledger, private_text="*" * 1200)
    private = next(x["id"] for x in proposals if x["amount"] == 1)

    async def run():
        coordinator = interaction(1, 31401)
        await coordinator.response.defer(ephemeral=True)
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_marker_selection")
        await open_discussion(coordinator, game, row["id"])
        form = coordinator.edit_original_response.call_args.kwargs["view"]
        form.values.update(proposal=(private,))
        await form.confirm.callback(interaction(1, 31402))
        assert form.completed
        assert len([x for x in game.choices(ADMIN) if x["kind"] == "tag_marker_agreement"]) == 1
        owner = interaction(2, 31403)
        await owner.response.defer(ephemeral=True)
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_marker_agreement")
        await open_discussion(owner, game, row["id"])
        pages = owner.edit_original_response.call_args.kwargs["view"]
        assert len(pages.pages) > 1 and pages.respond.disabled
        assert not await pages.interaction_check(interaction(4, 31404))
        while pages.index < len(pages.pages) - 1:
            await pages.next.callback(interaction(2, 31405 + pages.index))
        confirming = interaction(2, 31410)
        await pages.respond.callback(confirming)
        form = confirming.edit_original_response.call_args.kwargs["view"]
        form.values.update(agreement=("yes",))
        await form.confirm.callback(interaction(2, 31411))
        assert form.completed

    asyncio.run(run())
    assert not any(x.marked for x in state(game).sheets["2"].tags)
    for viewer in (OTHER, FOUR, ADMIN):
        answer(game, viewer, "tag_marker_agreement", flag=True)
    assert next(x for x in state(game).sheets["2"].tags if x.id == "actual-private-tag").marked


def test_changed_role_after_proposal_reopens_only_original_human_with_same_dice(ledger):
    game, worker, gateway, identity = mixed(ledger)
    data = tag_data(game, OTHER)
    marker = next(x["token"] for x in data["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE")
    tag(game, OTHER, marker)
    with ledger.transaction() as c:
        canon = state(game)
        npc = canon.world.npcs[0]
        canon.world = canon.world.model_copy(
            update={
                "npcs": (
                    npc.model_copy(update={"detail": "Changed actual resources after proposal"}),
                )
            }
        )
        game.event(c, 1, "actual-after-proposal-change", "synthetic.state", canon)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert not state(game).sheets["2"].tags[-1].marked and game.dice.calls == 1
    assert len(game.choices(OTHER)) == 1 and game.choices(OTHER)[0]["kind"] == "tag_window"
    fresh = next(
        x["token"] for x in tag_data(game, OTHER)["tag_markers"] if x["label"] == "PRIVATE_NPC_ROLE"
    )
    tag(game, OTHER, fresh)
    assert state(game).sheets["2"].tags[-1].marked and game.dice.calls == 1


def test_graph_only_bond_change_invalidates_reviewed_token_without_actor_json_change(ledger):
    from girlframe.engine.m3_actor_bonds import current_ref, set_depth
    from girlframe.services.m3_tag_markers import current

    game, worker, gateway, identity = mixed(ledger)
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
        before = next(x for x in current(game, c, state(game), action, 3) if x.actor.kind == "npc")
    with ledger.transaction() as c:
        canon = state(game)
        canon = set_depth(
            canon,
            ActorRef(kind="npc", entity="3"),
            current_ref(canon, 2),
            1,
            "actual-new-bond-source",
        )
        game.event(c, 1, "actual-graph-only-change", "synthetic.state", canon)
    with ledger.engine.connect() as c:
        after = next(
            x
            for x in current(game, c, state(game), game.action(c, identity), 3)
            if x.actor.kind == "npc"
        )
    assert before.source_actor_sha256 == after.source_actor_sha256
    assert before.token != after.token and before.bonus == 1 and after.bonus == 2
    with pytest.raises(WorkflowError, match="STALE_TAG_MARKER"):
        tag(game, OTHER, before.token)
    tag(game, OTHER, after.token)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        assert game.action(c, identity)["data"]["modifiers"][-1]["amount"] == 2


def test_new_own_role_cannot_bypass_existing_self_mark_exception_through_owned_npc(ledger):
    game, worker, gateway = ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(-2, -2), maximum=(2, 2)),
            locations=(),
            npcs=(
                Npc(
                    id="owned-by-roller",
                    name="Owned original NPC",
                    cell=(0, 0),
                    jobs=("guard",),
                    detail="Actual",
                    controller=2,
                ),
            ),
        )
        canon.sheets["2"].tags.append(
            TagState(id="actual-private-tag", label="Own tag", giver=3, observers=(1, 2, 3))
        )
        game.event(c, 1, "actual-own-npc-role", "synthetic.state", canon)
    casts = CastService(ActorService(MissionService(ledger)))
    view = casts.view(PLAYER, 900)
    casts.change(
        PLAYER,
        "join-own-npc-role",
        900,
        view["game_revision"],
        view["cast_revision"],
        "join",
        ActorRef(kind="npc", entity="owned-by-roller"),
    )
    game.begin(
        PLAYER,
        "actual-own-role-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(play="dive_deep", heat=0, context="Actual own role", trigger_confirmed=True),
    )["action_id"]
    tick(worker, gateway, 3)
    data = tag_data(game, PLAYER)
    assert len(data["tag_markers"]) == 1 and data["tag_markers"][0]["label"] != "Owned original NPC"
    with pytest.raises(WorkflowError, match="self-mark exception"):
        tag(game, PLAYER)
    assert not state(game).sheets["2"].tags[-1].marked and game.dice.calls == 1
