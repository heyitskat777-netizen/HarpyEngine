"""Offline, explicit owner-authorized bot appointment before campaign activation.

No web endpoint, OAuth bypass, automatic rulings, or character migration.
The caller must verify the actual Discord bot and stop the campaign's web worker.
"""
import sqlite3
from contextlib import closing
from dataclasses import replace

import sqlalchemy as sa
from girlframe.database import tables
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def assign_bot_handler(service, registry, binding, *, bot_id, expected_handler, actor_id, key):
    if not isinstance(bot_id, str) or bot_id != binding.application_id:
        raise ValueError("Use this campaign application's verified Discord bot.")
    if binding.id.replace("-", "") != str(service.store.campaign_id).replace("-", ""):
        raise ValueError("The authoritative store does not match the campaign binding.")
    if actor_id != expected_handler:
        raise ValueError("Use the explicitly authorized current Handler.")
    store = service.store
    with closing(sqlite3.connect(registry.path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT handler_id,owner_id,application_id,guild_id,role_id FROM bindings WHERE id=?", (binding.id,)).fetchone()
        if row is None or row[1] != actor_id or tuple(row[2:]) != (binding.application_id,binding.guild_id,binding.role_id):
            raise WorkflowError("Only the saved guild owner can reassign this exact campaign.")
        if row[0] not in (expected_handler,bot_id):
            raise WorkflowError("The campaign Handler changed. Review the current assignment.")
        handler = HandlerService(store)
        with store.engine.connect() as c:
            state = load_state(c,store.campaign_id)
            revision, setup = handler.current(c)
            if state.sheets or state.order or state.handler is not None or state.career_archives:
                raise WorkflowError("An activated campaign requires an explicit native Handler migration.")
            if setup.handler_id not in (int(expected_handler),int(bot_id)):
                raise WorkflowError("The native Handler changed. Review the current assignment.")
            if setup.mentors or setup.status_order or setup.creation_rulings is not None or setup.creation_rulings_explicit:
                raise WorkflowError("Review existing creation assignments before changing the Handler.")
            member = c.scalar(sa.select(tables.members.c.active).where(
                tables.members.c.campaign_id==store.campaign_id,
                tables.members.c.user_id==bot_id))
        bot = GuildViewer(int(bot_id),int(binding.guild_id),True,False)
        if member is False:
            raise WorkflowError("The bot's native campaign membership is inactive.")
        if member is None:
            store.join(bot,key+":join-bot")
        if setup.handler_id != int(bot_id):
            admin = GuildViewer(int(actor_id),int(binding.guild_id),True,True)
            handler.appoint(admin,key+":appoint-bot",revision,int(bot_id))
        db.execute("UPDATE bindings SET handler_id=? WHERE id=? AND handler_id IN (?,?)",
                   (bot_id,binding.id,expected_handler,bot_id))
    return replace(binding,handler_id=bot_id)
