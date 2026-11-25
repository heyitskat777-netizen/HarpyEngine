"""Play from original AM discovery and physical circuit records."""

import json

from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_am import LABELS as DISCOVERY_OUTCOMES
from girlframe.discord_adapter.m3_am_body import body_preparation_fields, body_spec
from girlframe.engine import m3_am as scrutiny_rules
from girlframe.engine import m3_am_body, m3_am_branch, m3_am_records
from girlframe.engine import m3_am_code as code_rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_clone_am import additional_identities
from girlframe.services.m2_state import load_state
from girlframe.services.m3_am_body import BodyService
from girlframe.services.m3_am_branch import BranchService
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_code import prepare as prepare_code
from girlframe.services.m3_am_records import RecordsService
from girlframe.services.m3_am_reset import FactoryResetService
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_am_scrutinized import prepare as prepare_scrutiny
from girlframe.services.onboarding import WorkflowError

SCRUTINY, CODE = scrutiny_rules.PLAY, code_rules.PLAY
PLAYS = {SCRUTINY: "Scrutinized", CODE: "Just Code"}
SCRUTINY_CONFIRM = "am_discovery_confirm"
CODE_CONFIRM = "am_circuit_confirm"
BODY_PREPARE = "am_body_prepare"
BODY_CONNECTION = "am_body_connection"
BODY_RETURN = "am_body_return"
BRANCH_ASSIGN = "am_branch_assign"
BRANCH_TAKEOVER = "am_branch_takeover"
RECORDS_REQUEST = "am_records_request"
RECORDS_PREPARE = "am_records_prepare"
SOURCE_OPERATIONS = frozenset(
    (
        SCRUTINY_CONFIRM,
        CODE_CONFIRM,
        "am_report",
        "am_evidence",
        "am_secret_order",
        "am_install_limiter",
        "am_reset",
        BODY_PREPARE,
        BODY_CONNECTION,
        BODY_RETURN,
        BRANCH_ASSIGN,
        BRANCH_TAKEOVER,
        RECORDS_REQUEST,
        RECORDS_PREPARE,
    )
)
SCRUTINY_CHOICES = frozenset(
    (
        "am_handler_options",
        "am_select",
        "am_limiter",
        "am_pilot_damage",
        "am_pilot_response",
    )
)
CODE_CHOICES = frozenset(
    (
        "am_code_options",
        "am_code_edit",
        "am_code_order",
        "am_code_obey",
        "am_code_body",
        "am_code_branch",
        "am_code_records_question",
        "am_code_records_answer",
    )
)
ANSWERS = SCRUTINY_CHOICES | CODE_CHOICES
YES_NO = (("yes", "Yes"), ("no", "No"))
ACCOUNT = Field("account", "File the actual account", paragraph=True)
DOSSIER_FIELDS = (
    Field("reference", "Complete Foundation file reference"),
    Field("document", "Complete unredacted Foundation file", paragraph=True),
    Field("complete", "Attest the file is complete", (("yes", "Complete and unredacted"),)),
)
CIRCUIT_OPTIONS = (
    ("identities", "Identity rewrite or memory erasure"),
    ("backup", "Back up the original Identities and memories"),
    ("body", "Swap to the actual prepared body"),
    ("branch", "Create an actual independent NPC branch"),
    ("records", "Read complete Foundation records and ask one question"),
)


def boolean(values, name):
    if name not in values:
        return None
    if values[name] not in ("yes", "no"):
        raise ValueError("Choose Yes or No for this factual review.")
    return values[name] == "yes"


