"""Project and interpret native Play forms for the Activity scene popup."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m2_ui import answer_values, choice_fields
from girlframe.discord_adapter.m3_battle import battle_answer, battle_fields
from girlframe.discord_adapter.m3_bonded import _answer as bonded_answer
from girlframe.discord_adapter.m3_bonded import _choice_fields as bonded_fields
from girlframe.discord_adapter.m3_doctor import (
    doctor_choice_answer,
    doctor_choice_fields,
)
from girlframe.discord_adapter.m3_easy_target import easy_target_choice_answer
from girlframe.discord_adapter.m3_enforcement_initiative import (
    initiative_answer,
    initiative_choice_fields,
)
from girlframe.discord_adapter.m3_engage import engage_answer, engage_fields
from girlframe.discord_adapter.m3_prince import (
    performance_choice_answer,
    performance_choice_fields,
)
from girlframe.discord_adapter.m3_vatgrown import doll_choice_fields
from girlframe.engine import m3_ankou, m3_bonded, m3_casualty
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_janus_pandora import ChildProposal
from girlframe.services.onboarding import WorkflowError

from alpha_controls import BRUTALIZE, result_answer, result_fields
from alpha_controls import RESULTS as ALPHA_RESULTS
from am_scene_controls import ANSWERS as AM_ANSWERS
from am_scene_controls import PLAYS as AM_PLAYS
from am_scene_controls import SOURCE_OPERATIONS as AM_OPERATIONS
from am_scene_controls import decision_answer as am_answer
from am_scene_controls import decision_fields as am_fields
from defeat_play import DEFEAT_CHOICES, defeat_choice
from doll_controls import ANSWERS as DOLL_ANSWERS
from doll_controls import DOLL
from doll_controls import OPERATIONS as DOLL_OPERATIONS
from easy_target_controls import ANSWERS as EASY_ANSWERS
from easy_target_controls import EASY
from easy_target_controls import OPERATIONS as EASY_OPERATIONS
from easy_target_controls import SELECTS as EASY_SELECTS
from easy_target_controls import choice_fields as easy_fields
from oldgen_play import OLDGEN_CHOICES, advice_choice
from prince_controls import ANSWERS as PRINCE_ANSWERS
from prince_controls import OPERATIONS as PRINCE_OPERATIONS
from prince_controls import PERFORMER
from rulebook_text import printed_fields
from wyvern_controls import ANSWERS as WYVERN_ANSWERS
from wyvern_controls import PLAYS as WYVERN_PLAYS
from wyvern_controls import SOURCE_OPERATIONS as WYVERN_SOURCE_OPERATIONS
from wyvern_controls import decision_answer as wyvern_answer
from wyvern_controls import decision_fields as wyvern_fields

ENFORCEMENT = "enforcement_initiative"
DOSE = "dose_up"
DOSE_CONTACT = "dose_up_contact"
PANDORA = "pandora_birth"
PANDORA_CHILD = "janus_pandora_child"
PROCESSOR = m3_ankou.PLAY
PROCESSOR_PROPOSAL = "ankou_processor_proposal"
PROCESSOR_UNLINK = "ankou_processor_unlink"
PROCESSOR_CHOICES = frozenset({"ankou_processor_benefits", "ankou_processor_symptoms"})
CASUALTY_PARTS = "handler_casualty_parts"
BARELY = m3_casualty.BARELY
RISK_CHOICE = "mockingbird_risk"
RISK_TOTAL = (("8", "8"), ("9", "9"), ("10", "10"))
TRACKER_MOMENT = "tracker_moment"
HANDLER_TRACKER = {
    "handler_tracker_intercept": "tracker_intercept",
    "handler_tracker_voyeur": "tracker_voyeur",
}
HANDLER_WARP = "handler_contaminant_warp"
HANDLER_SCENE_PLAYS = frozenset((CASUALTY_PARTS, HANDLER_WARP, *HANDLER_TRACKER))
BONDED_SIDE = m3_bonded.SIDE_PLAY
BONDED_SOURCE = "bonded_side_source"
BONDED_ANSWERS = frozenset({BONDED_SIDE, "bonded_reply"})
CONSUME_PLAYS = {"consume_eat": "Eat", "consume_feral": "Feral"}
CONSUME_CHOICES = frozenset((*CONSUME_PLAYS, "consume_erase", "consume_time_eat"))
CONSUME_CHILDREN = frozenset({"consume_child", "consume_order_child"})
CONSUME_CHILD_PLAYS = {
    "check_sensors": "Check Your Sensors",
    "keep_your_head": "Keep Your Head",
}
CHILD_SCENE_CHOICES = frozenset(
    {
        "actor_sensors", "handler_sensors", "actor_keep", "handler_keep",
        "actor_flirt", "target_flirt", "actor_flirt_answer", "flirt_owe_tag", "flirt_escape",
        "beneath_select", "beneath_details", "beneath_pin_response",
        *DEFEAT_CHOICES,
        *OLDGEN_CHOICES,
    }
)
CHILD_STARTS = {
    "escape_play": ("keep_your_head", "Keep Your Head · Escape"),
    "beneath_response_play": ("keep_your_head", "Keep Your Head · Respond"),
    "beneath_defeat": ("defeat", "Defeat · Original consequence"),
}
CHILD_BATTLE_CHOICES = frozenset({
    "battle_assault_table", "battle_handler", "battle_counter", "battle_low_damage",
    "battle_actor_damage", "battle_target_damage", "battle_trainer_protect",
})
CHILD_ENGAGE_CHOICES = frozenset({"engage_maneuvers", "engage_assault_extra"})
DOCTOR_PLAYS = {
    "nanobot_injection": "Nanobot Injection",
    "doctor_support": "Here for Support",
}
NATIVE_TITLES = {
    ENFORCEMENT: "Enforcement Initiative",
    DOSE: "Dose Up",
    PANDORA: "PANDORA",
    PROCESSOR: "Processor Core",
    BRUTALIZE: "Brutalize",
    BONDED_SIDE: "Always By Her Side",
    BARELY: "Barely a Girl",
    PERFORMER: "Performer",
    DOLL: "Unassuming Doll",
    EASY: "Easy Target",
    **AM_PLAYS,
    **WYVERN_PLAYS,
    **DOCTOR_PLAYS,
    **CONSUME_PLAYS,
}
NATIVE_OPERATIONS = frozenset(
    (*NATIVE_TITLES, DOSE_CONTACT, PROCESSOR_PROPOSAL, PROCESSOR_UNLINK, *HANDLER_SCENE_PLAYS,
     TRACKER_MOMENT, BONDED_SOURCE, *WYVERN_SOURCE_OPERATIONS, *PRINCE_OPERATIONS, *AM_OPERATIONS,
     *DOLL_OPERATIONS, *EASY_OPERATIONS)
)
DOSE_CHOICES = frozenset({"dose_up_components", "dose_up_target_low"})
DOCTOR_CHOICES = frozenset(
    {
        "doctor_support_response",
        "doctor_support_refused",
        "doctor_nanobot_benefits",
        "doctor_patient",
    }
)
DOCTOR_SELECTS = frozenset(
    {
        "decision",
        "bond",
        "choices",
        "effect",
        "confirm",
        "assets",
        "identity",
        "modular_assets",
        "none",
    }
)
ENFORCER_CHOICES = frozenset(
    {
        "enforcer_select",
        "enforcer_escape",
        "enforcer_tag",
        "enforcer_disapproval",
        "enforcer_item",
        "enforcer_item_context",
        "enforcer_receive",
        "enforcer_hesitate",
    }
)
NATIVE_TAG_FIELDS = frozenset(
    {
        "options",
        "denied",
        "number",
        "text",
        "fields.as_actor",
        "fields.status",
        "fields.marker",
        "fields.replace",
    }
)
TAG_DECISIONS = frozenset(
    {
        "tag_window", "tag_resolution", "tag_marker_selection", "tag_marker_agreement",
        "actor_tag_selection", "actor_tag_agreement",
    }
)


def form_fields(fields):
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "options": list(spec.options) if spec.options else None,
            "required": spec.required
            and not any(value == "" for value, _ in spec.options),
            "multiple": spec.maximum > 1,
            "paragraph": spec.paragraph,
        }
        for spec in fields
    ]


def tag_choice_card(decision):
    kind = decision["kind"]
    if kind == "tag_window":
        fields = native_choice_fields(decision)
        other_options = decision.get("consume_starvation") or decision.get("gender_man_tags")
        status = any(field["key"] == "fields.status" for field in fields)
        if not (decision["tags"] or other_options or status):
            return {"schema": []}
        if not decision["tags"]:
            mode = next(field for field in fields if field["key"] == "options")
            mode["options"] = [(value, label) for value, label in mode["options"] if value != "tag"]
        return {"schema": fields}
    if kind == "tag_marker_agreement":
        detail = decision["tag_marker_discussion"]
        proposal = next(row for row in detail["proposals"] if row["id"] == detail["candidate"])
        return {
            "schema": native_choice_fields(decision),
            "prompt": " · ".join(proposal[name] for name in ("label", "tag", "account")),
        }
    if kind == "actor_tag_agreement":
        return {
            "schema": form_fields(choice_fields(decision)),
            "prompt": decision.get("body", {}).get("account"),
        }
    return {"schema": native_choice_fields(decision)}


def risk_choice_card(decision):
    detail = decision["mockingbird"]
    total = Field("total", "New result", RISK_TOTAL)
    account = Field("account", "Describe the actual Void alteration", paragraph=True)
    operations = [{"id": RISK_CHOICE, "label": "Decline Risk Factor", "fields": []}]
    if detail["assets"]:
        fields = [
            total,
            Field("asset", "Original uncorrupted Asset",
                  tuple((row["id"], row["label"]) for row in detail["assets"])),
            account,
        ]
        if detail["storage_available"]:
            fields.append(Field("storage", "Optional destination",
                                (("yes", "Store Void in the connected Harpy"),), required=False))
        if detail["casualty_parts"]:
            fields.extend((
                Field("casualty_part", "Wounded God · Original part to break",
                      tuple((x["id"], x["name"]) for x in detail["casualty_parts"]), required=False),
                Field("casualty_site_account", "Actual infected site, if resisting",
                      paragraph=True, required=False),
            ))
        operations.append({
            "id": "risk_alter_asset", "label": "Choose result and alter Asset", "fields": form_fields(fields),
        })
    if growth := detail.get("sup"):
        fields = [
            total, Field("sup_name", "Name the new Void Asset"), account,
            Field("sup_family", "Asset family", tuple((x, x.title()) for x in growth["families"])),
            Field("sup_replace", "Replace a same-family Asset only at its cap",
                  tuple((x["id"], x["label"] + " · " + x["family"]) for x in growth["replacements"]),
                  required=False),
        ]
        operations.append({
            "id": "risk_grow_asset", "label": "Choose result and grow Void Asset", "fields": form_fields(fields),
        })
    return {
        "risk_operations": operations,
        "prompt": f"Current result · {detail['total']}" + (
            " · A shift spends the original one-use lesson." if detail.get("learned_source") else ""
        ),
    }


def risk_choice_answer(op, values):
    if op == RISK_CHOICE and not values:
        return ChoiceAnswer()
    required = {"total", "account"}
    if values.get("total") not in dict(RISK_TOTAL):
        raise ValueError("Choose a printed Risk Factor result.")
    if op == "risk_alter_asset" and required | {"asset"} <= values.keys() <= required | {
        "asset", "storage", "casualty_part", "casualty_site_account",
    }:
        fields = {key: value for key, value in values.items() if key not in required}
    elif op == "risk_grow_asset" and required | {"sup_name", "sup_family"} <= values.keys() <= (
        required | {"sup_name", "sup_family", "sup_replace"}
    ):
        fields = {key: values.get(key, "") for key in ("sup_name", "sup_family", "sup_replace")}
    else:
        raise ValueError("Use the fields from the current Risk Factor decision.")
    return ChoiceAnswer.model_validate({
        "number": int(values["total"]), "text": values["account"], "fields": fields,
    })


def heat_options(heat):
    return tuple(
        (str(amount), str(amount))
        for amount in ((heat,) if heat >= 5 else range(heat + 1))
    )


def child_operations(detail):
    result = []
    count = detail["count"]
    for variant in detail["types"]:
        names = tuple((name, name) for name in detail["assets"][variant])
        fields = [
            Field("name", "Name"),
            Field(
                "class",
                "Class from the original roll",
                tuple((kind, kind.title()) for kind in detail["classes"]),
            ),
        ]
        for position in range(count):
            fields.extend(
                (
                    Field(f"asset{position}", f"Asset {position + 1}", names),
                    Field(
                        f"description{position}",
                        f"Asset {position + 1} description",
                        paragraph=True,
                    ),
                )
            )
        fields.extend(
            (
                Field(
                    "core",
                    "Assets guarding the Core",
                    tuple((str(n), f"Asset {n + 1}") for n in range(count)),
                    minimum=1,
                    maximum=min(2, count),
                ),
                Field("weakness", "Actual weakness", paragraph=True),
                Field("account", "Actual birth and behavior", paragraph=True),
            )
        )
        result.append(
            {
                "id": PANDORA_CHILD + ":" + variant,
                "label": "File " + variant.title() + " description",
                "fields": form_fields(fields),
            }
        )
    return result


def child_proposal(variant, values):
    count = sum(key.startswith("asset") for key in values)
    core = values["core"]
    proposal = ChildProposal(
        name=values["name"],
        gorgon_type=variant,
        gorgon_class=values["class"],
        assets=tuple(values[f"asset{i}"] for i in range(count)),
        descriptions=tuple(values[f"description{i}"] for i in range(count)),
        core_assets=tuple(
            int(item) for item in ([core] if isinstance(core, str) else core)
        ),
        weakness=values["weakness"],
        account=values["account"],
    )
    return ChoiceAnswer(fields={"child": proposal.model_dump_json()})


def response_values(values, selects):
    if any(
        not isinstance(value, str)
        and not (
            key in selects
            and isinstance(value, list)
            and all(isinstance(item, str) for item in value)
        )
        for key, value in values.items()
    ):
        raise ValueError("Use the current engine form to file your response.")
    return {
        key: (value,) if isinstance(value, str) else tuple(value)
        for key, value in values.items()
        if key in selects and value != ""
    } | {key: value for key, value in values.items() if key not in selects}


def choice_supported(play, kind):
    return (
        play in NATIVE_TITLES
        and kind in TAG_DECISIONS
        or kind == "prince_bad_girl"
        or kind in AM_ANSWERS
        or kind in DOLL_ANSWERS
            or play == EASY and (kind.partition(":")[0] in EASY_ANSWERS or kind == "battle_target_damage")
        or (
            play == ENFORCEMENT
            and kind in ENFORCER_CHOICES
            or play in DOCTOR_PLAYS
            and kind in DOCTOR_CHOICES
            or play == DOSE
            and kind in DOSE_CHOICES
            or play in CONSUME_PLAYS
            and kind in CONSUME_CHOICES
            or play == PROCESSOR
            and kind in PROCESSOR_CHOICES
            or play == BRUTALIZE
            and kind in ALPHA_RESULTS
            or play in WYVERN_PLAYS
            and kind in WYVERN_ANSWERS
            or play == BONDED_SIDE
            and kind in BONDED_ANSWERS
            or play == PERFORMER
            and kind in PRINCE_ANSWERS
        )
    )


def is_native_child_choice(game, c, action, kind):
    data = action["data"]
    return (
        kind in TAG_DECISIONS | CHILD_SCENE_CHOICES | CHILD_STARTS.keys() | {RISK_CHOICE}
        and native_child(game, c, action)
        or data.get("easy_target_child") and kind in CHILD_BATTLE_CHOICES | CHILD_ENGAGE_CHOICES
    )


def native_child(game, c, action):
    # A Fanbase demand can start a source-bound action directly in its scene.
    while True:
        data = action["data"]
        if any(data.get(key) for key in ("consume_child", "alpha_counter_source",
                                        "prince_demand_attempt", "easy_target_child", "wyvern_child")):
            return True
        parent = action["parent_id"]
        if not parent:
            return False
        action = game.action(c, parent)


def mounted_roll(game, c, action):
    return action["data"]["play"] in NATIVE_TITLES or native_child(game, c, action)


def native_choice_fields(decision):
    kind = decision["kind"]
    if kind in ("tag_window", "tag_resolution", "actor_tag_selection", "actor_tag_agreement"):
        specs = choice_fields(decision)
        if (
            kind == "tag_window"
            and len(markers := decision.get("tag_markers", ())) == 1
        ):
            specs.append(
                Field(
                    "fields.marker",
                    "Role marking the Tag",
                    ((markers[0]["token"], markers[0]["label"]),),
                    required=False,
                )
            )
    elif kind in CHILD_BATTLE_CHOICES:
        specs = battle_fields(kind, decision["battle"])
    elif kind in CHILD_ENGAGE_CHOICES:
        specs = engage_fields(decision["engage"])
    elif kind in DEFEAT_CHOICES:
        specs = [Field(**row) for row in defeat_choice(decision)["schema"]]
    elif kind in CHILD_SCENE_CHOICES:
        specs = ([Field(**row) for row in advice_choice(decision)["fields"]]
                 if kind in OLDGEN_CHOICES else choice_fields(decision))
        return printed_fields(form_fields(specs), kind)
    elif kind == "tag_marker_selection":
        specs = [
            Field(
                "options",
                "Tag proposal to review",
                tuple(
                    (item["id"], item["label"])
                    for item in decision["tag_marker_discussion"]["proposals"]
                ),
            )
        ]
    elif kind == "tag_marker_agreement":
        specs = [
            Field(
                "flag",
                "Your response to this Tag proposal",
                (
                    ("yes", "Agree"),
                    ("no", "Reject and continue the discussion"),
                ),
            )
        ]
    elif kind in DOCTOR_CHOICES:
        if decision["doctor"].get("unsupported"):
            raise WorkflowError("The original treatment requires facilitator review.")
        specs = doctor_choice_fields(decision)
    elif kind in DOSE_CHOICES:
        detail = decision["detail"]
        specs = [
            Field(
                "components",
                "Your printed cocktail choice",
                tuple(map(tuple, detail["options"])),
                minimum=detail.get("minimum", 1),
                maximum=detail.get("maximum", 1),
            )
        ]
    elif kind in CONSUME_CHOICES:
        detail = decision["detail"]
        specs = [
            Field(
                "option", "Your printed outcome", tuple(map(tuple, detail["options"]))
            ),
            Field("account", "Describe your actual response", paragraph=True),
        ]
        if kind == "consume_eat":
            if detail["own_cost"]:
                specs.append(
                    Field(
                        "own_asset",
                        "Your Asset to damage",
                        tuple(map(tuple, detail["own_assets"])),
                    )
                )
            if detail["target_assets"]:
                specs.append(
                    Field(
                        "target_asset",
                        "Target Asset if biting",
                        tuple(map(tuple, detail["target_assets"])),
                        required=False,
                    )
                )
        if kind == "consume_time_eat" and detail["identities"]:
            specs.append(
                Field(
                    "identity",
                    "Identity to mark if giving",
                    tuple(map(tuple, detail["identities"])),
                    required=False,
                )
            )
    elif kind == "ankou_processor_benefits":
        specs = processor_benefit_fields(decision["detail"])
    elif kind == "ankou_processor_symptoms":
        detail = decision["detail"]
        specs = [
            Field(
                "options",
                "Actual processor symptoms",
                tuple((item, item) for item in detail["symptoms"]),
                minimum=detail["symptom_count"],
                maximum=detail["symptom_count"],
            )
        ]
    elif kind in ALPHA_RESULTS:
        specs = result_fields(decision)
    elif kind in WYVERN_ANSWERS:
        specs = wyvern_fields(decision)
    elif kind in BONDED_ANSWERS:
        specs = bonded_fields(decision.get("bonded") or decision["detail"])
    elif kind in PRINCE_ANSWERS:
        specs = performance_choice_fields(decision)
    elif kind in AM_ANSWERS:
        specs = am_fields(decision)
    elif kind in DOLL_ANSWERS:
        specs = doll_choice_fields(decision)
    elif kind.partition(":")[0] in EASY_ANSWERS:
        specs = easy_fields(decision.get("detail") or decision["easy_target"])
    else:
        specs = initiative_choice_fields(decision)
    return form_fields(specs)


def native_choice_answer(kind, values, *, source=None):
    tag_fields = NATIVE_TAG_FIELDS | {"flag", "member"}
    if kind in TAG_DECISIONS and values.keys() <= tag_fields:
        supplied = response_values(values, tag_fields - {"text"})
        return answer_values(supplied)
    if kind in CHILD_BATTLE_CHOICES:
        return battle_answer(kind, response_values(values, {"decision", "options", "asset"}))
    if kind in CHILD_ENGAGE_CHOICES:
        return engage_answer(response_values(values, values.keys() - {"text"}))
    if kind in CHILD_SCENE_CHOICES:
        if kind == "defeat_alternative":
            values = {
                key: ",".join(value) if key in {"fields.assets", "fields.identities"} and isinstance(value, list)
                else value for key, value in values.items()
            }
        return answer_values(
            response_values(
                values,
                {
                    "options",
                    "denied",
                    "flag",
                    "number",
                    "member",
                    "beneath_extra",
                },
            )
        )
    if kind in DOCTOR_CHOICES and all(
        key in DOCTOR_SELECTS
        or key == "tag"
        or key.startswith(("modular_name:", "modular_description:"))
        for key in values
    ):
        return doctor_choice_answer(kind, response_values(values, DOCTOR_SELECTS))
    if kind in DOSE_CHOICES and values.keys() == {"components"}:
        return ChoiceAnswer(
            options=response_values(values, {"components"})["components"]
        )
    if (
        kind in CONSUME_CHOICES
        and {"option", "account"} <= values.keys()
        and (
            not values.keys()
            - {"option", "account", "own_asset", "target_asset", "identity"}
        )
        and all(isinstance(value, str) for value in values.values())
    ):
        option = values["option"]
        use = {"own_asset"} if kind == "consume_eat" else set()
        if kind == "consume_eat" and option == "bite":
            use.add("target_asset")
        if kind == "consume_time_eat" and option == "give":
            use.add("identity")
        return ChoiceAnswer(
            options=(option,),
            text=values["account"],
            fields={key: values[key] for key in use if values.get(key)},
        )
    if kind == "ankou_processor_benefits":
        return processor_benefit_answer(values)
    if kind == "ankou_processor_symptoms" and values.keys() == {"options"}:
        return ChoiceAnswer(options=response_values(values, {"options"})["options"])
    if kind in ALPHA_RESULTS:
        return result_answer(kind, values)
    if kind in WYVERN_ANSWERS:
        return wyvern_answer(kind, values)
    if kind in BONDED_ANSWERS:
        return bonded_answer(response_values(values, {"options", "identities", "tags"}))
    if kind in PRINCE_ANSWERS and values.keys() <= {"option", "tags", "account"}:
        return performance_choice_answer(response_values(values, {"option", "tags"}))
    if kind in AM_ANSWERS:
        return am_answer(kind, values)
    if kind in DOLL_ANSWERS and values.keys() <= {"options", "text"}:
        option = response_values(values, {"options"})
        return ChoiceAnswer(options=option.get("options", ()), text=option.get("text", ""))
    base = kind.partition(":")[0]
    if base in EASY_ANSWERS and values.keys() <= EASY_SELECTS | {"account", "context"}:
        return easy_target_choice_answer(
            {"kind": base, "npc_reactor": (source or {}).get("actor", {}).get("kind") == "npc"},
            response_values(values, EASY_SELECTS),
        )
    selects = {"options", "item", "weapon", "inside_frame", "replace", "accept"}
    if kind in ENFORCER_CHOICES and values.keys() <= selects | {"account"}:
        return initiative_answer(kind, response_values(values, selects))
    raise WorkflowError("Open your original assigned Play response.")


def processor_benefit_fields(detail):
    available = tuple((item, item.title()) for item in detail["benefits"])
    identities = tuple((item["id"], item["label"]) for item in detail["identities"])
    marked = tuple(
        (item["id"], item["label"]) for item in detail["identities"] if item["marked"]
    )
    assets = tuple((item["id"], item["label"]) for item in detail["assets"])
    specs = []
    for slot in range(detail["count"]):
        specs.append(Field(f"benefit{slot}", f"Benefit {slot + 1}", available))
        if identities:
            specs.append(
                Field(
                    f"erase{slot}",
                    "Identity benefit · Erase",
                    identities,
                    required=False,
                )
            )
        if marked:
            specs.append(
                Field(
                    f"unmark{slot}", "Identity benefit · Unmark", marked, required=False
                )
            )
        specs.append(
            Field(
                f"gain{slot}",
                "Identity benefit · Heat gained",
                (("1", "1"), ("2", "2"), ("3", "3")),
                required=False,
            )
        )
        if assets:
            specs.append(
                Field(
                    f"replace{slot}",
                    "Temporary Asset · Replace at capacity",
                    assets,
                    required=False,
                )
            )
    return specs


def processor_benefit_answer(values):
    slots = sum(key.startswith("benefit") for key in values)
    if any(not isinstance(value, str) for value in values.values()):
        raise ValueError("Use the current owned Processor Core result.")
    selected = [values[f"benefit{slot}"] for slot in range(slots)]
    options = tuple(
        f"identity_repeat_{slot}"
        if item == "identity" and item in selected[:slot]
        else item
        for slot, item in enumerate(selected)
    )
    fields = {}
    for slot, item in enumerate(selected):
        keys = (
            ("erase", "unmark", "gain")
            if item == "identity"
            else ("replace",)
            if item in ("eyes", "will")
            else ()
        )
        for key in keys:
            name = f"{key}{slot}"
            if values.get(name):
                fields[name] = values[name]
    return ChoiceAnswer(options=options, fields=fields)
