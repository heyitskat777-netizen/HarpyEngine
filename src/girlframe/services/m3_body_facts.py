"""Explicit factual bodies and repairs of proved original starting entitlements."""

import json
from typing import Any, Literal

import sqlalchemy as sa
from pydantic import Field
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as rules
from girlframe.engine.creation_details import PsychStringAnchor
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import owned_refs, resolve
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_changeling import ChangelingService, require_rule, stage_start
from girlframe.services.m3_changeling_body import brain
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

BodyKind = Literal["girl", "gorgon", "harpy", "handler", "human_npc", "other"]


class NpcOriginalBody(Model):
    id: str
    owner: ActorRef
    frame: str
    start_event: str
    slot: int = Field(ge=0, le=3)
    anchor_reference: str
    subject: ActorRef
    introduced_event: str
    link_event: str
    body_fact: str
    body_event: str
    brain: str
    vessel: str
    author: ActorRef
    controller: int
    cast: SceneCast
    audience: tuple[int, ...]
    account: str = Field(min_length=1, max_length=1200)
    event: str


def npc_originals(state: GameState) -> tuple[NpcOriginalBody, ...]:
    return tuple(
        NpcOriginalBody.model_validate_json(value["body"])
        for value in state.facts
        if value.get("kind") == "npc_original_body"
    )


def _sources(game: GameService, c: Connection, kinds: tuple[str, ...]) -> list[Any]:
    return list(
        c.execute(
            sa.select(t.events)
            .where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.kind.in_(kinds))
            .order_by(t.events.c.seq)
        ).mappings()
    )


