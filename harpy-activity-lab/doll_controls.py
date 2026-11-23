"""Unassuming Doll, the original listener, and the same body's re-entry."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import m3_vatgrown as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_clone_am import additional_identities
from girlframe.services.m3_vatgrown import DollService
from girlframe.services.onboarding import WorkflowError

DOLL = "unassuming_doll"
DEPARTURE = "doll_depart"
RETURN = "doll_return"
OPERATIONS = frozenset((DOLL, DEPARTURE, RETURN))
ANSWERS = frozenset({"vat_doll_attention", "vat_doll_information", "vat_doll_benefits"})
SOURCE_ACCOUNT = Field("account", "Describe what actually happens", paragraph=True)


class DollControls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.service = DollService(game)

    def forms(self, viewer, state, sheet, card, *, can_start, locked):
        if can_start and sheet and not any(row.play == DOLL for row in sheet.blocked_plays):
            try:
                menu = self.service.menu(viewer, self.channel)
            except (ValueError, WorkflowError):
                menu = None
            if menu and menu["revision"] == state.revision and menu["targets"]:
                targets = tuple((ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"])
                                for row in menu["targets"])
                identities = tuple(
                    (item.id, item.name)
                    for item in (*sheet.identities, *additional_identities(state, sheet.owner))
                    if not item.marked
                )
                fields = [
                    Field("target", "Original person who could notice or answer", targets),
                    Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet.heat + 4))),
                    SOURCE_ACCOUNT,
                ]
                if identities:
                    fields.extend((
                        Field("identity", "Optional unmarked Identity", identities, required=False),
                        Field("gain", "Ordinary Heat from marking", tuple((str(n), str(n)) for n in range(1, 4)),
                              required=False),
                    ))
                yield card(DOLL, sheet.revision, "Unassuming Doll", fields)
        for source in rules.records(state, rules.Source):
            if source.cast.channel != self.channel or source.caster != viewer.user_id:
                continue
            try:
                data = self.service.view(viewer, source.id)
            except (ValueError, WorkflowError):
                continue
            if data["revision"] != state.revision:
                continue
            if data["departure"] and not locked:
                yield card(f"{RETURN}:{data['departure']}", state.revision, "Unassuming Doll · Return",
                           [SOURCE_ACCOUNT], label="File actual re-entry")
            elif data["leave"] and can_start:
                yield card(f"{DEPARTURE}:{data['leave']}", state.revision, "Unassuming Doll · Leave",
                           [SOURCE_ACCOUNT], label="File actual departure")

    def perform(self, viewer, key, operation, revision, values):
        kind, _, source = operation.partition(":")
        if kind == DOLL and {"target", "heat", "account"} <= values.keys() <= {
            "target", "heat", "account", "identity", "gain",
        }:
            return self.game.begin(viewer, key, self.channel, revision, PlayInput(
                play=DOLL, target_actor=ActorRef.model_validate_json(values["target"]),
                identity=values.get("identity") or None, gain=int(values.get("gain") or "0"),
                heat=int(values["heat"]), context=values["account"], trigger_confirmed=True,
            ))
        if kind in (DEPARTURE, RETURN) and values.keys() == {"account"}:
            method = self.game.depart_doll if kind == DEPARTURE else self.game.return_doll
            return method(viewer, key, self.channel, source, revision, values["account"])
        raise WorkflowError("Open the original owned Unassuming Doll control.")
