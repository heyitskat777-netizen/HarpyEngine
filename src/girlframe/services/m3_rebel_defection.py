"""Private actual Rebel contact and the original Bond's decision to stay."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_rebel_defection as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DefectionService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in rules.cases(state) if x.id == identity), None)
            if case is None:
                raise WorkflowError("Recover the original private Rebel contact")
            contacted, heard = rules.audience(state, case, viewer.user_id)
            if not (contacted or heard):
                raise WorkflowError(
                    "Only the actual contacted NPC and eventual Rebel recipient can read"
                )
            return dict(
                revision=state.revision,
                account=case.contact if contacted else None,
                can_stay=contacted and case.outcome is None,
                outcome=case.outcome,
                report=dict(name=case.known_name, jobs=case.known_jobs, cell=case.known_cell)
                if heard
                else None,
            )

    def stay(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        channel: int,
        account: str,
    ) -> dict[str, str]:
        if not 0 < len(account.strip()) <= 1200:
            raise WorkflowError("Describe the original NPC's actual decision in the Bond scene")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in rules.cases(state) if x.id == identity), None)
            if case is None or not rules.audience(state, case, viewer.user_id)[0]:
                raise WorkflowError("Only the original NPC controller records its decision")

        def operation(c: Connection) -> dict[str, str]:
            state = self.strain._state(c, expected)
            case = next(x for x in rules.cases(state) if x.id == identity)
            period = self.strain.periods._get(c, case.period)
            if case.outcome is not None or period.phase not in ("preparing", "active"):
                raise WorkflowError("Recover the still-open original defection deadline")
            cast, _ = CastService(ActorService(self.strain.missions))._current(c, state, channel)
            ref = ActorRef(kind="npc", entity=case.npc)
            bindings = profiles(c, self.store.campaign_id)
            actual = resolve(state, ref, bindings, require_current_profile=False)
            if (
                actual.controller != viewer.user_id
                or actual.custody
                or not any(x.actor == ref and x.controller == viewer.user_id for x in cast.roles)
                or not any(
                    x.actor in case.bonds
                    and x.controller
                    == resolve(state, x.actor, bindings, require_current_profile=False).controller
                    for x in cast.roles
                )
            ):
                raise WorkflowError("Join this actual NPC and an original Bond to its scene")
            event = str(uuid4())
            rules.put(
                state,
                case.model_copy(
                    update=dict(
                        outcome="stayed",
                        stay_scene=cast.id,
                        stay_account=account.strip(),
                        resolved_event=event,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_defection_averted",
                state,
                event_id=event,
                work=identity,
            )
            return dict(id=identity, outcome="stayed")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.rebel_defection_averted",
            dict(identity=identity, expected=expected, channel=channel, account=account),
            operation,
            authorize,
        )
