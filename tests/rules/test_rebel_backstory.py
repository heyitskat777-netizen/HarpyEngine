"""Actual backstory Strain Tag and Girl-owned alternate Handler consequence."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_control_ritual import source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_handler_tags import open_handler_tags
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_tags import uses
from girlframe.engine.m3_rebel_backstory import sources
from girlframe.services.m3_handler_consequences import HandlerConsequenceService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("body_choice", ["weakness", "death"])
def test_actual_backstory_source_native_alternative_owned_consequence_and_replay(
    ledger, body_choice
):
    game, _, _ = source(
        ledger,
        rebellion_face=5,
        rebellion_values=dict(
            backstory_tag="My abandoned home still haunts me",
            backstory_observers=("2",),
            account="The Handler describes a childhood abandoned home witnessed by this Girl",
        ),
    )
    value = sources(state(game))[0]
    service = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    menu = service.view(PLAYER, 900, girl)
    assert menu["tags"] == [dict(id=value.tag, label=value.label, backstory_helpless=True)]
    assert not service.view(OTHER, 900, current_ref(state(game), 3))["tags"]
    before = state(game)

    async def use_native():
        interaction = current(2, 29700)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_handler_tags(interaction, game, actor=girl)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        kind = next(x for x in form.fields if x.key == "kind")
        assert "helpless" in {x[0] for x in kind.options}
        form.values.update(
            tag=(value.tag,),
            kind=("helpless",),
            account="My actual action uses the witnessed backstory against the Handler",
        )
        await form.confirm.callback(current(2, 29701))
        assert form.completed

    asyncio.run(use_native())
    actual = state(game)
    assert all(x.id != value.tag for x in actual.handler_tags)
    assert actual.sheets == before.sheets and game.dice.calls == 0
    assert uses(actual)[0].kind == "helpless" and uses(actual)[0].state == "pending"
    case = actual.handler_consequences[-1]
    assert case.trigger == "helpless" and case.opponent == girl and case.state == "pending"
    consequences = HandlerConsequenceService(ledger)
    data = consequences.get(ADMIN, case.id)
    tag_use = uses(actual)[0]
    with pytest.raises(WorkflowError, match="body consequence"):
        service.respond(
            ADMIN,
            "no-ordinary-response-waiver",
            tag_use.id,
            tag_use.revision,
            "give_in",
            "Cannot waive the actual body consequence",
        )
    with pytest.raises(WorkflowError):
        consequences.respond(
            PLAYER,
            str(uuid4()),
            case.id,
            data["game_revision"],
            "injury",
            "I cannot choose for the Handler",
        )

    response_account = (
        "My real grief exposes a specific weakness to this Girl"
        if body_choice == "weakness"
        else "This original Handler dies as the actual replacement consequence"
    )

    async def resolve_actual_request():
        interaction = current(1, 29705)
        await interaction.response.defer(ephemeral=True)
        await open_handler_tags(interaction, game, identity=tag_use.id)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"choice", "account", "confirmation"}
        form.values.update(
            choice=(body_choice,),
            account=response_account,
            confirmation="END THIS HANDLER" if body_choice == "death" else "",
        )
        await form.confirm.callback(current(1, 29706))
        assert form.completed

    asyncio.run(resolve_actual_request())
    result = consequences.respond(
        ADMIN,
        "29706",
        case.id,
        data["game_revision"],
        body_choice,
        response_account,
    )
    assert (
        consequences.respond(
            ADMIN,
            "29706",
            case.id,
            data["game_revision"],
            body_choice,
            response_account,
        )
        == result
    )
    after = state(game)
    assert after.handler_consequences[-1].state == "resolved"
    if body_choice == "weakness":
        assert len(after.handler_opportunities) == len(before.handler_opportunities) + 1
        assert after.handler_opportunities[-1].beneficiary == girl
    else:
        assert len(after.handler_archives) == len(before.handler_archives) + 1
        assert after.handler_archives[-1].actor == case.actor
        assert after.handler_archives[-1].ending == "death"
    assert not consequences.tasks(ADMIN) and game.dice.calls == 0
    assert uses(after)[0].state == "resolved"
    with ledger.engine.connect() as c:
        from girlframe.database import tables as t

        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == tag_use.id)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
    # A fresh use cannot spend this source again.
    with pytest.raises(WorkflowError):
        service.use(
            PLAYER,
            "cannot-spend-again",
            900,
            girl,
            menu["source_sha256"],
            value.tag,
            "helpless",
            "No second use",
        )
    assert state(game) == after


def test_ordinary_handler_tag_does_not_gain_the_source_alternative(ledger):
    game, _, _ = source(ledger)
    with ledger.transaction() as c:
        changed = state(game)
        changed.handler_tags.append(
            TagState(id="ordinary", label="Ordinary Handler Tag", giver=1, observers=(1, 2))
        )
        game.event(c, 1, "synthetic-ordinary-tag", "synthetic.baseline", changed)
    service = HandlerTagService(game)
    girl = current_ref(state(game), 2)
    menu = service.view(PLAYER, 900, girl)
    before = state(game)
    with pytest.raises(WorkflowError, match="Strain-granted"):
        service.use(
            PLAYER,
            "ordinary-not-backstory",
            900,
            girl,
            menu["source_sha256"],
            "ordinary",
            "helpless",
            "An ordinary Tag cannot do this",
        )
    assert state(game) == before and game.dice.calls == 0
