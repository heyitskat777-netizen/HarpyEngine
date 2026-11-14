"""Unused, transaction-local preparation storage, NOT dispatch or shelf authority.

Only validated source producers may eventually call prepare in their source commit.
Event-carried evidence binds input; it does not prove completeness or current authority.
Reservation deliberately has no implementation until canonical admission is integrated.
"""

import hashlib
import json
import sqlite3
from typing import Literal, NoReturn
from uuid import uuid4

import sqlalchemy as sa
from pydantic import Field, model_validator
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef, Model


class JournalError(RuntimeError):
    """Safe journal conflict or unavailable authority, without private payloads."""


class Source(Model):
    kind: str = Field(min_length=1, max_length=100)
    id: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1)
    event_seq: int = Field(ge=1)
    step_key: str = Field(min_length=1, max_length=200)


class Incidence(Model):
    actor: ActorRef
    generation: int = Field(ge=1)
    relation: Literal["subject", "owner", "audience", "shared_scene"]


class Destination(Model):
    kind: Literal["guild_channel", "dm"]
    guild_id: str = Field(pattern=r"^[1-9][0-9]*$")
    channel_id: str = Field(pattern=r"^[1-9][0-9]*$")
    bot_id: str = Field(pattern=r"^[1-9][0-9]*$")
    recipient_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")

    @model_validator(mode="after")
    def exact_recipient(self) -> "Destination":
        if (self.kind == "dm") != (self.recipient_id is not None):
            raise ValueError("DM destinations require the original resolved recipient")
        return self

    @property
    def resource_key(self) -> str:
        # Discord channel IDs are global, including resolved private channels.
        return f"discord:channel:{self.channel_id}"


class ResourceBinding(Model):
    destination: Destination
    revision: int = Field(ge=1)
    owner_generation: int = Field(ge=1)
    scene_id: str = Field(min_length=1)
    cast_revision: int = Field(ge=1)
    source_generation: int = Field(ge=1)
    target_kind: Literal["role", "member"] | None = None
    target_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    owned_mask: int | None = Field(default=None, ge=1)


class Preparation(Model):
    source: Source
    operation: Literal[
        "control_post",
        "public_post",
        "private_post",
        "facilitator_notice",
        "permission_apply",
        "permission_restore",
    ]
    actors: tuple[Incidence, ...] = Field(min_length=1)
    resource: ResourceBinding
    # Retain exact private payload, not just its digest. Never log this object.
    payload: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self) -> "Preparation":
        if len({(i.actor, i.relation) for i in self.actors}) != len(self.actors):
            raise ValueError("Duplicate actor incidence")
        if len({i.actor for i in self.actors}) != len(
            {(i.actor, i.generation) for i in self.actors}
        ):
            raise ValueError("Conflicting original actor generations")
        permission = self.operation in ("permission_apply", "permission_restore")
        fields = (self.resource.target_kind, self.resource.target_id, self.resource.owned_mask)
        if permission != all(x is not None for x in fields) or (
            not permission and any(x is not None for x in fields)
        ):
            raise ValueError("Permission effects require one exact target and owned mask")
        private = self.operation == "private_post"
        if private != (self.resource.destination.kind == "dm"):
            raise ValueError("Operation must match immutable destination kind")
        return self


