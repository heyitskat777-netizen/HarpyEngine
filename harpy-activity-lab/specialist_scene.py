"""Scene entry points for the native Changeling and Red Queen workflows."""

import json

from girlframe.engine import m3_changeling, m3_red_queen
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_changeling import (
    ChangelingService,
)
from girlframe.services.m3_changeling import (
    require_rule as require_changeling,
)
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_red_queen import (
    RedQueenService,
    prepare as prepare_queen,
    prove_context,
    transfer_options,
)
from girlframe.services.m3_red_queen import (
    require_rule as require_queen,
)
from girlframe.services.onboarding import WorkflowError

from native_scene_forms import NATIVE_OPERATIONS
from native_scene_rolls import NativeSceneRolls
from play_continuations import ACCOUNT, field, operation

BLANK = "changeling_blank_slate"
CLAY = "changeling_body_of_clay"
MEMORY = "red_queen_memory"
TRANSFER = "red_queen_transfer"
CONSULT = "red_queen_consult"
PANOPTICON = "red_queen_panopticon"
PLAYS = {
    BLANK: "Blank Slate",
    CLAY: "Body of Clay",
    MEMORY: "Red Queen · Memory Extraction",
    CONSULT: "Red Queen · Consult the Court",
    PANOPTICON: "Red Queen · One-Girl Panopticon",
}
TRANSFER_KINDS = {
    "sex": "Completed intimacy",
    "bond": "Weakened Bond",
    "punishment": "Completed Punishment",
}


def as_ref(value):
    return ActorRef.model_validate_json(value)


def cast_labels(actors):
    return [(x["ref"].model_dump_json(), x["label"]) for x in actors]