def _birth(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[str, GameState]:
    frame = rules.frame(state, actor)
    for row in _sources(
        game,
        c,
        ("m2.character_activated", "m3.frame_swap_purchased", "m3.compulsory_frame_replaced"),
    ):
        saved = _history(c, game, row["id"])
        sheet = saved.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation or sheet.frame != rules.FRAME:
            continue
        if rules.frame(saved, actor) != frame:
            continue
        payload = json.loads(row["payload_json"])
        if row["kind"] == "m2.character_activated":
            if sheet.frame_runtime is not None or row["actor_id"] != actor.entity:
                continue
        elif sheet.frame_runtime is None or sheet.frame_runtime.source_work != payload.get(
            "plan_id" if row["kind"] == "m3.frame_swap_purchased" else "work_id"
        ):
            continue
        if row["kind"] == "m3.frame_swap_purchased" and not any(
            isinstance(value, SwapReceipt)
            and value.actor == actor
            and value.new_frame == frame
            and value.source_event == row["id"]
            and sheet.frame_runtime is not None
            and value.plan == sheet.frame_runtime.source_work
            for value in saved.requisitions
        ):
            continue
        return row["id"], saved
    raise WorkflowError("SOURCE_STARTING_FRAME_REQUIRED: recover the actual original Frame birth")


def _pilot_anchor(game: GameService, c: Connection, actor: ActorRef, anchor: Any) -> ActorRef:
    identity, revision = anchor.source_token.rsplit(":", 1)
    bond = (
        c.execute(
            sa.select(t.bond_revisions).where(
                t.bond_revisions.c.campaign_id == game.store.campaign_id,
                t.bond_revisions.c.id == identity,
                t.bond_revisions.c.revision == int(revision),
            )
        )
        .mappings()
        .first()
    )
    if bond is None or bond["state"] != "accepted":
        raise WorkflowError("Recover the exact accepted reviewed starting Bond")
    other = anchor.reference
    if {bond["source_id"], bond["target_id"]} != {actor.entity, other}:
        raise WorkflowError("Preserve both actual reviewed starting people")
    endpoint = "source_revision" if bond["source_id"] == other else "target_revision"
    own_endpoint = "source_revision" if bond["source_id"] == actor.entity else "target_revision"
    original: dict[str, ActorRef] = {}
    for row in _sources(game, c, ("m2.character_activated",)):
        saved = _history(c, game, row["id"])
        for uid, expected in ((actor.entity, bond[own_endpoint]), (other, bond[endpoint])):
            sheet = saved.sheets.get(uid)
            if (
                row["actor_id"] == uid
                and sheet is not None
                and sheet.source_profile_revision == expected
                and sheet.character_id
            ):
                original[uid] = ActorRef(kind="pilot", entity=uid, incarnation=sheet.character_id)
    if original.get(actor.entity) != actor or other not in original:
        raise WorkflowError("SOURCE_STARTING_PERSON_REQUIRED: recover the original reviewed people")
    return original[other]


def _npc_anchor(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, anchor: PsychStringAnchor
) -> ActorRef:
    slot = int(anchor.reference.rsplit(":", 1)[1])
    links = (
        [
            link
            for link in state.world.starting_npc_links
            if link.owner == int(actor.entity)
            and link.character_id == actor.incarnation
            and link.slot == slot
        ]
        if state.world
        else []
    )
    if len(links) != 1:
        raise WorkflowError("SOURCE_STARTING_NPC_LINK_REQUIRED: link the original saved role")
    link = links[0]
    if not any(
        link in historical.world.starting_npc_links
        for row in _sources(game, c, ("m3.starting_npc_linked",))
        if (historical := _history(c, game, row["id"])).world is not None
        and row["actor_id"] == actor.entity
        and json.loads(row["payload_json"]).get("entity_id") == link.npc
    ):
        raise WorkflowError("Recover the canonical original NPC starting-role link")
    return ActorRef(kind="npc", entity=link.npc)


def _subjects(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    saved: GameState,
    gaps: list[dict[str, Any]],
) -> tuple[ActorRef, ...]:
    sheet = saved.sheets[actor.entity]
    if sheet.frame_runtime is not None:
        runtime = sheet.frame_runtime
        if runtime.psych_string_refs:
            result = list(runtime.psych_string_refs)
        else:
            result = []
            for uid in runtime.psych_strings:
                native_sheet = saved.sheets.get(str(uid))
                if native_sheet is None or not native_sheet.character_id:
                    gaps.append(
                        dict(
                            actor=None,
                            reference=str(uid),
                            label="Original starting Pilot " + str(uid),
                            source_kind="pilot",
                            imported=False,
                            staged=False,
                            gap="SOURCE_STARTING_PERSON_REQUIRED: recover Frame birth people",
                        )
                    )
                    continue
                result.append(
                    ActorRef(kind="pilot", entity=str(uid), incarnation=native_sheet.character_id)
                )
    else:
        result = []
        anchors = sheet.review.psych_strings
        if not anchors:
            # Older saved reviews retain these immutable agreements without the newer index.
            anchors = tuple(
                PsychStringAnchor(
                    kind="pilot",
                    reference=str(value.counterpart),
                    source_token=value.id + ":" + str(value.revision),
                )
                for value in sheet.review.bonds
            ) + tuple(
                PsychStringAnchor(
                    kind="npc_role",
                    reference=f"npc:{actor.entity}:{value.slot}",
                    source_token="immutable-reviewed-role",
                )
                for value in sheet.review.creation.npc_bonds
            )
        for anchor in anchors:
            try:
                subject = (
                    _pilot_anchor(game, c, actor, anchor)
                    if anchor.kind == "pilot"
                    else _npc_anchor(game, c, state, actor, anchor)
                )
            except (ValueError, WorkflowError) as error:
                gaps.append(
                    dict(
                        actor=None,
                        reference=anchor.reference,
                        label="Starting " + anchor.kind + " " + anchor.reference,
                        source_kind=anchor.kind,
                        imported=False,
                        staged=False,
                        gap=str(error),
                    )
                )
                continue
            result.append(subject)
    if len(set(result)) != len(result) or actor in result:
        raise WorkflowError("Starting Strings require distinct original other people")
    return tuple(result)


def _npc_context(
    game: GameService, c: Connection, state: GameState, owner: ActorRef, slot: int
) -> dict[str, Any]:
    resolve(state, owner, profiles(c, game.store.campaign_id), require_current_profile=False)
    start, saved = _birth(game, c, state, owner)
    sheet = saved.sheets[owner.entity]
    selected = next(
        (value for value in sheet.review.creation.npc_bonds if value.slot == slot), None
    )
    if sheet.frame_runtime is not None or selected is None:
        raise WorkflowError(
            "SOURCE_STARTING_NPC_ROLE_REQUIRED: use the actual initial reviewed role"
        )
    reference = f"npc:{owner.entity}:{slot}"
    anchor = next(
        (
            value
            for value in sheet.review.psych_strings
            if value.kind == "npc_role" and value.reference == reference
        ),
        None,
    )
    if anchor is None:
        if sheet.review.psych_strings:
            raise WorkflowError("Preserve the exact saved starting NPC anchor")
        anchor = PsychStringAnchor(
            kind="npc_role", reference=reference, source_token="immutable-reviewed-role"
        )
    subject = _npc_anchor(game, c, state, owner, anchor)
    npc = (
        next((value for value in state.world.npcs if value.id == subject.entity), None)
        if state.world
        else None
    )
    from girlframe.engine.m3_am_reset import body as reset_body
    from girlframe.engine.m3_casualty import part_state

    if (
        npc is None
        or not npc.alive
        or npc.source_kind is not None
        or reset_body(state, subject) is not None
        or part_state(state, subject, "brain") in ("destroyed", "removed")
    ):
        raise WorkflowError("SOURCE_ORIGINAL_NPC_BODY_REQUIRED: no Wraith, reset or replaced brain")
    current = brain(game, c, state, subject, purpose="original starting NPC body")
    fact = next(
        (
            value
            for value in rules.records(state, rules.BodyFact)
            if value.actor == subject
            and value.brain == current.id
            and value.vessel == current.vessel
            and value.event == current.source
        ),
        None,
    )
    if (
        fact is None
        or fact.kind not in ("human_npc", "other")
        or fact.reset_record
        or fact.reset_source
    ):
        raise WorkflowError("Use the actual ordinary NPC's canonical current body fact")
    if any(
        value.actor == subject and (value.brain != current.id or value.vessel != current.vessel)
        for value in rules.records(state, rules.BodyFact)
    ):
        raise WorkflowError(
            "SOURCE_ORIGINAL_BRAIN_CONTRADICTION: preserve known original body evidence"
        )
    introduced = None
    for row in _sources(game, c, ("m3.npc_introduced",)):
        if json.loads(row["payload_json"]).get("entity_id") != subject.entity:
            continue
        born = _history(c, game, row["id"])
        original = (
            next((value for value in born.world.npcs if value.id == subject.entity), None)
            if born.world
            else None
        )
        if (
            original is not None
            and original.alive
            and original.source_kind is None
            and original.controller == int(row["actor_id"])
        ):
            introduced = row["id"]
            break
    if introduced is None:
        raise WorkflowError(
            "SOURCE_NPC_INTRODUCTION_REQUIRED: recover the genuine ordinary introduction"
        )
    linked = None
    for row in _sources(game, c, ("m3.starting_npc_linked",)):
        if (
            row["actor_id"] != owner.entity
            or json.loads(row["payload_json"]).get("entity_id") != subject.entity
        ):
            continue
        born = _history(c, game, row["id"])
        if born.world and any(
            value.owner == int(owner.entity)
            and value.character_id == owner.incarnation
            and value.slot == slot
            and value.npc == subject.entity
            for value in born.world.starting_npc_links
        ):
            linked = row["id"]
            break
    if linked is None:
        raise WorkflowError("Recover the exact canonical owner-authored starting-role link")
    return dict(
        owner=owner,
        frame=rules.frame(state, owner),
        start_event=start,
        slot=slot,
        anchor_reference=reference,
        subject=subject,
        introduced_event=introduced,
        link_event=linked,
        body_fact=fact.id,
        body_event=fact.event,
        brain=current.id,
        vessel=current.vessel,
        fact=fact,
        label=npc.name,
        npc_controller=npc.controller,
    )


def prove_npc_original(
    game: GameService,
    c: Connection,
    state: GameState,
    value: NpcOriginalBody,
    *,
    historical: bool = False,
) -> NpcOriginalBody:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    born = _history(c, game, value.event)
    if (
        row is None
        or row["kind"] != "m3.npc_original_body_established"
        or row["actor_id"] != str(value.controller)
        or json.loads(row["payload_json"]).get("id") != value.id
        or value not in npc_originals(born)
        or born.handler != value.controller
        or active_handler(born) != value.author
        or not value.account.strip()
    ):
        raise WorkflowError("Recover the original Handler-authored NPC body continuity source")
    if not historical:
        context = _npc_context(game, c, state, value.owner, value.slot)
        for key in (
            "owner",
            "frame",
            "start_event",
            "slot",
            "anchor_reference",
            "subject",
            "introduced_event",
            "link_event",
            "body_fact",
            "body_event",
            "brain",
            "vessel",
        ):
            if getattr(value, key) != context[key]:
                raise WorkflowError(
                    "Preserve the exact original role, Frame, link and brain/body evidence"
                )
    factual = rules.record(born, rules.BodyFact, value.body_fact)
    if (
        factual.actor != value.subject
        or factual.event != value.body_event
        or factual.brain != value.brain
        or factual.vessel != value.vessel
        or value.controller
        not in {factual.controller}
        | {member.controller for member in factual.cast.roles if member.actor == value.subject}
    ):
        raise WorkflowError("Preserve the proved body evidence and authorized factual witness")
    role = next((role for role in value.cast.roles if role.actor == value.subject), None)
    born_npc = (
        next((item for item in born.world.npcs if item.id == value.subject.entity), None)
        if born.world
        else None
    )
    if (
        role is None
        or value.cast not in born.scene_casts
        or born_npc is None
        or role.controller != born_npc.controller
        or value.audience
        != tuple(sorted({int(value.owner.entity), value.controller, role.controller}))
        or value.id
        != rules.identity(
            "npc-original-body",
            value.owner.token,
            value.frame,
            str(value.slot),
            value.subject.token,
            value.brain,
            value.vessel,
        )
    ):
        raise WorkflowError(
            "Preserve the actual witnessed role and original private factual audience"
        )
    return value


def _original_brain(
    game: GameService, c: Connection, state: GameState, saved: GameState, subject: ActorRef
) -> rules.BrainRef:
    current = brain(game, c, state, subject, purpose="starting repair")
    original = [value for value in rules.records(saved, rules.BodyFact) if value.actor == subject]
    if original:
        if not any(
            value.brain == current.id and value.vessel == current.vessel for value in original
        ):
            raise WorkflowError(
                "SOURCE_ORIGINAL_BRAIN_REQUIRED: do not inherit through replacement"
            )
        return current
    # Accepted first initial placement is positive evidence of this original native body.
    # Current Bond, shared controller and absence of a replacement record prove nothing.
    if subject.kind == "pilot":
        work = t.m3["m3_required_work"]
        rows = c.execute(
            sa.select(work).where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.kind == "physical_initial",
                work.c.state == "resolved",
                work.c.subject_id == subject.entity,
            )
        ).mappings()
        for row in rows:
            from girlframe.services.m3_physical import PhysicalService

            value = PhysicalService(game.store)._review(c, dict(row))
            if (
                value.origin is not None
                or value.decision != "accepted"
                or value.proposal.actor != subject
                or value.vessel_id != current.vessel
                or value.review_event != row["event_id"]
            ):
                continue
            source = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == value.review_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                source is None
                or source["kind"] != "m3.initial_placement_reviewed"
                or source["actor_id"] != str(value.handler)
                or json.loads(source["payload_json"]).get("work_id") != row["id"]
            ):
                continue
            born = _history(c, game, value.review_event or "")
            if any(
                pose.actor == subject
                and pose.vessel_id == current.vessel
                and pose.proposed_event == value.proposed_event
                for pose in born.placements
            ) and current.id == rules.identity("brain", subject.token, current.vessel):
                return current
    if subject.kind == "npc":
        for continuity in npc_originals(state):
            if continuity.subject == subject and _history(c, game, continuity.start_event) == saved:
                prove_npc_original(game, c, state, continuity)
                if continuity.brain == current.id and continuity.vessel == current.vessel:
                    return current
    raise WorkflowError(
        "SOURCE_ORIGINAL_BRAIN_REQUIRED: "
        "the starting person's original body continuity is unresolved"
    )


