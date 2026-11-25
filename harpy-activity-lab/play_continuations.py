"""Activity forms for native Call, Handler Void, and medical decisions."""

import json

import sqlalchemy as sa
from alpha_controls import BRUTALIZE, counter_fields, perform_counter
from alpha_controls import COUNTER as ALPHA_COUNTER
from consume_regrowth import KIND as PARTAKE
from consume_regrowth import regrowth_answer, regrowth_operations
from defeat_play import defeat_choice
from easy_target_controls import BATTLE_ACTION as EASY_BATTLE_ACTION
from easy_target_controls import CHILD_ACTION as EASY_CHILD_ACTION
from easy_target_controls import EASY, advance_battle, battle_origin
from easy_target_controls import SOURCE_KIND as EASY_CHILD
from easy_target_controls import battle_forms as easy_battle_forms
from easy_target_controls import begin_child as begin_easy_child
from easy_target_controls import child_fields as easy_child_fields
from easy_target_controls import needs_child as needs_easy_child
from easy_target_controls import unsupported_work as unsupported_easy_work
from native_scene_forms import (
    CHILD_STARTS,
    CONSUME_CHILD_PLAYS,
    CONSUME_CHILDREN,
    DOCTOR_CHOICES,
    DOCTOR_PLAYS,
    ENFORCEMENT,
    NATIVE_TITLES,
    PANDORA,
    PANDORA_CHILD,
    RISK_CHOICE,
    TAG_DECISIONS,
    child_operations,
    child_proposal,
    form_fields,
    is_native_child_choice,
    mounted_roll,
    native_choice_answer,
    native_choice_fields,
    risk_choice_answer,
    risk_choice_card,
    tag_choice_card,
)
from native_scene_forms import choice_supported as native_choice_supported
from replacement_forms import ReplacementForms
from snoop_play import CHOICES as SNOOP_CHOICES
from snoop_play import snoop_answer, snoop_form
from specialist_effects import CHOICES as SPECIALIST_CHOICES
from specialist_effects import SAVED as SPECIALIST_SAVED
from specialist_effects import SOURCE_PLAYS, copy_fields
from specialist_effects import (
    choice_answer as specialist_answer,
)
from specialist_effects import (
    choice_fields as specialist_fields,
)
from wyvern_controls import ESCAPE as WYVERN_ESCAPE
from wyvern_controls import ESCAPE_ACTION as WYVERN_ESCAPE_ACTION
from wyvern_controls import escape_fields, start_escape

from girlframe.database import tables
from girlframe.discord_adapter.m3_dive import LABELS, MANIFESTATIONS
from girlframe.engine import m3_changeling, m3_red_queen
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_medical import Care, Exchange
from girlframe.services.m2_state import load_state
from girlframe.services.m3_battle_director import DirectorService
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.m3_handler_consequences import HandlerConsequenceService
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_mockingbird_communion import CallService
from girlframe.services.m3_red_queen import RedQueenService
from girlframe.services.m3_supply_drop import SupplyDropService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService

ACTIONS = frozenset(
    {
        "dive_call",
        "handler_void",
        "defeat_medical",
        "frame_replacement",
        "supply_expiry",
        "snoop_decision",
        "consume_partake",
        "specialist_choice",
        "native_scene_choice",
        "native_choice_review",
        "native_body_consequence",
        "consume_child_play",
        "pandora_child",
        "native_scene_roll",
        "alpha_counter",
        EASY_CHILD_ACTION,
        EASY_BATTLE_ACTION,
        WYVERN_ESCAPE_ACTION,
        *SPECIALIST_SAVED,
    }
)
YES_NO = (("yes", "Yes"), ("no", "No"))
BODY_CONSEQUENCES = {
    "enforcer_handler_consequence": ("consequence", "Handler"),
    "enforcer_director_consequence": ("work_id", "Director"),
}


def choice_review_source(play, kind):
    return (
        play in DOCTOR_PLAYS
        and kind in DOCTOR_CHOICES
        or play == EASY
        and kind.partition(":")[0] in (EASY_CHILD, "easy_target_validate")
    )


def choice_review_reason(decision):
    if decision.get("doctor"):
        return decision["doctor"].get("unsupported")
    return unsupported_easy_work(decision.get("detail") or decision["easy_target"])