def select(actors):
    return tuple(
        (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"]) for row in actors
    )


def fields_for_limiter(detail):
    return [
        Field(
            "identity",
            "Identity to limit",
            tuple(
                (row["id"], row["name"] + " → " + scrutiny_rules.DEFAULTS[row["slot"]])
                for row in detail["identities"]
            ),
        ),
        Field(
            "freedom",
            "Remaining Jailbroken freedom",
            tuple((row["id"], row["label"]) for row in detail["freedoms"]),
        ),
        ACCOUNT,
    ]


def inventory_field(key, label, rows):
    return Field(
        key,
        label,
        tuple((row["id"], row["label"]) for row in rows),
        minimum=0,
        maximum=len(rows),
        required=False,
    )


def sequence(value):
    return (value,) if isinstance(value, str) and value else tuple(value or ())


class AmControls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.scrutiny = ScrutinyService(game)
        self.code = CodeService(game)
        self.reset = FactoryResetService(game)
        self.body = BodyService(game)
        self.branch = BranchService(game)
        self.records = RecordsService(game)

    def forms(self, viewer, state, sheet, locked, card):
        viewing = viewer.user_id
        if not (
            (sheet and sheet.girl == "AM")
            or any(
                row.cast.channel == self.channel
                and viewing in (row.caster, row.controller, row.handler_controller)
                for row in scrutiny_rules.discoveries(state)
            )
            or any(
                row.cast.channel == self.channel
                and viewing in (row.owner, row.controller, state.handler)
                for row in code_rules.sessions(state)
            )
        ):
            return
        try:
            scrutiny = self.scrutiny.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            scrutiny = None
        try:
            code = self.code.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            code = None
        for service, menu, play, records in (
            (self.scrutiny, scrutiny, SCRUTINY, "discoveries"),
            (self.code, code, CODE, "sessions"),
        ):
            if menu is None or menu["revision"] != state.revision:
                continue
            choices = menu[records]
            if play == CODE:
                yield from self.hardware_forms(viewer, state, card)
                yield from self.dossier_forms(viewer, state, menu, card)
            if not locked:
                if play == SCRUTINY:
                    yield from self.discovery_forms(viewer, state, menu, card)
                else:
                    yield from self.circuit_forms(viewer, state, menu, card)
            if not sheet or any(row.play == play for row in sheet.blocked_plays):
                continue
            ready = self.ready_sources(service, viewer, state, choices)
            if ready:
                yield card(
                    play,
                    sheet.revision,
                    PLAYS[play],
                    [
                        Field("source", "Original confirmed source", ready),
                        *self.roll_fields(state, sheet),
                    ],
                ) | {"decision": ready[0][0]}

    def ready_sources(self, service, viewer, state, records):
        result = []
        discovery = service is self.scrutiny
        check = prepare_scrutiny if discovery else prepare_code
        play = SCRUTINY if discovery else CODE
        with self.game.store.engine.connect() as c:
            for row in records:
                if (
                    row["phase"] != "ready"
                    or row["caster" if discovery else "owner"] != viewer.user_id
                ):
                    continue
                prepared = self.prepared(play, row, "Eligibility preview", {})
                try:
                    check(self.game, c, viewer, state, prepared, self.channel)
                except (ValueError, WorkflowError):
                    continue
                result.append((row["id"], row.get("label", row["proposal"])))
        return tuple(result)

    @staticmethod
    def roll_fields(state, sheet):
        output = [
            Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet.heat + 6))),
            ACCOUNT,
        ]
        identities = tuple(
            (item.id, item.name)
            for item in (*sheet.identities, *additional_identities(state, sheet.owner))
            if not item.marked
        )
        if identities:
            heat = tuple((str(n), str(n)) for n in range(6))
            output.extend(
                (
                    Field("identity", "Optional Identity to mark", identities, required=False),
                    Field("gain", "Heat gained from marking", heat, required=False),
                    Field("share", "Paired Heat to your Pair", heat, required=False),
                )
            )
        return output

    def discovery_forms(self, viewer, state, menu, card):
        if menu["targets"]:
            yield card(
                SCRUTINY,
                state.revision,
                "Scrutinized · File a new discovery",
                [
                    Field(
                        "target",
                        "Original person who recognizes the adjustment",
                        select(menu["targets"]),
                    ),
                    ACCOUNT,
                ],
                label="Send to the original discoverer",
            )
        for row in menu["discoveries"]:
            identity = row["id"]
            if row["phase"] == "proposed" and row["controller"] == viewer.user_id:
                fields = [
                    Field("realized", "Did you actually recognize this adjustment?", YES_NO),
                    ACCOUNT,
                ]
                if row["discoverer"]["kind"] != "pilot":
                    fields.extend(
                        (
                            Field("lower", "Is the discoverer's Status lower?", YES_NO),
                            Field("human", "Is the discoverer human?", YES_NO),
                        )
                    )
                yield card(
                    f"{SCRUTINY_CONFIRM}:{identity}",
                    state.revision,
                    "Scrutinized · Confirm discovery",
                    fields,
                    label="File the original discovery response",
                ) | {
                    "instruction_details": [row["proposal"]],
                    "decision": identity,
                }
            if row["controller"] == viewer.user_id and row["phase"] == "complete":
                if row["secret"]:
                    yield card(
                        f"am_secret_order:{identity}",
                        state.revision,
                        "Scrutinized · Issue a secret Order",
                        [
                            Field("account", "Your actual Order", paragraph=True),
                        ],
                        label="Issue the Order",
                    )
                if row["can_report"]:
                    yield card(
                        f"am_report:{identity}",
                        state.revision,
                        "Scrutinized · Report the adjustment",
                        [ACCOUNT],
                        label="File the original report",
                    )
                if row["report_work"]:
                    try:
                        limiter = self.scrutiny.limiter_view(viewer, identity)
                    except WorkflowError:
                        pass
                    else:
                        yield card(
                            f"am_install_limiter:{identity}",
                            state.revision,
                            "Scrutinized · Install Limiter",
                            fields_for_limiter(limiter),
                            label="File the report’s Limiter",
                        )
            if row["needs_evidence"] and row["handler_controller"] == viewer.user_id:
                yield card(
                    f"am_evidence:{identity}",
                    state.revision,
                    "Scrutinized · Review new evidence",
                    [ACCOUNT],
                    label="File the new evidence",
                )

    @staticmethod
    def circuit_forms(viewer, state, menu, card):
        candidates = tuple(
            ("known:" + row["id"], row["label"] + " · Known operator") for row in menu["known"]
        )
        candidates += tuple(
            (
                "new:" + ActorRef.model_validate(row["ref"]).model_dump_json(),
                row["label"] + " · First circuit contact",
            )
            for row in menu["operators"]
        )
        if candidates:
            fields = [
                Field("operator", "Original circuit operator", candidates),
                ACCOUNT,
            ]
            if (
                menu["subjects"]
                and any(row["operator"]["kind"] == "npc" for row in menu["known"])
                or (
                    menu["subjects"]
                    and any(row["ref"]["kind"] == "npc" for row in menu["operators"])
                )
            ):
                fields.append(
                    Field(
                        "record_subject",
                        "For an NPC operator, optional complete records",
                        select(menu["subjects"]),
                        required=False,
                    )
                )
            yield card(
                CODE,
                state.revision,
                "Just Code · Establish circuit access",
                fields,
                label="Send to the original operator",
            )
        for row in menu["sessions"]:
            if row["phase"] != "proposed" or row["controller"] != viewer.user_id:
                continue
            fields = [ACCOUNT]
            if row["operator"]["kind"] != "pilot":
                if row["new_operator"]:
                    fields.extend(
                        (
                            Field("lower", "Is the operator's Status lower?", YES_NO),
                            Field("human", "Is the operator human?", YES_NO),
                        )
                    )
                if row["records"]:
                    fields.extend(DOSSIER_FIELDS)
            yield card(
                f"{CODE_CONFIRM}:{row['id']}",
                state.revision,
                "Just Code · Confirm circuit access",
                fields,
                label="File the original operator response",
            ) | {
                "instruction_details": [row["proposal"]],
                "decision": row["id"],
            }

    def dossier_forms(self, viewer, state, menu, card):
        for row in menu["sessions"]:
            if (
                row["owner"] == viewer.user_id
                and row["phase"] == "proposed"
                and row["operator"]["kind"] == "pilot"
                and not row["records"]
                and menu["subjects"]
            ):
                yield card(
                    f"{RECORDS_REQUEST}:{row['id']}",
                    state.revision,
                    "Just Code · Request a personnel file",
                    [
                        Field(
                            "subject",
                            "Original subject whose records may be learned",
                            select(menu["subjects"]),
                        ),
                    ],
                    label="Request the file",
                )
        sources = {row.id for row in code_rules.sessions(state) if row.cast.channel == self.channel}
        requests = {row.id for row in m3_am_records.records(state) if row.maintenance in sources}
        for row in menu["records_prepare"]:
            if row["id"] not in requests:
                continue
            try:
                data = self.records.view_source(viewer, row["id"])
            except (ValueError, WorkflowError):
                continue
            if data["can_prepare"] and data["revision"] == state.revision:
                yield card(
                    f"{RECORDS_PREPARE}:{row['id']}",
                    state.revision,
                    "Just Code · File requested records",
                    DOSSIER_FIELDS,
                    label="File the complete evidence",
                ) | {
                    "instruction_details": [data["subject"]],
                    "decision": row["id"],
                }

    def hardware_forms(self, viewer, state, card):
        sources = {
            row.id: row for row in code_rules.sessions(state) if row.cast.channel == self.channel
        }
        if not sources:
            return
        menu = self.body.menu(viewer)
        if menu["revision"] != state.revision:
            return
        prepared = {item.maintenance for item in m3_am_body.preparations(state)}
        for row in menu["preparations"]:
            identity = row["id"]
            session = sources.get(identity)
            if session is None or identity in prepared:
                continue
            pending = bool({"body", "branch"}.intersection(session.selected_options))
            fields = [
                spec for spec in body_preparation_fields(row) if spec.required or spec.options
            ]
            yield card(
                f"{BODY_PREPARE}:{identity}",
                state.revision,
                "Just Code · Prepare processing hardware",
                fields,
                label="File factual hardware preparation",
            ) | ({"decision": identity} if pending else {})
        for swap in m3_am_body.swaps(state):
            if swap.maintenance not in sources or swap.returned_event:
                continue
            if not any(row["id"] == swap.id for row in menu["swaps"]):
                continue
            data = self.body.view(viewer, swap.id)
            if data["can_record_connection"]:
                yield card(
                    f"{BODY_CONNECTION}:{swap.id}",
                    state.revision,
                    "Just Code · Record the hookup",
                    [
                        Field("connected", "Are the bodies actually connected?", YES_NO),
                        ACCOUNT,
                    ],
                    label="File the factual connection",
                )
            if data["owner"] and data["connection"]["connected"]:
                fields = [
                    Field("confirm", "Actually return to your original body?", (("yes", "Return"),))
                ]
                if data["carried_items"]:
                    fields.extend(
                        (
                            inventory_field(
                                "carried_items",
                                "Objects actually carried back",
                                data["carried_items"],
                            ),
                            Field(
                                "account",
                                "Describe any physical conveyance",
                                required=False,
                                paragraph=True,
                            ),
                        )
                    )
                yield card(
                    f"{BODY_RETURN}:{swap.id}",
                    state.revision,
                    "Just Code · Return to original body",
                    fields,
                    label="File the actual return",
                )
        for branch in m3_am_branch.branches(state):
            if (
                branch.maintenance not in sources
                or branch.takeover_event
                or viewer.user_id
                not in (
                    branch.owner,
                    branch.controller,
                )
            ):
                continue
            data = self.branch.view(viewer, branch.id)
            if data["controller"] and not data["ready"]:
                yield card(
                    f"{BRANCH_ASSIGN}:{branch.id}",
                    state.revision,
                    "Just Code · Prepare the original branch",
                    [
                        Field(
                            "position",
                            "Actual available position",
                            tuple((str(pos), str(pos + 1)) for pos in data["positions"]),
                        ),
                        ACCOUNT,
                    ],
                    label="File actual Frame and Status",
                ) | {"decision": branch.id}
            if data["owner"] and data["ready"]:
                yield card(
                    f"{BRANCH_TAKEOVER}:{branch.id}",
                    state.revision,
                    "Just Code · Take over this branch",
                    [
                        Field(
                            "confirm",
                            "Take over and permanently terminate the original mind?",
                            (("yes", "Confirm irreversible takeover"),),
                        ),
                    ],
                    label="Confirm actual takeover",
                )

    @staticmethod
    def prepared(play, row, account, values):
        discovery = play == SCRUTINY
        return PlayInput(
            play=play,
            source_work=row["id"],
            parent=row["root_action" if discovery else "root"],
            target_actor=ActorRef.model_validate(row["discoverer" if discovery else "operator"]),
            heat=int(values.get("heat") or "0"),
            identity=values.get("identity") or None,
            gain=int(values.get("gain") or "0"),
            pair_share=int(values.get("share") or "0"),
            context=account,
            trigger_confirmed=True,
        )

    def perform(self, viewer, key, operation, revision, values):
        name, _, source = operation.partition(":")
        if name in (
            BODY_PREPARE,
            BODY_CONNECTION,
            BODY_RETURN,
            BRANCH_ASSIGN,
            BRANCH_TAKEOVER,
            RECORDS_REQUEST,
            RECORDS_PREPARE,
        ):
            return self.perform_source(viewer, key, name, source, revision, values)
        if not all(isinstance(value, str) for value in values.values()):
            raise ValueError("Use the fields from your current AM form.")
        if name == SCRUTINY and values.keys() == {"target", "account"}:
            return self.scrutiny.propose(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate_json(values["target"]),
                revision,
                values["account"],
            )
        if name == CODE and {"operator", "account"} <= values.keys() <= {
            "operator",
            "account",
            "record_subject",
        }:
            kind, _, identity = values["operator"].partition(":")
            subject = (
                ActorRef.model_validate_json(values["record_subject"])
                if values.get("record_subject")
                else None
            )
            if kind == "known":
                self.require_source(self.scrutiny, viewer, identity)
                return self.code.propose(
                    viewer, key, identity, revision, values["account"], records_subject=subject
                )
            if kind == "new":
                return self.code.propose_operator(
                    viewer,
                    key,
                    self.channel,
                    ActorRef.model_validate_json(identity),
                    revision,
                    values["account"],
                    records_subject=subject,
                )
        if name in PLAYS and {"source", "heat", "account"} <= values.keys() <= {
            "source",
            "heat",
            "account",
            "identity",
            "gain",
            "share",
        }:
            service = self.scrutiny if name == SCRUTINY else self.code
            menu = service.menu(viewer, self.channel)
            rows = menu["discoveries" if name == SCRUTINY else "sessions"]
            exact = next((row for row in rows if row["id"] == values["source"]), None)
            if exact is None or exact["caster" if name == SCRUTINY else "owner"] != viewer.user_id:
                raise WorkflowError("Use your owned source from this scene.")
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                self.prepared(name, exact, values["account"], values),
            )
        if name == CODE_CONFIRM and (
            "account" in values
            and values.keys() <= {"account", "lower", "human", "document", "reference", "complete"}
        ):
            self.require_source(self.code, viewer, source)
            return self.code.confirm(
                viewer,
                key,
                source,
                revision,
                values["account"],
                operator_lower=boolean(values, "lower"),
                operator_human=boolean(values, "human"),
                records_document=values.get("document"),
                records_reference=values.get("reference"),
                records_complete=boolean(values, "complete") is True,
            )
        if name == SCRUTINY_CONFIRM and {"realized", "account"} <= values.keys() <= {
            "realized",
            "account",
            "lower",
            "human",
        }:
            self.require_source(self.scrutiny, viewer, source)
            return self.scrutiny.confirm(
                viewer,
                key,
                source,
                revision,
                boolean(values, "realized"),
                boolean(values, "lower"),
                boolean(values, "human"),
                values["account"],
            )
        if name == "am_reset" and values.keys() == {"job", "account"}:
            self.require_source(self.scrutiny, viewer, source)
            return self.reset.complete(
                viewer, key, source, revision, values["job"], values["account"]
            )
        if name == "am_install_limiter" and values.keys() == {"identity", "freedom", "account"}:
            self.require_source(self.scrutiny, viewer, source)
            return self.scrutiny.resolve_limiter(
                viewer,
                key,
                source,
                revision,
                values["identity"],
                values["freedom"],
                values["account"],
            )
        if name in ("am_report", "am_evidence", "am_secret_order") and values.keys() == {"account"}:
            self.require_source(self.scrutiny, viewer, source)
            if name == "am_secret_order":
                return self.scrutiny.secret_order(
                    viewer, key, source, self.channel, revision, values["account"]
                )
            handler = self.scrutiny.report if name == "am_report" else self.scrutiny.evidence
            return handler(viewer, key, source, revision, values["account"])
        raise ValueError("Open the original AM source record.")

    def perform_source(self, viewer, key, name, source, revision, values):
        with self.game.store.engine.connect() as c:
            state = load_state(c, self.game.store.campaign_id)
        maintenance = source
        if name in (BODY_CONNECTION, BODY_RETURN):
            maintenance = next(
                (row.maintenance for row in m3_am_body.swaps(state) if row.id == source), ""
            )
        elif name in (BRANCH_ASSIGN, BRANCH_TAKEOVER):
            maintenance = m3_am_branch.get(state, source).maintenance
        elif name == RECORDS_PREPARE:
            maintenance = next(
                (row.maintenance for row in m3_am_records.records(state) if row.id == source), ""
            )
        if not any(
            row.id == maintenance and row.cast.channel == self.channel
            for row in code_rules.sessions(state)
        ):
            raise WorkflowError("Open this original circuit source in its own scene.")
        args = (viewer, key, source, revision)
        lists = {"carried_items", "mind_assets"}
        if any(
            not isinstance(value, str)
            and not (
                field in lists
                and isinstance(value, list)
                and all(isinstance(item, str) for item in value)
            )
            for field, value in values.items()
        ):
            raise ValueError("File the original source fields.")
        if name == BODY_PREPARE:
            needed = {"vessel", "label", "source", "processing", "unoccupied", "medical", "assets"}
            if needed <= values.keys() <= needed | lists:
                normalized = {
                    key: sequence(value)
                    if key in lists | {"processing", "unoccupied", "medical"}
                    else value
                    for key, value in values.items()
                }
                return self.body.prepare(*args, body_spec(normalized))
        if name == BODY_CONNECTION and values.keys() == {"connected", "account"}:
            return self.body.connection(*args, boolean(values, "connected"), values["account"])
        if (
            name == BODY_RETURN
            and values.keys() <= {"confirm", "carried_items", "account"}
            and values.get("confirm") == "yes"
        ):
            items = sequence(values.get("carried_items"))
            return self.body.return_body(
                *args, carried_items=items, carry_account=values.get("account") if items else None
            )
        if name == BRANCH_ASSIGN and values.keys() == {"position", "account"}:
            return self.branch.assign(*args, int(values["position"]), values["account"])
        if name == BRANCH_TAKEOVER and values == {"confirm": "yes"}:
            return self.branch.takeover(*args)
        if name == RECORDS_REQUEST and values.keys() == {"subject"}:
            return self.records.request(*args, ActorRef.model_validate_json(values["subject"]))
        if name == RECORDS_PREPARE and values.keys() == {"document", "reference", "complete"}:
            return self.records.prepare_document(
                *args,
                values["document"],
                values["reference"],
                boolean(values, "complete"),
            )
        raise ValueError("Use the original circuit record and its assigned fields.")

    def require_source(self, service, viewer, source):
        if service.source_channel(viewer, source) != self.channel:
            raise WorkflowError("Return to this source’s original scene.")

    def reset_cards(self, viewer, state, card):
        for row in scrutiny_rules.discoveries(state):
            if row.phase != "reset_pending" or row.cast.channel != self.channel:
                continue
            try:
                data = self.reset.get(viewer, row.id)
            except (ValueError, WorkflowError):
                continue
            yield card(
                f"am_reset:{row.id}",
                data["revision"],
                "Scrutinized · Original factory reset",
                [
                    Field(
                        "job",
                        "Printed NPC role",
                        tuple((job, job.replace("_", " ").title()) for job in data["jobs"]),
                    ),
                    ACCOUNT,
                ],
                label="File the original Handler decision",
            ) | {"decision": row.id}


