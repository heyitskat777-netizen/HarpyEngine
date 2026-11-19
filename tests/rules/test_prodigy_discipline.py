"""Prodigy notches and Ace protection come from actual Cadre Punishments."""

import asyncio

import pytest
from test_ancillary_creation import current, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_discipline import (
    EARNED,
    FAVOURITE,
    KIND,
    AncillaryDisciplineService,
)
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def test_prodigy_confidence_and_favourite_follow_real_punishments(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(EARNED, FAVOURITE))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    cast_service = CastService(ActorService(missions))
    partner = current_ref(state(game), OTHER.user_id)

    def create(viewer, book, name, bond):
        invitation = creation.invite(
            ADMIN,
            "invite-" + name,
            state(game).revision,
            viewer.user_id,
            "base0",
        )

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original actual gear.")

        frame = "SOLDIER_3" if book == "SOLDIER" else "JANUS"
        data = ancillary.Draft(
            book=book,
            name=name,
            bond=bond,
            frame_catalogue=frame,
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, frame)[:2]),
        )
        created = creation.respond(
            viewer, "create-" + name, invitation["id"], state(game).revision, data
        )
        actor = ActorRef.model_validate(created["actor"])
        change(cast_service, viewer, "join", actor)
        return actor

    soldier = create(PLAYER, "SOLDIER", "Original Soldier", partner)
    prodigy = create(OTHER, "PRODIGY", "Original Prodigy", current_ref(state(game), PLAYER.user_id))
    ranks = AncillaryCadreService(game)
    group = ranks.propose(
        ADMIN,
        "formation",
        900,
        state(game).revision,
        active_handler(state(game)).token,
        (soldier.token, prodigy.token),
    )
    for viewer, actor in ((OTHER, prodigy), (PLAYER, soldier)):
        ranks.approve(
            viewer, "join-" + actor.token, group["id"], state(game).revision, actor.token, True
        )

    discipline = AncillaryDisciplineService(game)
    roles = RolePunishmentService(game)

    def enact(actor, owner, label):
        first = discipline.start(
            ADMIN,
            label + "-start",
            900,
            state(game).revision,
            actor.token,
        )["id"]
        inst = Instruction(
            kind="quality_time",
            details_json=Details(kind="quality_time", tag=label).model_dump_json(),
        )
        roles.change(ADMIN, label + "-instruction", first, state(game).revision, instruction=inst)
        roles.change(
            ADMIN,
            label + "-scene",
            first,
            state(game).revision,
            scene="We carry out the actual review together.",
        )
        roles.change(owner, label + "-owner", first, state(game).revision, attest=True)
        roles.change(
            ADMIN,
            label + "-execute",
            first,
            state(game).revision,
            execute=True,
            account="The actual conversation and critique ended.",
        )

    enact(soldier, PLAYER, "Actual first Punishment")
    assert not is_helpless(state(game), prodigy)
    (notch,) = discipline.confidence_menu(OTHER, prodigy)["owned"]
    enact(prodigy, OTHER, "Actual second Punishment")
    assert is_helpless(state(game), prodigy, active_handler(state(game)))
    assert discipline.confidence_menu(OTHER, prodigy)["owned"] == (notch,)
    discipline.spend(OTHER, "advance-actual", prodigy, notch, state(game).revision)
    final = state(game)
    assert cadre.actual_members(final, cadre.current(final, prodigy))[0] == prodigy
    assert any(
        x.get("kind") == KIND and x.get("id") == notch and x.get("spent") for x in final.facts
    )
    with pytest.raises(WorkflowError, match="eligible"):
        discipline.start(ADMIN, "cannot-punish-ace", 900, final.revision, prodigy.token)

    enact(soldier, PLAYER, "Punishment while Prodigy is Ace")
    (ace_notch,) = [
        x["id"] for x in state(game).facts if x.get("kind") == KIND and not x.get("spent")
    ]
    plays = ActorPlayService(game)
    game.dice = Dice((2, 3))
    preview = plays.preview(OTHER, 900, prodigy)
    action = plays.begin(
        OTHER,
        "ace-keep",
        900,
        prodigy,
        preview["actor"]["source_sha256"],
        None,
        preview["cast_revision"],
        PlayInput(
            play="keep_your_head",
            context="I try to finish the report while the alarms continue.",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    (pending,) = [x for x in game.choices(OTHER) if x["kind"] == "prodigy_confidence_roll"]
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, pending["id"])
    ledger.engine.dispose()

    async def spend_from_inbox():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(OTHER) if x.identity == pending["id"])
        click = current(OTHER.user_id, 51230)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, OTHER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values["options"] = (ace_notch,)
        sent = current(OTHER.user_id, 51231)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(spend_from_inbox())
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("vicious",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The report is finished.")
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
    assert saved["state"] == "complete"
    assert saved["data"]["receipt"]["faces"] == [2, 3]
    assert saved["data"]["result"]["before_earned_confidence"] == 5
    assert saved["data"]["result"]["total"] == 9
    assert saved["data"]["result"]["tier"] == "mid"
    assert game.dice.calls == 1
    assert any(
        x.get("kind") == KIND and x.get("id") == ace_notch and x.get("roll") == action
        for x in state(game).facts
    )
