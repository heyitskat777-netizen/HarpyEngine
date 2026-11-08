"""Native control shape and owned submission tests; live mobile playtest remains separate."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from test_ledger import PLAYER
from test_m2_game import ledger_fixture, setup_game, start, state, tick

from girlframe.discord_adapter.m2_forms import Field, FormSelect, NarrativeModal, NativeForm
from girlframe.discord_adapter.m2_ui import SceneControls, answer_values, choice_fields
from girlframe.engine.m2_permissions import LOCK_MASK, SEND_MASK, merge, records

ledger = ledger_fixture


def interaction(owner=2):
    value = MagicMock()
    value.user.id = owner
    value.guild_id = 200
    value.response = MagicMock()
    value.response.is_done.return_value = False
    value.response.send_message = AsyncMock()
    value.response.defer = AsyncMock()
    value.edit_original_response = AsyncMock()
    return value


def test_native_form_owner_selection_and_explicit_confirmation():
    async def run():
        submit = AsyncMock(return_value="Saved")
        form = NativeForm(
            2,
            "Synthetic choice",
            "Select, review, confirm.",
            [
                Field("options", "Choose", (("yes", "Yes"),)),
                Field("text", "Describe", paragraph=True),
            ],
            submit,
        )
        assert not await form.interaction_check(interaction(3))
        native = next(x for x in form.children if isinstance(x, FormSelect))
        native._values = ["yes"]
        await native.callback(interaction())
        assert form.values == {"options": ("yes",)} and submit.await_count == 0
        await form.confirm.callback(interaction())
        assert submit.await_count == 0
        modal = NarrativeModal(form, form.fields[1])
        modal.input._value = "Player narrative"
        await modal.on_submit(interaction())
        assert submit.await_count == 0
        await form.confirm.callback(interaction())
        assert submit.await_count == 1 and form.completed
        assert not await form.interaction_check(interaction())

    asyncio.run(run())


def test_select_option_paging_stays_within_discord_limits():
    async def run():
        form = NativeForm(
            2,
            "Options",
            "Choose.",
            [Field("tag", "Tag", tuple((str(i), "Tag " + str(i)) for i in range(60)))],
            AsyncMock(),
        )
        assert len(next(x for x in form.children if isinstance(x, FormSelect)).options) == 25
        form.option_page = 2
        form.controls()
        assert len(next(x for x in form.children if isinstance(x, FormSelect)).options) == 10
        assert all(x.row is None or 0 <= x.row <= 4 for x in form.children)

    asyncio.run(run())


@pytest.mark.parametrize("tier", ["low", "mid", "high"])
@pytest.mark.parametrize(
    "kind",
    [
        "tag_window",
        "tag_resolution",
        "paired_tag",
        "actor_keep",
        "handler_keep",
        "actor_sensors",
        "handler_sensors",
        "actor_engage",
        "actor_disobey",
        "handler_disobey",
        "follow_disobey",
        "actor_flirt",
        "target_flirt",
        "actor_flirt_answer",
        "flirt_escape",
        "handler_brief",
        "flirt_owe_tag",
        "order_response",
        "followthrough_confirm",
    ],
)
def test_each_owned_response_has_native_fields(kind, tier):
    data = {
        "kind": kind,
        "own": {
            "girl": "OLDGEN",
            "identities": [{"id": "i", "name": "Identity", "marked": True, "protected": False}],
            "assets": [{"id": "asset", "name": "Asset", "damaged": False}],
        },
        "result": {"tier": tier, "questions": ["Question"], "off_list": True, "question": "name"},
        "tags": [{"id": "tag", "label": "Observed"}],
        "participants": [1, 2, 3],
        "actor": 2,
    }
    fields = choice_fields(data)
    assert fields and len({x.key for x in fields}) == len(fields)
    assert all("json" not in x.label.lower() for x in fields)
    assert all(x.minimum <= x.maximum for x in fields)


def test_permissions_cover_every_send_override_and_merge_safe_restoration():
    snapshot = {
        "everyone_id": 200,
        "bot_id": 100,
        "overwrites": [
            {"kind": "role", "id": "42", "allow": LOCK_MASK | 1024, "deny": 64},
            {"kind": "member", "id": "2", "allow": LOCK_MASK, "deny": 0},
        ],
    }
    result = records(snapshot)
    for entry in result:
        if entry["id"] == "100":
            assert entry["applied"]["allow"] & SEND_MASK == SEND_MASK
        else:
            assert (
                entry["applied"]["allow"] & LOCK_MASK == 0
                and entry["applied"]["deny"] & LOCK_MASK == LOCK_MASK
            )
        original = entry["original"]
        applied = merge(entry, original, restore=False)
        assert merge(entry, applied, restore=True) == original
    entry = next(x for x in result if x["id"] == "42")
    edited = dict(entry["applied"])
    edited["allow"] |= 1 << 20
    assert merge(entry, edited, restore=True)["allow"] == entry["original"]["allow"] | (1 << 20)
    conflict = dict(entry["applied"])
    conflict["deny"] &= ~(1 << 11)
    with pytest.raises(ValueError):
        merge(entry, conflict, restore=True)


def test_persistent_controls_and_inbox_route_owned_response(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    start(game)
    tick(worker, gateway)
    from girlframe.services.inbox import InboxService

    page = InboxService(ledger).page(PLAYER, category="plays")
    assert page.total == 1 and page.item.task == "m2_choice"

    async def run():
        controls = SceneControls(game)
        assert controls.is_persistent()
        for child in controls.children:
            assert child.custom_id.startswith("m2:scene:")

    asyncio.run(run())
    data = game.decision(PLAYER, page.item.identity)
    assert "review" not in data and data["kind"] == "tag_window"
    assert state(game).sheets["2"].heat == 0 and dice.calls == 1
    assert answer_values(
        {"options": ("pin",), "fields.pin": ("girl:0",), "fields.cover": ("girl:1",)}
    ).fields == {"pin": "girl:0"}