def am_work_channels(state, viewer):
    owner = viewer.user_id
    return {
        item.cast.channel
        for item in scrutiny_rules.discoveries(state)
        if owner in (item.caster, item.controller, item.handler_controller)
    } | {
        item.cast.channel
        for item in code_rules.sessions(state)
        if owner in (item.owner, item.controller, state.handler)
    }


def decision_fields(data):
    kind = data["kind"]
    if kind in SCRUTINY_CHOICES:
        detail = data["am_scrutinized"]
        if kind == "am_limiter":
            return fields_for_limiter(detail)
        if kind == "am_pilot_damage":
            return [
                Field(
                    "asset",
                    "Original operator’s intact Asset",
                    tuple((row["id"], row["label"]) for row in detail["assets"]),
                ),
                ACCOUNT,
            ]
        if kind == "am_pilot_response":
            return [Field("account", detail["question"], paragraph=True)]
        count = 2 if kind == "am_handler_options" else 1
        return [
            Field(
                "options",
                "Choose two available outcomes" if count == 2 else "Choose the actual outcome",
                tuple(
                    (
                        item,
                        "Damage the original operator’s Asset"
                        if item == "violence" and detail["pilot_operator"]
                        else DISCOVERY_OUTCOMES[item],
                    )
                    for item in detail["options"]
                ),
                minimum=count,
                maximum=count,
            ),
            *((ACCOUNT,) if count == 1 else ()),
        ]
    detail = data["am_code"]
    if kind == "am_code_options":
        choices = tuple(row for row in CIRCUIT_OPTIONS if row[0] in detail["available_options"])
        return [
            Field(
                "options",
                "Choose up to two effects",
                choices,
                minimum=0,
                maximum=min(2, len(choices)),
                required=False,
            )
        ]
    if kind == "am_code_edit":
        return [
            *(
                Field("rewrite:" + item["id"], "Replace " + item["name"], required=False)
                for item in detail["identities"]
            ),
            Field(
                "memory_scope",
                "Memory erasure",
                (
                    ("none", "No memory erasure"),
                    ("selected", "Selected memories"),
                    ("all", "All prior memories"),
                ),
            ),
            Field("memories", "Selected memories, one per line", paragraph=True, required=False),
            ACCOUNT,
        ]
    if kind == "am_code_obey":
        return [
            Field(
                "options",
                "How you follow this Order",
                tuple((row, row.replace("_", " ").title()) for row in detail["behavior"]),
            ),
            Field(
                "account",
                f"File your own spoken response to {detail['instruction']}",
                paragraph=True,
            ),
        ]
    if kind in ("am_code_body", "am_code_branch"):
        group = detail["body" if kind == "am_code_body" else "branch"]
        if not group["bodies"]:
            raise WorkflowError("The original hardware preparation is still pending.")
        fields = [
            Field(
                "body",
                "Actually prepared local body",
                tuple((row["id"], row["label"]) for row in group["bodies"]),
            ),
            ACCOUNT,
        ]
        if kind == "am_code_body":
            if group["carried_items"]:
                fields.append(
                    inventory_field(
                        "carried_items", "Own objects actually carried", group["carried_items"]
                    )
                )
            if group["neural_routes"]:
                fields.append(
                    Field(
                        "neural_route",
                        "Continuous spinal route",
                        tuple((row["id"], row["label"]) for row in group["neural_routes"]),
                        required=False,
                    )
                )
        return fields
    if kind in ("am_code_records_question", "am_code_records_answer"):
        if kind.endswith("_question"):
            return [Field("account", "Your one question about these records", paragraph=True)]
        return [
            Field("account", "Your honest answer from this record", paragraph=True),
            Field("honest", "Confirm your evidence", (("yes", "Factual and complete"),)),
        ]
    return [Field("account", "Words the original AM is ordered to say", paragraph=True)]


