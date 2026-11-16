"""Disposable engine-only synthetic trial; local fixtures, no Discord/model/network.

This development tool requires the checkout's pinned dev dependencies and reuses
its existing synthetic campaign setup. It is not a production bootstrap or an
alternate campaign store. Default runs a bounded demo; --interactive accepts only
explicitly entered synthetic test text and discards the database on exit.
"""

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "rules"))


def run(interactive: bool) -> None:
    import pytest
    from test_actor_service import ready
    from test_cast_service import change
    from test_director_observation import Clock, send
    from test_enforcer_requisitions import approved
    from test_ledger import ADMIN, OTHER, PLAYER, ledger
    from test_m2_game import state

    from girlframe.ai.observation import ObservationPolicy
    from girlframe.engine import m3_appearance_matrix as matrix
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_contributions import DirectorContributionService
    from girlframe.services.director_dialogue import DirectorDialogueService
    from girlframe.services.director_observation import DirectorObservationService
    from girlframe.services.director_shadow import DirectorShadowService
    from girlframe.services.m3_appearance_matrix import MatrixService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.onboarding import WorkflowError

    print("SYNTHETIC ENGINE TRIAL — disposable data, no provider calls or real delivery.")
    with TemporaryDirectory(prefix="harpy-director-trial-") as directory:
        patch = pytest.MonkeyPatch()
        fixture = ledger.__wrapped__(Path(directory), patch)
        store = next(fixture)
        try:
            actors, game = ready(store)
            npc = ActorRef(kind="npc", entity="secret-npc")
            change(CastService(actors), PLAYER, "join", npc)
            approved(store, game, Path(directory), patch, extra=(matrix.RULE,))
            venue = MatrixService(game).record_context(
                ADMIN, "console-venue", 900, state(game).revision, "base0"
            )["id"]
            clock = Clock()
            store.clock = clock
            observer = DirectorObservationService(store, synthetic=True)
            with store.engine.connect() as c:
                scene = game.scene(c, 900)["id"]
            observer.configure_scene(
                ADMIN, "console-policy", scene, 0, ObservationPolicy(mode="shadow")
            )
            for viewer in (ADMIN, PLAYER, OTHER):
                observer.set_consent(
                    viewer, f"console-consent:{viewer.user_id}", scene, 1, consent=True
                )
            context = DirectorContextService(observer)
            shadow = DirectorShadowService(context)
            dialogue = DirectorDialogueService(context)
            contributions = DirectorContributionService(dialogue)
            order = 0
            counter = 0
            draft = None
            commands = iter(
                [
                    "The synthetic hangar crew reports that the inspection is complete.",
                    "/wait",
                    "/npc",
                    "/approve",
                    "/publish",
                    "/status",
                    "/quit",
                ]
            )
            print(
                "Text = synthetic scene input. Commands: /wait /npc /approve /publish /status /quit"
            )
            while True:
                try:
                    text = input("trial> ") if interactive else next(commands)
                except (EOFError, StopIteration):
                    break
                if not interactive:
                    print("trial> " + text)
                if text == "/quit":
                    break
                counter += 1
                key = f"console:{counter}"
                try:
                    if text == "/wait":
                        clock.now += 120
                        batch = observer.claim_review(scene)
                        result = (
                            shadow.evaluate(ADMIN, scene, batch.run_id)
                            if batch
                            else {"status": "no_eligible_work"}
                        )
                    elif text == "/npc":
                        own = context.build(PLAYER, scene, actor=npc)
                        draft = dialogue.draft(
                            PLAYER,
                            key,
                            scene,
                            npc,
                            own.revision,
                            tuple(x.id for x in own.references),
                        )["id"]
                        result = dialogue.get(PLAYER, scene, draft)
                    elif text == "/approve":
                        if draft is None:
                            raise WorkflowError("Create a draft with /npc first.")
                        result = dialogue.review(PLAYER, key, scene, draft, decision="approve")
                    elif text == "/publish":
                        if draft is None:
                            raise WorkflowError("Create and approve a draft first.")
                        contributions.commit_synthetic_report(PLAYER, key, scene, draft, venue)
                        result = {"synthetic_projection": contributions.projections(OTHER, scene)}
                    elif text == "/status":
                        result = observer.status(PLAYER, scene).model_dump(mode="json")
                    elif text.startswith("/"):
                        raise WorkflowError("Unknown trial command.")
                    else:
                        _, source = send(observer, scene, key, text=text)
                        context.record(
                            ADMIN,
                            key + ":knowledge",
                            scene,
                            source.source_id,
                            order,
                            known_by=(npc,),
                        )
                        order += 1
                        result = {"source_id": source.source_id, "order": order}
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                except WorkflowError as error:
                    print(str(error))
        finally:
            store.engine.dispose()
            fixture.close()
            patch.undo()
    print("Trial ended; disposable campaign removed. External tokens/cost: 0.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true")
    run(parser.parse_args().interactive)
