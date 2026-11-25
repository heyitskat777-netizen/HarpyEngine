"""Source-bound Performer declaration, roll, and Fanbase exception forms."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import m3_prince as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_clone_am import additional_identities
from girlframe.services.m3_prince import PrinceService, _access, _parties, prepare
from girlframe.services.onboarding import WorkflowError

PERFORMER = rules.PLAY
EXCEPTION = "prince_demand_exception"
EXCEPTION_PLAY = "prince_demand_attempt"
OPERATIONS = frozenset((PERFORMER, EXCEPTION, EXCEPTION_PLAY))
DEMAND_PLAYS = (("keep_your_head", "Keep Your Head"), ("disobey_orders", "Disobey Orders"))
ANSWERS = frozenset(
    (
        "prince_choose_actor",
        "prince_choose_target",
        "prince_conform",
        "prince_falter",
        "prince_erase_tags",
        "prince_bad_girl",
    )
)
YES_NO = (("yes", "Yes"), ("no", "No"))
HEAT = tuple((str(n), str(n)) for n in range(6))


class PrinceControls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.service = PrinceService(game)

    def forms(self, viewer, state, sheet, card):
        try:
            ready = self.service.menu(viewer, self.channel)
            if ready["revision"] != state.revision:
                return []
            demand = self.service.demand_menu(viewer)
            if not demand["available"]:
                return []
            actor = current_ref(state, viewer.user_id)
            with self.game.store.engine.connect() as c:
                _access(self.game, c, viewer, rules.PERFORMER)
                performance, targets = self.performance_sources(c, viewer, state, actor, ready)
        except (ValueError, WorkflowError):
            return []
        result = []
        if performance:
            fields = [
                Field("source", "Your declared performance", performance),
                *self.roll_fields(state, sheet, allow_fans=True),
            ]
            if demand["exceptions"]:
                fields.append(
                    Field(
                        "exception",
                        "Completed exception for this contrary act",
                        tuple((row["id"], row["label"]) for row in demand["exceptions"]),
                        required=False,
                    )
                )
            result.append(card(PERFORMER, sheet.revision, "Play the actual part", fields))
        elif targets:
            result.append(
                card(
                    PERFORMER,
                    state.revision,
                    "Performer · Declare the part",
                    [
                        Field("target", "Original audience member", targets),
                        Field("part", "Part actually performed"),
                        Field("following", "Does it follow the Fanbase demands?", YES_NO),
                        Field(
                            "context",
                            "Describe what you do and how it relates to the demands",
                            paragraph=True,
                        ),
                    ],
                    label="File your performance declaration",
                )
            )
        original_acts = tuple(
            (row.id, row.account)
            for row in rules.records(state, rules.DemandAttempt)
            if row.actor == actor and row.cast.channel == self.channel and not row.action
        )
        if original_acts:
            result.append(
                card(
                    EXCEPTION_PLAY,
                    sheet.revision,
                    "Fanbase demands · Act against them",
                    [
                        Field("source", "Your recorded contrary act", original_acts),
                        Field("play", "Resolve the actual exception", DEMAND_PLAYS),
                        *self.roll_fields(state, sheet, allow_fans=False),
                    ],
                )
            )
        else:
            result.append(
                card(
                    EXCEPTION,
                    state.revision,
                    "Fanbase demands · Declare a contrary act",
                    [
                        Field(
                            "context", "Name the act and the demand it would break", paragraph=True
                        ),
                    ],
                    label="File the actual contrary act",
                )
            )
        return result

    def performance_sources(self, c, viewer, state, actor, ready):
        records, targets = [], []
        for row in rules.records(state, rules.Performance):
            if row.actor != actor or row.cast.channel != self.channel or row.action:
                continue
            try:
                prepare(
                    self.game,
                    c,
                    viewer,
                    state,
                    PlayInput(
                        play=PERFORMER,
                        source_work=row.id,
                        heat=0,
                        context=row.part,
                        trigger_confirmed=True,
                    ),
                    self.channel,
                )
            except (ValueError, WorkflowError):
                continue
            records.append((row.id, row.part))
        for target in ready["targets"]:
            ref = ActorRef.model_validate(target["ref"])
            try:
                _parties(self.game, c, state, actor, ref, self.channel)
            except (ValueError, WorkflowError):
                continue
            targets.append((ref.model_dump_json(), target["label"]))
        return tuple(records), tuple(targets)

    @staticmethod
    def roll_fields(state, sheet, *, allow_fans):
        identities = tuple(
            (item.id, item.name)
            for item in (*sheet.identities, *additional_identities(state, sheet.owner))
            if not item.marked
            and (allow_fans or not (item.id.startswith("fan:") or ":fan:" in item.id))
        )
        fields = [
            Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet.heat + 6))),
            Field("piloting", "Are you actually piloting your Frame?", YES_NO),
        ]
        if identities:
            fields.extend(
                (
                    Field(
                        "identity",
                        "Optional original unmarked Identity",
                        identities,
                        required=False,
                    ),
                    Field("gain", "Heat gained from marking", HEAT, required=False),
                    Field("share", "Paired Heat to the actual Pair", HEAT, required=False),
                )
            )
        return fields

    def perform(self, viewer, key, operation, revision, values):
        if operation == EXCEPTION and values.keys() == {"context"}:
            return self.service.exception_attempt(
                viewer, key, revision, self.channel, values["context"]
            )
        if operation == PERFORMER and values.keys() == {"target", "part", "following", "context"}:
            if values["following"] not in ("yes", "no"):
                raise ValueError("Record whether your part follows the original demands.")
            return self.service.perform(
                viewer,
                key,
                revision,
                self.channel,
                ActorRef.model_validate_json(values["target"]),
                values["part"],
                values["following"] == "yes",
                values["context"],
            )
        required = {"source", "heat", "piloting"}
        optional = {"identity", "gain", "share"}
        if operation == PERFORMER:
            optional.add("exception")
        else:
            required.add("play")
        if not (required <= values.keys() <= required | optional) or values["piloting"] not in (
            "yes",
            "no",
        ):
            raise ValueError("Use the original role, source, and costs.")
        play = PERFORMER if operation == PERFORMER else values["play"]
        if operation == EXCEPTION_PLAY and play not in dict(DEMAND_PLAYS):
            raise ValueError("Choose Keep Your Head or Disobey Orders.")
        data = self.service.view(viewer, values["source"])
        record = data["record"]
        expected = "Performance" if operation == PERFORMER else "DemandAttempt"
        if (
            data["kind"] != expected
            or record["cast"]["channel"] != self.channel
            or record["actor"]["entity"] != str(viewer.user_id)
        ):
            raise WorkflowError("Return to your original source scene.")
        return self.game.begin(
            viewer,
            key,
            self.channel,
            revision,
            PlayInput(
                play=play,
                source_work=record["id"],
                identity=values.get("identity") or None,
                gain=int(values.get("gain") or "0"),
                pair_share=int(values.get("share") or "0"),
                heat=int(values["heat"]),
                piloting=values["piloting"] == "yes",
                context=record.get("part", record["account"]),
                trigger_confirmed=True,
                prince_demands="following" if record.get("following") else "against",
                prince_demand_account=record["account"],
                prince_exception=values.get("exception") or None,
            ),
        )