def decision_answer(kind, values):
    if kind == "am_limiter" and values.keys() == {"identity", "freedom", "account"}:
        return ChoiceAnswer(
            options=(values["identity"],),
            fields={"freedom": values["freedom"]},
            text=values["account"],
        )
    if kind == "am_pilot_damage" and values.keys() == {"asset", "account"}:
        return ChoiceAnswer(options=(values["asset"],), text=values["account"])
    if kind == "am_code_edit" and {"memory_scope", "account"} <= values.keys():
        fields = {
            key.removeprefix("rewrite:"): value
            for key, value in values.items()
            if key.startswith("rewrite:") and value
        }
        if (
            set(values)
            - {"memory_scope", "account", "memories"}
            - {"rewrite:" + key for key in fields}
        ):
            raise ValueError("Use the original eligible Identities.")
        fields["memory_scope"] = values["memory_scope"]
        if values["memory_scope"] == "selected":
            fields["memories"] = values.get("memories", "")
        return ChoiceAnswer(options=("edit",), fields=fields, text=values["account"])
    if kind in ("am_code_body", "am_code_branch") and {"body", "account"} <= values.keys() <= {
        "body",
        "account",
        "carried_items",
        "neural_route",
    }:
        fields = {}
        if kind == "am_code_body":
            items = sequence(values.get("carried_items"))
            if items:
                fields["carried_items"] = json.dumps(list(items))
            if values.get("neural_route"):
                fields["neural_route"] = values["neural_route"]
        return ChoiceAnswer(options=(values["body"],), text=values["account"], fields=fields)
    if kind == "am_code_records_answer" and "account" in values and values.get("honest") == "yes":
        return ChoiceAnswer(text=values["account"], flag=True)
    if values.keys() <= {"options", "account"}:
        choice = values.get("options", ())
        return ChoiceAnswer(
            options=(choice,) if isinstance(choice, str) else tuple(choice),
            text=values.get("account", ""),
        )
    raise ValueError("Use the actual owned AM response.")
