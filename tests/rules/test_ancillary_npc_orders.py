"""Exact optional NPC authorities preserve owner choice and printed refusal permissions."""

import asyncio

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.discord_adapter.m3_ancillary_orders import open_ancillary_order, open_order_response
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_orders import ILLEGAL, SERVICE, AncillaryOrderService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_original_revolutionary_can_mark_owned_tag_and_wife_cannot_disobey_spouse(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(ILLEGAL, SERVICE))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    actors = ActorService(missions)
    cast = CastService(actors)
    change(cast, ADMIN, "join", REBEL)

    def create(viewer, book, name):
        invitation = creation.invite(
            ADMIN,
            "invite-" + name,
            state(game).revision,
            viewer.user_id,
            "city0",
            "group",
            contacts=(REBEL,),
        )

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original gear.")

        draft = ancillary.Draft(
            name=name,
            book=book,
            bond=REBEL,
            frame_catalogue="JANUS",
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
        )
        made = creation.respond(
            viewer, "create-" + name, invitation["id"], state(game).revision, draft
        )
        actor = ActorRef.model_validate(made["actor"])
        change(cast, viewer, "join", actor)
        return actor

    rev = create(PLAYER, "REVOLUTIONARY IDEALIST", "Original Revolutionary")
    wife = create(OTHER, "ANGEL-WIFE", "Original Wife")
    service = AncillaryOrderService(game)
    service.set_pronouns(PLAYER, "owned-pronouns", rev, state(game).revision, "they/them")
    assert actors.inspect(PLAYER, rev)["pronouns"] == "they/them"
    with ledger.transaction() as c:
        canon = state(game)
        body = ancillary.find(canon, rev)
        tag = TagState(id="already-owned", label="Knows the exit", giver=1, giver_actor=REBEL)
        ancillary.put(canon, body.model_copy(update=dict(tags=(tag,))))
        game.event(c, ADMIN.user_id, "established-original-tag", "synthetic.existing_tag", canon)

    game.dice = Dice((3, 4))
    first = service.issue(
        ADMIN, "rebel-order", 900, REBEL, state(game).revision, rev.token, "Remain here."
    )["id"]
    service.act(PLAYER, "owned-refusal", first, state(game).revision, "disobey")
    service.act(
        PLAYER,
        "my-tag",
        first,
        state(game).revision,
        "mark",
        tag=tag.id,
        direction=1,
        account="I know how to leave quietly.",
    )
    receipt = next(x for x in records(state(game)) if x.id == first)
    assert receipt.faces == (3, 4) and receipt.total == 8 and receipt.modifier == 1
    assert ancillary.find(state(game), rev).tags[0].marked
    service.act(
        PLAYER,
        "own-mid",
        first,
        state(game).revision,
        "act",
        heat=1,
        account="I slip through the side door.",
    )
    service.act(
        ADMIN,
        "actual-notice-check",
        first,
        state(game).revision,
        "unheard",
        account="The original Handler has yet to discover the quiet exit.",
    )

    second = service.issue(
        ADMIN,
        "spouse-order",
        900,
        REBEL,
        state(game).revision,
        wife.token,
        "Meet me in the original public room.",
    )["id"]
    assert service.get(OTHER, second)["forbidden"]
    with pytest.raises(WorkflowError, match="allowed"):
        service.act(OTHER, "forbidden-disobey", second, state(game).revision, "disobey")
    assert game.dice.calls == 1
    service.act(
        OTHER,
        "own-follow",
        second,
        state(game).revision,
        "follow",
        account="I decide to join him there.",
    )
    assert next(x for x in records(state(game)) if x.id == second).consequence == "chosen_follow"

    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_ancillary_order(click, service, 900, REBEL),
            dict(person=(wife.token,), reference=(REBEL.token,), pronouns=("he",)),
            94830,
        )
    )
    (item,) = [x for x in InboxService(ledger).items(OTHER) if x.task == "m3_ancillary_order"]
    assert "address_directives" not in actors.inspect(OTHER, wife)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, item.identity)
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_order_response(click, service, item.identity),
            dict(choice=("follow",), account="I heard that he uses he."),
            94832,
        )
    )
    (saved,) = actors.inspect(OTHER, wife)["address_directives"]
    assert saved["subject"] == REBEL.token and saved["pronouns"] == "he"
    with pytest.raises(WorkflowError, match="controlled by another"):
        actors.inspect(PLAYER, wife)
    with ledger.transaction() as c:
        canon = state(game)
        original_wife = ancillary.find(canon, wife)
        after = tuple(
            x.model_copy(update=dict(id="another-identity")) if x.name == "Wife" else x
            for x in original_wife.identities
        )
        ancillary.put(canon, original_wife.model_copy(update=dict(identities=after)))
        game.event(c, ADMIN.user_id, "old-wife-ended", "synthetic.identity_lost", canon)
    assert "address_directives" not in actors.inspect(OTHER, wife)
