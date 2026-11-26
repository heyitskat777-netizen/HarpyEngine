"""Verify the facilitator's sheet projection and the Activity access boundary."""

import json
from http import HTTPStatus

import mission_lab
import pytest
from campaign_registry import CampaignRegistry
from facilitator_dossiers import review_dossiers
from test_alternate_initiative import native_case
from test_artwork_activity import request
from test_campaign_role_access import CONFIG, role_activity
from test_handler_pilot_view import login
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.campaign_opening import Opening
from girlframe.engine.m3_world_state import Npc
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.onboarding import WorkflowError


def approve_facilitator(store, handler, participant, *, channel=900):
    opening = Opening(
        scene="synthetic-dossier-opening",
        channel=channel,
        handler=handler,
        audience=(handler, participant),
        plan="dossier-filing",
        goals="Review the roster.",
        difficulty="normal",
        introduction="Personnel intake.",
        first_mission_day=2,
        facilitator=participant,
    )
    with store.transaction() as conn:
        store._audit(conn, handler, "approved-dossier-plan", EVENT, opening.model_dump(mode="json"))


def test_campaign_dossiers_use_public_pilot_and_current_npc_sheets(ledger):
    game, *_ = native_case(ledger, "gorgon", harpy=True)
    canon = state(game)
    before = canon.sheets[str(PLAYER.user_id)]
    before.public_fields = ("assets",)
    before.assets[0].concealed = True
    hidden_asset = before.assets[0].name
    contact = Npc(
        id="concealed-contact",
        name="Classified contact",
        detail="A roster entry for a facilitator.",
        jobs=("fan",),
        cell=(0, 0),
        controller=ADMIN.user_id,
    )
    assert canon.world
    canon.world = canon.world.model_copy(update={"npcs": (*canon.world.npcs, contact)})
    with ledger.transaction() as conn:
        game.event(conn, ADMIN.user_id, "dossier-fixture", "synthetic.dossiers", canon)

    with pytest.raises(WorkflowError, match="approved facilitator"):
        review_dossiers(game, ADMIN)
    approve_facilitator(ledger, ADMIN.user_id, OTHER.user_id)
    for viewer in (ADMIN, PLAYER):
        with pytest.raises(WorkflowError, match="approved facilitator"):
            review_dossiers(game, viewer)
    view = review_dossiers(game, OTHER)
    assert {"Pilot", "Handler", "NPC", "Harpy", "Gorgon"} <= {
        row["kind"] for row in view["dossiers"]
    }
    pilot = next(row for row in view["dossiers"] if row["name"] == before.callsign)
    assert pilot["frame"] == before.frame and pilot["heat"] == before.heat
    assert not pilot["identities"] and pilot["assets"]
    assert all(item["name"] != hidden_asset for item in pilot["assets"])
    assert any(row["name"] == "Classified contact" for row in view["dossiers"])
    assert next(row for row in view["dossiers"] if row["kind"] == "Harpy")["assets"]
    assert next(row for row in view["dossiers"] if row["kind"] == "Gorgon")["gorgon_class"]
    encoded = json.dumps(view)
    assert "PRIVATE_CANARY" not in encoded
    private_keys = ('"controller"', '"source_sha256"', '"personal_notes"')
    assert not any(key in encoded for key in private_keys)
    assert state(game).revision == canon.revision


def test_activity_dossier_route_uses_selected_campaign_facilitator(tmp_path, monkeypatch):
    with role_activity(tmp_path) as host:
        facilitator, handler, other = (
            login(host, name) for name in ("invited", "handler", "other")
        )
        runtime = tmp_path / "role-runtime"
        fixture = runtime / "playtest-campaigns" / "discord-offline-single-role"
        catalog = CampaignRegistry(fixture / "managed-fixture.sqlite3")
        first, second = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)
        setup = "/api/player-setup?campaign=" + first.id
        route = "/api/facilitator-dossiers?campaign=" + first.id
        request(host, route, status=HTTPStatus.UNAUTHORIZED)
        assert not request(host, setup, facilitator)["can_review_dossiers"]
        request(host, route, facilitator, status=HTTPStatus.FORBIDDEN)
        monkeypatch.setattr(mission_lab, "RUNTIME", runtime)
        game = mission_lab.open_managed_campaign(first, initialize=False)
        try:
            approve_facilitator(
                game.store,
                int(first.handler_id),
                int(CONFIG.invited_user_id),
                channel=int(first.channel_id),
            )
        finally:
            game.store.engine.dispose()
        assert request(host, setup, facilitator)["can_review_dossiers"]
        assert not request(host, setup, handler)["can_review_dossiers"]
        request(host, route, handler, status=HTTPStatus.FORBIDDEN)
        request(host, route, other, status=HTTPStatus.FORBIDDEN)
        assert request(host, route, facilitator)["dossiers"] == []
        request(
            host,
            "/api/facilitator-dossiers?campaign=" + second.id,
            facilitator,
            status=HTTPStatus.FORBIDDEN,
        )
