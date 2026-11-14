"""SQLite append-only preparation evidence guards; no dispatch authority."""

GUARDS = (
    (
        "external_effects_no_update",
        """CREATE TRIGGER external_effects_no_update
BEFORE UPDATE ON external_effects
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effects_no_delete",
        """CREATE TRIGGER external_effects_no_delete
BEFORE DELETE ON external_effects
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_actors_no_update",
        """CREATE TRIGGER external_effect_actors_no_update
BEFORE UPDATE ON external_effect_actors
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_actors_no_delete",
        """CREATE TRIGGER external_effect_actors_no_delete
BEFORE DELETE ON external_effect_actors
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_resources_no_update",
        """CREATE TRIGGER external_resources_no_update
BEFORE UPDATE ON external_resources
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_resources_no_delete",
        """CREATE TRIGGER external_resources_no_delete
BEFORE DELETE ON external_resources
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_resources_no_update",
        """CREATE TRIGGER external_effect_resources_no_update
BEFORE UPDATE ON external_effect_resources
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_resources_no_delete",
        """CREATE TRIGGER external_effect_resources_no_delete
BEFORE DELETE ON external_effect_resources
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_source_no_update",
        """CREATE TRIGGER external_effect_source_no_update
BEFORE UPDATE ON events
WHEN EXISTS (SELECT 1 FROM external_effects
 WHERE campaign_id = OLD.campaign_id AND event_seq = OLD.seq)
BEGIN SELECT RAISE(ABORT, 'Referenced source evidence is immutable'); END""",
    ),
    (
        "external_effect_source_no_delete",
        """CREATE TRIGGER external_effect_source_no_delete
BEFORE DELETE ON events
WHEN EXISTS (SELECT 1 FROM external_effects
 WHERE campaign_id = OLD.campaign_id AND event_seq = OLD.seq)
BEGIN SELECT RAISE(ABORT, 'Referenced source evidence is immutable'); END""",
    ),
    (
        "external_effect_actor_matches_body",
        """CREATE TRIGGER external_effect_actor_matches_body
BEFORE INSERT ON external_effect_actors
WHEN NOT EXISTS (
 SELECT 1 FROM external_effects e, json_each(e.body_json, '$.actors') a
 WHERE e.campaign_id = NEW.campaign_id AND e.id = NEW.effect_id
 AND json_extract(a.value, '$.relation') = NEW.relation
 AND json_extract(a.value, '$.generation') = NEW.availability_generation
 AND json_extract(a.value, '$.actor.kind') = json_extract(NEW.actor_json, '$.kind')
 AND json_extract(a.value, '$.actor.entity') = json_extract(NEW.actor_json, '$.entity')
 AND json_extract(a.value, '$.actor.incarnation') IS json_extract(NEW.actor_json, '$.incarnation')
)
BEGIN SELECT RAISE(ABORT, 'Actor incidence does not match preparation'); END""",
    ),
    (
        "external_effect_resource_matches_body",
        """CREATE TRIGGER external_effect_resource_matches_body
BEFORE INSERT ON external_effect_resources
WHEN NOT EXISTS (
 SELECT 1 FROM external_effects e
 WHERE e.campaign_id = NEW.campaign_id AND e.id = NEW.effect_id
 AND NEW.resource_key = 'discord:channel:' ||
     json_extract(e.body_json, '$.resource.destination.channel_id')
 AND NOT EXISTS (
  SELECT fullkey, type, atom FROM json_tree(json_extract(e.body_json, '$.resource'))
  EXCEPT SELECT fullkey, type, atom FROM json_tree(NEW.binding_json)
 )
 AND NOT EXISTS (
  SELECT fullkey, type, atom FROM json_tree(NEW.binding_json)
  EXCEPT SELECT fullkey, type, atom FROM json_tree(json_extract(e.body_json, '$.resource'))
 )
)
BEGIN SELECT RAISE(ABORT, 'Resource binding does not match preparation'); END""",
    ),
    (
        "external_effects_no_replace",
        """CREATE TRIGGER external_effects_no_replace
BEFORE INSERT ON external_effects
WHEN EXISTS (SELECT 1 FROM external_effects WHERE (campaign_id = NEW.campaign_id
 AND id = NEW.id)
 OR (campaign_id = NEW.campaign_id
 AND source_kind = NEW.source_kind
 AND source_id = NEW.source_id
 AND source_revision = NEW.source_revision
 AND step_key = NEW.step_key))
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_resources_no_replace",
        """CREATE TRIGGER external_resources_no_replace
BEFORE INSERT ON external_resources
WHEN EXISTS (SELECT 1 FROM external_resources WHERE resource_key = NEW.resource_key)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_actors_no_replace",
        """CREATE TRIGGER external_effect_actors_no_replace
BEFORE INSERT ON external_effect_actors
WHEN EXISTS (SELECT 1 FROM external_effect_actors WHERE campaign_id = NEW.campaign_id
 AND effect_id = NEW.effect_id
 AND relation = NEW.relation
 AND (actor_token = NEW.actor_token
 OR (json_extract(actor_json, '$.kind') = json_extract(NEW.actor_json, '$.kind')
 AND json_extract(actor_json, '$.entity') = json_extract(NEW.actor_json, '$.entity')
 AND json_extract(actor_json, '$.incarnation') IS json_extract(NEW.actor_json, '$.incarnation'))))
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_resources_no_replace",
        """CREATE TRIGGER external_effect_resources_no_replace
BEFORE INSERT ON external_effect_resources
WHEN EXISTS (SELECT 1 FROM external_effect_resources WHERE campaign_id = NEW.campaign_id
 AND effect_id = NEW.effect_id)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_source_no_replace",
        """CREATE TRIGGER external_effect_source_no_replace
BEFORE INSERT ON events
WHEN EXISTS (
 SELECT 1 FROM events e JOIN external_effects x
 ON x.campaign_id = e.campaign_id AND x.event_seq = e.seq
 WHERE (e.campaign_id = NEW.campaign_id AND e.seq = NEW.seq) OR e.id = NEW.id
 OR (e.campaign_id = NEW.campaign_id AND e.command_key = NEW.command_key
     AND e.event_index = NEW.event_index)
)
BEGIN SELECT RAISE(ABORT, 'Referenced source evidence is immutable'); END""",
    ),
    (
        "external_effects_no_rowid_replace",
        """CREATE TRIGGER external_effects_no_rowid_replace
BEFORE INSERT ON external_effects
WHEN EXISTS (SELECT 1 FROM external_effects WHERE rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_actors_no_rowid_replace",
        """CREATE TRIGGER external_effect_actors_no_rowid_replace
BEFORE INSERT ON external_effect_actors
WHEN EXISTS (SELECT 1 FROM external_effect_actors WHERE rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_resources_no_rowid_replace",
        """CREATE TRIGGER external_resources_no_rowid_replace
BEFORE INSERT ON external_resources
WHEN EXISTS (SELECT 1 FROM external_resources WHERE rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_resources_no_rowid_replace",
        """CREATE TRIGGER external_effect_resources_no_rowid_replace
BEFORE INSERT ON external_effect_resources
WHEN EXISTS (SELECT 1 FROM external_effect_resources WHERE rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'External-effect evidence is immutable'); END""",
    ),
    (
        "external_effect_source_no_rowid_replace",
        """CREATE TRIGGER external_effect_source_no_rowid_replace
BEFORE INSERT ON events
WHEN EXISTS (
 SELECT 1 FROM events e JOIN external_effects x
 ON x.campaign_id = e.campaign_id AND x.event_seq = e.seq
 WHERE e.rowid = NEW.rowid
)
BEGIN SELECT RAISE(ABORT, 'Referenced source evidence is immutable'); END""",
    ),
    (
        "external_effect_actor_token_consistent",
        """CREATE TRIGGER external_effect_actor_token_consistent
BEFORE INSERT ON external_effect_actors
WHEN EXISTS (
 SELECT 1 FROM external_effect_actors a
 WHERE a.campaign_id = NEW.campaign_id
 AND ((a.actor_token = NEW.actor_token) != (
 json_extract(a.actor_json, '$.kind') = json_extract(NEW.actor_json, '$.kind')
 AND json_extract(a.actor_json, '$.entity') = json_extract(NEW.actor_json, '$.entity')
 AND json_extract(a.actor_json, '$.incarnation') IS json_extract(NEW.actor_json, '$.incarnation')
 ))
)
BEGIN SELECT RAISE(ABORT, 'Actor token conflicts with original identity'); END""",
    ),
)