def field(key, label, options=None, *, required=True, multiple=False):
    return {
        "key": key,
        "label": label,
        "options": options,
        "required": required,
        "multiple": multiple,
    }


def options(rows, label="label", key="id"):
    return [(str(row[key]), row[label]) for row in rows]


ACCOUNT = field("account", "Your account")


def operation(identity, label, fields):
    return {"id": identity, "label": label, "fields": fields}


def call_operations(data):
    phase = data["phase"]
    if phase == "invite":
        label = "Reply" if data["kind"] == "relay" else "Accept boarding"
        return [
            operation("accept", label, [ACCOUNT]),
            operation("decline", "Decline", [ACCOUNT]),
        ]
    if phase == "table":
        answer = (
            [field("accepted", "Accept this proposal?", YES_NO), ACCOUNT]
            if data["option"] == "table_replaces_identity"
            else [ACCOUNT]
        )
        return [operation("table", "File your table response", answer)]
    if phase == "npc":
        return [
            operation(
                "npc",
                "File nearby changes",
                [
                    *(
                        field("npc_" + npc["id"], npc["label"], MANIFESTATIONS)
                        for npc in data["npcs"]
                    ),
                    ACCOUNT,
                ],
            )
        ]
    result = [operation("decline_effect", "Stay aboard without an extra Dive choice", [ACCOUNT])]
    if phase != "effect":
        return []
    for effect in data["options"]:
        fields = [ACCOUNT]
        if effect == "void_and_unmark_all":
            fields.extend(
                [
                    field("asset", "Uncorrupted Asset", options(data["assets"])),
                    field("description", "Void alteration"),
                ]
            )
            if data.get("storage_available"):
                fields.append(field("storage", "Store newly gained Void?", YES_NO))
        elif effect in ("erase_identity_and_table_question", "table_replaces_identity"):
            fields.extend(
                [
                    field(
                        "identity",
                        "Original unprotected Identity",
                        options(data["identities"]),
                    ),
                    field(
                        "question" if effect.startswith("erase") else "replacement",
                        "Question for the table" if effect.startswith("erase") else "New Identity",
                    ),
                ]
            )
        result.append(operation(effect, LABELS[effect], fields))
    return result


def handler_void_operations(data):
    phase = data["episode"]["phase"]
    if phase == "surgery":
        confirmation = (("yes", "Confirmed"),)
        return [
            operation(
                "record_surgery",
                "Record performed surgery",
                [
                    field("account", "Actual personnel, procedure and removal"),
                    field("performed", "Procedure was performed", confirmation),
                    field("removed", "Source corruption was removed", confirmation),
                ],
            )
        ]
    operations = [
        operation(
            "knife",
            "Cut out the corruption",
            [field("site", "Actual body site"), ACCOUNT],
        ),
        operation("surgery", "Request immediate surgery", [ACCOUNT]),
    ]
    if phase == "choice":
        operations.insert(
            1,
            operation(
                "drugs",
                "Halt spread with drugs",
                [
                    field("site", "Actual body site"),
                    field("manifestation", "Localized manifestation", MANIFESTATIONS),
                    ACCOUNT,
                ],
            ),
        )
    return operations


def medical_operations(data):
    if data["can_propose"]:
        return [
            operation(
                "propose",
                "Save actual care and waking",
                [
                    field("account", "Describe actual care and waking"),
                    field("vitals", "Treatment restores inactive vital signs?", YES_NO),
                ],
            )
        ]
    if data["can_confirm"]:
        return [
            operation(
                "confirm",
                "Review medical facts",
                [
                    field("accepted", "Confirm this care and waking?", YES_NO),
                    field("evidence", "Actual medical evidence"),
                ],
            )
        ]
    choices = data.get("choices")
    if data["can_exchange"] and choices and choices["removed"] and choices["acquired"]:
        return [
            operation(
                "exchange",
                "Save Girl Play exchange",
                [
                    field(
                        "removed",
                        "Give up this Play",
                        options(choices["removed"], "name"),
                    ),
                    field(
                        "acquired",
                        "Acquire this Play",
                        [
                            (item["id"], f"{item['playbook']}: {item['name']}")
                            for item in choices["acquired"]
                        ],
                    ),
                ],
            )
        ]
    return []


