"""Handler-owned Strain preparation through HarpyEngine's native work ledger."""

import json
from dataclasses import asdict

from girlframe.discord_adapter.m3_strain import FACT_LABELS
from girlframe.discord_adapter.m3_strain_effects import WAIT, effect_form
from girlframe.engine.m3_strain import StartFacts
from girlframe.engine.m3_strain_catalog import ENDGAMES, ROWS
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Board, Gorgon, Location
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

from strain_special import RULES as SPECIAL_RULES
from strain_special import special_form

SCENARIOS = (
    ("business_as_usual", "Business As Usual"),
    ("disaster_management", "Disaster Management"),
    ("barely_hanging_on", "Barely Hanging On"),
    ("falling_apart", "Everything’s Falling Apart"),
)
TRACKS = ("void", "rebellion", "budget")


def effect_label(identity):
    parts = identity.split(".")
    if (
        len(parts) == 5
        and parts[3] in ("1", "2", "3", "4", "5", "6")
        and parts[4] in ("1", "2")
        and (row := ROWS.get((parts[1], parts[2])))
    ):
        return row[int(parts[3]) - 1][int(parts[4]) - 1]
    if len(parts) == 4 and parts[2] == "endgame" and parts[3].isdigit():
        labels = ENDGAMES.get(parts[1], ())
        if 1 <= (slot := int(parts[3])) <= len(labels):
            return labels[slot - 1]
    return identity


