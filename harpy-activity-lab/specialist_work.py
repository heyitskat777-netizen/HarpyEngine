"""Project source-owned specialist work into Activity forms."""

import json

import sqlalchemy as sa
from gorgon_counter_work import GorgonCounterWork
from gorgon_followups import normalize_choice
from harpy_recovery import KINDS as HARPY_RECOVERY
from harpy_recovery import HarpyRecovery
from harpy_specialists import HarpySpecialists
from p2_scene import alternate_choice_fields
from repossession_work import RepossessionWork

from girlframe.database import tables
from girlframe.discord_adapter import m3_harpy_defeat as defeat_forms
from girlframe.discord_adapter.m3_leviathan_obsession import response_answer, response_form
from girlframe.discord_adapter.m3_npc_flirt import response_answer as npc_flirt_answer
from girlframe.discord_adapter.m3_npc_flirt import response_fields as npc_flirt_fields
from girlframe.engine import m3_npc_guard as guard_rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_advancements import ADVANCEMENTS
from girlframe.engine.m3_leviathan_roll_state import Declaration
from girlframe.services.m2_state import load_state
from girlframe.services.m3_adjudication import AdjudicationService
from girlframe.services.m3_harpy_advancements import HarpyAdvancementService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_harpy_voidspace import APPROACHES, HarpyVoidspaceService
from girlframe.services.m3_leviathan_obsession import ObsessionService
from girlframe.services.m3_npc_care import JOBS, NpcCareService
from girlframe.services.m3_npc_flirt import NpcFlirtService
from girlframe.services.m3_npc_guard import GuardService
from girlframe.services.m3_parasite_excision import ExcisionService
from girlframe.services.native_form_fields import Field, form_fields, selected_fields
from girlframe.services.onboarding import WorkflowError

REVIEW = (("yes", "Approve the recorded facts"), ("no", "Return for review"))
ACCOUNT = Field("account", "Describe the actual event", paragraph=True)
NAVIGATION = Field("navigation", "How did the body navigate Voidspace?", paragraph=True)
DESTINATION = Field("destination", "Return cell (x,y)")
CONFIRM = (("yes", "Confirm"),)
TRAVEL = frozenset({"harpy_escape", "harpy_return", "harpy_rift"})
DEFEAT_TASKS = TRAVEL | {
    "harpy_defeat",
    "harpy_route",
    "harpy_setup",
    "harpy_fight",
    "harpy_message",
}


def operation(identity, title, *fields):
    return {"id": identity, "label": title, "fields": fields}


def select(name, label, choices, *, required=True):
    return Field(name, label, tuple(choices), required=required)


def account(values):
    return values.get("account", "")


def pick(values, name):
    return (values.get(name) or (None,))[0]


def record(kind, identity, title):
    return {"kind": kind, "id": identity, "title": title}


