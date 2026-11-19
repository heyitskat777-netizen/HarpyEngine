"""Run a sealed Dopplegänger search without publishing an unearned identity."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_sniff_out as rules
from girlframe.engine.m2 import GameState, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _visible
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class SniffOutService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)
        self.medical = MedicalService(store)

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(rules.RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _cast(self, state: GameState, scene: str, gm: int) -> SceneCast:
        cast = next((x for x in state.scene_casts if x.id == scene and x.open), None)
        if cast is None or cast.facilitator != gm:
            raise WorkflowError("Recover the original open search scene and its human GM")
        return cast

    def _hunter(self, c: Connection, state: GameState, cast: SceneCast, token: str) -> ActorView:
        role = next(
            (x for x in cast.roles if x.actor.kind == "pilot" and x.actor.token == token), None
        )
        if role is None:
            raise WorkflowError("Use the original Girl from this scene")
        hunter = resolve(
            state,
            role.actor,
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        )
        if (
            not hunter.alive
            or hunter.rules != "girl_frame"
            or hunter.cell is None
            or hunter.offstage_source
            or hunter.controller != role.controller
        ):
            raise WorkflowError("Use the available original investigating Girl")
        return hunter

    def _targets(
        self,
        state: GameState,
        hunter: ActorView,
    ) -> dict[str, tuple[ActorRef, ActorRef, str]]:
        if state.world is None:
            return {}
        sources = [
            x
            for x in state.world.gorgons
            if "doppleganger" in x.types and x.alive and not x.revealed and x.cell == hunter.cell
        ]
        guises = [
            (ActorRef(kind="npc", entity=x.id), x.name)
            for x in state.world.npcs
            if x.alive
            and x.controller == state.handler
            and not x.captive_of
            and x.cell == hunter.cell
            and "director" not in x.jobs
            and x.source_kind is None
            and _visible(state, ActorRef(kind="npc", entity=x.id), hunter.controller)
        ]
        return {
            f"{source.id}/{guise.token}": (
                ActorRef(kind="gorgon", entity=source.id),
                guise,
                f"{source.name} as {guise_name}",
            )
            for source in sources
            for guise, guise_name in guises
        }

    def _proof(self, c: Connection, case: rules.Search) -> None:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == case.event,
            )
        )
        root = (
            next(
                (x for x in rules.records(GameState.model_validate_json(raw)) if x.id == case.id),
                None,
            )
            if raw
            else None
        )
        marker = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == case.event,
            )
        ).first()
        original = case.model_copy(
            update=dict(
                roll=None, bait=None, bait_account=None, discovered=None, name=None, proof=None
            )
        )
        if (
            root != original
            or not marker
            or (marker.kind, marker.actor_id) != ("m3.sniff_out_offered", str(case.gm))
        ):
            raise WorkflowError("Recover the actual sealed Dopplegänger search")

    def _step_receipt(
        self, c: Connection, case: rules.Search, event: str, gm: bool, step: str
    ) -> None:
        from json import loads

        fact = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == event,
            )
        ).first()
        owner = str(case.gm) if gm else case.hunter.entity
        if (
            not fact
            or (fact.kind, fact.actor_id) != (f"m3.sniff_out_{step}", owner)
            or loads(fact.payload_json).get("case_id") != case.id
        ):
            raise WorkflowError("Recover the actual original search receipt")

    def tasks(self, c: Connection, viewer: GuildViewer, state: GameState) -> list[dict[str, Any]]:
        try:
            self._gate(c, viewer)
        except WorkflowError:
            return []
        cases = rules.records(state)
        result = []
        for case in cases:
            hunter = case.hunter.entity == str(viewer.user_id)
            review = viewer.user_id == case.gm and case.bait and not case.discovered
            if hunter or review:
                result.append(
                    dict(
                        id=case.id,
                        revision=state.revision,
                        pending=not case.discovered and (not case.bait or bool(review)),
                        label="Your discovered identity" if case.discovered else "Sniff You Out",
                    )
                )
        try:
            gm, _ = self.medical._handler(c)
        except WorkflowError:
            return result
        if gm != viewer.user_id:
            return result
        for scene in state.scene_casts:
            if not scene.open or scene.facilitator != gm:
                continue
            for role in scene.roles:
                if role.actor.kind != "pilot":
                    continue
                try:
                    hunter = self._hunter(c, state, scene, role.actor.token)
                except (ValueError, WorkflowError):
                    continue
                if self._targets(state, hunter):
                    result.append(
                        dict(
                            id=f"offer/{scene.id}/{role.actor.token}",
                            revision=state.revision,
                            label="Prepare a sealed Dopplegänger search",
                            pending=True,
                        )
                    )
        return result

    def _offer(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[int, str, SceneCast, ActorView, dict[str, tuple[ActorRef, ActorRef, str]]]:
        gm, appointment = self.medical._handler(c)
        parts = identity.split("/")
        if viewer.user_id != gm or len(parts) != 3 or parts[0] != "offer":
            raise WorkflowError("Only the original human GM can prepare a private search")
        cast = self._cast(state, parts[1], gm)
        hunter = self._hunter(c, state, cast, parts[2])
        return gm, appointment, cast, hunter, self._targets(state, hunter)

    def _case(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> rules.Search:
        current = next((x for x in rules.records(state) if x.id == identity), None)
        if current is None or viewer.user_id not in (int(current.hunter.entity), current.gm):
            raise WorkflowError("This private search is unavailable")
        self._proof(c, current)
        if current.roll:
            self._step_receipt(c, current, current.roll.event, False, "roll")
        if current.bait:
            self._step_receipt(c, current, current.bait, False, "bait")
        if current.discovered:
            self._step_receipt(c, current, current.discovered, True, "discover")
        return current

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity.startswith("offer/"):
                _, _, _, hunter, targets = self._offer(c, state, viewer, identity)
                return dict(
                    revision=state.revision,
                    targets={x: row[2] for x, row in targets.items()},
                    hunter=hunter.label,
                )
            case = self._case(c, state, viewer, identity)
            result: dict[str, Any] = dict(
                revision=state.revision,
                hook=case.hook,
                roll=case.roll.model_dump(mode="json") if case.roll else None,
                tier=case.roll.result if case.roll else None,
                bait=case.bait is not None,
                review=viewer.user_id == case.gm and case.bait is not None,
            )
            if result["review"] and not case.discovered:
                result["bait_account"] = case.bait_account
            if case.discovered:
                result.update(found=case.name, event=case.discovered)
            elif case.roll is None and viewer.user_id == int(case.hunter.entity):
                sheet = state.sheets.get(case.hunter.entity)
                result["heat"] = (
                    sheet.heat if sheet and sheet.character_id == case.hunter.incarnation else 0
                )
            return result

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        selected: str = "",
        account: str = "",
        heat: int | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self.medical._idle(c)
            state = load_state(c, self.store.campaign_id)
            if revision != state.revision:
                raise WorkflowError("STALE_SNIFF_OUT: reopen the actual original choice")
            event = str(uuid4())
            if step == "offer":
                gm, appoint, cast, hunter, targets = self._offer(c, state, viewer, identity)
                if (
                    selected not in targets
                    or heat is not None
                    or not 0 < len(account.strip()) <= 1200
                ):
                    raise WorkflowError("Seal the actual Gorgon, guise and concrete lead")
                source, guise, _ = targets[selected]
                if any(
                    x.gorgon == source
                    and (x.guise != guise or x.hunter == hunter.ref and not x.discovered)
                    for x in rules.records(state)
                ):
                    raise WorkflowError("Recover the original guise and existing search")
                current = rules.Search(
                    id=str(uuid4()),
                    scene=cast.id,
                    hunter=hunter.ref,
                    gorgon=source,
                    guise=guise,
                    gm=gm,
                    appointment=appoint,
                    event=event,
                    hook=account.strip(),
                )
            else:
                case = self._case(c, state, viewer, identity)
                current = self._advance(
                    c, state, viewer, case, step, selected, account, heat, event
                )
            rules.put(state, current)
            kind = "m3.sniff_out_offered" if step == "offer" else "m3.sniff_out_" + step
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, case_id=current.id)
            return dict(id=current.id, found=current.discovered is not None)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.sniff_out_choice",
                dict(
                    task=identity,
                    revision=revision,
                    step=step,
                    selected=selected,
                    account=account,
                    heat=heat,
                ),
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _advance(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        case: rules.Search,
        step: str,
        selected: str,
        account: str,
        heat: int | None,
        event: str,
    ) -> rules.Search:
        cast = self._cast(state, case.scene, case.gm)
        hunter = self._hunter(c, state, cast, case.hunter.token)
        targets = self._targets(state, hunter)
        key = f"{case.gorgon.entity}/{case.guise.token}"
        if (
            case.discovered
            or key not in targets
            or self.medical._handler(c) != (case.gm, case.appointment)
        ):
            raise WorkflowError(
                "Recover the actual still-concealed Gorgon and the original search appointment"
            )
        owner = hunter.controller == viewer.user_id
        if (
            step == "roll"
            and owner
            and case.roll is None
            and heat is not None
            and not selected
            and not account
        ):
            if heat and holds(state, hunter.ref, "trapped"):
                raise WorkflowError("The original Girl cannot spend Heat while actually trapped")
            sheet = state.sheets[hunter.ref.entity]
            spend_heat(sheet, heat)
            if heat:
                sheet.revision += 1
            return case.model_copy(
                update=dict(roll=Roll(faces=self.game.dice.roll(), heat=heat, event=event))
            )
        if (
            step == "bait"
            and owner
            and case.roll
            and case.roll.result == "mid"
            and not case.bait
            and not selected
            and heat is None
            and 0 < len(account.strip()) <= 1200
            and hunter.custody in (None, "free")
        ):
            return case.model_copy(update=dict(bait=event, bait_account=account.strip()))
        if (
            step == "discover"
            and viewer.user_id == case.gm
            and case.bait
            and not selected
            and heat is None
            and 0 < len(account.strip()) <= 1200
        ):
            world = state.world
            assert world is not None
            actual = next(x for x in world.npcs if x.id == case.guise.entity)
            return case.model_copy(
                update=dict(discovered=event, name=actual.name, proof=account.strip())
            )
        raise WorkflowError(
            "Complete this saved search's actual original choice or keep it pending"
        )