class StrainPreparation:
    def __init__(self, periods):
        self.service = StrainService(periods)
        self.effects = EffectService(self.service)
        self.world = WorldService(self.service.missions)
        self.rooms = lambda: {}

    def effect_fields(
        self,
        viewer,
        identity,
        values,
        *,
        commit=False,
        key=None,
        revision=None,
        game_revision=None,
    ):
        source = self.effects.get(viewer, identity)
        if revision != source["revision"] or game_revision != source["game_revision"]:
            raise WorkflowError("Reopen the saved Strain result.")
        channels = tuple(
            (str(channel), label) for channel, (_, label) in self.rooms().items()
        )
        if source["rule_id"] in SPECIAL_RULES:
            build, apply, instructions = special_form(
                self.service, viewer, source, channels
            )
        else:
            build, apply, instructions = effect_form(
                viewer, self.effects, identity, channels
            )
        if not isinstance(values, dict):
            raise ValueError("Use the form for this effect.")
        permitted = {}
        # Some controls become valid only after their earlier selector has been filled.
        for _ in range(len(values) + 2):
            fields = build(permitted)
            normalized = {}
            for spec in fields:
                value = values.get(spec.key)
                if spec.options:
                    allowed = {row[0] for row in spec.options if row != WAIT[0]}
                    if (
                        isinstance(value, list)
                        and all(isinstance(entry, str) for entry in value)
                        and len(set(value)) == len(value) <= spec.maximum
                        and set(value) <= allowed
                        and value
                    ):
                        normalized[spec.key] = tuple(value)
                elif isinstance(value, str) and value.strip() and len(value) <= 2400:
                    normalized[spec.key] = value
            if normalized == permitted:
                break
            permitted = normalized
        else:
            raise WorkflowError(
                "Reopen the effect before changing its dependent fields."
            )
        if commit:
            if any(
                spec.options == WAIT
                or spec.required
                and (
                    spec.key not in permitted
                    or spec.options
                    and len(permitted[spec.key]) < spec.minimum
                )
                or spec.options
                and spec.key in permitted
                and len(permitted[spec.key]) < spec.minimum
                for spec in fields
            ):
                raise WorkflowError(
                    "Complete all required effect choices before filing."
                )
            return {"notice": apply(viewer, key, permitted)}
        return {
            "instructions": instructions,
            "fields": [asdict(spec) for spec in fields],
            "values": permitted,
        }

    def view(self, viewer, review):
        snapshot = self.service.get(viewer)
        world = self.world.get(viewer, private=True)["world"]
        cards = []
        for item in review["work"]:
            kind = item["kind"]
            if kind == "strain_event":
                detail = self.effects.get(viewer, item["id"])
                cards.append(
                    {
                        **item,
                        "action": "strain_effect"
                        if detail["supported"] or detail["rule_id"] in SPECIAL_RULES
                        else None,
                        "label": effect_label(detail["rule_id"]),
                        "rule": detail["rule_id"],
                        "supply": detail["supply_outcome"],
                    }
                )
                continue
            if kind not in ("off_duty_strain_start", "strain_roll", "strain_endgame"):
                continue
            detail = self.service.work(viewer, item["id"])
            body = detail["body"]
            if kind == "off_duty_strain_start":
                if body.get("stage") == "pending_effects":
                    continue
                cards.append(
                    {
                        **item,
                        "action": "strain_prepare"
                        if snapshot["strain"]
                        else "strain_configure",
                        "label": "Review worldwide triggers"
                        if snapshot["strain"]
                        else "Set initial Strain",
                        "facts": list(FACT_LABELS.items()),
                        "scenarios": SCENARIOS,
                        "tracks": TRACKS,
                        "exemptions": [
                            row["label"] for row in detail["budget_death_exemptions"]
                        ],
                    }
                )
                continue
            track = body["track"]
            if kind == "strain_endgame":
                columns = [
                    (i, ENDGAMES[track][i - 1]) for i in detail["endgame_options"]
                ]
                cards.append(
                    {
                        **item,
                        "label": f"{track.title()} Endgame",
                        "action": "strain_endgame",
                        "columns": columns,
                        "track": track,
                        "rebel_groups": detail["rebel_groups"],
                    }
                )
                continue
            face = body.get("face")
            columns = (
                enumerate(ROWS[(track, body["severity"])][face - 1], 1) if face else ()
            )
            cards.append(
                {
                    **item,
                    "label": f"{track.title()} · {body['severity'].title()}",
                    "action": "strain_column" if face else "strain_roll",
                    "face": face,
                    "columns": list(columns),
                }
            )
        strain = snapshot["strain"]
        ready = bool(
            world
            and strain
            and review["id"] in strain["periods"]
            and not any(row["period_id"] == review["id"] for row in strain["requests"])
            and not cards
        )
        return {"cards": cards, "ready": ready, "needs_world": world is None}

    def perform(self, args, action, answer):
        viewer, key, period, revision, game_revision = args
        if action == "strain_world" and answer.keys() == {
            "board",
            "locations",
            "secret",
        }:
            return self.world.initialize(
                viewer,
                key,
                game_revision,
                Board.model_validate_json(json.dumps(answer["board"])),
                tuple(
                    Location.model_validate_json(json.dumps(row))
                    for row in answer["locations"]
                ),
                Gorgon.model_validate_json(json.dumps(answer["secret"])),
            )
        if action == "strain_configure" and answer.keys() == {"scenario", "high"}:
            if not isinstance(answer["high"], list) or any(
                track not in TRACKS for track in answer["high"]
            ):
                raise ValueError("Choose the printed starting tracks.")
            return self.service.configure(
                viewer,
                key,
                game_revision,
                answer["scenario"],
                frozenset(answer["high"]),
            )
        if action == "strain_prepare" and answer.keys() == {"id", "facts", "account"}:
            task = self.service.work(viewer, answer["id"])
            facts = answer["facts"]
            if (
                task["off_duty_id"] != period
                or task["kind"] != "off_duty_strain_start"
                or not isinstance(facts, dict)
                or facts.keys() != FACT_LABELS.keys()
                or any(type(flag) is not bool for flag in facts.values())
            ):
                raise ValueError("Answer every assigned Strain question.")
            return self.service.prepare(
                viewer,
                key,
                period,
                revision,
                game_revision,
                StartFacts(
                    **task["canonical_facts"], **facts, account=answer["account"]
                ),
            )
        if (
            not isinstance(answer.get("id"), str)
            or type(answer.get("revision")) is not int
        ):
            raise ValueError("Reopen the assigned Strain work.")
        cmd = (viewer, key, answer["id"], answer["revision"], game_revision)
        if action == "strain_roll":
            return self.service.roll(*cmd)
        if (
            action in ("strain_column", "strain_endgame")
            and type(answer.get("column")) is int
        ):
            return self.service.choose(
                *cmd,
                answer["column"],
                endgame=action == "strain_endgame",
                faction=answer.get("faction"),
            )
        if action in ("strain_effect_fields", "strain_effect_submit"):
            return self.effect_fields(
                viewer,
                answer["id"],
                answer.get("values"),
                commit=action == "strain_effect_submit",
                key=key,
                revision=answer["revision"],
                game_revision=game_revision,
            )
        if action == "strain_effect" and isinstance(answer.get("effect"), dict):
            return self.effects.apply(
                *cmd, Choice.model_validate_json(json.dumps(answer["effect"]))
            )
        raise ValueError("Choose the current Strain decision.")
