"""Private Activity controls for work spawned by a scene's alternate Plays."""

import json

import sqlalchemy as sa

from girlframe.database import tables
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_gorgon_aggressive import AggressiveService
from girlframe.services.m3_gorgon_dormant import GorgonDormantService
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.native_form_fields import Field, form_fields
from girlframe.services.onboarding import WorkflowError

DORMANT = "gorgon_dormant_void"
AGGRESSIVE = "battle_aggressive_damage"
SPRITE = "battle_sprite_intercept"
WORK = frozenset((DORMANT, AGGRESSIVE, SPRITE))
PASS = ("pass", "Decline")


class AlternateWork:
    def __init__(self, session):
        self.session = session
        self.store = session.store
        self.dormant = GorgonDormantService(self.store, session.game)
        self.aggressive = AggressiveService(self.store)
        self.sprites = SpriteService(self.store)

    def form(self, viewer, decision):
        kind = decision["kind"]
        if kind == DORMANT:
            work = self.dormant.get(viewer, decision["body"]["work_id"])
            if not work["can_act"]:
                return None
            options = (
                (("already_void", "All original Gorgon Assets are already Void"),)
                if (work["already_fully_void"])
                else tuple((asset["id"], asset["name"]) for asset in work["assets"])
            )
            title = "Dormant · Counter-Void"
            label = "Describe the alteration to the original Gorgon"
        elif kind == AGGRESSIVE:
            work = self.aggressive.get(viewer, decision["body"]["work_id"])
            if work["state"] != "pending":
                return None
            options = (PASS, *((asset["id"], asset["name"]) for asset in work["assets"]))
            title = "Aggressive · Immediate hit"
            label = "Describe the Gorgon's choice"
        else:
            work = self.sprites.get(viewer, decision["work_id"])
            if work["state"] != "pending" or work["phase"] != "choose" or work["answered"]:
                return None
            options = (
                PASS,
                *(
                    (
                        json.dumps([item["actor"], item["asset"]], separators=(",", ":")),
                        item["label"],
                    )
                    for item in work["options"]
                ),
            )
            title = "Sprite · Intercept the blow"
            label = "Describe the Sprite's actual response"
        return dict(
            id=decision["id"],
            kind=kind,
            title=title,
            revision=work["revision"],
            game_revision=work["game_revision"],
            native_work=True,
            fields=form_fields(
                (
                    Field("options", "Original source choice", options),
                    Field("text", label, paragraph=True),
                )
            ),
        )

    def answer(self, viewer, key, scene, identity, revision, game_revision, answer):
        def source(c):
            self.session.observer._scene(c, scene, viewer)
            table = tables.m2["m2_choices"]
            row = c.execute(
                sa.select(table.c.kind, table.c.action_id, table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.actor_id == str(viewer.user_id),
                    table.c.kind.in_(WORK),
                )
            ).first()
            if row is None or row.action_id not in self.session.reactions.alternate_action_ids(
                c, scene
            ):
                raise WorkflowError("Use your own required work from the original alternate Play.")
            return row.kind, json.loads(row.body_json)["work_id"]

        if len(answer.options) != 1 or not answer.text.strip():
            raise WorkflowError("Choose one native outcome and describe what happens.")
        selected = answer.options[0]
        with self.store.engine.connect() as c:
            kind, work_id = source(c)

        def guard(c):
            if source(c) != (kind, work_id):
                raise WorkflowError("Reopen the original alternate Play decision.")

        with self.store.source_guard(guard):
            if kind == DORMANT:
                return self.dormant.respond(
                    viewer,
                    key,
                    work_id,
                    revision,
                    game_revision,
                    None if selected == "already_void" else selected,
                    answer.text,
                )
            if kind == AGGRESSIVE:
                return self.aggressive.respond(
                    viewer,
                    key,
                    work_id,
                    revision,
                    game_revision,
                    None if selected == "pass" else selected,
                    answer.text,
                )
            if selected == "pass":
                actor, asset = None, None
            else:
                try:
                    ref, asset = json.loads(selected)
                    actor = ActorRef.model_validate(ref)
                    if not isinstance(asset, str):
                        raise ValueError
                except (TypeError, ValueError):
                    raise WorkflowError("Choose one of your original eligible Sprites.") from None
            return self.sprites.respond(
                viewer,
                key,
                work_id,
                revision,
                game_revision,
                actor,
                asset,
                answer.text,
            )
