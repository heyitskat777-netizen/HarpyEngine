"""Check the shared P2 sheet/scene catalog against HarpyEngine ownership."""

import re
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pytest
from girlframe.engine import m3_casualty
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_enforcer_requisitions import SNOOP
from girlframe.engine.m3_privileges import revoke
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.director_play_catalog import NATIVE_RULES
from girlframe.services.director_play_options import initiative_play_options
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_learned_plays import (
    CALL,
    HOUND,
    KEEP_RIDERS,
    NO_ONE_BETTER,
    PSYCHE,
    RISK,
    SHOW_DOG,
)
from test_enforcer_requisitions import approved, buy
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_requisition_service import ready
from test_vatgrown_plays import _learn_daily_source
from test_vatgrown_plays import ready as vatgrown_ready

from ai_native_plays import SCENE_STARTERS
from handler_playbook import RULES as HANDLER_STARTERS
from play_catalog import character_plays
from player_setup import RELAY, PlayerSetup

ledger = ledger_fixture
# Flirt follow-through effects are contextual and have no standalone entry.
GIRL_PLAYS = {
    "PRINCESS": set(),
    "MOCKINGBIRD": {"mockingbird_person"},
    "STIM-BLISSED": {"dose_up"},
    "NEWGIRL": {"easy_target"},
    "CASUALTY": set(),
    "OLDGEN": {"old_dog_new_pups"},
    "VATGROWN": {"unassuming_doll"},
    "ALPHA": {"brutalize"},
    "AM": {"am_scrutinized", "am_just_code"},
    "BONDED": {"bonded_side"},
}
FRAME_PLAYS = {
    "THE PRINCE": {"prince_performer"},
    "CONSUME": {"consume_eat"},
    "JANUS": {"living_battery"},
    "DOCTORDOCTOR MK. II": {"nanobot_injection"},
    "WYVERN 0.4": {"wyvern_explore", "wyvern_rouse"},
    "THE ENFORCER": {"enforcement_initiative"},
    "CHANGELING": {"changeling_blank_slate"},
    "PROJECT ANKOU": set(),  # Processor Core is a requisition.
    "THE RED QUEEN": {"red_queen_consult"},
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_catalog_covers_each_registered_girl_and_frame():
    assert GIRL_PLAYS.keys() == GIRL_TYPES.keys()
    assert FRAME_PLAYS.keys() == FRAME_TYPES.keys()


def test_parity_checklist_covers_the_native_pilot_handler_catalog(registry):
    path = Path(__file__).with_name("AI-PLAY-PARITY.md")
    recorded = set(re.findall(r"^\| `([^`]+)` \|", path.read_text(encoding="utf-8"), re.MULTILINE))
    expected = {key for key in NATIVE_RULES if not key.startswith("gorgon_")}
    expected.update((*KEEP_RIDERS, HOUND, CALL, SHOW_DOG, PSYCHE, RISK, NO_ONE_BETTER, m3_casualty.BARELY))
    known_rules = set(NATIVE_RULES.values())
    expected.update(
        entry.id for entry in registry.entries
        if entry.id not in known_rules and entry.scope in {
            "basic", "girl", "frame", "handler", "handler-playbook",
        }
        and (entry.kind == "play" or entry.contract and entry.contract.roll_kind in {"2d6", "d6"})
    )
    assert expected <= recorded


def test_all_private_playbooks_require_an_original_consent_source_and_registry_review(registry):
    gated = {
        entry.id for entry in registry.entries
        if entry.scope in {"girl", "handler-playbook"} and entry.id.endswith(".sex-play")
    }
    assert len(gated) == len(GIRL_TYPES) + 7
    direct = (*SCENE_STARTERS, *("handler_" + key for key in HANDLER_STARTERS))
    assert not (gated & {NATIVE_RULES.get(key, key) for key in direct})
    for rule in gated:
        entry = registry.entry(rule)
        assert entry.implementation == "subset"
        assert entry.independent_review == "pending"
        with pytest.raises(ValueError, match="independent_review=pending"):
            registry.require_available(rule)


@pytest.mark.parametrize("kind", ("npc", "external_pilot", "gorgon"))
def test_model_cannot_reuse_a_human_pilot_sheet_for_an_alternate_actor(kind):
    def would_use_wrong_sheet(*args):
        pytest.fail("An alternate body must not be passed to the Pilot and Handler projection.")
    context = SimpleNamespace(native_play_projection=would_use_wrong_sheet)
    assert initiative_play_options(context, None, "test-scene", ActorRef(kind=kind, entity="other-body")) == ()


@pytest.mark.parametrize(("girl", "frame"), list(product(GIRL_PLAYS, FRAME_PLAYS)))
def test_starter_specialists_stay_with_their_playbooks(registry, girl, frame):
    sheet = SimpleNamespace(
        girl=girl,
        frame=frame,
        frame_runtime=None,
        frame_scrapped=False,
        character_id=None,
        blocked_plays=(),
    )
    for own in (False, True):
        for scene in (False, True):
            plays = character_plays(
                registry,
                sheet,
                owns_sheet=own,
                state=GameState(),
                include_unimplemented=scene,
            )
            grouped = {
                scope: {item["id"] for item in plays if item["group"] == scope}
                for scope in ("girl", "frame")
            }
            assert grouped == {"girl": GIRL_PLAYS[girl], "frame": FRAME_PLAYS[frame]}
            assert all(not item["rule_id"].endswith(".sex-play") for item in plays)


def play_ids(registry, game_state, owns_sheet=True):
    return {
        play["id"]
        for play in character_plays(
            registry,
            game_state.sheets[str(PLAYER.user_id)],
            owns_sheet=owns_sheet,
            state=game_state,
        )
    }


def test_grafted_play_follows_paid_current_frame_not_legacy_sheet_or_old_scene(
    ledger, tmp_path, monkeypatch
):
    _, game = ready(ledger, frame="JANUS")
    service = approved(ledger, game, tmp_path, monkeypatch)
    receipt = buy(service, SNOOP, "frame_grafting")
    saved = state(game)
    sheet = saved.sheets[str(PLAYER.user_id)]
    assert (
        sheet.frame_runtime is None
    )  # Original Frame grants must work before runtime initialization.
    assert "snoop" in play_ids(service.registry, saved)
    assert "snoop" not in play_ids(service.registry, saved, owns_sheet=False)
    characters = {int(owner): row.character_id for owner, row in saved.sheets.items()}
    suspended = revoke(
        saved,
        PLAYER.user_id,
        ADMIN.user_id,
        receipt["id"],
        "Until reviewed",
        "synthetic-suspension",
        "synthetic-source",
        characters,
    )
    assert "snoop" not in play_ids(service.registry, suspended)

    setup = PlayerSetup(ledger, ADMIN, PLAYER, OTHER)
    setup.enable_scene_plays()
    adapter = setup.scene_plays
    monkeypatch.setattr(adapter, "for_channel", lambda _: adapter)
    historical = {"current": {"state": "complete"}, "choices": [], "can_start": False}
    monkeypatch.setattr(
        adapter, "play_options", lambda *_: {"snoop": historical.copy()}
    )
    args = (
        PLAYER,
        RELAY,
        900,
        game.sheet(PLAYER),
        game.sheet(PLAYER),
        suspended,
        {"paused": False},
        {},
    )
    projected = setup.scene_projection(*args)
    assert "snoop" not in {item["id"] for item in projected["plays"]}
    assert "snoop" not in projected["options"]
    historical["choices"] = [{"kind": "snoop_answer"}]
    historical["can_start"] = True
    assigned = setup.scene_projection(*args)
    assert assigned["options"]["snoop"]["choices"] == historical["choices"]
    assert not assigned["options"]["snoop"]["can_start"]

    sheet.frame_scrapped = True
    assert {"snoop", "living_battery"}.isdisjoint(play_ids(service.registry, saved))


def test_engine_learned_play_stays_on_only_its_owner_until_used(
    ledger, tmp_path, monkeypatch
):
    rule = "girl.am.scrutinized"
    game, worker, gateway, controls = vatgrown_ready(
        ledger, tmp_path, monkeypatch, teacher="AM"
    )
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, rule),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    before = state(game)
    sheet = before.sheets[str(PLAYER.user_id)]
    assert sheet.girl == "VATGROWN"
    registry = load_registry()
    assert "am_scrutinized" in play_ids(registry, before)
    assert "am_scrutinized" not in play_ids(registry, before, owns_sheet=False)
    sheet.girl_runtime = sheet.girl_runtime.model_copy(
        update={
            "learned_plays": (
                lesson.model_copy(update={"rolled_event": "synthetic-spent-roll"}),
            )
        }
    )
    assert "am_scrutinized" not in play_ids(registry, before)
