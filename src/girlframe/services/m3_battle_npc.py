"""Attacker-owned NPC Asset replacement; ordinary people gain no invented hit points."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle_npc as npc_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Required
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove_flirt_self_damage(
    game: GameService, c: Connection, state: GameState, identity: str
) -> npc_rules.FlirtSelfDamage:
    from girlframe.engine import m3_npc_flirt as flirt_rules
    from girlframe.services.m3_npc_flirt import prove_escape_damage

    value = npc_rules.self_damage(state, identity)
    born = _history(c, game, value.event)
    original = npc_rules.self_damage(born, identity)
    damage = prove_escape_damage(game, c, state, value.action, value.event)
    session = flirt_rules.get(state, flirt_rules.Session, value.action)
    if (
        value != original
        or value.id != npc_rules.escape_damage_id(damage.id)
        or value.cast != session.cast
        or session.target != value.npc
        or session.controller != value.controller
        or value.npc.kind != "npc"
        or damage.id != value.damage
        or damage.npc != value.npc
        or damage.controller != value.controller
        or damage.choice != value.choice
        or damage.work != (value.id,)
        or not any(
            role.actor == value.npc and role.controller == value.controller
            for role in value.cast.roles
        )
    ):
        raise WorkflowError("Preserve the actual NPC, human chooser and genuine escape self-cost")
    return value


def _self_can_move(game: GameService, c: Connection, state: GameState, target: ActorRef) -> bool:
    actual = resolve(
        state,
        target,
        profiles(c, game.store.campaign_id),
        require_alive=False,
        require_current_profile=False,
    )
    return (
        actual.alive
        and actual.cell is not None
        and actual.custody is None
        and actual.offstage_source is None
        and not is_helpless(state, target)
    )


class NpcDamageService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays")
        self.game.unpaused(c)

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "npc_damage":
            raise WorkflowError("Open the actual original NPC damage consequence.")
        return dict(row)

    def _proof(self, c: Connection, row: dict[str, Any]) -> tuple[ActorRef, ActorRef | None]:
        from girlframe.engine.m2 import GameState

        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == row["event_id"],
            )
        )
        # Later work revisions retain the original source separately.
        body = json.loads(row["body_json"])
        original = body.get("damage_source_event", row["event_id"])
        if original != row["event_id"]:
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == original,
                )
            )
        state = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "battle_damage_stage"
                    and x.get("id") == row["id"]
                    and "requirement" in x
                ),
                None,
            )
            if state
            else None
        )
        required = Required.model_validate_json(fact["requirement"]) if fact else None
        if (
            required is None
            or required.kind != "npc_damage"
            or required.target.model_dump(mode="json") != body.get("owner")
        ):
            raise WorkflowError(
                "SOURCE_NPC_DAMAGE_MISSING: recover the actual printed damage source."
            )
        if (required.details.get("source_kind") == npc_rules.SELF_SOURCE) != (
            body.get("source_kind") == npc_rules.SELF_SOURCE
        ):
            raise WorkflowError("Preserve the exact finite NPC self-damage source type")
        if body.get("source_kind") == npc_rules.SELF_SOURCE:
            if state is None:
                raise WorkflowError("Recover the actual NPC self-cost birth")
            source = prove_flirt_self_damage(self.game, c, state, row["id"])
            if (
                required.target != source.npc
                or required.opponent != source.npc
                or required.details.get("source_kind") != npc_rules.SELF_SOURCE
                or required.details.get("source_damage") != source.damage
                or body.get("source_action") != source.action
                or body.get("source_choice") != source.choice
                or body.get("source_damage") != source.damage
                or row["owner_id"] != str(source.controller)
            ):
                raise WorkflowError("Do not substitute a Girl attacker or unrelated damage source")
        return required.target, required.opponent

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            human = int(body.get("handler", MedicalService(self.store)._handler(c)[0]))
            owner = human if body.get("phase") == "optional_tag" else int(row["owner_id"])
            if viewer.user_id not in (owner, int(row["owner_id"])):
                raise WorkflowError("Only this actual printed chooser can read this consequence.")
            target, attacker = self._proof(c, row)
            state = load_state(c, self.store.campaign_id)
            npc = (
                next((x for x in state.world.npcs if x.id == target.entity), None)
                if state.world
                else None
            )
            if npc is None:
                raise WorkflowError("Recover the original actual NPC body.")
            from girlframe.engine.m3_assets import can_replace_at_limit
            from girlframe.services.m3_items import available_items

            receiving = (
                state.sheets.get(attacker.entity)
                if attacker is not None and attacker.kind == "pilot"
                else None
            )
            replacements = (
                [
                    dict(id=x.id, name=x.name)
                    for x in receiving.assets
                    if x.family == "girl" and can_replace_at_limit(receiving, x)
                ]
                if receiving is not None and sum(x.family == "girl" for x in receiving.assets) >= 4
                else []
            )

            from girlframe.engine.m3_am import require_harm

            can_harm = True
            try:
                require_harm(state, attacker, target)
            except ValueError:
                can_harm = False
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                phase=body.get("phase", "choose"),
                target=npc.name,
                items=available_items(c, self.game, state, target)
                if npc.alive and row["state"] != "resolved"
                else [],
                locations=[dict(id=x.id, name=x.name, cell=x.cell) for x in state.world.locations]
                if state.world
                else [],
                can_take=attacker is not None
                and (body.get("source_kind") != npc_rules.SELF_SOURCE or attacker != target),
                self_damage=body.get("source_kind") == npc_rules.SELF_SOURCE,
                allowed_effects=tuple(
                    effect
                    for effect in npc_rules.SELF_EFFECTS
                    if effect != "move" or _self_can_move(self.game, c, state, target)
                )
                if body.get("source_kind") == npc_rules.SELF_SOURCE
                else ("injure_tag", "take_item", "move", "advantage", "kill"),
                can_harm=can_harm,
                effect=body.get("effect"),
                replacements=replacements,
                can_respond=viewer.user_id == owner
                and body.get("phase", "choose") in ("choose", "optional_tag"),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        effect: str,
        account: str,
        *,
        tag: str = "",
        item: str = "",
        location: str = "",
        replace: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            if row["state"] == "resolved" or row["revision"] != revision:
                raise WorkflowError("STALE_NPC_DAMAGE: reopen the original consequence.")
            if body.get("phase", "choose") != "choose" or row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("The actual printed chooser owns this damage consequence.")
            if (
                effect not in ("injure_tag", "take_item", "move", "advantage", "kill")
                or not account.strip()
            ):
                raise WorkflowError(
                    "Choose a printed NPC consequence and describe its real effect."
                )
            if (
                (effect == "injure_tag") != (bool(tag.strip()))
                or bool(item) != (effect == "take_item")
                or bool(location) != (effect == "move")
            ):
                raise WorkflowError("Supply only the actual chosen NPC consequence details.")
            if replace is not None and effect != "take_item":
                raise WorkflowError("Only a real received Asset can require an owned replacement.")
            target, attacker = self._proof(c, row)
            state = load_state(c, self.store.campaign_id)
            self_cost = body.get("source_kind") == npc_rules.SELF_SOURCE
            if self_cost and effect not in npc_rules.SELF_EFFECTS:
                raise WorkflowError(
                    "A self-cost needs actual injury, death or a real different-cell move"
                )
            npc = (
                next((x for x in state.world.npcs if x.id == target.entity and x.alive), None)
                if state.world
                else None
            )
            if npc is None:
                raise WorkflowError(
                    "The original NPC is no longer alive; recover the actual source."
                )
            if effect in ("kill", "injure_tag"):
                from girlframe.engine.m3_am import require_harm

                require_harm(state, attacker, target)
            event = str(uuid4())
            if effect == "take_item":
                if attacker is None:
                    raise WorkflowError(
                        "Name the actual source attacker who takes the real object."
                    )
                from girlframe.engine.m3_items import actual_asset
                from girlframe.services.m3_items import take_in_transaction

                carried = next(
                    (x for x in state.held_items if x.id == item and x.holder == target), None
                )
                if replace is not None and (
                    carried is None or actual_asset(state, carried) is None
                ):
                    raise WorkflowError(
                        "An ordinary object does not replace a mechanical Girl Asset."
                    )

                state = take_in_transaction(
                    c,
                    self.game,
                    state,
                    source=target,
                    recipient=attacker,
                    selection=item,
                    action=body.get("source_action") or identity,
                    event=event,
                    account=account,
                    replace=replace,
                    source_work=identity,
                )
            elif effect == "move":
                assert state.world is not None
                destination = next((x for x in state.world.locations if x.id == location), None)
                if destination is None:
                    raise WorkflowError(
                        "Choose the actual campaign destination for this forced move."
                    )
                if self_cost and (
                    not _self_can_move(self.game, c, state, target)
                    or destination.cell
                    == resolve(
                        state,
                        target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).cell
                ):
                    raise WorkflowError("The actual free NPC must really move to a different cell")
                npc = npc.model_copy(update={"cell": destination.cell})
            elif effect == "kill":
                from girlframe.engine.m3_battle import end_actor_casts

                npc = npc.model_copy(update={"alive": False})
                state = interrupt_journeys(state, target, event, account)
                state = end_actor_casts(state, target, event)
            elif effect == "injure_tag":
                npc = npc.model_copy(
                    update={
                        "tags": npc.tags
                        + (
                            WorldTag(
                                id=identity + ":injury",
                                label=tag,
                                giver_entity=attacker.model_dump_json()
                                if attacker
                                else "gm:" + str(viewer.user_id),
                            ),
                        )
                    }
                )
            if effect != "take_item":
                assert state.world is not None
                state.world = state.world.model_copy(
                    update={"npcs": tuple(npc if x.id == npc.id else x for x in state.world.npcs)}
                )
            state.facts.append(
                dict(
                    kind="npc_asset_replacement",
                    work=identity,
                    target=target.model_dump_json(),
                    attacker=attacker.model_dump_json() if attacker else "",
                    effect=effect,
                    event=event,
                    account=account,
                    **({"source_kind": npc_rules.SELF_SOURCE} if self_cost else {}),
                )
            )
            phase = "optional_tag" if effect in ("take_item", "move", "advantage") else "done"
            changed = body | dict(
                damage_source_event=body.get("damage_source_event", row["event_id"]),
                effect=effect,
                effect_event=event,
                phase=phase,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_damage_applied",
                state,
                event_id=event,
                work_id=identity,
                effect=effect,
            )
            if effect == "kill":
                from girlframe.services.m3_battle import synchronize_casts

                synchronize_casts(self.game, c, event)
            table = t.m3["m3_required_work"]
            c.execute(
                table.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved" if phase == "done" else "pending",
                    event_id=event,
                    body_json=json.dumps(changed, sort_keys=True),
                )
            )
            if effect == "take_item":
                from girlframe.services.m3_items import create_npc_item_void

                actual_transfer = next(x for x in state.item_transfers if x.event == event)
                create_npc_item_void(self.game, c, actual_transfer.id, event)
            if phase == "done":
                from girlframe.services.m3_battle import complete_damage_work

                complete_damage_work(self.game, c, row, event, viewer, key)
            elif body.get("source_action"):
                action = self.game.action(c, body["source_action"])
                self.game.request(
                    c,
                    action,
                    body["handler"],
                    "battle_npc_optional_tag",
                    dict(work_id=identity),
                )
                self.game.save_action(c, action)
            return dict(
                id=identity,
                revision=row["revision"] + 1,
                state="resolved" if phase == "done" else "pending",
                phase=phase,
            )

        return self.store._write(
            viewer,
            key,
            "m3.npc_damage_applied",
            dict(
                id=identity,
                revision=revision,
                effect=effect,
                account=account,
                tag=tag,
                item=item,
                location=location,
                replace=replace,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def optional_tag(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        tag: str | None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                row["state"] == "resolved"
                or row["revision"] != revision
                or body.get("phase") != "optional_tag"
            ):
                raise WorkflowError("STALE_NPC_DAMAGE: reopen the actual optional Tag choice.")
            human, appointment = MedicalService(self.store)._handler(c)
            if human != body.get("handler") or appointment != body.get("appointment"):
                raise WorkflowError(
                    "STALE_HANDLER: recover this source's original optional Tag authority."
                )
            if viewer.user_id != human or tag is not None and not tag.strip():
                raise WorkflowError("The actual Handler explicitly gives a Tag or declines it.")
            target, _ = self._proof(c, row)
            state = load_state(c, self.store.campaign_id)
            event = str(uuid4())
            if tag is not None:
                assert state.world is not None
                state.world = state.world.model_copy(
                    update={
                        "npcs": tuple(
                            x.model_copy(
                                update={
                                    "tags": x.tags
                                    + (
                                        WorldTag(
                                            id=identity + ":advantage",
                                            label=tag,
                                            giver_entity="gm:" + appointment,
                                        ),
                                    )
                                }
                            )
                            if x.id == target.entity
                            else x
                            for x in state.world.npcs
                        )
                    }
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_damage_optional_tag",
                state,
                event_id=event,
                work_id=identity,
                given=tag is not None,
            )
            table = t.m3["m3_required_work"]
            ready = _void_ready(self.game, c, identity)
            c.execute(
                table.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved" if ready else "pending",
                    event_id=event,
                    body_json=json.dumps(
                        body
                        | dict(phase="done" if ready else "waiting_void", optional_tag_event=event),
                        sort_keys=True,
                    ),
                )
            )
            if body.get("source_action"):
                action = self.game.action(c, body["source_action"])
                choices = t.m2["m2_choices"]
                for choice in self.game.pending(c, action["id"]):
                    if (
                        choice["kind"] == "battle_npc_optional_tag"
                        and json.loads(choice["body_json"]).get("work_id") == identity
                    ):
                        c.execute(
                            choices.update()
                            .where(
                                choices.c.campaign_id == self.store.campaign_id,
                                choices.c.id == choice["id"],
                            )
                            .values(state="completed_by_work", revision=choice["revision"] + 1)
                        )
            from girlframe.services.m3_battle import complete_damage_work

            if ready:
                complete_damage_work(self.game, c, row, event, viewer, key)
            return dict(
                id=identity, state="resolved" if ready else "pending", revision=row["revision"] + 1
            )

        return self.store._write(
            viewer,
            key,
            "m3.npc_damage_optional_tag",
            dict(id=identity, revision=revision, tag=tag),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )


def _void_ready(game: GameService, c: Connection, parent: str) -> bool:
    table = t.m3["m3_required_work"]
    latest = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id)
            .order_by(table.c.revision)
        ).mappings()
    }
    return all(
        row["state"] == "resolved"
        for row in latest.values()
        if json.loads(row["body_json"]).get("source_work") == parent
        and json.loads(row["body_json"]).get("immediate")
    )


def complete_void_continuation(
    game: GameService,
    c: Connection,
    work_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """Actual final transfer corruption and an actual GM Tag choice both precede closure."""
    from girlframe.engine.m3_void import FINAL
    from girlframe.services.m3_battle import complete_damage_work
    from girlframe.services.m3_items import prove_transfer

    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work_id)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    body = json.loads(row["body_json"]) if row else {}
    if (
        row is None
        or row["kind"] != "void_threshold"
        or row["state"] != "resolved"
        or body.get("item_source") != "npc_damage"
    ):
        raise WorkflowError("Finish the actual NPC object-transfer Void consequence first.")
    state = load_state(c, game.store.campaign_id)
    threshold = next(
        (x for x in state.void_thresholds if work_id in x.source_works and x.stage in FINAL), None
    )
    _, _, transfer = prove_transfer(c, game, body["transfer"])
    if (
        threshold is None
        or transfer.source_kind != "npc_damage"
        or transfer.source_work != body.get("source_work")
    ):
        raise WorkflowError("Recover the actual original transfer and final threshold source.")
    service = NpcDamageService(game.store)
    parent = service._row(c, body["source_work"])
    original = json.loads(parent["body_json"])
    if body.get("source_action"):
        action = game.action(c, body["source_action"])
        choices = t.m2["m2_choices"]
        for choice in game.pending(c, action["id"]):
            if (
                choice["kind"] == "battle_item_void_threshold"
                and json.loads(choice["body_json"]).get("work_id") == work_id
            ):
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.id == choice["id"],
                    )
                    .values(state="completed_by_work", revision=choice["revision"] + 1)
                )
    if (
        parent["state"] == "resolved"
        or original.get("phase") != "waiting_void"
        or not _void_ready(game, c, parent["id"])
    ):
        return
    c.execute(
        table.insert().values(
            **{
                k: v
                for k, v in parent.items()
                if k not in ("revision", "state", "body_json", "event_id")
            },
            revision=parent["revision"] + 1,
            state="resolved",
            event_id=event,
            body_json=json.dumps(
                original | dict(phase="done", void_completion=event), sort_keys=True
            ),
        )
    )
    complete_damage_work(game, c, parent, event, viewer, key)