class PlayContinuations:
    def __init__(self, game):
        self.game = game
        self.call = CallService(game)
        self.handler_void = HandlerVoidService(game.store, game)
        self.medical = MedicalService(game.store)
        self.replacement = ReplacementForms(game)
        self.supply = SupplyDropService(game.store)
        self.changeling = ChangelingService(game)
        self.queen = RedQueenService(game)
        self.handler_body = HandlerConsequenceService(game.store)
        self.director_body = DirectorService(game.store)

    @staticmethod
    def card(data, action, title, operations, account=None):
        return {
            "id": data["id"],
            "revision": data["revision"],
            "action": action,
            "instruction": title,
            "scene": account,
            "operations": operations,
            **({"game_revision": data["game_revision"]} if "game_revision" in data else {}),
        }

    def view(self, viewer):
        with self.game.store.engine.connect() as c:
            calls = self.call._tasks(c, viewer)
            handler_void = self.handler_void._tasks(c, viewer)
            deliveries = self.supply._tasks(c, viewer)
            state = load_state(c, self.game.store.campaign_id)
            actions = tables.m2["m2_actions"]
            ready = []
            for identity in c.scalars(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.game.store.campaign_id,
                    actions.c.actor_id == str(viewer.user_id),
                    actions.c.state == "ready_to_roll",
                )
            ):
                action = self.game.action(c, identity)
                if mounted_roll(self.game, c, action):
                    ready.append(action)
        cards = [
            self.card(
                row,
                "native_scene_roll",
                "Roll "
                + NATIVE_TITLES.get(row["data"]["play"], row["data"]["play"].replace("_", " ")),
                [operation("roll", "Confirm the original roll", [])],
            )
            for row in ready
        ]
        for source, step, title, fields, account in easy_battle_forms(self.game, viewer):
            cards.append(
                self.card(
                    source,
                    EASY_BATTLE_ACTION,
                    title,
                    [operation(step, title, form_fields(fields))] if step else [],
                    account,
                )
            )
        for task in calls:
            if not task["actionable"]:
                continue
            data = self.call.get(viewer, task["id"])
            if data["phase"] == "table":
                effect = data["effect"]
                account = effect.get("question") or effect.get("replacement")
            else:
                account = data["message"] if data["kind"] == "relay" else data["account"]
            cards.append(
                self.card(
                    data,
                    "dive_call",
                    "Dive Deep · Call",
                    call_operations(data),
                    account,
                )
            )
        for task in handler_void:
            if not task["can_act"]:
                continue
            data = self.handler_void.get(viewer, task["id"])
            cards.append(
                self.card(data, "handler_void", task["label"], handler_void_operations(data))
            )
        for task in self.medical.tasks(viewer):
            data = self.medical.get(viewer, task["id"])
            if operations := medical_operations(data):
                cards.append(
                    self.card(
                        data,
                        "defeat_medical",
                        "Defeat · medical recovery",
                        operations,
                        (data["care"] or {}).get("account"),
                    )
                )
        for data, operations, summary in self.replacement.view(viewer, field, operation, YES_NO):
            cards.append(
                self.card(
                    data,
                    "frame_replacement",
                    "Frame replacement · " + data["callsign"],
                    operations,
                    summary,
                )
            )
        for task in deliveries:
            if task["phase"] != "expired":
                continue
            try:
                data = self.supply.view_delivery(viewer, task["id"])
            except WorkflowError:
                continue
            cards.append(
                self.card(
                    data,
                    "supply_expiry",
                    "Supply Drop · Review last Asset loss",
                    [
                        operation(
                            "review",
                            "File the loss context",
                            [
                                field("battle", "Was this an actual battle?", YES_NO),
                                ACCOUNT,
                            ],
                        )
                    ],
                    data["name"],
                )
                | {"mission_work": task["work_id"]}
            )
        for choice in self.game.choices(viewer):
            with self.game.store.engine.connect() as c:
                original = self.game.action(c, choice["action_id"])
                mounted = is_native_child_choice(self.game, c, original, choice["kind"])
            if choice_review_source(original["data"]["play"], choice["kind"]):
                try:
                    decision = self.game.decision(viewer, choice["id"])
                    gap = choice_review_reason(decision)
                except (ValueError, WorkflowError):
                    continue
                if gap:
                    cards.append(
                        self.card(
                            choice | {"revision": state.revision},
                            "native_choice_review",
                            "Original Play · Facilitator review",
                            [operation(choice["kind"], "File and share with the facilitator", [])],
                            gap,
                        )
                    )
                    continue
            if choice["kind"] == WYVERN_ESCAPE and original["data"]["play"] == "wyvern_explore":
                try:
                    self.game.decision(viewer, choice["id"])
                    revision, fields = escape_fields(self.game, viewer)
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice | {"revision": revision},
                        WYVERN_ESCAPE_ACTION,
                        "Wyvern · Escape",
                        [
                            operation(
                                WYVERN_ESCAPE, "Start the actual escape Play", form_fields(fields)
                            )
                        ],
                    )
                )
                continue
            if choice["kind"].partition(":")[0] == EASY_CHILD and original["data"]["play"] == EASY:
                try:
                    decision = self.game.decision(viewer, choice["id"])
                    detail = decision.get("detail") or decision["easy_target"]
                    if needs_easy_child(detail):
                        staged = easy_child_fields(self.game, viewer, detail, choice)
                        if staged:
                            revision, title, fields = staged
                            cards.append(
                                self.card(
                                    choice | {"revision": revision},
                                    EASY_CHILD_ACTION,
                                    "Easy Target · " + title,
                                    [operation(choice["kind"], title, form_fields(fields))]
                                    if fields
                                    else [],
                                    detail["work"]["context"],
                                )
                            )
                        continue
                except (ValueError, WorkflowError):
                    continue
            if choice["kind"] == ALPHA_COUNTER and original["data"]["play"] == BRUTALIZE:
                try:
                    decision = self.game.decision(viewer, choice["id"])
                    revision, specs = counter_fields(self.game, viewer, decision)
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice | {"revision": revision},
                        "alpha_counter",
                        "Brutalize · Your original counter",
                        [operation(ALPHA_COUNTER, "File your counter", form_fields(specs))],
                    )
                )
                continue
            if choice["kind"] == PANDORA_CHILD and original["data"]["play"] == PANDORA:
                try:
                    detail = self.game.decision(viewer, choice["id"])["janus"]
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice,
                        "pandora_child",
                        "PANDORA · File the actual child",
                        child_operations(detail),
                        detail["behavior"],
                    )
                )
                continue
            if choice["kind"] in CONSUME_CHILDREN:
                try:
                    self.game.decision(viewer, choice["id"])
                    sheet = self.game.sheet(viewer)
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice | {"revision": sheet["revision"]},
                        "consume_child_play",
                        "CONSUME · Perform the assigned follow-up",
                        [
                            operation(
                                choice["kind"],
                                "Start original follow-up",
                                [
                                    field(
                                        "play",
                                        "Choose how to perform the follow-up",
                                        list(CONSUME_CHILD_PLAYS.items()),
                                    ),
                                    field(
                                        "heat",
                                        "Heat to spend",
                                        [(str(n), str(n)) for n in range(sheet["heat"] + 1)],
                                    ),
                                    field(
                                        "context",
                                        "Describe the action that fulfills the original trigger",
                                    )
                                    | {"paragraph": True},
                                ],
                            )
                        ],
                    )
                )
                continue
            if original["data"]["play"] == ENFORCEMENT and choice["kind"] in BODY_CONSEQUENCES:
                kind = choice["kind"]
                source_key, title = BODY_CONSEQUENCES[kind]
                try:
                    source = self.game.decision(viewer, choice["id"])["enforcement"][source_key]
                    service = self.handler_body if title == "Handler" else self.director_body
                    detail = service.get(viewer, source)
                except (ValueError, WorkflowError):
                    continue
                if detail["state"] == "resolved" or title == "Handler" and not detail["can_act"]:
                    continue
                fields = [
                    field(
                        "choice",
                        "Your consequence",
                        (
                            ("opportunity", "Offer an opportunity"),
                            ("chance_to_act", "Offer a chance to act"),
                            ("weakness", "Show a weakness"),
                            ("injury", "Suffer an injury and survive"),
                            ("death", f"This {title} dies"),
                        ),
                    ),
                    ACCOUNT | {"paragraph": True},
                ]
                if title == "Handler":
                    fields.append(
                        field(
                            "confirmation", "For death only, type END THIS HANDLER", required=False
                        )
                    )
                cards.append(
                    self.card(
                        choice | {"revision": detail.get("game_revision", detail.get("revision"))},
                        "native_body_consequence",
                        title + " · Assigned body consequence",
                        [operation(kind, "File the body consequence", fields)],
                    )
                )
                continue
            if mounted and choice["kind"] in CHILD_STARTS:
                _, title = CHILD_STARTS[choice["kind"]]
                try:
                    self.game.decision(viewer, choice["id"])
                    revision = self.game.sheet(viewer)["revision"]
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice | {"revision": revision},
                        "native_scene_choice",
                        title,
                        [
                            operation(
                                choice["kind"],
                                "Start the assigned Play",
                                [
                                    field("context", "Describe the actual response")
                                    | {"paragraph": True}
                                ],
                            )
                        ],
                    )
                )
                continue
            if choice["kind"] == RISK_CHOICE and (
                mounted or original["data"]["play"] in NATIVE_TITLES.keys() | SOURCE_PLAYS
            ):
                try:
                    view = risk_choice_card(self.game.decision(viewer, choice["id"]))
                except (ValueError, WorkflowError):
                    continue
                cards.append(
                    self.card(
                        choice,
                        "specialist_choice",
                        "Risk Factor",
                        view["risk_operations"],
                        view["prompt"],
                    )
                )
                continue
            if native_choice_supported(original["data"]["play"], choice["kind"]) or mounted:
                try:
                    decision = self.game.decision(viewer, choice["id"])
                    fields = native_choice_fields(decision)
                except (ValueError, WorkflowError):
                    continue
                receipt = original["data"].get("receipt")
                roll = (
                    " + ".join(str(value) for value in receipt.get("faces", ())) if receipt else ""
                )
                card = self.card(
                    choice,
                    "native_scene_choice",
                    NATIVE_TITLES.get(
                        original["data"]["play"],
                        CONSUME_CHILD_PLAYS.get(original["data"]["play"], "Play"),
                    )
                    + " · Assigned decision",
                    [operation(choice["kind"], "File your response", fields)],
                    f"Original roll · {roll}" if roll else None,
                )
                if choice["kind"] in ("am_code_records_question", "am_code_records_answer"):
                    record = decision["am_code"]["records"]
                    card["instruction_details"] = [
                        value
                        for value in (
                            record["subject"],
                            record["reference"],
                            record["document"],
                            record["question"],
                        )
                        if value
                    ]
                if choice["kind"] == "vat_doll_information":
                    card["instruction_details"] = [
                        decision["detail"]["question"]
                        or "No question filed. Offer an actual secret."
                    ]
                if choice["kind"] == "defeat_accept_alternative":
                    offer = defeat_choice(decision)["offer"]
                    card["instruction_details"] = [
                        offer["account"],
                        f"Permissions removed · {offer['permissions']}",
                        *(f"Asset · {value}" for value in offer["assets"]),
                        *(f"Identity · {value}" for value in offer["identities"]),
                        *(
                            f"{label} · {offer[key]}"
                            for label, key in (("Tag", "tag"), ("Foe", "foe"))
                            if offer[key]
                        ),
                    ]
                cards.append(card)
                continue
            if choice["kind"] in TAG_DECISIONS and original["data"]["play"] in SOURCE_PLAYS:
                kind = choice["kind"]
                try:
                    projected = tag_choice_card(self.game.decision(viewer, choice["id"]))
                except (ValueError, WorkflowError):
                    continue
                label = (
                    "Pass Tag window"
                    if kind == "tag_window" and not projected["schema"]
                    else "File Tag decision"
                )
                cards.append(
                    self.card(
                        choice,
                        "specialist_choice",
                        label,
                        [operation(kind, label, projected["schema"])],
                        projected.get("prompt"),
                    )
                )
            if choice["kind"] in SPECIALIST_CHOICES:
                kind = choice["kind"]
                data = self.game.decision(viewer, choice["id"])["detail"]
                if kind == "changeling_recent":
                    session = m3_changeling.session(state, choice["action_id"])
                    if session.speech:
                        speech = m3_changeling.record(state, m3_changeling.Speech, session.speech)
                        data["anchors"] = [
                            (speech.event, "Original defining statement"),
                            (session.event, "Original roll result"),
                        ]
                fields = specialist_fields(kind, data, field, ACCOUNT, YES_NO)
                description = (
                    f"Fill {data['minimum']}–{data['maximum']} of the facet fields."
                    if kind.startswith("changeling_clay_")
                    else None
                )
                cards.append(
                    self.card(
                        choice,
                        "specialist_choice",
                        SPECIALIST_CHOICES[kind],
                        [operation(kind, "File your response", fields)],
                        description,
                    )
                )
            if choice["kind"] == PARTAKE:
                data = self.game.decision(viewer, choice["id"])["detail"]
                cards.append(
                    self.card(
                        choice,
                        PARTAKE,
                        "CONSUME · Let Us Partake",
                        regrowth_operations(data, field, operation, ACCOUNT),
                        f"Available Frame capacity: {data['regrow_free']}. "
                        "Pair a replacement with a missing component if capacity requires it.",
                    )
                )
            if choice["kind"] in SNOOP_CHOICES:
                details = self.game.decision(viewer, choice["id"])
                label, fields = snoop_form(details, field, options, YES_NO)
                cards.append(
                    self.card(
                        choice,
                        "snoop_decision",
                        "Snoop · " + label,
                        [operation(choice["kind"], "File your response", fields)],
                    )
                )
        return cards + self.identity_records(viewer, state)

    def identity_records(self, viewer, state):
        cards = []
        for blank in m3_changeling.records(state, m3_changeling.BlankSlate):
            current = state.sheets.get(blank.actor.entity)
            if (
                blank.actor.entity != str(viewer.user_id)
                or blank.replaced_event
                or current is None
                or current.character_id != blank.actor.incarnation
            ):
                continue
            data = self.changeling.view(viewer, blank.id)
            if fields := copy_fields(data, field):
                cards.append(
                    self.card(
                        data,
                        "changeling_copy",
                        "Blank Slate · Adopt a disclosed Identity",
                        [operation("copy", "Adopt Identity", fields)],
                    )
                )
        for extraction in m3_red_queen.records(state, m3_red_queen.Extraction):
            if not extraction.low or extraction.restored_event:
                continue
            if extraction.target.kind == "pilot":
                current = state.sheets.get(extraction.target.entity)
                if current is None or current.character_id != extraction.target.incarnation:
                    continue
            try:
                data = self.queen.view(viewer, extraction.id)
            except (ValueError, WorkflowError):
                continue
            if not data["can_restore"]:
                continue
            options = self.queen.restoration_options(viewer, extraction.id)
            if options["options"]:
                fields = [
                    field(
                        "association",
                        "New associated Identity or Tag",
                        [(json.dumps(x), x["label"]) for x in options["options"]],
                    ),
                    field("am", "Optional Court AM", options["ams"], required=False),
                    ACCOUNT,
                ]
                cards.append(
                    self.card(
                        data | {"revision": options["revision"]},
                        "red_queen_restore",
                        "Red Queen · Restore memory",
                        [operation("restore", "Restore memory", fields)],
                        f"{extraction.category.title()} · {extraction.scope}",
                    )
                )
        return cards

    @staticmethod
    def origin(identity, action, state, work):
        if action == EASY_BATTLE_ACTION:
            return battle_origin(state, identity)
        if action in SPECIALIST_SAVED:
            records = (
                m3_changeling.records(state, m3_changeling.BlankSlate)
                if action == "changeling_copy"
                else m3_red_queen.records(state, m3_red_queen.Extraction)
            )
            return next((item.session for item in records if item.id == identity), None)
        if action == "dive_call":
            return next(
                (item.source_action for item in state.mockingbird.calls if item.id == identity),
                None,
            )
        visited = set()
        while identity in work and identity not in visited:
            visited.add(identity)
            body = json.loads(work[identity]["body_json"])
            if body.get("source_action"):
                return body["source_action"]
            identity = body.get("root_id") or body.get("source_work")
        return None

    def perform(self, viewer, key, request):
        identity, revision, action, answer = (
            request[k] for k in ("id", "revision", "action", "answer")
        )
        op, values = answer["operation"], answer["values"]
        if action == EASY_BATTLE_ACTION:
            return advance_battle(self.game, viewer, key, identity, revision, op, values)
        if action == "native_scene_roll" and op == "roll" and not values:
            with self.game.store.engine.connect() as c:
                original = self.game.action(c, identity)
                mounted = mounted_roll(self.game, c, original)
            if mounted:
                return self.game.roll(viewer, key, identity)
            raise WorkflowError("Open the original scene Play before rolling.")
        if action in (
            "snoop_decision",
            PARTAKE,
            "specialist_choice",
            "native_scene_choice",
            "native_body_consequence",
            "consume_child_play",
            "pandora_child",
            "alpha_counter",
            EASY_CHILD_ACTION,
            WYVERN_ESCAPE_ACTION,
            "native_choice_review",
        ):
            table = tables.m2["m2_choices"]
            with self.game.store.engine.connect() as c:
                row = c.execute(
                    sa.select(
                        table.c.kind, table.c.action_id, table.c.body_json, table.c.actor_id
                    ).where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.id == identity,
                    )
                ).first()
                kind = row.kind if row else None
                original = self.game.action(c, row.action_id) if row else None
                source_play = original["data"]["play"] if original else ""
                mounted = original and is_native_child_choice(self.game, c, original, kind)
            if action == PARTAKE and kind == PARTAKE:
                response = regrowth_answer(op, values)
            elif action == "snoop_decision" and kind in SNOOP_CHOICES and kind == op:
                response = snoop_answer(op, values)
            elif (
                action == "native_scene_choice"
                and kind == op
                and (native_choice_supported(source_play, kind) or mounted)
            ):
                if kind in CHILD_STARTS:
                    if values.keys() != {"context"} or row.actor_id != str(viewer.user_id):
                        raise WorkflowError("Only the assigned player can start this response.")
                    return self.game.begin(
                        viewer,
                        key,
                        int(original["channel_id"]),
                        revision,
                        PlayInput(
                            play=CHILD_STARTS[kind][0],
                            context=values["context"],
                            trigger_confirmed=True,
                            parent=original["id"],
                            heat=0,
                            piloting=kind == "beneath_defeat"
                            and original["data"]["prepared"]["piloting"],
                        ),
                    )
                response = native_choice_answer(kind, values, source=json.loads(row.body_json))
            elif (
                action == "native_choice_review"
                and kind == op
                and choice_review_source(source_play, kind)
                and not values
            ):
                decision = self.game.decision(viewer, identity)
                gap = choice_review_reason(decision)
                if not gap:
                    raise WorkflowError(
                        "The native response is available. Reopen its original choice."
                    )
                result = FacilitatorService(self.game).request(
                    viewer,
                    key,
                    int(original["channel_id"]),
                    "action",
                    original["id"],
                    "choice:" + kind,
                    revision,
                    gap,
                    shared=True,
                )
                return result | {"review_id": result["id"]}
            elif (
                action == EASY_CHILD_ACTION
                and kind == op
                and kind.partition(":")[0] == EASY_CHILD
                and source_play == EASY
            ):
                return begin_easy_child(
                    self.game,
                    viewer,
                    key,
                    original,
                    revision,
                    json.loads(row.body_json)["work"],
                    values,
                )
            elif (
                action == WYVERN_ESCAPE_ACTION
                and kind == op == WYVERN_ESCAPE
                and source_play == "wyvern_explore"
            ):
                return start_escape(self.game, viewer, key, original, revision, values)
            elif action == "consume_child_play" and kind == op and kind in CONSUME_CHILDREN:
                if (
                    values.keys() != {"play", "heat", "context"}
                    or values["play"] not in CONSUME_CHILD_PLAYS
                ):
                    raise ValueError(
                        "Choose the supported Play for this original CONSUME follow-up."
                    )
                return self.game.begin(
                    viewer,
                    key,
                    int(original["channel_id"]),
                    revision,
                    PlayInput(
                        play=values["play"],
                        trigger_confirmed=True,
                        heat=int(values["heat"]),
                        context=values["context"],
                        parent=row.action_id,
                        source_work=json.loads(row.body_json)["source_work"],
                    ),
                )
            elif (
                action == "pandora_child"
                and kind == PANDORA_CHILD
                and source_play == PANDORA
                and op.startswith(kind + ":")
            ):
                response = child_proposal(op.split(":", 1)[1], values)
            elif (
                action == "alpha_counter"
                and kind == op == ALPHA_COUNTER
                and source_play == BRUTALIZE
            ):
                return perform_counter(self.game, viewer, key, original, identity, revision, values)
            elif (
                action == "native_body_consequence"
                and source_play == ENFORCEMENT
                and kind in BODY_CONSEQUENCES
                and kind == op
            ):
                body = json.loads(row.body_json)
                if kind == "enforcer_handler_consequence":
                    if (
                        values["choice"] == "death"
                        and values.get("confirmation") != "END THIS HANDLER"
                    ):
                        raise ValueError("Type END THIS HANDLER to confirm that consequence.")
                    return self.handler_body.respond(
                        viewer,
                        key,
                        body["consequence"],
                        revision,
                        values["choice"],
                        values["account"],
                    )
                return self.director_body.respond(
                    viewer, key, body["work_id"], revision, values["choice"], values["account"]
                )
            elif (
                action == "specialist_choice"
                and kind == RISK_CHOICE
                and (mounted or source_play in NATIVE_TITLES.keys() | SOURCE_PLAYS)
            ):
                response = risk_choice_answer(op, values)
            elif action == "specialist_choice" and kind in SPECIALIST_CHOICES and kind == op:
                response = specialist_answer(kind, values)
            elif (
                action == "specialist_choice"
                and kind == op
                and kind in TAG_DECISIONS
                and source_play in SOURCE_PLAYS
            ):
                response = (
                    ChoiceAnswer(options=("pass",))
                    if kind == "tag_window" and not values
                    else native_choice_answer(kind, values)
                )
            else:
                raise WorkflowError("Open your original assigned Frame response.")
            return self.game.respond(viewer, key, identity, revision, response)
        if action == "changeling_copy" and op == "copy":
            selected = json.loads(values["copy"])
            return self.changeling.copy_blank(
                viewer,
                key,
                revision,
                identity,
                ActorRef.model_validate(selected["other"]),
                selected["identity"],
                (values["first"], values["second"]),
            )
        if action == "red_queen_restore" and op == "restore":
            selected = json.loads(values["association"])
            return self.queen.restore_memory(
                viewer,
                key,
                revision,
                identity,
                selected["event"],
                selected["source"],
                values.get("am"),
                values["account"],
            )
        if action == "frame_replacement":
            return self.replacement.perform(
                viewer, key, identity, revision, request["game_revision"], op, values
            )
        if action == "supply_expiry" and op == "review" and values.get("battle") in ("yes", "no"):
            return self.supply.review_expiry(
                viewer,
                key,
                identity,
                revision,
                values["battle"] == "yes",
                values["account"],
            )
        if action == "dive_call":
            if op == "table":
                values = {
                    "account": values["account"],
                    "accepted": values.get("accepted", "yes") == "yes",
                }
            elif op == "npc":
                values = {
                    "account": values["account"],
                    "manifestations": {
                        key.removeprefix("npc_"): value
                        for key, value in values.items()
                        if key.startswith("npc_")
                    },
                }
            elif op in LABELS:
                values = values | {"option": op}
                if "storage" in values:
                    values["storage"] = values["storage"] == "yes"
                op = "effect"
            return self.call.respond(viewer, key, identity, revision, op, values)
        if action == "handler_void":
            if op == "record_surgery":
                return self.handler_void.record_surgery(
                    viewer,
                    key,
                    identity,
                    revision,
                    values["account"],
                    performed=values["performed"] == "yes",
                    removed=values["removed"] == "yes",
                )
            return self.handler_void.choose(
                viewer,
                key,
                identity,
                revision,
                op,
                values["account"],
                site=values.get("site", ""),
                manifestation=values.get("manifestation"),
            )
        if op == "propose":
            return self.medical.propose(
                viewer,
                key,
                identity,
                revision,
                Care(account=values["account"], restore_vitals=values["vitals"] == "yes"),
            )
        if op == "confirm":
            return self.medical.confirm(
                viewer,
                key,
                identity,
                revision,
                request["game_revision"],
                values["accepted"] == "yes",
                values["evidence"],
            )
        if op == "exchange":
            return self.medical.exchange(
                viewer,
                key,
                identity,
                revision,
                request["game_revision"],
                Exchange.model_validate(values),
            )
        raise WorkflowError("Reopen your assigned decision.")
