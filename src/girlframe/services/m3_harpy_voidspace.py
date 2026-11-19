"""An original Harpy's carried Girl may gain actual Void through an owned continuation."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat_state import Declaration, DefeatEffect
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_void import FINAL
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "harpy.harpy.come-to-me-now-once-again"
KIND = "harpy_voidspace_carry"
APPROACHES = {
    "fractal_patterns": "Share fractal patterns",
    "venom": "Offer the Harpy’s venom",
    "lost_names": "Speak the names of lost Girls",
    "lullaby": "Sing a quiet lullaby",
    "dying_stars": "Show her dying stars",
    "former_link": "Leave her pilot suit and link behind",
    "anger": "Let her express her anger",
    "reshape": "Help her change her form",
    "harpy_blood": "Share the Harpy’s blood",
    "intimacy": "Offer an intimate encounter",
    "confession": "Ask her to recite a confession",
    "embrace": "Hold her in a long embrace",
    "impossible_song": "Share an impossible song",
    "memory": "Share one of your memories",
    "portal_lesson": "Teach her about the portals",
    "moon_walk": "Let her walk the craters",
    "kiss": "Offer an intense kiss",
    "reassurance": "Tell her you love her",
}


class Round(Model):
    event: str
    account: str
    method: str | None
    response: str | None = None
    accepted: bool = False
    used_method: str | None = None
    asset: str | None = None
    work: str | None = None


class Return(Model):
    event: str
    work: str
    frame: str
    cell: tuple[int, int]
    route: str
    response: str | None = None
    accepted: bool = False
    completed: str | None = None
    rejected: str | None = None
    review: str | None = None


class Carry(Model):
    id: str
    escape: str
    harpy: ActorRef
    girl: ActorRef
    controller: int
    gm: int
    appointment: str
    scene: str
    account: str
    verified: str | None = None
    declined: str | None = None
    verification: str | None = None
    rounds: tuple[Round, ...] = ()
    returning: Return | None = None

    @property
    def outstanding(self) -> Round | None:
        current = self.rounds[-1] if self.rounds else None
        return current if current and current.response is None else None

    @property
    def threshold(self) -> str | None:
        return next((step.work for step in reversed(self.rounds) if step.work), None)


def carries(state: GameState) -> tuple[Carry, ...]:
    return tuple(Carry.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def _put(state: GameState, carry: Carry) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, carry.id)]
    state.facts.append(dict(kind=KIND, id=carry.id, body=carry.model_dump_json()))


def _history(
    c: Connection,
    game: GameService,
    event: str,
    *,
    kind: str | None = None,
    human: int | None = None,
) -> GameState | None:
    table = t.m2["m2_state_history"]
    query = sa.select(table.c.body_json).where(
        table.c.campaign_id == game.store.campaign_id, table.c.event_id == event
    )
    if kind is not None:
        query = query.join(t.events, t.events.c.id == table.c.event_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == kind,
            t.events.c.actor_id == str(human),
        )
    raw = c.scalar(query)
    return GameState.model_validate_json(raw) if raw else None


class HarpyVoidspaceService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        try:
            access.require_specialist_rule(RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _escape(
        self, c: Connection, state: GameState, identity: str
    ) -> tuple[DefeatEffect, Declaration]:
        effect = next((x for x in state.harpy_defeats if x.id == identity), None)
        if (
            effect is None
            or effect.choice != "kidnap"
            or effect.tier != "high"
            or effect.phase != "complete"
            or not effect.escaped
            or effect.girl is None
            or effect.girl.kind != "pilot"
            or set(effect.departed) != {effect.actor, effect.girl}
        ):
            raise WorkflowError("Use the actual completed Harpy kidnapping")
        action = self.game.action(c, effect.action)
        service = HarpyDefeatService(self.store, self.game)
        declaration = service._declaration(c, action)
        work, work_body, owner = service._source(c, declaration.work, pending=False)
        receipt = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        historical = _history(c, self.game, effect.source_event)
        if (
            action["state"] != "complete"
            or not receipt
            or json.loads(receipt) != action["data"].get("receipt")
            or declaration.actor != effect.actor
            or declaration.cast != effect.source_cast
            or work["state"] != "resolved"
            or work_body.get("defeat_action") != action["id"]
            or owner != effect.actor
            or historical is None
            or effect not in historical.harpy_defeats
        ):
            raise WorkflowError("Recover the actual owned Defeat roll and kidnapping receipt")
        girl = state.sheets.get(effect.girl.entity)
        original = next((x for x in historical.placements if x.actor == effect.girl), None)
        now = next((x for x in state.placements if x.actor == effect.girl), None)
        body = resolve(state, effect.actor, (), require_alive=False, require_current_profile=False)
        if (
            girl is None
            or girl.character_id != effect.girl.incarnation
            or original is None
            or now is None
            or now.custody != effect.actor
            or now.source_event != original.source_event
            or now.source_event != effect.source_event
            or now.girl_cell is not None
            or now.frame_instance != original.frame_instance
            or body.controller != declaration.controller
            or not body.alive
            or body.cell is not None
        ):
            raise WorkflowError("Recover both original bodies still offstage in this custody")
        return effect, declaration

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_voidspace",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def start(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            effect, declared = self._escape(c, state, identity)
            gm, appointment = MedicalService(self.store)._handler(c)
            if (
                revision != state.revision
                or viewer.user_id != declared.controller
                or (gm, appointment) != (declared.gm_controller, declared.appointment)
                or not 0 < len(account.strip()) <= 1200
                or any(x.escape == identity and x.declined is None for x in carries(state))
            ):
                raise WorkflowError(
                    "Use the original Harpy’s owned passage and original facilitator"
                )
            event = str(uuid4())
            assert effect.girl is not None
            carry = Carry(
                id=event,
                escape=identity,
                harpy=effect.actor,
                girl=effect.girl,
                controller=declared.controller,
                gm=gm,
                appointment=appointment,
                scene=declared.cast.id,
                account=account.strip(),
            )
            _put(state, carry)
            self.game.event(
                c, viewer.user_id, key, "m3.harpy_voidspace_proposed", state, event_id=event
            )
            return dict(id=event)

        return self._write(
            viewer, key, dict(escape=identity, revision=revision, account=account), operation
        )

    def _assets(self, state: GameState, actor: ActorRef) -> dict[str, str]:
        return {
            x.id: x.name
            for x in effective_assets(state, actor)
            if x.family == "girl" and not x.void
        }

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[str, str], ...]:
        steps = []
        cases = carries(state)
        for carry in cases:
            if carry.declined is not None:
                continue
            returning = carry.returning
            if returning is not None and returning.completed:
                continue
            if not carry.verified and viewer.user_id == carry.gm:
                steps.append((carry.id, "verify"))
            elif (
                carry.verified
                and carry.outstanding is not None
                and int(carry.girl.entity) == viewer.user_id
            ):
                steps.append((carry.id, "gain"))
            elif carry.threshold and carry.verified:
                if (
                    returning is None
                    or returning.rejected
                    or returning.response
                    and not returning.accepted
                ):
                    if viewer.user_id == carry.controller:
                        steps.append((carry.id, "release_offer"))
                elif returning.response is None and viewer.user_id == int(carry.girl.entity):
                    steps.append((carry.id, "release_accept"))
                elif returning.accepted and viewer.user_id == carry.gm:
                    steps.append((carry.id, "release_verify"))
            elif (
                carry.verified
                and carry.outstanding is None
                and carry.controller == viewer.user_id
                and state.sheets.get(carry.girl.entity) is not None
                and self._assets(state, carry.girl)
            ):
                steps.append((carry.id, "offer"))
        for effect in state.harpy_defeats:
            if (
                effect.choice == "kidnap"
                and effect.phase == "complete"
                and not any(x.escape == effect.id and x.declined is None for x in cases)
            ):
                try:
                    _, declared = self._escape(c, state, effect.id)
                    if declared.controller == viewer.user_id:
                        steps.append((effect.id, "propose"))
                except (ValueError, WorkflowError):
                    continue
        if steps:
            try:
                self._gate(c, viewer)
            except WorkflowError:
                return ()
        return tuple(steps)

    def _case(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Carry, str]:
        carry = next((x for x in carries(state) if x.id == identity), None)
        step = dict(self.tasks(c, state, viewer)).get(identity)
        if carry is None or step not in (
            "verify",
            "offer",
            "gain",
            "release_offer",
            "release_accept",
            "release_verify",
        ):
            raise WorkflowError("This original private Harpy passage is unavailable")
        effect, declared = self._escape(c, state, carry.escape)
        if (
            carry.controller != declared.controller
            or carry.harpy != effect.actor
            or carry.girl != effect.girl
            or carry.scene != declared.cast.id
            or MedicalService(self.store)._handler(c) != (carry.gm, carry.appointment)
        ):
            raise WorkflowError("Recover the original carry and original appointment")
        proposed = _history(
            c, self.game, carry.id, kind="m3.harpy_voidspace_proposed", human=carry.controller
        )
        root = carry.model_copy(
            update=dict(verified=None, verification=None, rounds=(), returning=None)
        )
        if proposed is None or root not in carries(proposed):
            raise WorkflowError("Recover the original verified Voidspace passage")
        if carry.verified:
            verified = _history(
                c, self.game, carry.verified, kind="m3.harpy_voidspace_verify", human=carry.gm
            )
            if verified is None or carry.model_copy(
                update=dict(rounds=(), returning=None)
            ) not in carries(verified):
                raise WorkflowError("Recover the original GM’s actual Voidspace verification")
        if carry.outstanding:
            offered = _history(
                c,
                self.game,
                carry.outstanding.event,
                kind="m3.harpy_voidspace_offer",
                human=carry.controller,
            )
            if offered is None or carry not in carries(offered):
                raise WorkflowError("Recover the actual original Void experience offered")
        if carry.returning:
            self._prove_return(c, carry)
        return carry, step

    def _prove_return(self, c: Connection, carry: Carry) -> None:
        value = carry.returning
        assert value is not None
        undecided = value.model_copy(update=dict(rejected=None, review=None))
        original = undecided.model_copy(update=dict(response=None, accepted=False))
        offered = _history(
            c,
            self.game,
            value.event,
            kind="m3.harpy_voidspace_release_offer",
            human=carry.controller,
        )
        if offered is None or carry.model_copy(update=dict(returning=original)) not in carries(
            offered
        ):
            raise WorkflowError("Recover the original retained route from the Harpy")
        if value.response:
            decided = _history(
                c,
                self.game,
                value.response,
                kind="m3.harpy_voidspace_release_accept",
                human=int(carry.girl.entity),
            )
            if decided is None or carry.model_copy(update=dict(returning=undecided)) not in carries(
                decided
            ):
                raise WorkflowError("Recover the original Girl’s actual decision about return")
        if value.rejected:
            reviewed = _history(
                c,
                self.game,
                value.rejected,
                kind="m3.harpy_voidspace_release_verify",
                human=carry.gm,
            )
            if reviewed is None or carry not in carries(reviewed):
                raise WorkflowError("Recover the original facilitator’s actual return review")

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            step = dict(self.tasks(c, state, viewer)).get(identity)
            if step == "propose":
                return dict(step=step, revision=state.revision)
            carry, step = self._case(c, state, viewer, identity)
            pending = carry.outstanding if step == "gain" else None
            route = carry.returning
            return dict(
                step=step,
                revision=state.revision,
                account=carry.account if step == "verify" else pending.account if pending else "",
                method=pending.method if pending else None,
                assets=self._assets(state, carry.girl) if step == "gain" else {},
                route=route.route if route and step in ("release_accept", "release_verify") else "",
                destination=route.cell
                if route and step in ("release_accept", "release_verify")
                else None,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        account: str = "",
        method: str | None = None,
        asset: str | None = None,
        allow: bool | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            carry, expected = self._case(c, state, viewer, identity)
            if (
                revision != state.revision
                or expected != step
                or len(account.strip()) > 1200
                or step not in ("gain", "release_accept")
                and not account.strip()
            ):
                raise WorkflowError("Refresh the actual original Voidspace decision")
            event = str(uuid4())
            work = None
            if step == "verify" and type(allow) is bool and asset is None and method is None:
                carry = carry.model_copy(
                    update=dict(
                        verified=event if allow else None,
                        declined=None if allow else event,
                        verification=account.strip(),
                    )
                )
            elif step == "offer" and allow is None and asset is None:
                sheet = state.sheets[carry.girl.entity]
                if (
                    method is not None
                    and method not in APPROACHES
                    or not any(x.family == "girl" for x in sheet.assets)
                    or any(
                        x.actor == carry.girl and x.stage not in FINAL
                        for x in state.void_thresholds
                    )
                ):
                    raise WorkflowError("Choose an actual approach after required Void work")
                carry = carry.model_copy(
                    update=dict(
                        rounds=(
                            *carry.rounds,
                            Round(event=event, method=method, account=account.strip()),
                        )
                    )
                )
            elif step == "gain" and type(allow) is bool and carry.outstanding is not None:
                original = carry.outstanding
                result = dict(response=event, accepted=allow)
                if allow:
                    selection = original.method or method
                    if (
                        selection not in APPROACHES
                        or original.method is not None
                        and method is not None
                        or asset not in self._assets(state, carry.girl)
                        or not account.strip()
                        or any(
                            x.actor == carry.girl and x.stage not in FINAL
                            for x in state.void_thresholds
                        )
                    ):
                        raise WorkflowError(
                            "Choose the actual experience and your exact clean Girl Asset"
                        )
                    assert asset is not None
                    state, required = alter(
                        state, carry.girl, asset, account.strip(), carry.id, event, piloting=False
                    )
                    applied = any(
                        x.id == asset and x.void for x in effective_assets(state, carry.girl)
                    )
                    if applied and any(x.kind == "girl_void_threshold" for x in required):
                        work = f"{event}:void:girl"
                    result.update(
                        used_method=selection, asset=asset if applied else None, work=work
                    )
                elif asset is not None or method is not None or account:
                    raise WorkflowError("Decline without selecting or applying an Asset change")
                carry = carry.model_copy(
                    update=dict(rounds=(*carry.rounds[:-1], original.model_copy(update=result)))
                )
            elif step.startswith("release_") and method is None and asset is None:
                state, carry = self._release(c, state, carry, step, allow, account.strip(), event)
            else:
                raise WorkflowError("Use only the fields for this original decision")
            _put(state, carry)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_voidspace_" + step,
                state,
                event_id=event,
            )
            if work:
                self._void(c, carry, work, event)
            return dict(id=identity, event=event, work=work)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                method=method,
                asset=asset,
                allow=allow,
                account=account,
            ),
            operation,
        )

    def _release(
        self,
        c: Connection,
        state: GameState,
        carry: Carry,
        step: str,
        allow: bool | None,
        account: str,
        event: str,
    ) -> tuple[GameState, Carry]:
        from girlframe.engine import m3_physical as physical
        from girlframe.services.m3_void import prepare_threshold, source

        work = carry.threshold
        if work is None:
            raise WorkflowError("Recover the actual pending Void threshold before return")
        route = carry.returning
        if route is not None and allow is False:
            if step == "release_accept" and not account:
                rejected = route.model_copy(update=dict(response=event, accepted=False))
                return state, carry.model_copy(update=dict(returning=rejected))
            if step == "release_verify" and route.accepted:
                rejected = route.model_copy(update=dict(rejected=event, review=account))
                return state, carry.model_copy(update=dict(returning=rejected))
        row, _, owner = source(self.game, c, work)
        _, threshold = prepare_threshold(c, self.game, work, state)
        if row["state"] != "pending" or owner != carry.girl or threshold.stage != "allured":
            raise WorkflowError("Recover the actual original Girl's pending approach to her Frame")
        body = next((x for x in state.placements if x.actor == carry.girl), None)
        if (
            body is None
            or body.frame_instance != threshold.frame_instance
            or body.frame_cell is None
            or body.custody != carry.harpy
            or body.incapacitated
            or not body.vitals_active
            or state.sheets[carry.girl.entity].frame_scrapped
        ):
            raise WorkflowError("Recover the original capable Girl and her parked Frame")
        if step == "release_offer" and allow is None:
            route = Return(
                event=event,
                work=work,
                frame=body.frame_instance,
                cell=body.frame_cell,
                route=account,
            )
        elif route is None or (route.frame, route.cell, route.work) != (
            body.frame_instance,
            body.frame_cell,
            work,
        ):
            raise WorkflowError("Recover the original parked Frame and approved route")
        elif step == "release_accept" and type(allow) is bool and not account:
            route = route.model_copy(update=dict(response=event, accepted=allow))
        elif step == "release_verify" and allow is True and route.accepted:
            physical._source(state, event, account, carry.girl)
            physical._save(
                state,
                body.model_copy(
                    update=dict(
                        custody=None, girl_cell=route.cell, source_event=event, account=account
                    )
                ),
            )
            state = physical._finish(state, carry.girl, event, account, "harpy_voidspace_return")
            route = route.model_copy(update=dict(completed=event, review=account))
        else:
            raise WorkflowError("Record the original owned return decision")
        return state, carry.model_copy(update=dict(returning=route))

    def _void(self, c: Connection, carry: Carry, work: str, event: str) -> None:
        related(
            c,
            self.store,
            dict(campaign_id=self.store.campaign_id, scene_id=carry.scene),
            work,
            int(carry.girl.entity),
            int(carry.girl.entity),
            "void_threshold",
            dict(
                owner=carry.girl.model_dump(mode="json"),
                character=carry.girl.incarnation,
                source_action=None,
                source_pdf=19,
                reason=KIND,
                case=carry.id,
                details=dict(family="girl"),
            ),
            event,
        )


def prove_void(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    carry = next((x for x in carries(state) if x.id == body.get("case")), None)
    if carry is None or carry.girl != actor or not carry.verified or carry.scene != row["scene_id"]:
        raise WorkflowError("Recover the original private Harpy passage")
    final = next(
        (x for x in carry.rounds if x.work == row["id"] and x.response == row["event_id"]), None
    )
    original = _history(
        c, game, row["event_id"], kind="m3.harpy_voidspace_gain", human=int(actor.entity)
    )
    if (
        final is None
        or not final.accepted
        or original is None
        or carry not in carries(original)
        or not any(x.id == final.asset and x.void for x in effective_assets(state, actor))
    ):
        raise WorkflowError("Recover the actual original owned Void depth and its source")


def audience(game: GameService, c: Connection, state: GameState, body: dict[str, Any]) -> list[int]:
    carry = next((x for x in carries(state) if x.id == body.get("case")), None)
    if carry is None or MedicalService(game.store)._handler(c) != (carry.gm, carry.appointment):
        raise WorkflowError("Recover the original Harpy passage’s scope")
    return sorted({int(carry.girl.entity), carry.gm})
