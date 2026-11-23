"""The original NPC tries to kill the Handler and a real Girl's Core strike stops it."""

import asyncio

import pytest
from test_battle_service import confirm
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import depth, is_helpless, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_rebel_bond_attack import RULE, attacks
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_bond_attack import AttackService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_high_rebellion_betrayal_needs_one_original_girl_intervention_to_close(ledger):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    outsider = GuildViewer(4, 200, True, False)
    ledger.join(outsider, "outsider-campaign-join")
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN,
        "betrayal-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    group = Faction(id="unseen-rebels", kind="rebel", name="Unseen Rebels", cells=((0, 0),))
    worlds.faction(ADMIN, "betrayal-group", state(game).revision, group)
    roles = NpcRoleService(worlds)
    npc = Npc(
        id="original-contact",
        name="Trusted Contact",
        jobs=("base_personnel",),
        controller=3,
        cell=(0, 0),
        revealed=True,
        detail="The original contact",
    )
    offer = roles.offer(ADMIN, "betrayal-npc-invitation", state(game).revision, npc)
    roles.respond(OTHER, "betrayal-npc-accept", offer["id"], state(game).revision, "accept")
    target = ActorRef(kind="npc", entity=npc.id)
    handler = active_handler(state(game))
    assert handler is not None
    with ledger.transaction() as c:
        canon = place(
            place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame", cell=(2, 0)
        )
        canon = set_depth(canon, handler, target, 1, "original-contact-bond")
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=handler.model_dump_json(),
                cell="[0,0]",
                event="original-handler-here",
            )
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "betrayal-physical", "synthetic.original_roles", canon)
    cast = CastService(ActorService(strain.missions))
    change(cast, ADMIN, "join", handler)
    change(cast, OTHER, "join", target)
    period = prepared(strain, game, high=frozenset({"rebellion"}))
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="A Gorgon arrives.",
                gorgon=gorgon("dormant", "perimeter-threat", (0, 1)),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned.", rooms=((2, 3),)),
        ),
        ("rebellion", 3, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "betrayal-die-" + track, request.id, 1, state(game).revision)
        selected = strain.choose(
            ADMIN, "betrayal-column-" + track, request.id, 2, state(game).revision, column
        )
        work = request.id + ":effect"
        if choice:
            effects.apply(ADMIN, "betrayal-other-" + track, work, 1, state(game).revision, choice)
    assert selected["rule_id"] == RULE
    inbox = InboxService(ledger)

    async def native(viewer, number, *, stage=False, **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        if stage:
            await open_effect(click, effects, work)
        else:
            entry = next(x for x in inbox.items(viewer) if x.task == "m3_rebel_bond_attack")
            await InboxView(inbox, viewer.user_id).route(click, entry)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        confirm_click = current(viewer.user_id, number + 1)
        confirm_click.channel_id = 900
        await form.confirm.callback(confirm_click)
        assert form.completed, confirm_click.edit_original_response.call_args

    asyncio.run(
        native(
            ADMIN,
            40600,
            stage=True,
            betrayal_bond=(npc.id,),
            betrayal_faction=(group.id,),
            account="The original contact follows the Rebels.",
        )
    )
    assert effects.get(ADMIN, work)["awaiting_rebel_bond"]
    assert not any(x.task == "m3_rebel_bond_attack" for x in inbox.items(PLAYER))
    assert group.id not in str(worlds.get(PLAYER)["world"].get("npcs", []))
    service = AttackService(strain)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="original Rebel and Handler"):
        service.act(ADMIN, "handler-cannot-attack", work, revision, 900, account="Impersonation")
    with pytest.raises(WorkflowError, match="original Rebel and Handler"):
        service.act(
            OTHER, "unrelated-scene", work, revision, 901, account="No original participants"
        )
    ledger.safety(PLAYER, "pause-betrayal", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.act(OTHER, "paused-betrayal", work, revision, 900, account="Actual attempt")
    ledger.safety(PLAYER, "resume-betrayal", ledger.status(PLAYER)["revision"], pause=False)
    revision = state(game).revision
    asyncio.run(native(OTHER, 40610, account="PRIVATE_ASSASSINATION_ATTEMPT"))
    assert (
        service.act(OTHER, "40611", work, revision, 900, account="PRIVATE_ASSASSINATION_ATTEMPT")[
            "finished"
        ]
        is False
    )
    canon = state(game)
    assert is_helpless(canon, handler, target)
    assert canon.world.npcs[0].id == npc.id and canon.world.npcs[0].alive
    assert depth(canon, handler, target) == 1
    assert service.get(PLAYER, work, 900)["account"] == "PRIVATE_ASSASSINATION_ATTEMPT"
    with pytest.raises(WorkflowError, match="actual involved parties"):
        service.get(outsider, work, 900)
    with pytest.raises(WorkflowError, match="Strain"):
        activate(CycleService(strain.periods), game, period)

    fight = BattleService(ledger)
    data = fight.preview(PLAYER, 900)
    pilot = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    foe = next(x for x in data["actors"] if x["ref"]["entity"] == npc.id)
    declaration = Declaration(
        play="go_for_the_core",
        actor=ActorRef.model_validate(pilot["ref"]),
        target=target,
        attacking_asset=pilot["assets"][0]["id"],
        actor_sha256=pilot["sha256"],
        target_sha256=foe["sha256"],
        account="I intervene to save the original Handler.",
    )
    opening = confirm(fight, game, data, declaration)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        "original-cadre-rescue",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="go_for_the_core",
            heat=0,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            battle_context=opening,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=False,
        ),
    )["action_id"]
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.act(ADMIN, "premature-rescue-proof", work, state(game).revision, 900, action=action)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [4, 5]
    assert not state(game).world.npcs[0].alive and effects.get(ADMIN, work)["state"] == "pending"
    with pytest.raises(WorkflowError, match="original Cadre defender"):
        service.act(
            ADMIN, "handler-cannot-claim-rescue", work, state(game).revision, 900, action=action
        )
    ledger.engine.dispose()
    asyncio.run(native(PLAYER, 40620, rescue=(action,)))
    (resolved,) = attacks(state(game))
    assert resolved.finished and resolved.defense and resolved.attempt
    assert not is_helpless(state(game), handler, target)
    assert effects.get(ADMIN, work)["state"] == "resolved"
    tick(worker, gateway, 5)
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
