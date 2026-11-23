"""Source-bound Gorgon Tags adjust the saved Engage roll and offer owned removal."""

import asyncio
import json

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_engage_actual import pass_tags, pilot_start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_world import open_world
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import WorldTag
from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon_tags import REMOVE, RULE, SELECT, GorgonTagService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("branch", ["stack", "single", "unreleased"])
def test_gorgon_tags_use_an_actual_original_roll_and_preserve_review_scope(
    ledger, tmp_path, monkeypatch, branch
):
    game, worker, gateway, _, _, _ = prepared(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    if branch != "unreleased":
        registry = load_registry().model_dump(mode="json")
        row = next(x for x in registry["entries"] if x["id"] == RULE)
        row.update(
            implementation="implemented",
            source_audit="audited",
            independent_review="approved",
            reviewer="Synthetic Gorgon Tags only",
            review_reference="Temporary fixture",
            contract=next(
                x["contract"] for x in registry["entries"] if x["id"].endswith("personal-firearm")
            ),
            test_evidence=["tests/rules/test_gorgon_tags.py"],
        )
        parsed = Registry.model_validate_json(json.dumps(registry))
        path = tmp_path / "gorgon-tags-synthetic-review.json"
        path.write_text(parsed.model_dump_json())
        monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
        approved = ledger.policy.m3_approval.model_copy(update={"registry_sha256": digest(parsed)})
        ledger.policy = ledger.policy.model_copy(update={"m3_approval": approved})

    target = ActorRef(kind="gorgon", entity="secret")
    with ledger.transaction() as c:
        canon = state(game)
        giver = current_ref(canon, PLAYER.user_id).model_dump_json()
        # Previously established, known Tags are the starting fixture for their use.
        creature = canon.world.gorgons[0].model_copy(
            update=dict(
                revealed=True,
                tags=(
                    WorldTag(id="twisted", label="Twisted", giver_entity=giver),
                    WorldTag(id="cracked", label="Cracked", giver_entity="1"),
                    WorldTag(id="static", label="PRIVATE_OTHER_TAG", giver_entity="1"),
                ),
            )
        )
        canon.world = update(canon.world, gorgons=(creature,))
        game.event(c, 1, "known-original-gorgon", "synthetic.known_gorgon", canon)
    change(CastService(ActorService(MissionService(ledger))), ADMIN, "join", target)
    if branch != "unreleased":
        source = GorgonTagService(game)
        assert source.view(OTHER, 900)["gorgons"] == {}
        with pytest.raises(WorkflowError, match="controlled Gorgon"):
            source.disclose(
                OTHER,
                "unowned-gorgon",
                900,
                state(game).revision,
                target.entity,
                "cracked",
                ("2",),
                "I cannot authorize this.",
            )
        with pytest.raises(WorkflowError, match="original witnesses"):
            source.disclose(
                ADMIN,
                "absent-recipient",
                900,
                state(game).revision,
                target.entity,
                "cracked",
                ("999",),
                "It was not observed by this account.",
            )

        async def share():
            opening = current(ADMIN.user_id, 89550)
            opening.channel_id = 900
            await opening.response.defer(ephemeral=True)
            await open_world(opening, WorldService(MissionService(ledger)))
            world_menu = opening.edit_original_response.call_args.kwargs["view"]
            assert isinstance(world_menu, Picker)
            selecting = current(ADMIN.user_id, 89551)
            selecting.channel_id = 900
            await selecting.response.defer(ephemeral=True)
            await world_menu.open_item(selecting, "share_gorgon_tag")
            gorgons = selecting.edit_original_response.call_args.kwargs["view"]
            assert isinstance(gorgons, Picker)
            choosing = current(ADMIN.user_id, 89552)
            await choosing.response.defer(ephemeral=True)
            await gorgons.open_item(choosing, target.entity)
            form = choosing.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values.update(
                tag=("cracked",), audience=("2",), account="Actual crack observed by the Girl."
            )
            await form.confirm.callback(current(ADMIN.user_id, 89553))
            assert form.completed

        asyncio.run(share())
    game.dice.faces = (3, 3)
    action = pilot_start(game, target)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, "one-roll", action)
    receipt = game.inspect(PLAYER, action)["receipt"]
    pass_tags(game)
    if branch == "unreleased":
        assert not any(x["kind"] == SELECT for x in game.choices(PLAYER))
        assert any(x["kind"] == "engage_maneuvers" for x in game.choices(PLAYER))
        assert state(game).world.gorgons[0].tags == creature.tags
        return

    row = next(x for x in game.choices(PLAYER) if x["kind"] == SELECT)
    view = game.decision(PLAYER, row["id"])
    assert {x["id"] for x in view["gorgon_tags"]} == {"twisted", "cracked"}
    assert "PRIVATE_OTHER_TAG" not in str(view)
    if branch == "single":
        choice = ChoiceAnswer(denied=("twisted",), text="The actual complication matters.")
        game.respond(PLAYER, "lower-roll", row["id"], row["revision"], choice)
        assert not any(x["kind"] == REMOVE for x in game.choices(ADMIN))
        asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
        answer(
            game,
            PLAYER,
            "engage_maneuvers",
            options=("cover",),
            fields={"cover": asset.id},
            denied=(asset.id,),
            text="The actual tactical setback.",
        )
        result = game.inspect(PLAYER, action)
        assert result["state"] == "complete" and result["result"]["total"] == 5
        assert result["receipt"] == receipt and game.dice.calls == 1
        assert state(game).world.gorgons[0].tags == creature.tags
        return
    with pytest.raises(WorkflowError):
        game.decision(OTHER, row["id"])
    with pytest.raises(WorkflowError, match="distinct original Gorgon Tags"):
        game.respond(
            PLAYER,
            "invalid-double",
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("twisted",), denied=("twisted",), text="Must select each source once."
            ),
        )
    ledger.safety(OTHER, "pause-gorgon-tags", ledger.status(OTHER)["revision"], pause=True)
    selected = ChoiceAnswer(options=("twisted", "cracked"), text="PRIVATE_TAG_RELEVANCE")
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.respond(PLAYER, "pause-select", row["id"], row["revision"], selected)
    ledger.safety(OTHER, "resume-gorgon-tags", ledger.status(OTHER)["revision"], pause=False)

    async def native(viewer, serial, identity, **values):
        click = current(viewer.user_id, serial)
        await click.response.defer(ephemeral=True)
        await open_choice(click, game, identity)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirm = current(viewer.user_id, serial + 1)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    asyncio.run(native(PLAYER, 89600, row["id"], options=selected.options, text=selected.text))
    game.respond(PLAYER, "89601", row["id"], row["revision"], selected)
    assert not any(x["kind"] == "engage_maneuvers" for x in game.choices(PLAYER))
    ledger.engine.dispose()
    reopened = GameService(ledger)
    remove = next(x for x in reopened.choices(ADMIN) if x["kind"] == REMOVE)
    with pytest.raises(WorkflowError):
        reopened.decision(PLAYER, remove["id"])
    asyncio.run(native(ADMIN, 89610, remove["id"], options=("static",)))
    assert tuple(x.id for x in state(game).world.gorgons[0].tags) == ("twisted", "cracked")
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("pin", "advance"),
        fields={"pin": asset.id, "advance": asset.id},
        text="The actual held ground.",
    )
    result = reopened.inspect(PLAYER, action)
    assert result["state"] == "complete" and result["result"]["total"] == 8
    assert result["receipt"] == receipt and game.dice.calls == 1
    assert "PRIVATE_TAG_RELEVANCE" not in str(gateway.messages)
