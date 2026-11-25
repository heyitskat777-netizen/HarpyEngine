"""Original-owner controls for HarpyEngine's Off-Duty Tag rebuilding."""

from girlframe.engine.m3_disposable_psyche import TagSelection
from girlframe.services.m3_disposable_psyche import PsycheService
from girlframe.services.onboarding import WorkflowError


class PsycheControls:
    def __init__(self, game):
        self.service = PsycheService(game.store, game)

    def cards(self, viewer, state, period):
        for task in self.service.menu(viewer)["tasks"]:
            if task["phase"] == "removed":
                continue
            try:
                detail = self.service.view(viewer, task["id"])
            except (ValueError, WorkflowError):
                continue
            if detail["period"] != period or detail["revision"] != state.revision:
                continue
            card = {
                "kind": "disposable_psyche",
                "label": "Disposable Psyche · Tag rebuilding",
                "id": task["id"],
                "source_action": detail["source_action"],
                "revision": detail["revision"],
                "phase": detail["phase"],
            }
            if detail["phase"] == "pending":
                card["tags"] = [(row["id"], row["label"]) for row in detail["tags"]]
                card["identities"] = [(row["id"], row["label"]) for row in detail["identities"]]
                card["count"] = detail["count"]
            else:
                card["identities"] = detail["identities"]
            yield card

    def perform(self, viewer, key, period, game_revision, answer):
        if (
            answer.keys() != {"id", "work_revision", "tags", "replacements"}
            or not isinstance(answer["id"], str)
            or type(answer["work_revision"]) is not int
            or answer["work_revision"] != game_revision
            or not isinstance(answer["tags"], list)
            or not isinstance(answer["replacements"], list)
            or not 1 <= len(answer["tags"]) <= 4
            or len(answer["replacements"]) > len(answer["tags"])
            or not all(
                isinstance(value, str) and value
                for value in answer["tags"] + answer["replacements"]
            )
        ):
            raise ValueError(
                "Choose Tags and eligible replacements from your original rebuilding record."
            )
        source = self.service.view(viewer, answer["id"])
        if source["period"] != period:
            raise WorkflowError("Reopen your original Off-Duty period.")
        replacements = answer["replacements"]
        selections = tuple(
            TagSelection(tag=tag, replace=replacements[i] if i < len(replacements) else None)
            for i, tag in enumerate(answer["tags"])
        )
        return self.service.convert(viewer, key, answer["id"], game_revision, selections)