def _body(preparation: Preparation) -> str:
    data = preparation.model_dump(mode="json")
    data["actors"] = sorted(data["actors"], key=lambda item: json.dumps(item, sort_keys=True))
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def prepare(connection: Connection, campaign_id: str, preparation: Preparation) -> str:
    """Persist in an already-open SQLite transaction, never commit it.

    The source event must already carry the exact canonical preparation in its
    external_effect_preparations list. An unrelated event is never sufficient.
    This is evidence binding, not a canonical producer authorization check: future
    producers must validate actors, generations and complete incidence in their
    source transaction. Historical unbound events cannot be backfilled through
    this API. No stored state is considered safe to dispatch.
    """
    # Revalidate even model_copy/model_construct inputs at the storage boundary.
    preparation = Preparation.model_validate(preparation.model_dump())
    raw = connection.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection) or not raw.in_transaction:
        raise JournalError("Preparation requires an open SQLite source transaction")
    destination = preparation.resource.destination
    guild = connection.scalar(
        sa.select(t.campaigns.c.guild_id).where(t.campaigns.c.id == campaign_id)
    )
    if guild != destination.guild_id:
        raise JournalError("Destination does not match the source campaign")
    event = connection.scalar(
        sa.select(t.events.c.payload_json).where(
            t.events.c.campaign_id == campaign_id, t.events.c.seq == preparation.source.event_seq
        )
    )
    if event is None:
        raise JournalError("Original source event is missing")
    body = _body(preparation)
    try:
        payload = json.loads(event)
        evidence = (
            payload.get("external_effect_preparations") if isinstance(payload, dict) else None
        )
        authenticated = isinstance(evidence, list) and body in [
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for item in evidence
        ]
    except (TypeError, ValueError):
        authenticated = False
    if not authenticated:
        raise JournalError("Source event does not attest this exact preparation")
    tables = t.external_effects
    effects = tables["effects"]
    source = preparation.source
    predicate = sa.and_(
        effects.c.campaign_id == campaign_id,
        effects.c.source_kind == source.kind,
        effects.c.source_id == source.id,
        effects.c.source_revision == source.revision,
        effects.c.step_key == source.step_key,
    )
    existing = connection.execute(sa.select(effects).where(predicate)).mappings().first()
    if existing is not None:
        if existing["body_json"] != body:
            raise JournalError("Semantic effect key conflicts with its original preparation")
        expected_fields = {
            "event_seq": source.event_seq,
            "operation": preparation.operation,
            "payload_digest": hashlib.sha256(preparation.payload.encode()).hexdigest(),
            "state": "prepared",
            "revision": 1,
            "schema_version": 1,
        }
        if any(existing[key] != value for key, value in expected_fields.items()):
            raise JournalError("Stored preparation metadata is inconsistent")
        _verify_projection(connection, campaign_id, str(existing["id"]), preparation)
        return str(existing["id"])
    effect_id = str(uuid4())
    resource_key = destination.resource_key
    # A resolved physical private channel cannot silently change recipient or bot.
    descriptor = json.dumps(destination.model_dump(mode="json"), sort_keys=True)
    resources = tables["resources"]
    # Savepoint makes a caught conflict unable to leave a half-prepared effect.
    from girlframe.services.p1_write_capture import source_savepoint

    with source_savepoint(connection):
        resource = (
            connection.execute(sa.select(resources).where(resources.c.resource_key == resource_key))
            .mappings()
            .first()
        )
        if resource is None:
            connection.execute(
                resources.insert().values(
                    campaign_id=campaign_id, resource_key=resource_key, descriptor_json=descriptor
                )
            )
        elif resource["campaign_id"] != campaign_id or resource["descriptor_json"] != descriptor:
            raise JournalError("Physical destination ownership conflicts with original campaign")
        connection.execute(
            effects.insert().values(
                campaign_id=campaign_id,
                id=effect_id,
                event_seq=source.event_seq,
                source_kind=source.kind,
                source_id=source.id,
                source_revision=source.revision,
                step_key=source.step_key,
                operation=preparation.operation,
                body_json=body,
                payload_digest=hashlib.sha256(preparation.payload.encode()).hexdigest(),
            )
        )
        for incidence in preparation.actors:
            connection.execute(
                tables["actors"]
                .insert()
                .values(
                    campaign_id=campaign_id,
                    effect_id=effect_id,
                    actor_token=incidence.actor.token,
                    actor_json=incidence.actor.model_dump_json(),
                    relation=incidence.relation,
                    availability_generation=incidence.generation,
                )
            )
        connection.execute(
            tables["links"]
            .insert()
            .values(
                campaign_id=campaign_id,
                effect_id=effect_id,
                resource_key=resource_key,
                binding_json=preparation.resource.model_dump_json(),
            )
        )
    return effect_id


def _verify_projection(
    connection: Connection, campaign_id: str, effect_id: str, preparation: Preparation
) -> None:
    """Reject stale/corrupt legacy projections instead of blessing them on replay."""
    tables = t.external_effects
    actors = tables["actors"]
    actual = {
        (row.actor_token, row.relation, row.actor_json, row.availability_generation)
        for row in connection.execute(
            sa.select(actors).where(
                actors.c.campaign_id == campaign_id, actors.c.effect_id == effect_id
            )
        )
    }
    expected = {
        (i.actor.token, i.relation, i.actor.model_dump_json(), i.generation)
        for i in preparation.actors
    }
    links = tables["links"]
    actual_links = list(
        connection.execute(
            sa.select(links.c.resource_key, links.c.binding_json).where(
                links.c.campaign_id == campaign_id, links.c.effect_id == effect_id
            )
        )
    )
    resources = tables["resources"]
    destination = preparation.resource.destination
    descriptor = connection.scalar(
        sa.select(resources.c.descriptor_json).where(
            resources.c.campaign_id == campaign_id,
            resources.c.resource_key == destination.resource_key,
        )
    )
    if (
        actual != expected
        or actual_links != [(destination.resource_key, preparation.resource.model_dump_json())]
        or descriptor != json.dumps(destination.model_dump(mode="json"), sort_keys=True)
    ):
        raise JournalError("Stored preparation incidence or resource evidence is inconsistent")


def reserve(*, campaign_id: str, effect_id: str, expected_revision: int) -> NoReturn:
    """Never returns authority, even for a cached valid preparation or old lease."""
    raise JournalError(
        "Dispatch unavailable: canonical admission and shared drain are not installed"
    )
