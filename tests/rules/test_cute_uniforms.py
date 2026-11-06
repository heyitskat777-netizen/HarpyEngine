"""One genuine advancement, actual dressing, sourced Keep and real uniform responses."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_mission_ui import current
from test_punishment_service import submit
from test_supply_drop import ready as source

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_cute_uniforms import open_uniforms
from girlframe.engine import m3_cute_uniforms as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import AssetState, ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_cute_uniforms import CuteUniformService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    actual_propose = PhysicalService.propose

    def actual_other_position(self, viewer, key, revision, choice):
        if viewer.user_id == OTHER.user_id:
            choice = choice.model_copy(update=dict(girl_cell=(1, 0), frame_cell=(1, 0)))
        return actual_propose(self, viewer, key, revision, choice)

    monkeypatch.setattr(PhysicalService, "propose", actual_other_position)
    game, _, _, award = source(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(*awards.RULES, rules.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    service = CuteUniformService(store)

    async def buy():
        own = current(1, 32000)
        await own.response.defer(ephemeral=True)
        await open_uniforms(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(award=(award,), account="Actual genuine advancement for uniforms")
        await form.confirm.callback(current(1, 32001))
        assert form.completed

    asyncio.run(buy())
    return game, service, GameWorker(game), Gateway()


def propose(game, service, viewer=PLAYER):
    return service.propose(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        current_ref(state(game), viewer.user_id),
        "Actual sailor uniform",
        "The actual Handler dresses the Girl in this physical sailor uniform",
        True,
    )["id"]


def dress(game, service, identity):
    async def confirm():
        own = current(2, 32010)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        inbox = InboxService(service.store)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_cute_uniforms" and x.identity == identity
        )
        await InboxView(inbox, 2).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            actual=("actual",),
            account="PRIVATE_UNIFORM_DRESSING: my original Handler actually dressed me here",
        )
        await form.confirm.callback(current(2, 32011))
        assert form.completed

    asyncio.run(confirm())


def finish_keep(game, worker, gateway, action):
    answer(
        game,
        PLAYER,
        "actor_keep",
        options=("tough", "sexy"),
        denied=("in_control",),
        fields={"cute_uniform": "helpless_adorable"},
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="Actual sufficient result, including adorable appearance",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def marked_keep(game, worker, gateway, uniform, channel=900):
    game.dice = Dice((4, 4))
    action = game.begin(
        PLAYER, str(uuid4()), channel, state(game).sheets["2"].revision, dict_input()
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        ADMIN,
        "tag_window",
        options=("tag",),
        denied=(uniform,),
        number=1,
        text="The actual worn uniform is relevant",
    )
    return action


def dict_input():
    from girlframe.engine.m2 import PlayInput

    return PlayInput(
        play="keep_your_head",
        context="Actual danger in the uniform",
        trigger_confirmed=True,
        heat=0,
    )


def next_scene(game, channel):
    game.close_scene(ADMIN, str(uuid4()), channel - 1)
    game.bind_scene(ADMIN, str(uuid4()), channel)
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), channel)


def test_actual_native_award_dressing_extra_keep_asset_embrace_capacity_and_replay(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    assert awards.awards(before)[0].acquired_rule == rules.RULE
    with pytest.raises(WorkflowError):
        service.buy(
            ADMIN, str(uuid4()), awards.awards(before)[0].id, before.revision, "No duplicate source"
        )
    uniform = propose(game, service)
    proposed = state(game)
    assert proposed.order == before.order and not rules.tags(proposed, 2)
    assert not any(x.get("kind") == "cute_uniform_actual_dressing_position" for x in proposed.facts)
    dress(game, service, uniform)
    actual = state(game)
    assert actual.order[-1] == 2
    assert rules.uniforms(actual)[0].wearing
    with ledger.engine.connect() as c:
        audits = list(
            c.scalars(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.campaign_id == ledger.campaign_id
                )
            )
        )
        assert "PRIVATE_UNIFORM_DRESSING" not in str(audits)
    with ledger.engine.connect() as c:
        value = rules.uniforms(actual)[0]
        assert (
            resolve(
                actual,
                value.handler,
                profiles(c, ledger.campaign_id),
                require_current_profile=False,
            ).cell
            == value.cell
        )
    with pytest.raises(WorkflowError, match="genuine movement"):
        propose(game, service, OTHER)
    assert state(game) == actual
    key = "actual-owned-dressing-replay"
    # Same actual confirmed event cannot lower Status a second time under a fresh command.
    with pytest.raises(WorkflowError):
        service.confirm(PLAYER, key, uniform, actual.revision, True, "Already dressed")
    assert state(game) == actual
    physical = (actual.sheets["2"].helpless_against, actual.helpless_conditions)
    game.dice = Dice((4, 4))
    action = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    pending = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError, match="helpless and adorable"):
        game.respond(
            PLAYER,
            str(uuid4()),
            pending["id"],
            pending["revision"],
            ChoiceAnswer(options=("tough", "sexy"), denied=("in_control",)),
        )
    finish_keep(game, worker, gateway, action)
    with ledger.engine.connect() as c:
        result = game.action(c, action)["data"]["result"]
        assert len(result["positive"]) == 2 and result["negative"] == ["in_control"]
        assert result["forced_presentations"][0]["presentation"] == rules.PRESENTATION
    assert (state(game).sheets["2"].helpless_against, state(game).helpless_conditions) == physical
    with ledger.transaction() as c:
        prior = state(game)
        sheet = prior.sheets["2"]
        while len([x for x in sheet.assets if x.family == "girl"]) < 4:
            sheet.assets.append(
                AssetState(id=str(uuid4()), family="girl", name="Actual prior owned clothing")
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_equipment", prior)
    marked = marked_keep(game, worker, gateway, uniform)
    finish_keep(game, worker, gateway, marked)
    next_scene(game, 901)
    marked = marked_keep(game, worker, gateway, uniform, 901)
    identities = state(game).sheets["2"].identities
    before_embrace = state(game)
    with pytest.raises(WorkflowError, match="cap"):
        answer(game, PLAYER, "tag_resolution", options=("embrace_asset",))
    assert state(game) == before_embrace
    replace = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "girl" and not x.void
    )

    async def embrace_asset():
        request = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_resolution")
        own = current(2, 32040)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, request["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=("embrace_asset",), **{"fields.replace": (replace,)})
        await form.confirm.callback(current(2, 32041))
        assert form.completed

    asyncio.run(embrace_asset())
    assert state(game).sheets["2"].identities == identities
    asset = rules.uniforms(state(game))[0].asset
    assert asset and any(
        x.id == asset and x.family == "girl" for x in state(game).sheets["2"].assets
    )
    assert rules.tags(state(game), 2)
    finish_keep(game, worker, gateway, marked)
    # Reaffirming the already-owned Asset cannot install a second copy.
    for channel in (902, 903):
        next_scene(game, channel)
        marked = marked_keep(game, worker, gateway, uniform, channel)
        if channel == 903:
            answer(game, PLAYER, "tag_resolution", options=("embrace_asset",))
        finish_keep(game, worker, gateway, marked)
    assert len([x for x in state(game).sheets["2"].assets if x.id == asset]) == 1
    # Actual doffing is not a Tag rejection or an actual physical Helpless effect.
    service.wearing(
        PLAYER, str(uuid4()), uniform, state(game).revision, "I actually take the uniform off"
    )
    assert rules.tags(state(game), 2) and not rules.uniforms(state(game))[0].wearing
    order = state(game).order
    service.wearing(
        PLAYER,
        str(uuid4()),
        uniform,
        state(game).revision,
        "I actually put my own garment back on",
        True,
    )
    assert rules.uniforms(state(game))[0].wearing and state(game).order == order
    assert (state(game).sheets["2"].helpless_against, state(game).helpless_conditions) == physical


def test_actual_uniform_tag_rejection_then_real_handler_punishment_ending(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    uniform = propose(game, service)
    dress(game, service, uniform)
    marked = marked_keep(game, worker, gateway, uniform)
    finish_keep(game, worker, gateway, marked)
    next_scene(game, 901)
    marked = marked_keep(game, worker, gateway, uniform, 901)
    answer(game, PLAYER, "tag_resolution", options=("reject",))
    assert rules.uniforms(state(game))[0].phase == "worn"
    finish_keep(game, worker, gateway, marked)
    owed = next(
        x for x in state(game).obligations if x.kind == "reject_tag" and x.state == "pending"
    )
    action = game.fulfill(
        PLAYER, str(uuid4()), 901, owed.id, "I actually reject the uniform in character"
    )["action_id"]
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    value = rules.uniforms(state(game))[0]
    assert value.phase == "rejected" and value.punishment
    discipline = PunishmentService(ledger)
    original = state(game).sheets["2"].character_id
    submit(
        discipline,
        ADMIN,
        value.punishment,
        Details(kind="execution"),
        "actual-uniform-punishment",
    )
    assert "2" not in state(game).sheets
    assert any(
        x.actor.incarnation == original and x.ending == "execution"
        for x in state(game).career_archives
    )
    assert discipline.get(ADMIN, value.punishment)["state"] == "resolved"


def test_actual_declined_proposal_no_effect_then_ordinary_identity_embrace(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    declined = propose(game, service)
    before = state(game)
    service.confirm(
        PLAYER, str(uuid4()), declined, before.revision, False, "This dressing did not happen"
    )
    after = state(game)
    assert after.order == before.order and after.sheets == before.sheets
    assert not rules.tags(after, 2) and not rules.uniforms(after)[0].punishment
    uniform = propose(game, service)
    dress(game, service, uniform)
    marked = marked_keep(game, worker, gateway, uniform)
    finish_keep(game, worker, gateway, marked)
    next_scene(game, 901)
    marked = marked_keep(game, worker, gateway, uniform, 901)
    sheet = state(game).sheets["2"]
    old = next(x.id for x in sheet.identities if not x.protected)
    before_assets = sheet.assets
    answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(old,))
    updated = state(game).sheets["2"]
    assert updated.assets == before_assets and all(x.id != old for x in updated.identities)
    assert any(x.name == "Actual sailor uniform" for x in updated.identities)
    assert not rules.tags(state(game), 2)
    finish_keep(game, worker, gateway, marked)


def test_actual_mid_disobey_uniform_rejection_and_genuine_delegated_punishment(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    uniform = propose(game, service)
    dress(game, service, uniform)
    root = game.issue_order(ADMIN, str(uuid4()), 900, 2, "Actually obey this direct order")
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    game.dice = Dice((4, 4))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            order_id=root["order_id"],
            parent=root["action_id"],
            context="Actually reject this uniform while refusing the order",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_disobey", options=("reject_tag",), denied=(uniform,))
    value = rules.uniforms(state(game))[0]
    assert value.phase == "rejected" and value.punishment
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, root["action_id"])["state"] == "complete"
    discipline = PunishmentService(ledger)
    delegated = submit(
        discipline,
        ADMIN,
        value.punishment,
        Details(kind="passing_responsibility", delegate=3),
        "actual-uniform-delegation",
    )
    assert delegated["state"] == "delegated"
    before = state(game).sheets["2"].heat
    request = discipline.get(OTHER, value.punishment)
    args = (
        OTHER,
        "actual-delegated-uniform-effect",
        value.punishment,
        request["revision"],
        request["game_revision"],
        Details(kind="stimulant_injection"),
    )
    result = discipline.apply(*args)
    assert discipline.apply(*args) == result
    assert state(game).sheets["2"].heat == before + 7
    assert discipline.get(OTHER, value.punishment)["state"] == "resolved"
