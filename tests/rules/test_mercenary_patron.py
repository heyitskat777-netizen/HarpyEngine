"""The actual original sponsor withdraws and the original new Patron accepts."""

import asyncio

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.discord_adapter.m3_mercenary_patron import open_patron_inbox
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_mercenary_patron import RULE, MercenaryPatronService, sponsorship
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_mercenary_patron_withdrawal_and_owned_replacement(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    replacement = ActorRef(kind="npc", entity="original-new-patron")
    WorldService(missions).npc(
        ADMIN,
        "new-patron",
        state(game).revision,
        Npc(
            id=replacement.entity,
            name="Original new Patron",
            jobs=("patron",),
            detail="An actual local economic sponsor.",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    options = AncillaryService(missions)
    offer = options.invite(
        ADMIN,
        "actual-mercenary",
        state(game).revision,
        PLAYER.user_id,
        "base0",
        contacts=(PATRON,),
    )["id"]

    def gear(name):
        return ancillary.NamedAsset(name=name, description="The original actual owned gear.")

    draft = ancillary.Draft(
        book="MERCENARY",
        name="Original Mercenary",
        bond=current_ref(state(game), OTHER.user_id),
        patron=PATRON,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["MERCENARY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("MERCENARY", "JANUS")[:2]),
    )
    created = options.respond(PLAYER, "accept-actual-mercenary", offer, state(game).revision, draft)
    mercenary = ActorRef.model_validate(created["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", mercenary)
    for role in (PATRON, replacement):
        change(cast, ADMIN, "join", role)
    service = MercenaryPatronService(game)
    assert service.menu(PLAYER, 900, mercenary)["funded"]
    assert depth(state(game), mercenary, PATRON) == 1

    async def cast_open(click, actor):
        await open_cast(click, cast)
        picker = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        await picker.open_item(click, "patronage:" + actor.token)

    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: cast_open(click, PATRON),
            dict(person=(mercenary.token,), account="My NPC ends the exact original sponsorship."),
            93600,
        )
    )
    loss = sponsorship(state(game), mercenary).loss
    assert loss and not service.menu(PLAYER, 900, mercenary)["funded"]
    inbox = InboxService(ledger)
    assert any(x.identity == loss and x.task == "m3_mercenary_patron" for x in inbox.items(PLAYER))
    assert not any(x.identity == loss for x in inbox.items(OTHER))

    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: cast_open(click, mercenary),
            dict(person=(replacement.token,), account="I ask this actual NPC to back me."),
            93604,
        )
    )
    current = sponsorship(state(game), mercenary)
    assert (
        current.proposal
        and current.loss == loss
        and depth(state(game), mercenary, replacement) == 0
    )
    with pytest.raises(WorkflowError, match="unavailable"):
        service.offer(OTHER, current.proposal)
    ledger.engine.dispose()
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_patron_inbox(click, service, current.proposal, "offer"),
            dict(choice=("yes",)),
            93608,
        )
    )
    final = state(game)
    funded = sponsorship(final, mercenary)
    assert funded.patron == replacement and funded.old == PATRON and funded.loss is None
    assert depth(final, mercenary, replacement) == 1 and depth(final, mercenary, PATRON) == 1
    assert service.menu(PLAYER, 900, mercenary)["funded"]
