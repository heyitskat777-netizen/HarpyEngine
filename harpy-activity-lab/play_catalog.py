"""Project HarpyEngine's Play inventory using a character's actual sheet."""

from girlframe.engine.creation import official_frame
from girlframe.engine.m2_registry import REGISTRY
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_enforcer_requisitions import BASE, RULES, held
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_plays import (
    ASSET_IDS,
    FIXED_IDS,
    HEAT_IDS,
    JANUS_ROLL_IDS,
    ROLL_IDS,
)
from girlframe.engine.playbooks import GIRL_TYPES

BASIC = {play["play_id"]: play for play in REGISTRY["plays"]}
RECEIVE_ORDERS = "receive_orders"
DISOBEY_ORDERS = "disobey_orders"
ORDER_PLAYS = frozenset({RECEIVE_ORDERS, DISOBEY_ORDERS})
BOOK_BY_SLUG = {name.lower().replace(" ", "-"): name for name in GIRL_TYPES}
TITLES = {
    "engage": "Engage",
    "all_out_assault": "All-Out Assault",
    "go_for_the_core": "Go for the Core",
}
PLAY_CATEGORIES = {
    "talk": (
        "flirt",
        "flirt_followthrough",
        "receive_orders",
        "disobey_orders",
        "put_someone_beneath_you",
        "mockingbird_person",
        "bonded_side",
        "old_dog_new_pups",
        "unassuming_doll",
        "prince_performer",
    ),
    "fight": (
        "engage",
        "all_out_assault",
        "go_for_the_core",
        "defeat",
        "brutalize",
        "easy_target",
        "consume_feral",
        "enforcement_initiative",
        "wyvern_wraith",
        "wyvern_protector",
    ),
    "scan": (
        "check_sensors",
        "dive_deep",
        "am_scrutinized",
        "snoop",
        "wyvern_explore",
        "red_queen_consult",
        "red_queen_panopticon",
        "red_queen_memory",
        "ankou_processor",
    ),
    "recover": (
        "keep_your_head",
        "go_off_duty",
        "void_observation",
        "reject_tag",
        "dose_up",
        "am_just_code",
        "consume_eat",
        "living_battery",
        "pandora_birth",
        "nanobot_injection",
        "doctor_support",
        "wyvern_rouse",
        "changeling_blank_slate",
        "changeling_body_of_clay",
    ),
}
CATEGORY_BY_ID = {
    identity: category
    for category, identities in PLAY_CATEGORIES.items()
    for identity in identities
}
NATIVE_PLAYS = frozenset((*ASSET_IDS, *FIXED_IDS, *HEAT_IDS, *JANUS_ROLL_IDS, *ROLL_IDS))
# Older registry entries use printed headings for these registered operations.
LEGACY_IDS = {
    "girl.mockingbird.bad-at-being-a-person": "mockingbird_person",
    "girl.am.scrutinized": "am_scrutinized",
    "girl.am.just-code": "am_just_code",
    "frame.doctordoctor.here-for-support": "doctor_support",
    "frame.janus.pandora": "pandora_birth",
}


def play_category(identity):
    return CATEGORY_BY_ID.get(identity, "other")


def character_plays(registry, sheet, *, owns_sheet, state, include_unimplemented=False):
    """List public book Plays, plus private gained or lost Plays for the owner."""
    girl, frame = sheet.girl, official_frame(sheet.frame)
    acquired = set()
    if owns_sheet and not sheet.frame_scrapped:
        if sheet.frame_runtime:
            acquired.update(sheet.frame_runtime.acquired_rules)
        # The engine can attach a graft to the original Frame before it has a runtime.
        # Its payment/custody record also detects suspensions and Frame changes.
        acquired.difference_update((*BASE, *RULES))
        if sheet.character_id:
            actor = ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id)
            for rule_id in (*BASE, *RULES):
                try:
                    if held(state, actor, rule_id):
                        acquired.add(rule_id)
                except ValueError:
                    continue
    blocked = {item.play for item in sheet.blocked_plays} if owns_sheet else set()
    entries = []
    for rule in registry.entries:
        # These rules can be contextual effects. They are never manual Play starters.
        if rule.id.endswith(".sex-play"):
            continue
        if rule.module not in registry.enabled_modules or (
            rule.implementation == "unimplemented" and not include_unimplemented
        ):
            continue
        slug = rule.id.rsplit(".", 1)[-1].replace("-", "_")
        native_id = (
            rule.m2_play_id or LEGACY_IDS.get(rule.id) or (slug if slug in NATIVE_PLAYS else None)
        )
        if rule.scope == "basic" and rule.kind == "play":
            native_id = native_id or rule.id.rsplit(".", 1)[-1]
        elif rule.scope == "girl" and rule.kind != "playbook":
            book = BOOK_BY_SLUG.get(rule.id.split(".")[1])
            if not book or not (has_rule(sheet, rule.id, book) if owns_sheet else girl == book):
                continue
        elif rule.scope == "frame" and rule.kind != "playbook":
            if sheet.frame_scrapped or (
                rule.id not in acquired
                and (rule.frame_playbook != frame or rule.frame_rule == "requisition")
            ):
                continue
        else:
            continue
        if native_id is None and not (
            rule.kind == "play" or rule.contract and rule.contract.roll_kind in ("2d6", "d6")
        ):
            continue
        identity = native_id or rule.id
        if identity in ORDER_PLAYS:
            continue
        trigger = BASIC.get(identity, {}).get("trigger") or (
            rule.contract.trigger if rule.contract else ""
        )
        entries.append(
            {
                "id": identity,
                "rule_id": rule.id,
                "label": TITLES.get(identity, rule.title),
                "group": rule.scope,
                "category": play_category(identity),
                "trigger": trigger,
                "blocked": identity in blocked or rule.id in blocked,
            }
        )
    return list({item["id"]: item for item in entries}.values())


def frame_upgrades(registry, runtime):
    if not runtime:
        return []
    rules = {entry.id: entry for entry in registry.entries}
    upgrades = []
    for identity in runtime["acquired_rules"]:
        entry = rules.get(identity)
        upgrades.append(
            {
                "id": identity,
                "name": entry.title if entry else identity,
                "description": entry.contract.trigger if entry and entry.contract else "",
            }
        )
    return upgrades
