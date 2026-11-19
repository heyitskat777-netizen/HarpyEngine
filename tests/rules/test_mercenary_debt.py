"""Debt charges only the original Mercenary and preserves the modified native dice."""

import asyncio

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_mercenary_debt import open_debt_response
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_items import ItemService
from girlframe.services.m3_mercenary_debt import RULE, DebtService, records
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_mercenary_debt_verifies_cash_then_reopens_original_modified_roll(
    ledger, tmp_path, monkeypatch
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN, "debt-mercenary", state(game).revision, PLAYER.user_id, "base0", contacts=(PATRON,)
    )

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Original gear.")

    sample = ancillary.Draft(
        name="Mercenary pursuing her own goal",
        book="MERCENARY",
        bond=current_ref(state(game), OTHER.user_id),
        patron=PATRON,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["MERCENARY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("MERCENARY", "JANUS")[:2]),
    )
    made = creation.respond(
        PLAYER, "debt-original-role", invitation["id"], state(game).revision, sample
    )
    mercenary = ActorRef.model_validate(made["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", mercenary)
    with ledger.transaction() as c:
        canon = state(game)
        original = ancillary.find(canon, mercenary)
        ancillary.put(canon, original.model_copy(update=dict(heat=2)))
        game.event(c, ADMIN.user_id, "debt-fixture-heat", "synthetic.scene_context", canon)

    source = current_ref(state(game), OTHER.user_id)
    items = ItemService(game)
    cash = items.propose(
        OTHER, "propose-actual-cash", source, "Envelope of credits", "Actual cash."
    )
    receipt = items.get(ADMIN, cash["id"])
    items.confirm(
        ADMIN,
        "confirmed-actual-cash",
        cash["id"],
        receipt["revision"],
        exists=True,
        account="The envelope contains the original Girl’s fictional cash.",
    )
    service = DebtService(game)
    assert not service.menu(OTHER, 900, source)["people"]

    async def cast_open(click, token):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, token)

    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: cast_open(click, "debt-contact:" + mercenary.token),
            dict(person=(source.token,)),
            93796,
        )
    )
    assert mercenary.token in service.menu(OTHER, 900, source)["people"]
    assert not any(x.id == mercenary.entity and x.revealed for x in state(game).world.pilots)
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: cast_open(click, "debt:" + source.token),
            dict(item=(cash["id"],), person=(mercenary.token,), account="Leave the records alone."),
            93800,
        )
    )

    (offered,) = records(state(game))
    inbox = InboxService(ledger)
    assert not any(x.identity == offered.id for x in inbox.items(PLAYER))
    assert any(
        x.identity == offered.id and x.task == "m3_mercenary_debt" for x in inbox.items(ADMIN)
    )
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_debt_response(click, service, offered.id),
            dict(choice=("verify",), account="The offeror showed the cash in this scene."),
            93804,
        )
    )
    expected = service.get(PLAYER, offered.id)["revision"]
    monkeypatch.setattr(game.dice, "roll", lambda: (5, 6))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.act(OTHER, "debt-wrong-owner", offered.id, expected, "disobey", heat=1)
    rolled = service.act(PLAYER, "debt-original-roll", offered.id, expected, "disobey", heat=1)
    assert rolled["total"] == 10 and rolled["step"] == "result"
    ledger.engine.dispose()
    resent = service.act(PLAYER, "debt-original-roll", offered.id, expected, "disobey", heat=1)
    assert resent == rolled
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_debt_response(click, service, offered.id),
            dict(heat=("2",), account="Nobody buys my silence"),
            93808,
        )
    )
    assert records(state(game))[0].step == "witness"
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_debt_response(click, service, offered.id),
            dict(choice=("unnoticed",), account="Nobody in authority learned of the refusal."),
            93812,
        )
    )
    final = state(game)
    (closed,) = records(final)
    original = ancillary.find(final, mercenary)
    assert closed.step == "closed" and closed.witness_event
    assert closed.outcome == "chose_to_disobey" and closed.roll.faces == (5, 6)
    assert original.heat == 3 and original.tags[0].label == "Nobody buys my silence"
    assert next(x for x in final.held_items if x.id == cash["id"]).holder == source
    assert source != original.actor