class SpecialistScene:
    def __init__(self, game, channel):
        self.game = game
        self.channel = channel
        self.changeling = ChangelingService(game)
        self.queen = RedQueenService(game)
        self.native = NativeSceneRolls(game, channel)

    def view(self, viewer, room):
        native = [
            card | {"room": room[0], "room_name": room[1]} for card in self.native.view(viewer)
        ]
        try:
            with self.game.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                self.game.unpaused(c)
                state = load_state(c, self.game.store.campaign_id)
                if not any(
                    x.frame in (m3_changeling.FRAME, m3_red_queen.FRAME)
                    for x in state.sheets.values()
                ):
                    return native
                cast = _cast(self.game, c, state, self.channel)
                bound = profiles(c, self.game.store.campaign_id)
                actors = []
                for role in cast.roles:
                    actor = resolve(
                        state, role.actor, bound, require_current_profile=False
                    )
                    if actor.alive:
                        actors.append(
                            {
                                "ref": role.actor,
                                "controller": role.controller,
                                "label": actor.label,
                            }
                        )
                mine = [x for x in actors if x["controller"] == viewer.user_id]
                if not mine and viewer.user_id != state.handler:
                    return native
                sheet = state.sheets.get(str(viewer.user_id))
                frames = {
                    actor["ref"]: state.sheets[actor["ref"].entity].frame
                    for actor in actors
                    if actor["ref"].kind == "pilot"
                    and actor["ref"].entity in state.sheets
                }
                changelings = []
                queens = []
                for actor in actors:
                    ref = actor["ref"]
                    try:
                        if frames.get(ref) == m3_changeling.FRAME:
                            require_changeling(
                                self.game, c, state, ref, m3_changeling.BLANK
                            )
                            changelings.append(actor)
                        if frames.get(ref) == m3_red_queen.FRAME:
                            require_queen(
                                self.game,
                                c,
                                state,
                                ref,
                                m3_red_queen.COURT,
                                initialize_court=True,
                            )
                            queens.append(actor)
                    except (ValueError, WorkflowError):
                        continue
                # Court discovery is based on the engine's initialized Court, including a
                # Queen who has transferred the office but still owns this original Frame.
                courts = m3_red_queen.records(state, m3_red_queen.Court)
                court_actors = {court.actor for court in courts}
                queens = [x for x in actors if x["ref"] in court_actors or x in queens]
        except (ValueError, WorkflowError):
            return native

        cards = []
        if changelings:
            cards += self.changeling_cards(
                viewer, state, sheet, actors, mine, changelings
            )
        if queens:
            cards += self.queen_cards(
                viewer, state, sheet, actors, mine, queens, courts
            )
        if (
            not cards
            and sheet
            and sheet.frame in (m3_changeling.FRAME, m3_red_queen.FRAME)
        ):
            notice = self.card(
                state, "specialist-review", sheet.frame + " · Specialist work", []
            )
            cards.append(
                notice
                | {
                    "scene": "Join an applicable scene and establish the required source in HarpyEngine."
                }
            )
        return native + [card | {"room": room[0], "room_name": room[1]} for card in cards]

    @staticmethod
    def card(state, identity, title, forms, sheet=None):
        return {
            "id": identity,
            "revision": state.revision,
            "action": "specialist_scene",
            "instruction": title,
            "operations": forms,
            **({"game_revision": sheet.revision} if sheet else {}),
        }

    @staticmethod
    def costs(sheet):
        return [
            field(
                "heat",
                "Heat to spend",
                [(str(n), str(n)) for n in range(sheet.heat + 6)],
            ),
            field(
                "identity",
                "Optional Identity to mark",
                [(x.id, x.name) for x in sheet.identities if not x.marked],
                required=False,
            ),
            field(
                "gain",
                "Heat gained from marking",
                [(str(n), str(n)) for n in range(6)],
                required=False,
            ),
            field(
                "pair_share",
                "Heat sent to your Pair",
                [(str(n), str(n)) for n in range(6)],
                required=False,
            ),
            ACCOUNT,
        ]

    def changeling_cards(self, viewer, state, sheet, actors, mine, changelings):
        menu = self.changeling.menu(viewer, self.channel)
        forms = []
        owns_frame = any(x in mine for x in changelings)
        for speaker in mine:
            other = [x for x in actors if x["ref"] != speaker["ref"]]
            label = speaker["label"]
            encoded = speaker["ref"].model_dump_json()
            if speaker["ref"].kind in ("pilot", "handler"):
                forms.append(
                    operation(
                        "body:" + encoded, "Record original body · " + label, [ACCOUNT]
                    )
                )
            appearances = [
                x
                for x in menu["appearances"]
                if x["actor"] == speaker["ref"].model_dump(mode="json")
            ]
            if appearances and (
                targets := cast_labels([x for x in changelings if x in other])
            ):
                forms.append(
                    operation(
                        "show-appearance",
                        "Disclose your appearance · " + label,
                        [
                            field(
                                "appearance",
                                "Your recorded appearance",
                                [(x["id"], x["label"]) for x in appearances],
                            ),
                            field("target", "Present Changeling", targets),
                        ],
                    )
                )
            elif not appearances and any(x in changelings for x in other):
                forms.append(
                    operation(
                        "appearance:" + encoded,
                        "Record your appearance · " + label,
                        [
                            field(key, caption)
                            for key, caption in m3_changeling.FACET_LABELS.items()
                        ],
                    )
                )
            if targets := cast_labels([x for x in changelings if x in other]):
                forms.append(
                    operation(
                        "define:" + encoded,
                        "Define a Changeling · " + label,
                        [
                            field("target", "Addressed Changeling", targets),
                            field("words", "Your defining words"),
                        ],
                    )
                )
            conversation = cast_labels(
                other
                if speaker in changelings
                else [x for x in changelings if x in other]
            )
            if conversation:
                forms.append(
                    operation(
                        "talk:" + encoded,
                        "Record conversation · " + label,
                        [
                            field("target", "Addressed person", conversation),
                            field("words", "Your part of the conversation"),
                        ],
                    )
                )
        forms += self.overstep_forms(viewer, state, mine, actors)
        speeches = [
            x for x in menu["conversations"] if self.speech_in_scene(state, x["id"])
        ]
        if speeches:
            fields = [
                (
                    json.dumps({"speech": item["id"], "identity": identity}),
                    label + " · " + item["label"],
                )
                for item in speeches
                for identity, label in item["identities"]
            ]
            if fields:
                forms.append(
                    operation(
                        "disclose",
                        "Disclose one of your Identities",
                        [
                            field(
                                "disclosure", "Identity and conversation entry", fields
                            )
                        ],
                    )
                )
        if owns_frame and sheet:
            ready = {row["id"] for row in menu["plays"]}
            blocked = {entry.play for entry in sheet.blocked_plays}
            definitions = [
                (x["id"], x["label"])
                for x in menu["definitions"]
                if x["actor"]["kind"] == "pilot"
                and x["actor"]["entity"] == str(viewer.user_id)
            ]
            if BLANK in ready - blocked and definitions:
                forms.append(
                    operation(
                        BLANK,
                        "Start Blank Slate",
                        [
                            field("source", "Original defining words", definitions),
                            *self.costs(sheet),
                        ],
                    )
                )
            if CLAY in ready - blocked:
                forms.append(operation(CLAY, "Start Body of Clay", self.costs(sheet)))
            elif any(x["id"] == m3_changeling.CLAY for x in menu["requisitions"]):
                forms.append(operation("buy-clay", "Acquire Body of Clay", [ACCOUNT]))
        return (
            [
                self.card(
                    state, "changeling", "CHANGELING · Identity effects", forms, sheet
                )
            ]
            if forms
            else []
        )

    def overstep_forms(self, viewer, state, mine, actors):
        from girlframe.services.m3_changeling_identity import can_lower_status

        controlled = {x["ref"] for x in mine}
        present = {x["ref"]: x["label"] for x in actors}
        pushes = {x.session for x in m3_changeling.records(state, m3_changeling.Push)}
        statements = {
            x.session: x
            for x in m3_changeling.records(state, m3_changeling.Speech)
            if x.kind == "push"
            and x.controller == viewer.user_id
            and not x.used_by
            and x.cast.channel == self.channel
        }
        forms = []
        with self.game.store.engine.connect() as c:
            for source in m3_changeling.records(state, m3_changeling.Session):
                if (
                    source.play != BLANK
                    or source.cast.channel != self.channel
                    or not 8 <= source.total <= 10
                    or not source.completed_event
                    or source.target not in controlled
                    or source.actor not in present
                    or source.id in pushes
                    or not can_lower_status(self.game, c, state, source.target)
                ):
                    continue
                if statement := statements.get(source.id):
                    forms.append(
                        operation(
                            "overstep-tag:" + statement.id,
                            "Give a Tag and lower your Status · "
                            + present[source.actor],
                            [field("tag", "Your Tag")],
                        )
                    )
                else:
                    forms.append(
                        operation(
                            "overstep:" + source.id,
                            "Push the original definition · " + present[source.actor],
                            [field("words", "Your words when you push the matter")],
                        )
                    )
        return forms

    def speech_in_scene(self, state, identity):
        return any(
            row.id == identity and row.cast.channel == self.channel
            for row in m3_changeling.records(state, m3_changeling.Speech)
        )

    def queen_cards(self, viewer, state, sheet, actors, mine, queens, courts):
        forms = []
        own = next((x for x in queens if x in mine), None)
        for queen in queens:
            if not any(court.actor == queen["ref"] for court in courts):
                continue
            eligible = [
                x
                for x in actors
                if x["ref"] != queen["ref"]
                and (x in mine or viewer.user_id == state.handler)
                and x["ref"].kind in ("pilot", "npc")
            ]
            if eligible:
                forms.append(
                    operation(
                        "brain:" + queen["ref"].model_dump_json(),
                        "Confirm restrained brain access · " + queen["label"],
                        [
                            field("target", "Affected person", cast_labels(eligible)),
                            ACCOUNT,
                        ],
                    )
                )
        if own and sheet:
            forms += self.queen_owner_forms(viewer, state, own, sheet, courts)
        return (
            [
                self.card(
                    state, "red-queen", "Red Queen · Court operations", forms, sheet
                )
            ]
            if forms
            else []
        )

    def queen_owner_forms(self, viewer, state, own, sheet, courts):
        forms = []
        menu = self.queen.menu(viewer, self.channel)
        if menu["can_initialize"]:
            return [operation("initialize", "Initialize the approved Court", [])]
        allowed = next(
            (x for x in menu["requisitions"] if x["id"] == m3_red_queen.MEMORY), None
        )
        actor = own["ref"]
        with self.game.store.engine.connect() as c:
            access = Access(self.game.store)
            if self.queen_ready(c, viewer, state, CONSULT) and not any(
                item.play == CONSULT for item in sheet.blocked_plays
            ):
                forms.append(operation(CONSULT, "Consult the Court", self.costs(sheet)))
            try:
                access.require_specialist_rule(m3_red_queen.PANOPTICON)
            except (ValueError, WorkflowError):
                pass
            else:
                forms.extend(self.panopticon_forms(c, viewer, state, sheet, actor, menu))
            try:
                access.require_specialist_rule(m3_red_queen.MEMORY)
            except (ValueError, WorkflowError):
                memory_ready = False
            else:
                memory_ready = True
            if memory_ready and allowed and not allowed["held"]:
                forms.append(
                    operation(
                        "buy", "Acquire Memory Extraction (2 Permissions)", [ACCOUNT]
                    )
                )
            if (
                memory_ready
                and MEMORY in dict(menu["plays"])
                and not any(entry.play == MEMORY for entry in sheet.blocked_plays)
            ):
                contexts = []
                for context in m3_red_queen.records(state, m3_red_queen.Context):
                    if (
                        context.actor != actor
                        or context.kind != "brain"
                        or context.cast.channel != self.channel
                    ):
                        continue
                    try:
                        prove_context(self.game, c, state, context.id)
                    except (ValueError, WorkflowError):
                        continue
                    label = next(
                        (
                            x["label"]
                            for x in menu["targets"]
                            if x["ref"] == context.target.model_dump(mode="json")
                        ),
                        "Original subject",
                    )
                    contexts.append(
                        (
                            json.dumps(
                                {
                                    "id": context.id,
                                    "target": context.target.model_dump(mode="json"),
                                }
                            ),
                            label,
                        )
                    )
                if contexts:
                    forms.append(
                        operation(
                            MEMORY,
                            "Start Memory Extraction",
                            [
                                field("memory", "Confirmed brain access", contexts),
                                *self.costs(sheet),
                            ],
                        )
                    )
            court = next((x for x in courts if x.actor == actor), None)
            if not court:
                return forms
            try:
                require_queen(self.game, c, state, actor, m3_red_queen.TRANSFER)
            except (ValueError, WorkflowError):
                return forms
            ams = [
                (x.id, x.role)
                for x in m3_red_queen.ams(state, court)
                if x.bearer == actor
            ]
            assigned = {
                (x.target.token, x.source)
                for x in m3_red_queen.records(state, m3_red_queen.Assignment)
                if x.previous == actor
            }
            sources = []
            if ams:
                for target in menu["targets"]:
                    other = ActorRef.model_validate(target["ref"])
                    if other != actor:
                        for kind, label in TRANSFER_KINDS.items():
                            for entry in transfer_options(
                                self.game, c, state, actor, other, kind
                            ):
                                if (other.token, entry["id"]) not in assigned:
                                    source = json.dumps(
                                        {
                                            "id": entry["id"],
                                            "kind": kind,
                                            "target": target["ref"],
                                        }
                                    )
                                    sources.append(
                                        (
                                            source,
                                            f"{target['label']} · {label} · {entry['label'].split()[-1]}",
                                        )
                                    )
            if sources:
                forms.append(
                    operation(
                        TRANSFER,
                        "Transfer a self-borne AM",
                        [
                            field("am", "AM you currently bear", ams),
                            field("source", "Recipient and completed source", sources),
                        ],
                    )
                )
        return forms

    def queen_ready(self, connection, viewer, state, play, target=None, source=None):
        try:
            prepare_queen(self.game, connection, viewer, state, PlayInput(
                play=play, target_actor=target, source_work=source,
                heat=0, context="Eligibility preview", trigger_confirmed=True,
            ), self.channel)
        except (ValueError, WorkflowError):
            return False
        return True

    def panopticon_forms(self, connection, viewer, state, sheet, actor, menu):
        if PANOPTICON not in dict(menu["plays"]):
            return [operation("buy-panopticon", "Acquire One-Girl Panopticon", [ACCOUNT])]
        if any(item.play == PANOPTICON for item in sheet.blocked_plays):
            return []
        observed = []
        other = [row for row in menu["targets"] if row["ref"] != menu["actor"]]
        labels = {row["id"]: row["label"] for row in other}
        for context in menu["contexts"]:
            if context["kind"] != "distant":
                continue
            target = ActorRef.model_validate(context["target"])
            if self.queen_ready(connection, viewer, state, PANOPTICON, target, context["id"]):
                observed.append((
                    json.dumps({"id": context["id"], "target": context["target"]}),
                    labels.get(target.token, "Original observed person"),
                ))
        forms = []
        if other:
            forms.append(operation("distant:" + actor.model_dump_json(), "Record distant observation", [
                field("target", "Person actually observed", [
                    (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"]) for row in other
                ]),
                ACCOUNT,
            ]))
        if observed:
            forms.append(operation(PANOPTICON, "Start One-Girl Panopticon", [
                field("observation", "Original distant observation", observed), *self.costs(sheet),
            ]))
        return forms

    def perform(self, viewer, key, data):
        revision = data["revision"]
        op, values = (data["answer"][k] for k in ("operation", "values"))
        if (
            type(revision) is not int
            or not isinstance(values, dict)
            or not isinstance(op, str)
        ):
            raise ValueError("Reopen the assigned specialty form.")
        if op.partition(":")[0] in NATIVE_OPERATIONS:
            return self.native.perform(viewer, key, op, revision, values)
        action, _, payload = op.partition(":")
        if action in ("define", "talk"):
            return self.changeling.speak(
                viewer,
                key,
                revision,
                self.channel,
                as_ref(payload),
                as_ref(values["target"]),
                "definition" if action == "define" else "conversation",
                values["words"],
            )
        if action == "body":
            actor = as_ref(payload)
            kind = {"pilot": "girl", "handler": "handler"}.get(actor.kind)
            if not kind:
                raise WorkflowError("Choose a supported original body.")
            return self.changeling.body_fact(
                viewer, key, revision, self.channel, actor, kind, values["account"]
            )
        if action == "appearance":
            return self.changeling.appearance(
                viewer, key, revision, self.channel, as_ref(payload), values
            )
        if action == "show-appearance":
            return self.changeling.disclose_appearance(
                viewer,
                key,
                revision,
                self.channel,
                values["appearance"],
                as_ref(values["target"]),
            )
        if action == "overstep":
            with self.game.store.engine.connect() as c:
                state = load_state(c, self.game.store.campaign_id)
                source = m3_changeling.record(state, m3_changeling.Session, payload)
                if source.cast.channel != self.channel or source.target is None:
                    raise WorkflowError("Use the original Blank Slate scene.")
            return self.changeling.speak(
                viewer,
                key,
                revision,
                self.channel,
                source.target,
                source.actor,
                "push",
                values["words"],
                session=source.id,
            )
        if action == "overstep-tag":
            with self.game.store.engine.connect() as c:
                state = load_state(c, self.game.store.campaign_id)
                if not self.speech_in_scene(state, payload):
                    raise WorkflowError("Use the original Blank Slate scene.")
            return self.changeling.push(viewer, key, revision, payload, values["tag"])
        if action == "disclose":
            selected = json.loads(values["disclosure"])
            with self.game.store.engine.connect() as c:
                state = load_state(c, self.game.store.campaign_id)
                if not self.speech_in_scene(state, selected["speech"]):
                    raise WorkflowError("Use the original scene of the conversation.")
            return self.changeling.disclose_identity(
                viewer, key, revision, selected["speech"], selected["identity"]
            )
        if action in ("brain", "distant"):
            return self.queen.record_context(
                viewer,
                key,
                self.channel,
                revision,
                action,
                as_ref(payload),
                as_ref(values["target"]),
                values["account"],
            )
        if op == "initialize":
            return self.queen.initialize(viewer, key, revision)
        if op == "buy":
            return self.queen.buy(
                viewer, key, revision, m3_red_queen.MEMORY, values["account"]
            )
        if op == "buy-panopticon":
            return self.queen.buy(
                viewer, key, revision, m3_red_queen.PANOPTICON, values["account"]
            )
        if op == "buy-clay":
            return self.changeling.purchase(
                viewer, key, revision, m3_changeling.CLAY, values["account"]
            )
        if op == TRANSFER:
            selected = json.loads(values["source"])
            return self.queen.transfer(
                viewer,
                key,
                revision,
                values["am"],
                ActorRef.model_validate(selected["target"]),
                selected["id"],
                selected["kind"],
            )
        if op not in PLAYS or type(data.get("game_revision")) is not int:
            raise WorkflowError("Choose an available specialist Play.")
        selected = (
            json.loads(values["memory"]) if op == MEMORY
            else json.loads(values["observation"]) if op == PANOPTICON
            else None
        )
        return self.game.begin(
            viewer,
            key,
            self.channel,
            data["game_revision"],
            PlayInput(
                play=op,
                context=values["account"],
                trigger_confirmed=True,
                heat=int(values["heat"]),
                identity=values.get("identity"),
                gain=int(values.get("gain", 0)),
                pair_share=int(values.get("pair_share", 0)),
                target_actor=ActorRef.model_validate(selected["target"])
                if selected
                else None,
                source_work=selected["id"] if selected else values.get("source"),
            ),
        )
