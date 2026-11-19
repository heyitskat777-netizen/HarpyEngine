"""Original participants retain authority over approved private Ancillary Plays."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_actor_plays as actor_plays
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre_rank
from girlframe.engine.m2 import GameState, IdentityState, tier
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, make_helpless
from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import (
    ActorRef,
    ActorView,
    CastRole,
    Model,
    ProfileBinding,
    SceneCast,
)
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import damage
from girlframe.engine.m3_cast import validate_role
from girlframe.engine.m3_chained_darling import EXEMPTION
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_world import update as update_world
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

CHAINED = "ancillary.chained-darling.sex-play"
WARBOY = "ancillary.warboy.sex-play"
ANGEL = "ancillary.angel-wife.sex-play"
CHASTE = "ancillary.angel-wife.chaste"
REVOLUTIONARY = "ancillary.revolutionary-idealist.sex-play"
PRODIGY = "ancillary.prodigy.sex-play"
MERCENARY = "ancillary.mercenary.sex-play"
ABYSSAL = "ancillary.abyssal-acolyte.sex-play"
SOLDIER = "ancillary.soldier.sex-play"
REVOLUTIONARY_OPTIONS = ("erase", "tag", "remain")
RULES: dict[ancillary.Book, str] = {
    "CHAINED DARLING": CHAINED,
    "WARBOY": WARBOY,
    "ANGEL-WIFE": ANGEL,
    "REVOLUTIONARY IDEALIST": REVOLUTIONARY,
    "PRODIGY": PRODIGY,
    "MERCENARY": MERCENARY,
    "ABYSSAL ACOLYTE": ABYSSAL,
    "SOLDIER": SOLDIER,
}
WARBOY_REFUSAL = "warboy_private_refusal"
RESULTS = {
    "CHAINED DARLING": {"low": "ask", "mid": "middle", "high": "tag"},
    "WARBOY": {"low": "warboy_bond", "mid": "warboy_weaken", "high": "warboy_strong"},
    "ANGEL-WIFE": {"low": "angel_replace", "mid": "angel_tag", "high": "angel_replace"},
    "REVOLUTIONARY IDEALIST": {
        "low": "revolutionary_erase_two",
        "mid": "revolutionary_clear",
        "high": "revolutionary_offer",
    },
    "PRODIGY": {"low": "prodigy_low", "mid": "prodigy_rank", "high": "prodigy_choose"},
    "MERCENARY": {
        "low": "mercenary_low_hold",
        "mid": "mercenary_request",
        "high": "mercenary_high_hold",
    },
    "ABYSSAL ACOLYTE": {
        "low": "abyssal_void_hold",
        "mid": "abyssal_erase_tag",
        "high": "abyssal_ask",
    },
    "SOLDIER": {"low": "soldier_rank_low", "mid": "soldier_mid", "high": "soldier_high"},
}
KIND = "ancillary_private_play"


class Dice(Model):
    faces: tuple[int, int]
    heat: int
    source: str
    rng: str

    @property
    def result(self) -> str:
        return tier(sum(self.faces) + self.heat)


class Encounter(Model):
    id: str
    book: ancillary.Book
    actor: CastRole
    partner: CastRole
    channel: int
    scene: str
    gm: int
    appointment: str
    step: Literal[
        "consent",
        "verify",
        "roll",
        "middle",
        "tag",
        "reaffirm",
        "ask",
        "answer",
        "closed",
        "warboy_bond",
        "warboy_weaken",
        "warboy_strong",
        "warboy_partner_tag",
        "warboy_identity",
        "warboy_replace",
        "chaste",
        "angel_tag",
        "angel_space",
        "angel_replace",
        "angel_damage",
        "angel_helpless",
        "revolutionary_erase_two",
        "revolutionary_clear",
        "revolutionary_offer",
        "revolutionary_choice",
        "revolutionary_erase",
        "revolutionary_tag",
        "revolutionary_release",
        "revolutionary_escape",
        "prodigy_low",
        "prodigy_rank",
        "prodigy_choose",
        "prodigy_jealous",
        "mercenary_low_hold",
        "mercenary_high_hold",
        "mercenary_request",
        "mercenary_reply",
        "mercenary_verify",
        "mercenary_give_tag",
        "abyssal_void_hold",
        "abyssal_erase_tag",
        "abyssal_leave",
        "abyssal_ask",
        "abyssal_reply",
        "abyssal_verify",
        "abyssal_damage",
        "soldier_rank_low",
        "soldier_mid",
        "soldier_high",
        "soldier_repair",
        "soldier_alone",
    ]
    consent: str | None = None
    confirmed: str | None = None
    roll: Dice | None = None
    tag: str | None = None
    account: str | None = None
    answer: str | None = None
    disposition: str | None = None
    identity: str | None = None
    partner_pose: str | None = None
    partner_cell: tuple[int, int] | None = None
    picks: tuple[str, ...] = ()
    reaction_actor: ActorRef | None = None
    reaction_owner: int | None = None
    repair_asset: str | None = None
    repair_resource: str | None = None


def records(state: GameState) -> tuple[Encounter, ...]:
    return tuple(
        Encounter.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def _related(state: GameState, actor: ActorRef) -> set[ActorRef]:
    people = {
        edge.second if edge.first == actor else edge.first
        for edge in state.actor_bonds
        if actor in (edge.first, edge.second)
    }
    handler = active_handler(state)
    if handler:
        people.add(handler)
    people.update(
        current_ref(state, int(key)) for key in state.sheets if state.sheets[key].character_id
    )
    if state.world:
        people.update(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive)
    return {person for person in people if person != actor and depth(state, actor, person) > 0}


def _replaceable(state: GameState, actor: ActorRef) -> dict[str, str]:
    original = ancillary.find(state, actor)
    return (
        {x.id: x.name for x in original.identities if not x.protected and not x.paired}
        if (original and len(original.identities) >= 4)
        else {}
    )


class AncillaryIntimacyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer, book: ancillary.Book | None = None) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        if book is not None:
            gate = Access(self.store)
            rule = RULES.get(book)
            if gate.registry is None or rule is None:
                raise WorkflowError("The original Ancillary Play awaits its approved rule port.")
            gate.require_specialist_rule(rule)
            if book == "ANGEL-WIFE":
                gate.require_specialist_rule(CHASTE)
            gate.registry.require_available(ancillary.STARTERS[book].rule)

    def _separated(self, first: ActorView, second: ActorView, case: Encounter) -> bool:
        return bool(
            case.partner_pose
            and case.partner_pose != second.position_sha256
            and first.cell != second.cell
            and case.partner_cell != second.cell
        )

    def _person(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorRef,
    ) -> tuple[CastRole, ActorView]:
        actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        role = validate_role(cast, actual)
        if (
            actual.cell is None
            or actual.offstage_source
            or actual.custody not in (None, "free", "converted")
            or not knowledge_allowed(state, actor)
        ):
            raise WorkflowError("Recover the original participant in the actual scene.")
        return role, actual

    def _scene(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
    ) -> tuple[SceneCast, CastRole, ActorView, ancillary.Book, int, str]:
        cast = _cast(self.game, c, state, channel)
        role, actual = self._person(c, state, cast, actor)
        original = ancillary.find(state, actor)
        gm, appointment = MedicalService(self.store)._handler(c)
        if original is None or original.draft.book not in RULES or cast.facilitator != gm:
            raise WorkflowError(
                "Use an approved actual Ancillary role with the original facilitator."
            )
        return cast, role, actual, original.draft.book, gm, appointment

    def _together(self, first: ActorView, second: ActorView) -> bool:
        return first.cell == second.cell and (
            first.inside_frame is second.inside_frame is False
            or (
                first.inside_frame is second.inside_frame is True
                and first.occupied_frame_instance is not None
                and first.occupied_frame_instance == second.occupied_frame_instance
            )
        )

    def options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        actor: ActorRef,
    ) -> dict[str, str]:
        cast, role, actual, book, _, _ = self._scene(c, state, channel, actor)
        self._gate(c, viewer, book)
        if role.controller != viewer.user_id:
            raise WorkflowError("The original participant can only invite as their own character.")
        blocked = {
            x.partner.actor
            for x in records(state)
            if x.step != "closed" and x.actor == role and x.scene == cast.id
        }
        people = {}
        for member in cast.roles:
            if (
                member.actor.kind != "pilot"
                or member.controller == viewer.user_id
                or member.actor in blocked
            ):
                continue
            try:
                _, other = self._person(c, state, cast, member.actor)
            except (ValueError, WorkflowError):
                continue
            if other.rules == "girl_frame" and self._together(actual, other):
                people[other.ref.token] = other.label
        return people

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            people = self.options(c, state, viewer, channel, actor)
            return dict(revision=state.revision, people=people)

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        case: Encounter,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
        state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.ancillary_private_" + case.step,
            state,
            event_id=event,
            scene_id=case.scene,
        )
        return dict(id=case.id, step=case.step, event=event)

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
                "m3.ancillary_private_play",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_clear(self.game, c, channel)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or target not in self.options(
                c, state, viewer, channel, actor
            ):
                raise WorkflowError("Choose an eligible original counterpart in the current scene.")
            cast, role, _, book, gm, appointment = self._scene(c, state, channel, actor)
            partner = next(x for x in cast.roles if x.actor.token == target)
            event = str(uuid4())
            value = Encounter(
                id=event,
                book=book,
                actor=role,
                partner=partner,
                channel=channel,
                scene=cast.id,
                gm=gm,
                appointment=appointment,
                step="consent",
            )
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                target=target,
            ),
            operation,
        )

    def _recipient(self, case: Encounter) -> int | None:
        if case.step in (
            "consent",
            "tag",
            "answer",
            "warboy_partner_tag",
            "warboy_identity",
            "angel_space",
            "angel_replace",
            "angel_helpless",
            "revolutionary_erase_two",
            "revolutionary_choice",
            "revolutionary_erase",
            "revolutionary_tag",
            "revolutionary_release",
            "prodigy_low",
            "mercenary_reply",
            "abyssal_reply",
        ):
            return case.partner.controller
        if case.step in (
            "roll",
            "middle",
            "reaffirm",
            "ask",
            "warboy_bond",
            "warboy_weaken",
            "warboy_strong",
            "warboy_replace",
            "chaste",
            "angel_tag",
            "angel_damage",
            "revolutionary_clear",
            "revolutionary_offer",
            "revolutionary_escape",
            "prodigy_choose",
            "mercenary_request",
            "mercenary_give_tag",
            "abyssal_erase_tag",
            "abyssal_leave",
            "abyssal_ask",
            "abyssal_damage",
            "soldier_mid",
            "soldier_high",
            "soldier_repair",
        ):
            return case.actor.controller
        if case.step == "prodigy_jealous":
            return case.reaction_owner
        return (
            case.gm
            if case.step
            in (
                "verify",
                "prodigy_rank",
                "mercenary_verify",
                "mercenary_low_hold",
                "mercenary_high_hold",
                "abyssal_void_hold",
                "abyssal_verify",
                "soldier_rank_low",
                "soldier_alone",
            )
            else None
        )

    def _source(self, c: Connection, state: GameState, case: Encounter) -> ActorView:
        cast, actor, actual, book, gm, appointment = self._scene(
            c, state, case.channel, case.actor.actor
        )
        role, partner = self._person(c, state, cast, case.partner.actor)
        if (
            (cast.id, actor, role, book, gm, appointment)
            != (
                case.scene,
                case.actor,
                case.partner,
                case.book,
                case.gm,
                case.appointment,
            )
            or case.step
            not in (
                "angel_space",
                "revolutionary_escape",
                "abyssal_leave",
                "soldier_repair",
                "soldier_alone",
            )
            and not self._together(actual, partner)
            or partner.rules != "girl_frame"
        ):
            raise WorkflowError("Recover the original private encounter and both present actors.")
        return actual

    def _revalidate_reaction(self, state: GameState, case: Encounter) -> None:
        if case.step != "prodigy_jealous":
            return
        if not any(
            person == case.reaction_actor and owner == case.reaction_owner
            for person, owner, _ in _prodigy_people(state, case.actor.actor).values()
        ):
            raise WorkflowError("Recover the original living NPC Bond and its actual controller.")

    def _get(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[Encounter, ActorView]:
        case = next((x for x in records(state) if x.id == identity), None)
        if case is None or self._recipient(case) != viewer.user_id:
            raise WorkflowError("This original private encounter is unavailable.")
        self._gate(c, viewer, case.book)
        self._revalidate_reaction(state, case)
        return case, self._source(c, state, case)

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[str, str], ...]:
        ready = []
        for case in records(state):
            recipient = self._recipient(case)
            participant = viewer.user_id in (case.actor.controller, case.partner.controller)
            if case.step == "closed" or not (recipient == viewer.user_id or participant):
                continue
            try:
                self._gate(c, viewer, case.book)
            except (ValueError, WorkflowError):
                continue
            if participant:
                ready.append((case.id, "withdraw"))
            if recipient == viewer.user_id:
                try:
                    self._source(c, state, case)
                    self._revalidate_reaction(state, case)
                except (ValueError, WorkflowError):
                    continue
                ready.append((case.id, case.step))
        return tuple(ready)

    def _withdrawal(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> Encounter:
        case = next((x for x in records(state) if x.id == identity), None)
        if (
            case is None
            or case.step == "closed"
            or viewer.user_id not in (case.actor.controller, case.partner.controller)
        ):
            raise WorkflowError("This original withdrawal is unavailable.")
        self._gate(c, viewer, case.book)
        return case

    def withdrawal(self, viewer: GuildViewer, identity: str) -> int:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            self._withdrawal(c, state, viewer, identity)
            return state.revision

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, actual = self._get(c, state, viewer, identity)
            counterpart = resolve(
                state,
                case.partner.actor,
                profiles(c, self.store.campaign_id),
            )
            role = ancillary.find(state, case.actor.actor)
            label = (
                next((tag.label for tag in role.tags if tag.id == case.tag), None)
                if case.step == "reaffirm" and role is not None
                else None
            )
            if case.step == "prodigy_jealous":
                return dict(revision=state.revision, step=case.step, known=actual.label)
            return dict(
                revision=state.revision,
                step=case.step,
                heat=actual.heat if case.step == "roll" else None,
                account=case.account,
                actual_favor=case.answer
                if case.step in ("mercenary_verify", "abyssal_verify")
                else None,
                participants=(actual.label, counterpart.label),
                tier=case.roll.result if case.roll else None,
                tag=label,
                identity=case.identity if case.step == "warboy_replace" else None,
                replace=_replaceable(state, actual.ref)
                if case.step == "warboy_replace"
                else _angel_identities(state, actual.ref)
                if case.step == "angel_replace"
                else {},
                assets=_angel_assets(counterpart)
                if case.step == "angel_damage"
                else _abyssal_assets(counterpart)
                if case.step == "abyssal_damage"
                else {},
                stepped_away=(
                    case.step == "angel_space"
                    and self._separated(actual, counterpart, case)
                    or case.step in ("revolutionary_escape", "abyssal_leave")
                    and self._separated(counterpart, actual, case)
                ),
                can_change_status=case.step
                in (
                    "prodigy_rank",
                    "prodigy_low",
                    "soldier_mid",
                    "soldier_high",
                )
                and cadre_rank.current(state, actual.ref) is not None,
                soldier_bond=depth(state, actual.ref, counterpart.ref)
                if case.step == "soldier_mid"
                else None,
                own_damaged={x.id: x.name for x in actual.assets if x.damaged and not x.concealed}
                if case.step == "soldier_repair"
                else {},
                repair_choices=_soldier_resources(state, actual.ref, case.scene)
                if case.step == "soldier_repair"
                else {},
                npc_bonds={
                    key: label for key, (_, _, label) in _prodigy_people(state, actual.ref).items()
                }
                if case.step == "prodigy_choose"
                else {},
                offered=case.picks if case.step == "revolutionary_choice" else (),
                identities=_revolutionary_identities(state, actual.ref)
                if case.step in ("revolutionary_erase", "revolutionary_erase_two")
                else _abyssal_identities(state, counterpart.ref)
                if case.step == "abyssal_erase_tag"
                else {},
            )

    def withdraw(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self._withdrawal(c, state, viewer, identity)
            if state.revision != revision:
                raise WorkflowError("Reopen the original withdrawal.")
            event = str(uuid4())
            closed = case.model_copy(update=dict(step="closed", disposition="withdrawn"))
            return self._save(c, state, viewer, key, closed, event)

        return self._write(
            viewer, key, dict(id=identity, revision=revision, withdrawal=True), operation
        )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        *,
        heat: int = 0,
        account: str = "",
        picks: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case, actual = self._get(c, state, viewer, identity)
            MedicalService(self.store)._idle(c)
            require_clear(self.game, c, case.channel)
            require_scene_clear(self.game, c, case.channel)
            if (
                state.revision != revision
                or type(heat) is not int
                or heat < 0
                or len(account) > 1200
                or case.step != "roll"
                and heat
                or len(picks) > (4 if case.step == "abyssal_damage" else 2)
                or len(set(picks)) != len(picks)
                or picks
                and case.step
                not in (
                    "revolutionary_offer",
                    "revolutionary_erase",
                    "revolutionary_erase_two",
                    "abyssal_damage",
                    "soldier_repair",
                )
            ):
                raise WorkflowError(
                    "Reopen the original choice and use only its allowed resources."
                )
            event = str(uuid4())
            update: dict[str, Any]
            if case.step == "consent" and choice in ("yes", "no") and not account:
                update = (
                    dict(step="verify", consent=event)
                    if choice == "yes"
                    else dict(step="closed", disposition="declined")
                )
            elif case.step == "verify" and choice in ("yes", "no") and not account:
                update = (
                    dict(step="chaste" if case.book == "ANGEL-WIFE" else "roll", confirmed=event)
                    if choice == "yes"
                    else dict(step="closed", disposition="unconfirmed")
                )
            elif case.step == "chaste" and choice in ("man", "not_man") and not account:
                if choice == "man":
                    update = dict(step="roll")
                elif any(
                    depth(state, actual.ref, person) == 2 for person in _related(state, actual.ref)
                ):
                    raise WorkflowError("The original Intense Bond needs human Chaste review.")
                else:
                    update = dict(step="closed", disposition="chaste")
            elif case.step == "roll" and choice == "roll" and not account:
                state = commit(
                    state,
                    actual.ref,
                    profiles(c, self.store.campaign_id),
                    Commitment(heat=heat),
                    actual.source_sha256,
                ).state
                faces = self.game.dice.roll()
                if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                    raise ValueError("Dice source returned invalid faces.")
                dice = Dice(faces=faces, heat=heat, source=event, rng=self.game.rng_source)
                update = dict(roll=dice, step=RESULTS[case.book][dice.result])
            elif case.step == "middle" and choice == "apply" and not account:
                state = make_helpless(state, case.partner.actor, case.actor.actor, event)
                state.facts.append(
                    dict(
                        kind=EXEMPTION,
                        actor=case.actor.actor.token,
                        cast=case.actor.source_event,
                        scene=case.scene,
                        source=event,
                    )
                )
                update = dict(step="closed", disposition="applied")
            elif case.step == "tag" and choice == "tag" and 0 < len(account.strip()) <= 120:
                tag = str(uuid4())
                state = give_tag(
                    state,
                    case.actor.actor,
                    case.partner.actor,
                    account.strip(),
                    event,
                    tag,
                    (case.actor.controller, case.partner.controller),
                )
                update = dict(step="reaffirm", tag=tag)
            elif case.step == "reaffirm" and choice == "act" and account.strip():
                original = ancillary.find(state, case.actor.actor)
                if original is None or not any(x.id == case.tag for x in original.tags):
                    raise WorkflowError("Recover the actual Tag from the original participant.")
                update = dict(step="closed", account=account.strip(), disposition="reaffirmed")
            elif case.step == "ask" and choice == "ask" and account.strip():
                update = dict(step="answer", account=account.strip())
            elif case.step == "answer" and choice == "answer" and account.strip():
                update = dict(step="closed", answer=account.strip(), disposition="answered")
            elif case.book == "WARBOY" and case.step.startswith("warboy_"):
                state, update = _warboy(state, case, choice, account.strip(), event)
            elif case.book == "ANGEL-WIFE" and case.step.startswith("angel_"):
                bindings = profiles(c, self.store.campaign_id)
                partner = resolve(state, case.partner.actor, bindings)
                if case.step == "angel_space" and choice == "confirm" and not account:
                    if not self._separated(actual, partner, case):
                        raise WorkflowError(
                            "Verify your actual departure through physical movement first."
                        )
                    update = dict(step="closed", disposition="space_given")
                else:
                    state, update = _angel(
                        state, case, partner, bindings, choice, account.strip(), event
                    )

            elif case.book == "REVOLUTIONARY IDEALIST" and case.step.startswith("revolutionary_"):
                partner = resolve(state, case.partner.actor, profiles(c, self.store.campaign_id))
                if case.step == "revolutionary_escape" and choice == "confirm" and not account:
                    if not self._separated(partner, actual, case):
                        raise WorkflowError(
                            "Verify your actual departure through physical movement first."
                        )
                    update = dict(step="closed", disposition="escaped")
                else:
                    state, update = _revolutionary(
                        state,
                        case,
                        actual,
                        choice,
                        account.strip(),
                        picks,
                        event,
                    )
            elif case.book == "PRODIGY" and case.step.startswith("prodigy_"):
                state, update = _prodigy(state, case, choice, account.strip(), event)
            elif case.book == "MERCENARY" and case.step.startswith("mercenary_"):
                state, update = _mercenary(state, case, choice, account.strip(), event)
            elif case.book == "ABYSSAL ACOLYTE" and case.step.startswith("abyssal_"):
                bindings = profiles(c, self.store.campaign_id)
                partner = resolve(state, case.partner.actor, bindings)
                if case.step == "abyssal_leave" and choice == "confirm" and not account:
                    if not self._separated(partner, actual, case):
                        raise WorkflowError("Verify your actual departure through movement first.")
                    update = dict(step="closed", disposition="abyssal_departed")
                else:
                    state, update = _abyssal(
                        state,
                        case,
                        actual,
                        partner,
                        bindings,
                        choice,
                        account.strip(),
                        picks,
                        event,
                    )
            elif case.book == "SOLDIER" and case.step.startswith("soldier_"):
                state, update = _soldier(
                    state,
                    case,
                    actual,
                    choice,
                    account.strip(),
                    picks,
                    event,
                )
            else:
                raise WorkflowError("Choose the original owner's supported private response.")
            return self._save(c, state, viewer, key, case.model_copy(update=update), event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                choice=choice,
                heat=heat,
                account=account,
                picks=picks,
            ),
            operation,
        )


def _warboy(
    state: GameState,
    case: Encounter,
    choice: str,
    account: str,
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, other = case.actor.actor, case.partner.actor
    audience = (case.actor.controller, case.partner.controller)
    if case.step == "warboy_weaken" and choice == "apply" and not account:
        if depth(state, actor, other):
            state = change(state, actor, other, -1, event)
        return state, dict(step="warboy_partner_tag")
    if case.step == "warboy_partner_tag" and choice == "pass" and not account:
        return state, dict(step="closed", disposition="weakened")
    if case.step == "warboy_partner_tag" and choice == "tag" and 0 < len(account) <= 120:
        tag = str(uuid4())
        state = give_tag(state, actor, other, account, event, tag, audience)
        return state, dict(step="closed", tag=tag, disposition="weakened")
    if case.step == "warboy_strong" and choice == "tag" and 0 < len(account) <= 120:
        people = sorted(_related(state, other), key=lambda x: x.token)
        for person in people:
            state = change(state, other, person, -1, event)
        tag = str(uuid4())
        state = give_tag(state, other, actor, account, event, tag, audience)
        return state, dict(step="closed", tag=tag, disposition="counterpart_bonds_weakened")
    if case.step == "warboy_bond" and choice == "apply" and not account:
        state = change(state, actor, other, 1, event)
        state.facts.append(
            dict(
                kind=WARBOY_REFUSAL,
                actor=actor.token,
                issuer=other.token,
                event=event,
                encounter=case.id,
            )
        )
        return state, dict(step="warboy_identity")
    if case.step == "warboy_identity":
        if choice == "pass" and not account:
            return state, dict(step="closed", disposition="bonded")
        if choice == "offer" and 0 < len(account) <= 120:
            return state, dict(step="warboy_replace", identity=account)
    if case.step == "warboy_replace" and not account and case.identity:
        original = ancillary.find(state, actor)
        if original is None:
            raise WorkflowError("Recover the original Warboy and Identity slots.")
        identities = original.identities
        replace = _replaceable(state, actor)
        if len(identities) >= 4:
            if choice not in replace:
                raise WorkflowError("Choose a current original replaceable Identity.")
            from girlframe.engine.m3_leviathan_obsession import require_identity_change

            require_identity_change(state, actor, (choice,))
            slot = next(x.slot for x in identities if x.id == choice)
            identities = tuple(x for x in identities if x.id != choice)
        else:
            if choice != "accept":
                raise WorkflowError("Confirm the actual new Identity in an unoccupied slot.")
            slot = next(i for i in range(4) if all(x.slot != i for x in identities))
        item = IdentityState(id=str(uuid4()), name=case.identity, slot=slot)
        ancillary.put(state, original.model_copy(update=dict(identities=(*identities, item))))
        return state, dict(step="closed", disposition="bonded")
    raise WorkflowError("Choose the original player's printed Warboy result.")


def _angel_identities(state: GameState, actor: ActorRef) -> dict[str, str]:
    role = ancillary.find(state, actor)
    return (
        {
            x.id: x.name
            for x in role.identities
            if x.name != "Wife" and not x.protected and not x.paired
        }
        if role is not None
        else {}
    )


def _angel_assets(partner: ActorView) -> dict[str, str]:
    if partner.inside_frame is not False:
        return {}
    assets = {x.id: x.name for x in partner.assets if not x.damaged and x.family == "girl"}
    return (
        {x.id: x.name for x in partner.assets if x.id in assets and not x.concealed}
        if len(assets) >= 2
        else {}
    )


def _angel(
    state: GameState,
    case: Encounter,
    partner: ActorView,
    bindings: tuple[ProfileBinding, ...],
    choice: str,
    account: str,
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, other = case.actor.actor, case.partner.actor
    audience = (case.actor.controller, case.partner.controller)
    if case.step == "angel_tag" and (
        choice == "pass" and not account or choice == "tag" and 0 < len(account) <= 120
    ):
        tag = None
        if choice == "tag":
            tag = str(uuid4())
            state = give_tag(state, other, actor, account, event, tag, audience)
        return state, dict(
            step="angel_space",
            tag=tag,
            partner_pose=partner.position_sha256,
            partner_cell=partner.cell,
        )
    if case.step == "angel_replace" and case.roll is not None:
        if choice != "pass" or account:
            if choice not in _angel_identities(state, actor) or not 0 < len(account) <= 120:
                raise WorkflowError("Choose an original allowed Identity and its replacement.")
            from girlframe.engine.m3_leviathan_obsession import require_identity_change

            require_identity_change(state, actor, (choice,))
            role = ancillary.find(state, actor)
            assert role is not None
            identities = tuple(
                IdentityState(id=str(uuid4()), name=account, slot=x.slot) if x.id == choice else x
                for x in role.identities
            )
            ancillary.put(state, role.model_copy(update=dict(identities=identities)))
        return state, dict(
            step="angel_helpless" if case.roll.result == "low" else "angel_damage",
        )
    if case.step == "angel_helpless" and choice in ("yes", "no") and not account:
        if choice == "yes":
            state = make_helpless(state, actor, other, event)
        return state, dict(step="closed", disposition="helpless" if choice == "yes" else "spared")
    if case.step == "angel_damage" and choice in _angel_assets(partner) and not account:
        state, followups = damage(state, other, choice, bindings, event, opponent=actor)
        if followups:
            raise WorkflowError("Resolve the unsupported Asset consequence with the human GM.")
        return state, dict(step="closed", disposition="asset_damaged")
    raise WorkflowError("Choose the original player's printed Angel-Wife result.")


def _revolutionary_identities(state: GameState, actor: ActorRef) -> dict[str, str]:
    role = ancillary.find(state, actor)
    return (
        {
            x.id: x.name
            for x in role.identities
            if not x.protected and not x.paired and not x.obsession_sources and not x.am_limiter
        }
        if role is not None
        else {}
    )


def require_revolutionary_departure(state: GameState, actor: ActorRef) -> None:
    for case in records(state):
        if case.actor.actor != actor or case.step != "revolutionary_release":
            continue
        if any(
            cast.open
            and cast.id == case.scene
            and case.actor in cast.roles
            and case.partner in cast.roles
            for cast in state.scene_casts
        ):
            raise WorkflowError("The original private choice to permit departure is still pending.")


def _revolutionary(
    state: GameState,
    case: Encounter,
    actual: ActorView,
    choice: str,
    account: str,
    picks: tuple[str, ...],
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, other = case.actor.actor, case.partner.actor
    if case.step == "revolutionary_clear" and choice in ("finish", "leave") and not account:
        role = ancillary.find(state, actor)
        assert role is not None
        identities = tuple(
            x.model_copy(update=dict(marked=False))
            if not x.obsession_sources and not x.am_limiter
            else x
            for x in role.identities
        )
        ancillary.put(state, role.model_copy(update=dict(identities=identities)))
        if choice == "leave":
            return state, dict(
                step="revolutionary_escape",
                partner_pose=actual.position_sha256,
                partner_cell=actual.cell,
            )
        return state, dict(step="closed", disposition="unmarked")
    if case.step == "revolutionary_offer" and choice == "offer" and not account:
        if len(picks) != 2 or not set(picks) <= set(REVOLUTIONARY_OPTIONS):
            raise WorkflowError("Choose exactly two distinct printed consequences.")
        if "erase" in picks and not _revolutionary_identities(state, actor):
            raise WorkflowError("The original actor has no eligible Identity to remove.")
        state = change(state, actor, other, 1, event)
        return state, dict(step="revolutionary_choice", picks=picks)
    if case.step == "revolutionary_choice" and choice in case.picks and not account:
        return state, dict(
            step={
                "erase": "revolutionary_erase",
                "tag": "revolutionary_tag",
                "remain": "revolutionary_release",
            }[choice]
        )
    if case.step in ("revolutionary_erase", "revolutionary_erase_two") and not account:
        count = 2 if case.step == "revolutionary_erase_two" else 1
        choices = ("erase", "bond") if count == 2 else ("erase",)
        if (
            choice not in choices
            or len(picks) != count
            or not set(picks) <= _revolutionary_identities(state, actor).keys()
        ):
            raise WorkflowError("Choose the exact number of eligible original Identities.")
        from girlframe.engine.m3_leviathan_obsession import require_identity_change

        require_identity_change(state, actor, picks)
        role = ancillary.find(state, actor)
        assert role is not None
        ancillary.put(
            state,
            role.model_copy(
                update=dict(
                    identities=tuple(x for x in role.identities if x.id not in picks),
                )
            ),
        )
        if choice == "bond":
            state = change(state, actor, other, 1, event)
        return state, dict(step="closed", disposition="identities_erased")
    if case.step == "revolutionary_tag" and choice == "tag" and 0 < len(account) <= 120:
        tag = str(uuid4())
        state = give_tag(
            state,
            actor,
            other,
            account,
            event,
            tag,
            (case.actor.controller, case.partner.controller),
        )
        return state, dict(step="closed", tag=tag, disposition="tag_given")
    if case.step == "revolutionary_release" and choice == "release" and not account:
        return state, dict(step="closed", disposition="released")
    raise WorkflowError("Choose the original player's printed Revolutionary result.")


def _prodigy_people(
    state: GameState,
    actor: ActorRef,
) -> dict[str, tuple[ActorRef, int, str]]:
    if state.world is None:
        return {}
    people = {}
    for npc in state.world.npcs:
        ref = ActorRef(kind="npc", entity=npc.id)
        if (
            npc.alive
            and "director" not in npc.jobs
            and knowledge_allowed(state, ref)
            and (depth(state, actor, ref) > 0)
        ):
            people[ref.token] = (ref, npc.controller, npc.name)
    return people


def _prodigy(
    state: GameState,
    case: Encounter,
    choice: str,
    account: str,
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, partner = case.actor.actor, case.partner.actor
    if case.step == "prodigy_choose" and 0 < len(account) <= 120:
        subject = _prodigy_people(state, actor).get(choice)
        if subject is None:
            raise WorkflowError("Choose the original actual NPC who has a current Bond with you.")
        tag = str(uuid4())
        state = give_tag(
            state,
            partner,
            actor,
            account,
            event,
            tag,
            (case.actor.controller, case.partner.controller),
        )
        return state, dict(
            step="prodigy_jealous",
            tag=tag,
            reaction_actor=subject[0],
            reaction_owner=subject[1],
        )
    if case.step == "prodigy_jealous" and choice == "confirm" and account:
        assert case.reaction_actor is not None
        state.facts.append(
            dict(
                kind="prodigy_jealous_bond",
                event=event,
                encounter=case.id,
                npc=case.reaction_actor.token,
                prodigy=actor.token,
                counterpart=partner.token,
                account=account,
            )
        )
        return state, dict(step="closed", disposition="actual_npc_reaction")
    if case.step == "prodigy_rank" and choice == "raise" and not account:
        cadre_rank.shift(state, actor, -1, event)
        return state, dict(step="closed", disposition="status_applied")
    if case.step == "prodigy_low":
        if choice == "pass" and not account:
            return state, dict(step="closed", disposition="declined_status_and_tag")
        if choice == "apply" and 0 < len(account) <= 120:
            cadre_rank.shift(state, actor, 1, event)
            tag = str(uuid4())
            state = give_tag(
                state,
                actor,
                partner,
                account,
                event,
                tag,
                (case.actor.controller, case.partner.controller),
            )
            return state, dict(step="closed", disposition="status_applied", tag=tag)
    raise WorkflowError("The original Status or outstanding reaction requires human review.")


def _mercenary(
    state: GameState,
    case: Encounter,
    choice: str,
    account: str,
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    if case.step == "mercenary_request":
        if choice == "pass" and not account:
            return state, dict(step="closed", disposition="no_favour")
        if choice == "ask" and account:
            return state, dict(step="mercenary_reply", account=account)
    if case.step == "mercenary_reply":
        if choice == "decline" and not account:
            return state, dict(step="mercenary_give_tag")
        if choice == "did_it" and account:
            return state, dict(step="mercenary_verify", answer=account)
    if case.step == "mercenary_verify":
        if choice == "confirmed" and account:
            state.facts.append(
                dict(
                    kind="mercenary_favour_verified",
                    encounter=case.id,
                    event=event,
                    account=account,
                )
            )
            return state, dict(step="closed", disposition="favour_verified")
        if choice == "not_fulfilled" and account:
            state.facts.append(
                dict(
                    kind="mercenary_favour_unfulfilled",
                    encounter=case.id,
                    event=event,
                    account=account,
                )
            )
            return state, dict(step="mercenary_give_tag")
    if case.step == "mercenary_give_tag" and choice == "tag" and 0 < len(account) <= 120:
        tag = str(uuid4())
        state = give_tag(
            state,
            case.partner.actor,
            case.actor.actor,
            account,
            event,
            tag,
            (case.actor.controller, case.partner.controller),
        )
        return state, dict(step="closed", tag=tag, disposition="favour_refused")
    raise WorkflowError("The original private outcome requires its actual supported consequence.")


def _abyssal_identities(state: GameState, actor: ActorRef) -> dict[str, str]:
    return {
        item.id: item.name
        for item in state.sheets[actor.entity].identities
        if not item.protected
        and not item.paired
        and not item.obsession_sources
        and not item.am_limiter
    }


def _abyssal_assets(partner: ActorView) -> dict[str, str]:
    return (
        {
            x.id: x.name
            for x in partner.assets
            if x.family == "girl" and not x.damaged and not x.concealed
        }
        if partner.inside_frame is False
        else {}
    )


def _abyssal(
    state: GameState,
    case: Encounter,
    actual: ActorView,
    partner: ActorView,
    bindings: tuple[ProfileBinding, ...],
    choice: str,
    account: str,
    picks: tuple[str, ...],
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, other = case.actor.actor, case.partner.actor
    if case.step == "abyssal_ask" and choice == "ask" and account:
        return state, dict(step="abyssal_reply", account=account)
    if case.step == "abyssal_reply":
        if choice == "refuse" and not account:
            return state, dict(step="abyssal_damage")
        if choice == "did_it" and account:
            return state, dict(step="abyssal_verify", answer=account)
    if case.step == "abyssal_verify" and choice in ("yes", "no") and account:
        state.facts.append(
            dict(
                kind="abyssal_private_request_review",
                event=event,
                encounter=case.id,
                account=account,
                choice=choice,
            )
        )
        return state, (
            dict(step="closed", disposition="abyssal_request_fulfilled")
            if choice == "yes"
            else dict(step="abyssal_damage")
        )
    if case.step == "abyssal_damage" and choice == "damage" and not account:
        if not set(picks) <= _abyssal_assets(partner).keys():
            raise WorkflowError("Choose real reachable undamaged Girl Assets.")
        for item in picks:
            state, followups = damage(state, other, item, bindings, event, opponent=actor)
            if followups:
                raise WorkflowError("Resolve the unsupported actual damage with the original GM.")
        return state, dict(step="closed", disposition="abyssal_damage_applied")
    if case.step == "abyssal_erase_tag" and 0 < len(account) <= 120:
        if choice not in _abyssal_identities(state, other):
            raise WorkflowError("Choose one real eligible original Identity.")
        from girlframe.engine.m3_leviathan_obsession import require_identity_change

        require_identity_change(state, other, (choice,))
        tag = str(uuid4())
        state = give_tag(
            state,
            other,
            actor,
            account,
            event,
            tag,
            (case.actor.controller, case.partner.controller),
        )
        sheet = state.sheets[other.entity]
        sheet.identities = [x for x in sheet.identities if x.id != choice]
        sheet.revision += 1
        return state, dict(
            step="abyssal_leave",
            tag=tag,
            partner_pose=actual.position_sha256,
            partner_cell=actual.cell,
        )
    raise WorkflowError("The original Abyssal result awaits its actual supported consequence.")


def _soldier_resources(state: GameState, actor: ActorRef, scene: str) -> dict[str, str]:
    owner = ancillary.find(state, actor)
    if owner is None:
        return {}
    return {
        x.id: x.name
        for x in owner.identities
        if not x.marked and not x.obsession_sources and not x.am_limiter
    } | {x.id: x.label for x in owner.tags if not x.marked and x.scene_used != scene}


def _soldier(
    state: GameState,
    case: Encounter,
    actual: ActorView,
    choice: str,
    account: str,
    picks: tuple[str, ...],
    event: str,
) -> tuple[GameState, dict[str, Any]]:
    actor, other = case.actor.actor, case.partner.actor
    if case.step == "soldier_mid" and choice in ("pass", "deepen", "weaken") and not account:
        cadre_rank.shift(state, actor, -1, event)
        if choice in ("deepen", "weaken"):
            state = change(state, actor, other, 1 if choice == "deepen" else -1, event)
        return state, dict(step="closed", disposition="soldier_advanced")
    if case.step == "soldier_high" and choice == "apply" and not account:
        cadre_rank.shift(state, actor, 1, event)
        return state, dict(step="soldier_repair")
    if case.step == "soldier_repair":
        if choice == "pass" and not picks and not account:
            return state, dict(step="closed", disposition="soldier_lowered")
        resources = _soldier_resources(state, actor, case.scene)
        if (
            len(picks) == 1
            and picks[0] in resources
            and account
            and any(x.id == choice and x.damaged and not x.concealed for x in actual.assets)
        ):
            return state, dict(
                step="soldier_alone",
                account=account,
                repair_asset=choice,
                repair_resource=picks[0],
            )
    if case.step == "soldier_alone":
        if choice == "no" and not account:
            return state, dict(step="soldier_repair", repair_asset=None, repair_resource=None)
        if choice == "yes" and not account:
            original = ancillary.find(state, actor)
            assets = _soldier_resources(state, actor, case.scene)
            if (
                original is None
                or case.repair_resource is None
                or case.repair_resource not in assets
                or state.world is None
                or not any(x.id == case.repair_asset and x.damaged for x in actual.assets)
            ):
                raise WorkflowError(
                    "Recover the actual original unmarked resource and damaged Asset."
                )
            body = next(x for x in state.world.pilots if x.id == actor.entity)
            if any(x.id == case.repair_resource for x in original.tags):
                actor_plays.mark(state, actor, case.repair_resource, case.scene)
            else:
                ancillary.put(
                    state,
                    original.model_copy(
                        update=dict(
                            identities=tuple(
                                x.model_copy(update=dict(marked=True))
                                if x.id == case.repair_resource
                                else x
                                for x in original.identities
                            ),
                        )
                    ),
                )
            changed = body.model_copy(
                update=dict(
                    assets=tuple(
                        x.model_copy(update=dict(damaged=False)) if x.id == case.repair_asset else x
                        for x in body.assets
                    ),
                )
            )
            state.world = update_world(
                state.world,
                pilots=tuple(changed if x.id == actor.entity else x for x in state.world.pilots),
            )
            return state, dict(step="closed", disposition="soldier_repaired")
    raise WorkflowError("The original Soldier result needs its actual Status or repair source.")
