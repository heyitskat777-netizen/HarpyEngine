"""Expected source gift, actual compelled roll and each printed result endpoint."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_leviathan_layers import source
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_leviathan_obsession import open_choice, open_influence
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_leviathan_roll_state import Declaration
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_leviathan_obsession import ROLL, TYPE, ObsessionService


@pytest.fixture(autouse=True)
def reviewed_candidate(monkeypatch):
    original = Registry.require_available

    def available(registry, identity):
        if identity in (TYPE, ROLL):
            return next(x for x in registry.entries if x.id == identity)
        return original(registry, identity)

    monkeypatch.setattr(Registry, "require_available", available)


def declare(service, *, tag=None):
    preview = service.preview(ADMIN, 900)
    source = next(x for x in preview["actors"] if x["leviathan"])
    subject = next(
        x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    return service.begin(
        ADMIN,
        str(uuid4()),
        900,
        preview["revision"],
        Declaration(
            mode="succumb" if tag else "give_tag",
            source=ActorRef.model_validate(source["ref"]),
            subject=ActorRef.model_validate(subject["ref"]),
            source_sha256=source["source_sha256"],
            subject_sha256=subject["source_sha256"],
            tag=tag,
            reach_confirmed=True,
            account="The actual Leviathan reaches this original Girl with its influence",
        ),
    )["action_id"]


@pytest.mark.parametrize("outcome", ["low", "mid", "high"])
def test_actual_gift_roll_and_expected_result(ledger, outcome):
    game, worker, gateway, _, _ = source(ledger)
    service = ObsessionService(game)
    before = state(game).sheets["2"].heat
    if outcome == "high":

        async def native_gift():
            interaction = current(1, 19100)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_influence(interaction, service)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            form.values = {
                "source": (form.fields[0].options[0][0],),
                "subject": (
                    ActorRef(
                        kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id
                    ).token,
                ),
            }
            selected = current(1, 19101)
            selected.channel_id = 900
            await form.confirm.callback(selected)
            details = selected.edit_original_response.call_args.kwargs["view"]
            details.values = {
                "mode": ("give",),
                "account": "The original source gives its influence Tag",
            }
            confirmed = current(1, 19102)
            confirmed.channel_id = 900
            await details.confirm.callback(confirmed)

        asyncio.run(native_gift())
        with ledger.engine.connect() as c:
            gift = game.lock(c, 900)["action_id"]
    else:
        gift = declare(service)
    tick(worker, gateway, 3)
    gift_view = game.inspect(PLAYER, gift)
    assert gift_view["state"] == "complete" and game.dice.calls == 0
    tag = gift_view["result"]["tag"]
    tick(worker, gateway, 3)
    count = len(state(game).sheets["2"].tags)
    desired = max(2, 8 - count)
    game.dice.faces = (
        (1, 1)
        if outcome == "low"
        else ((6, 6) if outcome == "high" else (desired // 2, desired - desired // 2))
    )
    root = declare(service, tag=tag)
    tick(worker, gateway, 3)
    rolled = game.inspect(PLAYER, root)
    assert rolled["receipt"]["pre_total"] == sum(game.dice.faces) + count
    assert state(game).sheets["2"].heat == before and game.dice.calls == 1
    pass_tags(game)
    if outcome == "mid":
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "leviathan_identity_result")

        async def native_result():
            interaction = current(2, 19103)
            await interaction.response.defer(ephemeral=True)
            await open_choice(interaction, service, choice["id"])
            form = interaction.edit_original_response.call_args.kwargs["view"]
            form.values = {"result": (form.fields[0].options[0][0],)}
            await form.confirm.callback(current(2, 19104))

        asyncio.run(native_result())
    elif outcome == "low":
        answer(
            game,
            PLAYER,
            "leviathan_arrival_owner",
            flag=True,
            text="I follow the influence trail to its actual endpoint",
        )
        answer(
            game,
            ADMIN,
            "leviathan_arrival_judge",
            flag=True,
            text="The actual owner completed this movement",
        )
        answer(
            game,
            PLAYER,
            "leviathan_low_play",
            text="I face the original source at the end of its trail",
        )
        assert state(game).leviathan_arrivals[-1].source_action == root
    final = game.inspect(PLAYER, root)
    assert final["state"] == "complete" and final["result"]["tier"] == outcome
    if outcome != "low":
        assert state(game).leviathan_obsessions[-1].level == outcome
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