class SpecialistWork:
    def __init__(self, game, rooms=()):
        self.game, self.store = game, game.store
        self.rooms = dict(rooms)
        self.excision = ExcisionService(self.store)
        self.care = NpcCareService(self.store)
        self.advancement = HarpyAdvancementService(self.store)
        self.passage = HarpyVoidspaceService(game)
        self.defeat = HarpyDefeatService(self.store, game=game)
        self.influence = ObsessionService(game)
        self.repossession = RepossessionWork(self.store)
        self.counter = GorgonCounterWork(game)
        self.guard = GuardService(game)
        self.npc_flirt = NpcFlirtService(game)
        self.harpy = HarpySpecialists(game, self.rooms)
        self.recovery = HarpyRecovery(game, self.defeat)
        self.adjudication = AdjudicationService(self.store)

    def list(self, viewer):
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            self.game.authorize(connection, viewer, game=False)
            state = load_state(connection, self.store.campaign_id)
            choices = self.game.choices(viewer)
            return {
                "work": [
                    record("excision", row["id"], "Parasite Excision · " + row["label"])
                    for row in self.excision.tasks(connection, viewer, state)
                ]
                + [
                    record("care", row["id"], row["label"])
                    for row in self.care.tasks(connection, viewer, state)
                ]
                + [
                    record("advancement", actor.entity, "Harpy advancements")
                    for actor, _ in self.advancement.tasks(connection, state, viewer)
                ]
                + [
                    record("passage", identity, "Come to Me Now Once Again")
                    for identity, _ in self.passage.tasks(connection, state, viewer)
                ]
                + [
                    record(row["kind"], row["id"], row["label"])
                    for row in self.defeat._tasks(connection, viewer)
                    if row["kind"] in DEFEAT_TASKS
                ]
                + self.source_actions(
                    connection, viewer, choices, "leviathan", "leviathan_obsession"
                )
                + self.source_actions(connection, viewer, choices, "defeat", "harpy_defeat")
                + self.influence_starts(viewer)
                + self.repossession_records(connection, viewer)
                + self.counter_records(connection, viewer, choices)
                + self.npc_assignments(connection, viewer, choices)
                + self.source_actions(connection, viewer, choices, "gorgon", "gorgon_play")
                + [record(*item) for item in self.harpy.tasks(connection, state, viewer)]
                + [record(*item) for item in self.recovery.tasks(connection, state, viewer)]
            }

    def npc_assignments(self, connection, viewer, choices):
        direct = {row["action_id"] for row in choices if row["kind"].startswith("npc_flirt_")}
        result = [
            record("npc_followthrough", item["id"], "Flirt · Follow-through")
            | {"assigned": item["pending"] and item["id"] not in direct}
            for item in self.npc_flirt._tasks(connection, viewer)
        ]
        for choice in choices:
            if choice["kind"].startswith("npc_flirt_"):
                result.append(record("npc_flirt", choice["id"], "Flirt · Assigned reply"))
            elif choice["kind"] == "alpha_counter_play":
                try:
                    decision = self.game.decision(viewer, choice["id"])
                    if decision.get("alpha", {}).get("npc"):
                        data = self.guard.counter(viewer, decision["parent"], choice["id"])
                        result.append(
                            record("npc_guard", choice["id"], data["label"] + " · Counter")
                        )
                except (ValueError, WorkflowError):
                    continue
        return result

    def npc_detail(self, viewer, kind, identity):
        if kind == "npc_followthrough":
            data = self.npc_flirt.view(viewer, identity)
            source = data["source"]
            title = "Flirt · Follow-through"
            text = f"{source['actor_label']} → {source['target_label']}"
            if source["wanted"]:
                text += "\nRequested outcome · " + source["wanted"]
            forms = []
            if data["can_perform"]:
                forms.append(
                    operation(
                        "perform",
                        "File follow-through",
                        ACCOUNT,
                        Field("action", "Completed Play reference if mechanical", required=False),
                    )
                )
            judged = {x["performance"] for x in data["judgments"]}
            for item in data["performances"]:
                text += "\n" + item["rendition"]
                if (
                    data["can_judge"]
                    and item["kind"] == "followthrough"
                    and item["id"] not in judged
                ):
                    forms.append(
                        operation(
                            item["id"],
                            "Review this follow-through",
                            select(
                                "accepted",
                                "Did it fulfill the requested outcome?",
                                (("yes", "Fulfilled"), ("no", "Not fulfilled")),
                            ),
                            ACCOUNT,
                        )
                    )
            return data, title, text, forms
        decision = self.game.decision(viewer, identity)
        if kind == "npc_flirt" and decision["kind"].startswith("npc_flirt_"):
            return (
                decision,
                "Flirt · Assigned reply",
                "File the response for the assigned role.",
                [operation("answer", "File reply", *npc_flirt_fields(decision))],
            )
        if kind != "npc_guard" or decision["kind"] != "alpha_counter_play":
            raise WorkflowError("Choose an assigned NPC response.")
        data = self.guard.counter(viewer, decision["parent"], identity)
        weapons = data["weapons"]
        moves = [move for move in guard_rules.MOVES if weapons or move[0] != "draw_weapon"]
        fields = [select("move", "Printed Guard move", moves), ACCOUNT]
        if weapons:
            fields.append(
                select(
                    "weapon",
                    "Carried weapon if drawn",
                    ((x["id"], x["label"]) for x in weapons),
                    required=False,
                )
            )
        return (
            data | {"parent": decision["parent"]},
            "Guard · " + data["label"],
            "",
            [operation("perform", "File counter", *fields)],
        )

    def counter_records(self, connection, viewer, choices):
        result = []
        for choice in choices:
            if choice["kind"] != "gorgon_response_play":
                continue
            try:
                data = self.counter.declaration(viewer, choice["id"])
            except (ValueError, WorkflowError):
                continue
            if data["plays"]:
                result.append(record("gorgon_counter", choice["id"], "Gorgon counter"))
        for task in self.counter.battle._tasks(connection, viewer):
            if task["source_action"] and self.game.action(connection, task["source_action"])[
                "data"
            ].get("gorgon_play"):
                result.append(
                    record("gorgon_counter_context", task["id"], task["label"])
                    | {"assigned": task["incoming"] or task["state"] == "confirmed"}
                )
        return result

    def counter_detail(self, viewer, kind, identity):
        if kind == "gorgon_counter":
            data = self.counter.declaration(viewer, identity)
            forms = []
            for play, (label, weapons, targets) in data["plays"].items():
                fields = [
                    ACCOUNT,
                    select("weapon", "Attacking Asset", ((x["id"], x["name"]) for x in weapons)),
                ]
                if play == "all_out_assault":
                    fields.append(
                        select("asset", "Target Asset", ((x["id"], x["name"]) for x in targets))
                    )
                forms.append(operation(play, label, *fields))
            return data, "Gorgon counter", "File the opening against the original attacker.", forms
        data = self.counter.context(viewer, identity)
        context = data["decision"]
        forms = []
        if context.state == "proposed" and viewer.user_id == context.adjudicator:
            facts = [("opening", "An opening exists"), ("reach", "Attack can reach")]
            if context.declaration.play == "go_for_the_core":
                facts.append(("core", "The attacking Asset can strike the Core"))
            forms.append(
                operation(
                    "review",
                    "File the tactical ruling",
                    Field(
                        "facts", "Confirmed facts", tuple(facts), maximum=len(facts), required=False
                    ),
                    Field("account", "Evidence for the ruling", paragraph=True),
                )
            )
        elif context.state == "confirmed" and viewer.user_id == context.owner:
            if context.reach and context.opening and data["heat"] is not None:
                forms.append(
                    operation(
                        "begin",
                        "Commit Heat and start",
                        select(
                            "heat",
                            "Heat to commit",
                            ((str(x), str(x)) for x in range(data["heat"] + 1)),
                        ),
                    )
                )
        text = context.declaration.account
        if context.evidence:
            text += "\nRuling · " + context.evidence
        elif not forms:
            text += "\nAwaiting the assigned judge."
        return data, "Gorgon counter · Opening", text, forms

    def repossession_records(self, connection, viewer):
        service = self.repossession.service
        try:
            service._access(connection, viewer)
        except (ValueError, WorkflowError):
            return []
        result = [
            record("repossession", row["id"], row["label"])
            for row in service._tasks(connection, viewer)
        ]
        try:
            if service.menu(viewer)["candidates"]:
                result.append(record("repossession", "captured", "File captured Harpy"))
        except (ValueError, WorkflowError):
            pass
        return result

    def source_actions(self, connection, viewer, choices, family, source):
        result = []
        actions = tables.m2["m2_actions"]
        title = "Leviathan" if family == "leviathan" else "Harpy Defeat"
        active = connection.execute(
            sa.select(actions.c.id, actions.c.actor_id, actions.c.state).where(
                actions.c.campaign_id == self.store.campaign_id,
                sa.func.json_type(actions.c.body_json, "$." + source).is_not(None),
                actions.c.state.not_in(("complete", "aborted")),
            )
        ).all()
        for action, owner, state in active:
            if (
                family != "gorgon"
                and owner == str(viewer.user_id)
                and state in ("acquiring", "ready_to_roll")
            ):
                result.append(record(family + "_roll", action, "Continue " + title))
        scope = {row.id for row in active}
        result += [
            record(
                family + "_choice",
                row["id"],
                title
                + " · "
                + row["kind"]
                .removeprefix(family + "_")
                .removeprefix("harpy_")
                .replace("_", " ")
                .capitalize(),
            )
            for row in choices
            if row["action_id"] in scope and family != "gorgon"
        ]
        if family == "gorgon":
            for row in choices:
                if row["action_id"] not in scope or row["kind"] == "gorgon_response_play":
                    continue
                try:
                    _, label, _, forms = self.gorgon_detail(viewer, row["id"])
                except (WorkflowError, ValueError):
                    continue
                if forms:
                    result.append(record("gorgon_choice", row["id"], label))
        return result

    def gorgon_detail(self, viewer, identity):
        data = self.game.decision(viewer, identity)
        if not data.get("gorgon_play") or data["kind"] == "gorgon_response_play":
            raise WorkflowError("Choose an assigned Gorgon decision.")
        fields = alternate_choice_fields(data)
        title = data["kind"].removeprefix("gorgon_").replace("_", " ").capitalize()
        return (
            data,
            "Gorgon · " + title,
            "",
            [operation("answer", "File response", *fields)] if fields else [],
        )

    @staticmethod
    def gorgon_answer(data, values):
        answers, fields = {}, {}
        for key, value in values.items():
            if key.startswith("fields."):
                fields[key[7:]] = ",".join(value) if isinstance(value, tuple) else value
            elif key == "flag":
                answers[key] = value == ("yes",)
            elif key == "number":
                answers[key] = int(value)
            elif key in ("options", "denied"):
                answers[key] = list(value)
            else:
                answers[key] = value[0] if isinstance(value, tuple) else value
        return ChoiceAnswer.model_validate_json(
            json.dumps(normalize_choice(data["kind"], answers | {"fields": fields}))
        )

    def influence_starts(self, viewer):
        result = []
        for channel, (_, name) in self.rooms.items():
            try:
                data = self.influence.preview(viewer, channel)
            except (WorkflowError, ValueError):
                continue
            if any(actor["leviathan"] and actor["owned"] for actor in data["actors"]):
                result.append(
                    record("leviathan_start", str(channel), "Leviathan influence · " + name)
                )
        return result

    def influence_detail(self, viewer, kind, identity):
        if kind == "leviathan_start":
            channel = int(identity)
            if channel not in self.rooms:
                raise WorkflowError("Choose the original Activity scene.")
            data = self.influence.preview(viewer, channel)
            forms = []
            pairs = []
            for source in data["actors"]:
                if not source["leviathan"] or not source["owned"]:
                    continue
                for target in data["actors"]:
                    if source["ref"] == target["ref"]:
                        continue
                    modes = [("give", "Give an obsessed Tag")]
                    modes += [
                        (tag["id"], "Mark obsessed · " + tag["label"])
                        for tag in target["trigger_tags"]
                    ]
                    forms.append(
                        operation(
                            str(len(pairs)),
                            source["name"] + " → " + target["name"],
                            select("mode", "Influence", modes),
                            ACCOUNT,
                        )
                    )
                    pairs.append((source, target))
            return (
                data | {"pairs": pairs},
                "Leviathan influence",
                ("Describe the actual influence for the assigned reach review."),
                forms,
            )
        if kind == "leviathan_roll":
            data = self.influence.inspect(viewer, identity)
            with self.store.engine.connect() as connection:
                owner = self.game.action(connection, identity)["actor_id"] == str(viewer.user_id)
            forms = (
                [operation("roll", "Continue original Play")]
                if owner and data["state"] in ("ready_to_roll", "acquiring")
                else []
            )
            receipt = data.get("receipt")
            text = "Continue the original Play when its scene lock and reach allow it."
            if receipt:
                text = f"Original roll · {' + '.join(map(str, receipt['faces']))}"
            return data, "Leviathan influence", text, forms
        if kind == "leviathan_choice":
            data = self.game.decision(viewer, identity)
            if not data["kind"].startswith("leviathan_") and data["kind"] != "tag_window":
                raise WorkflowError("Choose an assigned Leviathan response.")
            with self.store.engine.connect() as connection:
                action = self.game.action(connection, data["action_id"])
                if not action["data"].get("leviathan_obsession"):
                    raise WorkflowError("Choose an assigned Leviathan response.")
            text, fields = response_form(data)
            return (
                data,
                "Leviathan response",
                text,
                [operation("answer", "File response", *fields)] if fields else [],
            )
        raise WorkflowError("Choose the original Leviathan record.")

    def detail(self, viewer, kind, identity):
        if kind == "excision":
            data = self.excision.get(viewer, identity)
            title = "Experimental Parasite Excision"
            if data["patient"] and data["consent"]:
                text, forms = (
                    "Excision consent is on file.",
                    [
                        operation(
                            "withdraw", "Withdraw consent", select("confirm", "Decision", CONFIRM)
                        )
                    ],
                )
            elif data["patient"] and data["options"]:
                text, forms = (
                    "Choose the doctor and scene for this surgery.",
                    [
                        operation(
                            "consent",
                            "File consent",
                            select("doctor", "Doctor and scene", data["options"].items()),
                        )
                    ],
                )
            elif data["patient"]:
                text, forms = "Awaiting an active scene with an available local doctor.", []
            else:
                text, forms = (
                    "Review the consented operation after it has occurred.",
                    [operation("performed", "File performed excision", ACCOUNT)],
                )
        elif kind == "care":
            data = self.care.get(viewer, identity)
            title = JOBS[data["job"]][1]
            if "targets" in data:
                text, forms = (
                    "",
                    [
                        operation(
                            "offer",
                            "Offer care",
                            select("target", "Local recipient", data["targets"].items()),
                            ACCOUNT,
                        )
                    ]
                    if data["targets"]
                    else [],
                )
            else:
                text = data["account"]
                options = [(f"asset/{key}", label) for key, label in data["assets"].items()]
                fields = [select("care", "Your response", (*options, ("decline", "Decline care")))]
                if data["job"] == "scientist":
                    fields.append(
                        Field("alteration", "Change if accepted", paragraph=True, required=False)
                    )
                forms = [operation("answer", "File response", *fields)]
        elif kind == "advancement":
            data = self.advancement.get(viewer, identity)
            title = "Harpy advancements"
            learned = [dict(ADVANCEMENTS)[rule] for rule in data["learned"]]
            text = f"Advancement slots · {len(learned)} / {data['slots']}"
            if learned:
                text += "\n" + ", ".join(learned)
            forms = (
                [
                    operation(
                        "learn",
                        "Record advancement",
                        select("advancement", "Available advancement", data["choices"]),
                    )
                ]
                if data["available"]
                else []
            )
        elif kind == "passage":
            data = self.passage.get(viewer, identity)
            title, text, forms = self.passage_form(data)
        elif kind in DEFEAT_TASKS:
            data = self.defeat.task(viewer, kind, identity)
            if kind == "harpy_defeat":
                title, text, forms = self.defeat_start(viewer, identity, data)
            else:
                title, text, forms = self.defeat_form(kind, data)
        elif kind in ("defeat_roll", "defeat_choice"):
            data, title, text, forms = self.defeat_detail(viewer, kind, identity)
        elif kind.startswith("leviathan_"):
            data, title, text, forms = self.influence_detail(viewer, kind, identity)
        elif kind == "repossession":
            data, title, text, forms = self.repossession.detail(viewer, identity)
        elif kind in ("gorgon_counter", "gorgon_counter_context"):
            data, title, text, forms = self.counter_detail(viewer, kind, identity)
        elif kind == "gorgon_choice":
            data, title, text, forms = self.gorgon_detail(viewer, identity)
        elif kind in ("npc_flirt", "npc_guard", "npc_followthrough"):
            data, title, text, forms = self.npc_detail(viewer, kind, identity)
        elif kind.startswith("advancement_"):
            data, title, text, fields = self.harpy.detail(viewer, kind, identity)
            forms = [operation("file", "File record", *fields)] if fields else []
        elif kind in HARPY_RECOVERY:
            data, title, text, forms = self.recovery.detail(viewer, kind, identity)
        else:
            raise ValueError("Choose a filed specialist record.")
        return data, dict(
            record(kind, identity, title), revision=data["revision"], text=text, operations=forms
        )

    def defeat_start(self, viewer, identity, data):
        if data.get("action"):
            return "Harpy Defeat", "The original Play is underway. Open its assigned response.", []
        try:
            preview = self.defeat.setup_preview(viewer, identity)
        except WorkflowError:
            return (
                "Harpy Defeat",
                "",
                [
                    operation(
                        "begin",
                        "Begin original Harpy Defeat",
                        select("confirm", "Original mandatory source", CONFIRM),
                    )
                ],
            )
        actual = ActorRef.model_validate(preview["actor"])
        setup = self.defeat.setup_preview_actor(viewer, actual)
        return (
            "Harpy Defeat",
            "File the original Harpy's current factual record for review.",
            [operation("setup", "File original Harpy facts", *defeat_forms.setup_fields(setup))],
        )

    def defeat_detail(self, viewer, kind, identity):
        if kind == "defeat_roll":
            data = self.defeat.inspect(viewer, identity)
            with self.store.engine.connect() as c:
                owner = self.game.action(c, identity)["actor_id"] == str(viewer.user_id)
            can_roll = owner and data["state"] in ("acquiring", "ready_to_roll")
            return (
                data,
                "Harpy Defeat",
                "The original Play keeps its roll and source record.",
                [operation("roll", "Continue original Defeat")] if can_roll else [],
            )
        data = self.defeat.decision(viewer, identity)
        if data["state"] != "pending":
            return data, "Harpy Defeat", "The original response is on file.", []
        if data["kind"] == "manual_adjudication":
            manual = self.adjudication.get(viewer, identity)
            forms = (
                [
                    operation(
                        "manual",
                        "File adjudication",
                        Field("total", "Assigned total before Tags"),
                        Field("reason", "Ruling and circumstances", paragraph=True),
                    )
                ]
                if manual["can_act"]
                else []
            )
            text = manual.get("restriction_reason") or "The original actor cannot roll."
            return (
                data | {"revision": manual["revision"]},
                "Harpy Defeat · Manual ruling",
                text,
                forms,
            )
        if data["kind"] == "harpy_bond_void":
            return (
                data,
                "Sin of Temptation",
                "File the Void change from the original Bond.",
                (self.bond_void_forms(data["harpy_bond_void"])),
            )
        if data["kind"] == "harpy_defeat_select":
            return (
                data,
                "Harpy Defeat · Outcome",
                "Choose the printed result for the actual source.",
                [
                    operation(outcome, label, *defeat_forms.outcome_fields(data, outcome))
                    for outcome, label in defeat_forms.outcome_options(data["tier"])
                    if self.outcome_available(outcome, data)
                ],
            )
        return (
            data,
            "Harpy Defeat · Response",
            "",
            [operation("answer", "File response", *defeat_forms.choice_fields(data))],
        )

    @staticmethod
    def outcome_available(outcome, data):
        if outcome in ("message", "plead", "kidnap"):
            return bool(data["girls"])
        if outcome == "rescue":
            return any(str(x.get("girl", "")).lower() == "harpy" for x in data["actors"])
        return True

    @staticmethod
    def bond_void_forms(data):
        if data["phase"] != "rewrite" or data.get("blocked"):
            return []
        forms = []
        if assets := data["assets"]:
            fields = [
                select("asset", "Eligible Asset", ((x["id"], x["label"]) for x in assets)),
                Field("account", "Describe the Void alteration", paragraph=True),
            ]
            if data["storage"]:
                fields.append(
                    select(
                        "storage",
                        "Use linked JANUS Void Storage?",
                        (("yes", "Store"), ("no", "Alter Asset permanently")),
                    )
                )
            if parts := data.get("casualty_parts"):
                fields.extend(
                    [
                        select(
                            "part",
                            "Optional Wounded God resistance",
                            ((x["id"], x["name"]) for x in parts),
                            required=False,
                        ),
                        Field("site", "Infected site if resisting", paragraph=True, required=False),
                    ]
                )
            forms.append(operation("bond_asset", "Alter original Asset", *fields))
        if source := data.get("sup"):
            replacements = (
                ("none", "None"),
                *((x["id"], x["label"] + " · " + x["family"]) for x in source["replacements"]),
            )
            forms.append(
                operation(
                    "bond_growth",
                    "Grow a Sup Asset",
                    select("family", "Asset family", ((x, x.title()) for x in source["families"])),
                    Field("name", "New Asset name"),
                    select("replace", "Replace existing Asset if at cap", replacements),
                    Field("account", "Describe the Void alteration", paragraph=True),
                )
            )
        return forms

    @staticmethod
    def bond_void_answer(verb, values):
        if verb == "bond_growth":
            replacement = pick(values, "replace")
            return ChoiceAnswer(
                text=account(values),
                fields={
                    "sup_name": values["name"],
                    "sup_family": pick(values, "family"),
                    "sup_replace": "" if replacement == "none" else replacement,
                },
            )
        options = [pick(values, "asset")]
        if pick(values, "storage") == "yes":
            options.append("storage")
        fields = {}
        if part := pick(values, "part"):
            fields["casualty_part"] = part
        if site := values.get("site"):
            fields["casualty_site_account"] = site
        return ChoiceAnswer(options=tuple(options), text=account(values), fields=fields)

    @staticmethod
    def passage_form(data):
        step = data["step"]
        options = tuple(APPROACHES.items())
        text = data.get("route") or data.get("account", "")
        if step == "propose":
            form = operation(step, "Record the Voidspace passage", ACCOUNT)
        elif step == "verify":
            form = operation(
                step, "Review the recorded passage", select("allow", "Review", REVIEW), ACCOUNT
            )
        elif step == "offer":
            form = operation(
                step,
                "Offer a Voidspace experience",
                select("method", "Experience", (*options, ("delegate", "Let the pilot choose"))),
                ACCOUNT,
            )
        elif step == "release_offer":
            form = operation(
                step,
                "Offer a return route",
                Field("account", "Route to the parked Frame", paragraph=True),
            )
        elif step in ("release_accept", "release_verify"):
            fields = [select("allow", "Return route", REVIEW)]
            if step == "release_verify":
                text += f"\nParked Frame · {data['destination']}"
                fields.append(ACCOUNT)
            form = operation(step, "File return decision", *fields)
        elif step == "gain":
            fields = [
                select(
                    "asset",
                    "Your response",
                    (
                        *((f"asset/{key}", name) for key, name in data["assets"].items()),
                        ("decline", "Decline"),
                    ),
                ),
                Field("account", "Alteration if accepted", required=False, paragraph=True),
            ]
            if data["method"] is None:
                fields.append(
                    select("method", "Your experience if accepted", options, required=False)
                )
            else:
                text += "\n" + APPROACHES[data["method"]]
            form = operation(step, "File your response", *fields)
        else:
            raise WorkflowError("The passage has no pending decision for this account.")
        return "Come to Me Now Once Again", text, [form]

    @staticmethod
    def defeat_form(kind, data):
        title = data["label"]
        if kind == "harpy_message":
            return title, data["account"], []
        if kind == "harpy_fight":
            return (
                title,
                "The original Harpy must become Helpless before this resolves.",
                [
                    operation(
                        "finish",
                        "File the proved Helpless condition",
                        select("confirm", "Decision", CONFIRM),
                    )
                ]
                if data["can_act"]
                else [],
            )
        if kind == "harpy_rift":
            forms = []
            if data["actors"]:
                forms.append(
                    operation(
                        "travel",
                        "Propose following through the Rift",
                        select(
                            "actor", "Your body", ((x["token"], x["label"]) for x in data["actors"])
                        ),
                        ACCOUNT,
                        NAVIGATION,
                    )
                )
            if data["can_close"]:
                forms.append(
                    operation("close", "Close this Rift", select("confirm", "Decision", CONFIRM))
                )
            return title, data["rift"]["description"], forms
        if kind in TRAVEL:
            return (
                title,
                "",
                [operation("travel", "File return proposal", ACCOUNT, NAVIGATION, DESTINATION)],
            )
        if not data["can_act"]:
            return title, "Awaiting the assigned reviewer.", []
        if kind == "harpy_route":
            route = data["route"]
            text = f"{route['account']}\nNavigation · {route['navigation']}"
            if route["destination"] is not None:
                text += f"\nDestination · {route['destination']}"
        else:
            facts = data["setup"]["facts"]
            identities = ", ".join(item["name"] for item in facts["identities"])
            tags = ", ".join(item["label"] for item in facts["tags"])
            text = (
                f"{facts['account']}\nHeat · {facts['heat']}\nLinked · {facts['linked']}"
                f"\nGirl cell · {facts['girl_cell']}\nFrame cell · {facts['frame_cell']}"
                f"\nIdentities · {identities}\nTags · {tags}"
            )
        return (
            title,
            text,
            [
                operation(
                    "review", "File factual review", select("allow", "Review", REVIEW), ACCOUNT
                )
            ],
        )

    def read(self, viewer, kind, identity):
        _, form = self.detail(viewer, kind, identity)
        return form | {
            "operations": [
                value | {"fields": form_fields(value["fields"])} for value in form["operations"]
            ]
        }

    def write(self, viewer, key, body):
        if body.keys() != {"kind", "id", "revision", "operation", "values"}:
            raise ValueError("Choose a filed specialist record.")
        kind, identity, revision = body["kind"], body["id"], body["revision"]
        verb, values = body["operation"], body["values"]
        if (
            not all(isinstance(x, str) and 0 < len(x) <= 300 for x in (kind, identity, verb))
            or type(revision) is not int
            or not isinstance(values, dict)
        ):
            raise ValueError("Use the original specialist decision.")
        data, form = self.detail(viewer, kind, identity)
        spec = next((row for row in form["operations"] if row["id"] == verb), None)
        if not spec or revision != form["revision"]:
            raise WorkflowError("This original specialist record changed. Reopen it to continue.")
        values = selected_fields(spec["fields"], values)
        args = viewer, key, identity, revision
        if kind == "excision":
            return self.excision.respond(
                *args, verb, doctor=pick(values, "doctor"), account=account(values)
            )
        if kind == "care":
            choice = pick(values, "care") or ""
            return self.care.respond(
                *args,
                target=pick(values, "target"),
                account=account(values),
                asset=choice.removeprefix("asset/") if choice.startswith("asset/") else None,
                alteration=values.get("alteration", ""),
            )
        if kind == "advancement":
            return self.advancement.select(*args, pick(values, "advancement"))
        if kind == "passage":
            if verb == "propose":
                return self.passage.start(*args, account(values))
            asset = pick(values, "asset")
            method = pick(values, "method")
            return self.passage.act(
                *args,
                verb,
                account=account(values),
                method=method if method != "delegate" else None,
                asset=asset.removeprefix("asset/")
                if asset and asset.startswith("asset/")
                else None,
                allow=(
                    asset != "decline"
                    if verb == "gain"
                    else pick(values, "allow") == "yes"
                    if "allow" in values
                    else None
                ),
            )
        if kind == "harpy_fight":
            return self.defeat.finish_fight(*args)
        if kind == "harpy_setup":
            return self.defeat.review_setup(*args, pick(values, "allow") == "yes", account(values))
        if kind == "harpy_route":
            return self.defeat.review_route(
                *args, allow=pick(values, "allow") == "yes", account=account(values)
            )
        if kind == "harpy_rift" and verb == "close":
            return self.defeat.close_rift(*args)
        if kind == "harpy_defeat" and verb == "begin":
            return self.defeat.begin(viewer, key, identity, channel=None)
        if kind == "harpy_defeat" and verb == "setup":
            preview = self.defeat.setup_preview(viewer, identity)
            actor = ActorRef.model_validate(preview["actor"])
            current = self.defeat.setup_preview_actor(viewer, actor)
            return self.defeat.propose_runtime(
                viewer, key, revision, defeat_forms.setup_facts(current, actor, values)
            )
        if kind == "defeat_roll":
            return self.defeat.roll(viewer, key, identity)
        if kind == "defeat_choice":
            if data["kind"] == "harpy_bond_void":
                return self.game.respond(*args, self.bond_void_answer(verb, values))
            if data["kind"] == "manual_adjudication":
                return self.adjudication.submit(*args, int(values["total"]), values["reason"])
            answer = (
                defeat_forms.choice_answer(data, values)
                if verb == "answer"
                else defeat_forms.outcome_answer(verb, values)
            )
            return self.defeat.respond(*args, answer)
        if kind == "leviathan_start":
            source, target = data["pairs"][int(verb)]
            selected = pick(values, "mode")
            return self.influence.begin(
                viewer,
                key,
                int(identity),
                revision,
                Declaration(
                    mode="give_tag" if selected == "give" else "succumb",
                    source=ActorRef.model_validate(source["ref"]),
                    subject=ActorRef.model_validate(target["ref"]),
                    source_sha256=source["source_sha256"],
                    subject_sha256=target["source_sha256"],
                    tag=None if selected == "give" else selected,
                    account=account(values),
                    reach_confirmed=True,
                ),
            )
        if kind == "leviathan_roll":
            return self.influence.roll(viewer, key, identity)
        if kind == "leviathan_choice":
            return self.game.respond(*args, response_answer(data, values))
        if kind == "repossession":
            return self.repossession.write(viewer, key, identity, revision, verb, data, values)
        if kind == "gorgon_counter":
            return self.counter.file(
                viewer,
                key,
                data,
                verb,
                account(values),
                pick(values, "weapon"),
                pick(values, "asset"),
            )
        if kind == "gorgon_counter_context":
            if verb == "begin":
                return self.counter.start(viewer, key, identity, data, int(pick(values, "heat")))
            facts = set(values.get("facts", ()))
            return self.counter.battle.confirm(
                viewer,
                key,
                revision,
                identity,
                opening="opening" in facts,
                reach="reach" in facts,
                outside_permission=False,
                indirect=False,
                core_capability_confirmed="core" in facts,
                evidence=account(values),
            )
        if kind == "npc_flirt":
            return self.game.respond(*args, npc_flirt_answer(data, values))
        if kind == "npc_followthrough":
            if verb == "perform":
                return self.npc_flirt.record_followthrough(
                    *args,
                    int(data["source"]["cast"]["channel"]),
                    account(values),
                    performed_action=values.get("action"),
                )
            return self.npc_flirt.confirm_followthrough(
                viewer,
                key,
                verb,
                revision,
                pick(values, "accepted") == "yes",
                account(values),
            )
        if kind == "gorgon_choice":
            return self.game.respond(*args, self.gorgon_answer(data, values))
        if kind == "npc_guard":
            return self.guard.perform_counter(
                viewer,
                key,
                data["parent"],
                identity,
                revision,
                pick(values, "move"),
                account(values),
                pick(values, "weapon"),
            )
        if kind.startswith("advancement_"):
            return self.harpy.write(viewer, key, kind, identity, data, values)
        if kind in HARPY_RECOVERY:
            return self.recovery.write(viewer, key, kind, identity, verb, data, values)
        return self.travel(viewer, key, kind, identity, revision, data, values)

    def travel(self, viewer, key, kind, identity, revision, data, values):
        if kind == "harpy_rift":
            actor = next(x["ref"] for x in data["actors"] if x["token"] == pick(values, "actor"))
            rift, escape, prior = identity, None, None
        elif kind == "harpy_return":
            route = data["route"]
            actor, rift, escape, prior = (
                route["actor"],
                route["rift"],
                route["escape_effect"],
                identity,
            )
        else:
            actor, rift, escape, prior = data["actor"], None, data["effect"], None
        destination = None
        if raw := values.get("destination"):
            x, y = raw.split(",")
            destination = int(x), int(y)
        return self.defeat.propose_route(
            viewer,
            key,
            revision,
            ActorRef.model_validate(actor),
            rift=rift,
            escape_effect=escape,
            return_of=prior,
            destination=destination,
            account=account(values),
            navigation=values["navigation"],
        )