class BodyFactsService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.source = ChangelingService(game)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)

    def _audience(self, value: rules.BodyFact) -> set[int]:
        return {value.controller} | {
            role.controller for role in value.cast.roles if role.actor == value.actor
        }

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=value.id,
                revision=state.revision,
                label="Actual body: " + value.kind,
                pending=False,
                phase="resolved",
            )
            for value in rules.records(state, rules.BodyFact)
            if viewer.user_id in self._audience(value)
        ]
        result.extend(
            dict(
                id=value.id,
                revision=state.revision,
                label="Original starting NPC body",
                pending=False,
                phase="resolved",
            )
            for value in npc_originals(state)
            if viewer.user_id in value.audience
        )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            original = next((value for value in npc_originals(state) if value.id == identity), None)
            if original is not None:
                if viewer.user_id not in original.audience:
                    raise WorkflowError(
                        "Only the original factual source participants may read this account"
                    )
                prove_npc_original(self.game, c, state, original, historical=True)
                return dict(
                    id=identity,
                    revision=state.revision,
                    kind="npc_original_body",
                    fact=original.model_dump(mode="json"),
                )
            value = rules.record(state, rules.BodyFact, identity)
            if viewer.user_id not in self._audience(value):
                raise WorkflowError(
                    "Only this actual body owner or original factual author may read it"
                )
            row = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == value.event,
                    )
                )
                .mappings()
                .first()
            )
            born = rules.record(_history(c, self.game, value.event), rules.BodyFact, identity)
            if (
                row is None
                or row["kind"] != "m3.changeling_body_proved"
                or row["actor_id"] != str(value.controller)
                or born != value
            ):
                raise WorkflowError("Recover the original immutable body account")
            return dict(id=value.id, revision=state.revision, fact=value.model_dump(mode="json"))

    def _import(self, c: Connection, state: GameState, actor: ActorRef) -> dict[str, Any]:
        source, saved = _birth(self.game, c, state, actor)
        rows: list[dict[str, Any]] = []
        subjects = _subjects(self.game, c, state, actor, saved, rows)
        frame = rules.frame(state, actor)
        for subject in subjects:
            old = [
                value
                for value in rules.records(state, rules.StartingBond)
                if value.actor == actor and value.frame == frame and value.subject == subject
            ]
            gap = None
            if not any(value.node for value in old):
                try:
                    _original_brain(self.game, c, state, saved, subject)
                except (ValueError, WorkflowError) as error:
                    gap = str(error)
            label = "Original " + subject.kind + " " + subject.entity
            try:
                label = resolve(
                    state,
                    subject,
                    profiles(c, self.store.campaign_id),
                    require_alive=False,
                    require_current_profile=False,
                ).label
            except ValueError:
                pass
            rows.append(
                dict(
                    actor=subject.model_dump(mode="json"),
                    label=label,
                    reference=subject.token,
                    source_kind=subject.kind,
                    imported=any(value.node is not None for value in old),
                    staged=bool(old),
                    gap=gap,
                )
            )
        return dict(
            actor=actor.model_dump(mode="json"),
            source_event=source,
            frame=frame,
            subjects=rows,
            pending=any(not row["imported"] for row in rows),
            ready=any(not row["imported"] and not row["gap"] for row in rows),
            eligible=sum(not row["imported"] and not row["gap"] for row in rows),
            unresolved=[row for row in rows if row["gap"]],
        )

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            refs = list(owned_refs(state, viewer.user_id, bound))
            handler = active_handler(state)
            scene = None
            try:
                scene = _cast(self.game, c, state, channel or 0)
            except (ValueError, WorkflowError):
                pass
            if viewer.user_id == state.handler:
                if handler and handler not in refs:
                    refs.append(handler)
                if scene:
                    refs.extend(role.actor for role in scene.roles if role.actor not in refs)
                if state.world:
                    refs.extend(
                        ActorRef(kind="npc", entity=value.id)
                        for value in state.world.npcs
                        if value.alive and ActorRef(kind="npc", entity=value.id) not in refs
                    )
            actors, imports = [], []
            for ref in refs:
                try:
                    actual = resolve(state, ref, bound, require_current_profile=False)
                except ValueError:
                    continue
                kinds: tuple[BodyKind, ...] = ()
                if ref.kind == "pilot":
                    kinds = ("girl",)
                elif ref.kind == "handler":
                    kinds = ("handler",)
                elif ref.kind == "gorgon":
                    kinds = ("gorgon",)
                elif ref.kind == "external_pilot":
                    kinds = (
                        ("harpy",) if actual.girl == "harpy" else ("girl",) if actual.girl else ()
                    )
                elif (
                    ref.kind == "npc"
                    and viewer.user_id == state.handler
                    and state.world is not None
                ):
                    from girlframe.engine.m3_am_reset import body as reset_body

                    npc = next(value for value in state.world.npcs if value.id == ref.entity)
                    if npc.source_kind != "wyvern_wraith":
                        kinds = ("other",) if reset_body(state, ref) else ("human_npc", "other")
                proved = any(
                    value.actor == ref and value.vessel == actual.vessel_id
                    for value in rules.records(state, rules.BodyFact)
                )
                if kinds:
                    actors.append(
                        dict(
                            id=ref.token,
                            actor=ref.model_dump(mode="json"),
                            label=actual.label,
                            kinds=kinds,
                            proved=proved,
                            joined=bool(scene and any(role.actor == ref for role in scene.roles)),
                        )
                    )
                if (
                    ref.kind == "pilot"
                    and actual.controller == viewer.user_id
                    and actual.frame == rules.FRAME
                ):
                    try:
                        imports.append(self._import(c, state, ref))
                    except (ValueError, WorkflowError) as error:
                        imports.append(dict(actor=ref.model_dump(mode="json"), gap=str(error)))
            npc_options = []
            if viewer.user_id == state.handler and handler is not None:
                for sheet in state.sheets.values():
                    if sheet.frame != rules.FRAME or not sheet.character_id:
                        continue
                    owner = ActorRef(
                        kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id
                    )
                    for selected in sheet.review.creation.npc_bonds:
                        try:
                            context = _npc_context(self.game, c, state, owner, selected.slot)
                            if any(
                                value.owner == owner
                                and value.frame == context["frame"]
                                and value.slot == selected.slot
                                for value in npc_originals(state)
                            ):
                                continue
                            if viewer.user_id not in self._audience(context["fact"]):
                                raise WorkflowError(
                                    "Use a body account you actually authored or own"
                                )
                            if scene is None or not any(
                                role.actor == context["subject"] for role in scene.roles
                            ):
                                raise WorkflowError(
                                    "Join the actual NPC role in this witnessed scene first"
                                )
                            npc_options.append(
                                dict(
                                    owner=owner.model_dump(mode="json"),
                                    slot=selected.slot,
                                    label=context["label"],
                                    frame=context["frame"],
                                    start_event=context["start_event"],
                                    subject=context["subject"].model_dump(mode="json"),
                                    gap=None,
                                )
                            )
                        except (ValueError, WorkflowError) as error:
                            npc_options.append(
                                dict(
                                    owner=owner.model_dump(mode="json"),
                                    slot=selected.slot,
                                    gap=str(error),
                                )
                            )
            return dict(
                revision=state.revision,
                actors=actors,
                imports=imports,
                npc_originals=npc_options,
                tasks=self._tasks(c, viewer),
            )

    def record(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        actor: ActorRef,
        kind: BodyKind,
        account: str,
    ) -> dict[str, Any]:
        return self.source.body_fact(viewer, key, revision, channel, actor, kind, account)

    def establish_npc_original(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        owner: ActorRef,
        slot: int,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Provide the actual positive original NPC brain/body evidence")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_recovery import pending

            HandlerService(self.store).authorize(c, viewer)
            author = active_handler(state)
            if viewer.user_id != state.handler or author is None:
                raise WorkflowError(
                    "Only the actual current original Handler authors witnessed evidence"
                )
            if self.game.pending_actions(c) or pending(self.game, c, include_unrolled=True):
                raise WorkflowError(
                    "Finish held source work before recording original-body evidence"
                )
            require_rule(self.game, c, state, owner, rules.STRINGS)
            context = _npc_context(self.game, c, state, owner, slot)
            if viewer.user_id not in self._audience(context["fact"]):
                raise WorkflowError(
                    "Use the existing factual body account you actually authored or own"
                )
            scene = _cast(self.game, c, state, channel)
            role = next((role for role in scene.roles if role.actor == context["subject"]), None)
            if role is None or role.controller != context["npc_controller"]:
                raise WorkflowError(
                    "Witness the actual NPC role and its real controller in the source scene"
                )
            if any(
                value.owner == owner and value.frame == context["frame"] and value.slot == slot
                for value in npc_originals(state)
            ):
                raise WorkflowError("This immutable original NPC body source is already recorded")
            identity = rules.identity(
                "npc-original-body",
                owner.token,
                context["frame"],
                str(slot),
                context["subject"].token,
                context["brain"],
                context["vessel"],
            )
            value = NpcOriginalBody(
                **{
                    name: context[name]
                    for name in (
                        "owner",
                        "frame",
                        "start_event",
                        "slot",
                        "anchor_reference",
                        "subject",
                        "introduced_event",
                        "link_event",
                        "body_fact",
                        "body_event",
                        "brain",
                        "vessel",
                    )
                },
                id=identity,
                author=author,
                controller=viewer.user_id,
                cast=scene,
                audience=tuple(sorted({int(owner.entity), viewer.user_id, role.controller})),
                account=account,
                event=event,
            )
            state.facts.append(
                dict(kind="npc_original_body", id=identity, body=value.model_dump_json())
            )
            return dict(id=identity)

        return self.source._write(
            viewer,
            key,
            "m3.npc_original_body_established",
            revision,
            dict(channel=channel, owner=owner.model_dump(mode="json"), slot=slot, account=account),
            operation,
        )

    def import_starting(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        source_event: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_recovery import pending

            if self.game.pending_actions(c) or pending(self.game, c, include_unrolled=True):
                raise WorkflowError("Finish the actual held Play before repairing starting sources")
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actor.kind != "pilot" or actual.controller != viewer.user_id:
                raise WorkflowError(
                    "Only the actual original Changeling owner repairs her starting source"
                )
            require_rule(self.game, c, state, actor, rules.STRINGS)
            original, _ = _birth(self.game, c, state, actor)
            if original != source_event:
                raise WorkflowError(
                    "Reopen the exact original current Frame's immutable starting source"
                )
            projected = self._import(c, state, actor)
            eligible = tuple(
                ActorRef.model_validate(row["actor"])
                for row in projected["subjects"]
                if not row["imported"] and not row["gap"]
            )
            # Every selected subject was independently proved before this single mutation.
            stage_start(self.game, c, state, actor, event, eligible, source=original)
            return dict(
                id=rules.identity("starting-repair", actor.token, rules.frame(state, actor)),
                imported=len(eligible),
                unresolved=projected["unresolved"],
                source_event=original,
            )

        return self.source._write(
            viewer,
            key,
            "m3.changeling_starting_imported",
            revision,
            dict(actor=actor.model_dump(mode="json"), source_event=source_event),
            operation,
        )
