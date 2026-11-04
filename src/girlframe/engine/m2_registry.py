"""Versioned source registry; independent review is deliberately not self-attested."""

import hashlib
import json
from typing import Any

from girlframe.engine.m2 import RULESET

REGISTRY: dict[str, Any] = {
    "ruleset": RULESET,
    "review_status": "implementation_pending_independent_review",
    "scope": "Human-controlled pilot subset; no AI or complete published-rule claim",
    "plays": [
        {
            "play_id": "keep_your_head",
            "scope": "girl",
            "pdf": 21,
            "printed": 19,
            "trigger": "Describe what you are trying to endure",
            "actor": "pilot",
            "tiers": {
                "low": "one positive; remaining base traits negative; Handler ruling",
                "mid": "two positive and one distinct negative; Handler ruling",
                "high": "four base traits positive, control negative; Tag; Handler ruling",
            },
        },
        {
            "play_id": "check_sensors",
            "scope": "frame",
            "pdf": 26,
            "printed": 24,
            "trigger": "Take stock of the situation",
            "actor": "pilot",
            "tiers": {
                "low": "one listed question",
                "mid": "any two questions",
                "high": "any three questions; off-list uncertainty or later punishment",
            },
        },
        {
            "play_id": "engage",
            "scope": "frame",
            "pdf": 25,
            "printed": 23,
            "trigger": "Hold your own on the battlefield",
            "actor": "pilot",
            "tiers": {
                "low": "one maneuver; damage an Asset used",
                "mid": "two maneuvers",
                "high": "three maneuvers; damage an Asset used",
            },
        },
        {
            "play_id": "disobey_orders",
            "scope": "girl",
            "pdf": 23,
            "printed": 21,
            "trigger": "A recorded direct order from a current superior",
            "actor": "ordered pilot",
            "tiers": {
                "low": "refusal halted",
                "mid": "one of three branches",
                "high": "act immediately without thinking; gain two Heat",
            },
        },
        {
            "play_id": "flirt",
            "scope": "girl",
            "pdf": 23,
            "printed": 21,
            "trigger": "Flirt with another active human Pilot",
            "actor": "pilot",
            "tiers": {
                "low": "weaken Bond; target answer, optional unmark/question",
                "mid": "question and two-party unmark; conditional follow-through",
                "high": "mid plus one of all three printed extra branches",
            },
        },
        {
            "play_id": "receive_orders",
            "scope": "girl",
            "pdf": 22,
            "printed": 20,
            "trigger": "Receive an order from a current superior",
            "actor": "ordered pilot",
            "tiers": {"diceless": "obedient, immediate, qualified compliance, or Disobey"},
        },
        {
            "play_id": "handler_brief",
            "scope": "handler",
            "pdf": 116,
            "printed": 114,
            "trigger": "Another Play calls for a Handler Play",
            "actor": "appointed Handler",
            "tiers": {"diceless": "Handler-authored situation information"},
        },
    ],
    "core_sources": {"heat_identities": 10, "tags": 11, "bonds": 13, "status": 14},
    "known_passives": {
        "Princess": 32,
        "Oldgen": 46,
        "Alpha": 52,
        "Bonded": 58,
        "Prince": 62,
        "CONSUME": 65,
        "Wyvern": 75,
        "Newgirl": 42,
    },
    "unsupported": [
        "other rolled Plays",
        "AI",
        "NPC/Gorgon mechanical targets",
        "missions/off-duty/Strain",
        "unimplemented playbook triggers",
    ],
}


for _entry in REGISTRY["plays"]:
    _entry.update(
        {
            "source_document": "GIRL_FRAME_rulebook.pdf",
            "version": 1,
            "enabled_by_default": False,
            "pre_roll": (
                "Owner confirms trigger, optional Identity and Heat; "
                "acknowledged scene lock required"
            ),
            "post_roll": (
                "Durable participant Tag proposals, one Girl Tag, Status arbitration; no late Heat"
            ),
            "target_policy": "Another active human Pilot in joined scene"
            if _entry["play_id"] == "flirt"
            else "Printed trigger and owned scene context",
            "asset_policy": "Owned undamaged Assets; printed counts and used-Asset damage"
            if _entry["play_id"] == "engage"
            else "No generic Asset bonus",
            "idempotency": (
                "Campaign-scoped authenticated command key, expected "
                "sheet/choice revision, immutable receipt"
            ),
            "response_policy": "Only the designated human owner; no timeout responses",
            "completion": (
                "Required immediate responses, canonical effects and outcome "
                "delivery before lock restoration"
            ),
            "unsupported_policy": (
                "UNSUPPORTED_RULE; no substituted mechanics, AI or NPC/Gorgon targets"
            ),
            "test_module": "tests/test_m2_game.py",
            "test_ids": {
                "keep_your_head": ["test_keep_three_tiers_and_handler_ownership"],
                "check_sensors": ["test_sensors_exact_questions_and_human_answers"],
                "engage": ["test_engage_exact_counts_and_used_asset_damage"],
                "disobey_orders": ["test_disobey_requires_recorded_superior_order_and_low_halts"],
                "flirt": [
                    "test_flirt_all_tiers_full_high_branches_and_target_ownership",
                    "test_nested_escape_play_is_real_roll_then_mutual_followthrough",
                ],
                "receive_orders": ["test_disobey_requires_recorded_superior_order_and_low_halts"],
                "handler_brief": ["test_flirt_all_tiers_full_high_branches_and_target_ownership"],
            }[_entry["play_id"]],
        }
    )


def registry_digest() -> str:
    return hashlib.sha256(json.dumps(REGISTRY, sort_keys=True).encode()).hexdigest()
