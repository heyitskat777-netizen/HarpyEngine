"""Typed Activity access to the original Wyvern scene and its table."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_state import load_state
from girlframe.services.m3_wyvern import WyvernService, prepare
from girlframe.services.onboarding import WorkflowError

PLAYS = {
    "wyvern_explore": "Explore the Wyvern",
    "wyvern_wraith": "Wraith AM",
    "wyvern_protector": "Protector",
}
ANSWERS = frozenset(
    {
        "wyvern_questions",
        "wyvern_unmark",
        "wyvern_wraith",
        "wyvern_wraith_rules",
        "wyvern_answers_done",
        "wyvern_danger",
        "wyvern_shield_bond",
    }
)
PARTY = "wyvern_declare_party"
ATTEND = "wyvern_attend_party"
QUESTION = "wyvern_frame_answer"
ELAPSED = "wyvern_elapsed_return"
VOICE = "wyvern_voice"
DISMISS = "wyvern_dismiss"
APPROACH = "wyvern_approach"
GIVE_UP = "wyvern_give_up"
ESCAPE = "wyvern_child"
ESCAPE_ACTION = "wyvern_escape_play"
ESCAPE_PLAYS = (("keep_your_head", "Keep Your Head"), ("check_sensors", "Check Your Sensors"))
SOURCE_OPERATIONS = frozenset({PARTY, ATTEND, QUESTION, ELAPSED, VOICE, DISMISS, APPROACH, GIVE_UP})


def decision_fields(decision):
    kind, data = decision["kind"], decision["detail"]
    specs = []
    if kind == "wyvern_questions":
        specs.append(
            Field(
                "options",
                "Frame questions",
                tuple(map(tuple, data["questions"])),
                minimum=data["count"],
                maximum=data["count"],
            )
        )
        if data["danger"]:
            specs.append(
                Field(
                    "danger",
                    "Return danger",
                    (
                        ("delay", "Time to return safely"),
                        ("escape", "A Play is required to escape"),
                    ),
                )
            )
    elif kind == "wyvern_unmark":
        if data["count"]:
            specs.append(
                Field(
                    "identities",
                    "Actual Identities",
                    tuple(map(tuple, data["identities"])),
                    minimum=data["count"],
                    maximum=data["count"],
                )
            )
    elif kind in ("wyvern_danger", "wyvern_wraith", "wyvern_shield_bond"):
        specs.append(Field("options", "Your response", tuple(map(tuple, data["options"]))))
        if kind == "wyvern_wraith":
            specs.append(Field("name", "Name if this mind has never been named", required=False))
    elif kind == "wyvern_wraith_rules":
        specs.extend(
            (
                Field(
                    "profile",
                    "Rules for the actual Frame mind",
                    (("frame_bound_npc", "Frame-bound NPC mind"),),
                ),
                Field("rules", "Your actual rules for this mind", paragraph=True),
            )
        )
        if data["tag"]:
            specs.append(Field("tag", "Your Tag for the actual mind"))
        return specs
    elif kind == "wyvern_answers_done":
        specs.append(
            Field(
                "confirm", "Close the answered questions", (("close", "I have read the answers"),)
            )
        )
    return [*specs, Field("account", "Your account", paragraph=True)]


def decision_answer(kind, values):
    def selections(key):
        selected = values.get(key)
        return (selected,) if isinstance(selected, str) else tuple(selected or ())

    if kind == "wyvern_wraith_rules":
        return ChoiceAnswer(
            options=selections("profile"),
            text=values["rules"],
            fields={"tag": values["tag"]} if values.get("tag") else {},
        )
    if kind == "wyvern_answers_done":
        if values.get("confirm") != "close":
            raise ValueError("Confirm that you have read the original answers.")
        return ChoiceAnswer(options=("done",), text=values.get("account", ""))
    return ChoiceAnswer(
        options=selections("options"),
        denied=selections("identities"),
        text=values.get("account", ""),
        fields={key: values[key] for key in ("name", "danger") if values.get(key)},
    )


class WyvernControls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.native = WyvernService(game)

    def starters(self, viewer, state, sheet):
        try:
            menu = self.native.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return []
        if menu["revision"] != state.revision:
            return []
        actor = ActorRef.model_validate(menu["actor"])
        targets = [(ActorRef.model_validate(row["ref"]), row["label"]) for row in menu["targets"]]
        parties = [
            (entry.id, "Filed exploration party")
            for entry in rules.records(state, rules.Party)
            if entry.actor == actor
            and entry.cast.channel == self.channel
            and not entry.bound_action
            and not entry.cancelled_event
            and set(entry.present) == {actor, *entry.companions}
        ]
        party_fields = (
            [
                Field(
                    "companions",
                    "Actual companions, if any",
                    tuple((ref.model_dump_json(), label) for ref, label in targets),
                    minimum=0,
                    maximum=max(1, len(targets)),
                    required=False,
                ),
            ]
            if targets
            else []
        )
        starters = [
            (PARTY, state.revision, "Declare an exploration party", party_fields, "File the party")
        ]
        blocked = {item.play for item in sheet.blocked_plays}
        identities = tuple(map(tuple, menu["identities"]))
        with self.game.store.engine.connect() as c:
            for play, _ in menu["plays"]:
                if play not in PLAYS or play in blocked:
                    continue
                candidates = [(None, None, "")]
                if play == "wyvern_protector":
                    candidates = [(target, None, label) for target, label in targets]
                elif play == "wyvern_explore":
                    candidates = [(None, party, label) for party, label in parties]
                eligible = []
                for target, party, label in candidates:
                    try:
                        prepare(
                            self.game,
                            c,
                            viewer,
                            state.model_copy(deep=True),
                            PlayInput(
                                play=play,
                                target_actor=target,
                                source_work=party,
                                heat=0,
                                context="Eligibility preview",
                                trigger_confirmed=True,
                            ),
                            self.channel,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    eligible.append((target.model_dump_json() if target else party, label))
                if not eligible:
                    continue
                fields = [
                    Field(
                        "heat",
                        "Heat to spend",
                        tuple(
                            (str(n), str(n)) for n in range(sheet.heat + (6 if identities else 1))
                        ),
                    ),
                    Field("context", "Describe the actual trigger", paragraph=True),
                ]
                if play == "wyvern_explore":
                    fields.insert(
                        0, Field("source", "Original party with attendance", tuple(eligible))
                    )
                elif play == "wyvern_protector":
                    fields.insert(0, Field("target", "Person to shield", tuple(eligible)))
                if identities:
                    fields.extend(
                        (
                            Field(
                                "identity", "Optional Identity to mark", identities, required=False
                            ),
                            Field(
                                "gain",
                                "Heat gained from marking",
                                tuple((str(n), str(n)) for n in range(6)),
                                required=False,
                            ),
                        )
                    )
                starters.append(
                    (play, menu["sheet_revision"], PLAYS[play], fields, "Confirm and start Play")
                )
        return starters

    def assigned(self, viewer, state):
        source_by_id = {row.id: row for row in rules.records(state, rules.Session)}
        rows = []
        for party in rules.records(state, rules.Party):
            if party.cast.channel != self.channel or party.bound_action or party.cancelled_event:
                continue
            actual_roles = {
                role.actor for role in party.cast.roles if role.controller == viewer.user_id
            }
            roles = (set(party.companions) - set(party.present)).intersection(actual_roles)
            if roles:
                picks = tuple(
                    (
                        role.model_dump_json(),
                        state.sheets[role.entity].callsign
                        if role.kind == "pilot" and role.entity in state.sheets
                        else role.kind.replace("_", " ").title(),
                    )
                    for role in sorted(roles, key=lambda role: role.token)
                )
                rows.append(
                    (
                        ATTEND,
                        party.id,
                        state.revision,
                        "Confirm exploration attendance",
                        [
                            Field(
                                "actors",
                                "Actual roles you control",
                                picks,
                                minimum=1,
                                maximum=len(picks),
                            ),
                        ],
                    )
                )
        for question in rules.records(state, rules.Question):
            source = source_by_id.get(question.session)
            if (
                source
                and source.cast.channel == self.channel
                and viewer.user_id in question.table
                and not question.closed_event
                and not source.answers_closed_event
            ):
                try:
                    self.native.view(viewer, question.id)
                except (ValueError, WorkflowError):
                    continue
                rows.append(
                    (
                        QUESTION,
                        question.id,
                        state.revision,
                        question.text,
                        [
                            Field("context", "Your contribution as the Frame", paragraph=True),
                        ],
                    )
                )
        for danger in rules.records(state, rules.Danger):
            source = source_by_id.get(danger.session)
            if (
                source
                and source.cast.channel == self.channel
                and viewer.user_id == source.handler_controller
                and danger.kind == "delay"
                and not danger.returned_event
            ):
                rows.append(
                    (
                        ELAPSED,
                        danger.id,
                        state.revision,
                        "Record the safe return",
                        [
                            Field("context", "Actual elapsed time and safe return", paragraph=True),
                        ],
                    )
                )
        for mind in rules.records(state, rules.Wraith):
            source = source_by_id.get(mind.session)
            if (
                source is None
                or source.cast.channel != self.channel
                or not mind.active
                or mind.ended_event
            ):
                continue
            if viewer.user_id in mind.table:
                rows.append(
                    (
                        VOICE,
                        mind.id,
                        state.revision,
                        "Wraith · Speak as the Frame mind",
                        [
                            Field("context", "What the Frame mind actually says", paragraph=True),
                            Field(
                                "take_control",
                                "Assume control of the mind?",
                                (
                                    ("no", "Speak only"),
                                    ("yes", "Assume control"),
                                ),
                            ),
                        ],
                    )
                )
            if mind.actor.entity == str(viewer.user_id) and not mind.stubborn:
                rows.append(
                    (
                        DISMISS,
                        mind.id,
                        state.revision,
                        "Wraith · Dismiss the mind",
                        [
                            Field("confirm", "Dismiss the actual mind now?", (("yes", "Dismiss"),)),
                        ],
                    )
                )
        for shield in rules.records(state, rules.Shield):
            source = source_by_id.get(shield.session)
            if (
                source is None
                or source.cast.channel != self.channel
                or shield.ended_event
                or not shield.high
            ):
                continue
            try:
                projected = self.native.view(viewer, shield.id)
            except (ValueError, WorkflowError):
                continue
            if projected.get("approachers"):
                refs = tuple(
                    (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"])
                    for row in projected["approachers"]
                )
                rows.append(
                    (
                        APPROACH,
                        shield.id,
                        state.revision,
                        "Protector · Approach",
                        [
                            Field("actor", "Actual nearby person you control", refs),
                            Field("context", "Describe the actual approach", paragraph=True),
                        ],
                    )
                )
            for approach in rules.records(state, rules.Approach):
                if (
                    approach.shield == shield.id
                    and approach.controller == viewer.user_id
                    and not approach.gave_up_event
                ):
                    rows.append(
                        (
                            GIVE_UP,
                            approach.id,
                            state.revision,
                            "Protector · End your approach",
                            [
                                Field(
                                    "confirm",
                                    "Actually give up the approach?",
                                    (("yes", "Give up"),),
                                ),
                                Field("tag", "Optional Tag for the protector", required=False),
                            ],
                        )
                    )
        return rows

    def perform(self, viewer, key, operation, revision, values):
        action, _, source = operation.partition(":")
        if action == PARTY and not values.keys() - {"companions"}:
            selected = self.refs(values.get("companions"))
            return self.native.party(viewer, key, self.channel, revision, selected)
        if action in (ATTEND, QUESTION, ELAPSED):

            def guard(c):
                state = load_state(c, self.game.store.campaign_id)
                model = {ATTEND: rules.Party, QUESTION: rules.Question, ELAPSED: rules.Danger}[
                    action
                ]
                record = next(
                    (item for item in rules.records(state, model) if item.id == source), None
                )
                origin = (
                    record
                    if action == ATTEND
                    else next(
                        (
                            item
                            for item in rules.records(state, rules.Session)
                            if record and item.id == record.session
                        ),
                        None,
                    )
                )
                if origin is None or origin.cast.channel != self.channel:
                    raise WorkflowError("Open the original Wyvern scene.")

            with self.game.store.source_guard(guard):
                if action == ATTEND and values.keys() == {"actors"}:
                    return self.native.attend(
                        viewer, key, source, revision, self.refs(values["actors"])
                    )
                if action == QUESTION and values.keys() == {"context"}:
                    return self.native.answer(viewer, key, source, revision, values["context"])
                if action == ELAPSED and values.keys() == {"context"}:
                    return self.native.elapsed(viewer, key, source, revision, values["context"])
        if action in (VOICE, DISMISS, APPROACH, GIVE_UP):
            return self.saved_control(viewer, key, action, source, revision, values)
        if action not in PLAYS:
            raise ValueError("Use the current Wyvern Play.")
        required = {"heat", "context"} | (
            {"source"}
            if action == "wyvern_explore"
            else {"target"}
            if action == "wyvern_protector"
            else set()
        )
        if not required <= values.keys() or values.keys() - required - {"identity", "gain"}:
            raise ValueError("Use the current Wyvern Play fields.")
        target = values.get("target")
        return self.game.begin(
            viewer,
            key,
            self.channel,
            revision,
            PlayInput(
                play=action,
                trigger_confirmed=True,
                context=values["context"],
                heat=int(values["heat"]),
                identity=values.get("identity") or None,
                gain=int(values.get("gain") or "0"),
                target_actor=ActorRef.model_validate_json(target) if target else None,
                source_work=values.get("source"),
            ),
        )

    def saved_control(self, viewer, key, action, identity, revision, values):
        with self.game.store.engine.connect() as c:
            state = load_state(c, self.game.store.campaign_id)
        if action == GIVE_UP:
            bound = next(
                (row.shield for row in rules.records(state, rules.Approach) if row.id == identity),
                "",
            )
        else:
            bound = identity
        record = next(
            (
                row
                for row in rules.all_records(state)
                if row.id == bound and isinstance(row, (rules.Wraith, rules.Shield))
            ),
            None,
        )
        if record is None or not any(
            row.id == record.session and row.cast.channel == self.channel
            for row in rules.records(state, rules.Session)
        ):
            raise WorkflowError("Open the saved original Wyvern source.")
        args = (viewer, key, identity, revision)
        if (
            action == VOICE
            and values.keys() == {"context", "take_control"}
            and values["take_control"] in ("yes", "no")
        ):
            return self.native.voice(
                *args, values["context"], take_control=values["take_control"] == "yes"
            )
        if action == DISMISS and values == {"confirm": "yes"}:
            return self.native.dismiss(*args)
        if action == APPROACH and values.keys() == {"actor", "context"}:
            return self.native.approach(
                *args, ActorRef.model_validate_json(values["actor"]), values["context"]
            )
        if (
            action == GIVE_UP
            and values.keys() <= {"confirm", "tag"}
            and values.get("confirm") == "yes"
        ):
            return self.native.give_up(*args, tag=values.get("tag") or None)
        raise ValueError("Use the current original Wyvern control.")

    @staticmethod
    def refs(selected):
        return tuple(
            ActorRef.model_validate_json(item)
            for item in ([selected] if isinstance(selected, str) else selected or ())
        )


def escape_fields(game, viewer):
    sheet = game.sheet(viewer)
    return sheet["revision"], [
        Field("play", "Play that actually enables escape", ESCAPE_PLAYS),
        Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet["heat"] + 1))),
        Field("context", "Describe the actual escape trigger", paragraph=True),
    ]


def start_escape(game, viewer, key, original, revision, values):
    if values.keys() != {"play", "heat", "context"} or values["play"] not in dict(ESCAPE_PLAYS):
        raise ValueError("Use a supported native Play for this actual escape.")
    with game.store.engine.connect() as c:
        state = load_state(c, game.store.campaign_id)
    source = next(
        (row for row in rules.records(state, rules.Session) if row.id == original["id"]), None
    )
    if source is None or source.actor.entity != str(viewer.user_id) or not source.danger:
        raise WorkflowError("Only the original escaping pilot can file this Play.")
    return game.begin(
        viewer,
        key,
        int(original["channel_id"]),
        revision,
        PlayInput(
            play=values["play"],
            parent=source.id,
            source_work=source.danger,
            heat=int(values["heat"]),
            context=values["context"],
            trigger_confirmed=True,
        ),
    )
