"""Read only actual owned Amygdala choices before a player confirms a Play."""

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_ankou import require_rule
from girlframe.services.read_only_bot import GuildViewer


def pulse_tags(game: GameService, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        sheet = state.sheets.get(str(viewer.user_id))
        if sheet is None or sheet.frame != rules.FRAME or not sheet.character_id:
            return ()
        actor = current_ref(state, viewer.user_id)
        if not rules.held(state, actor, rules.PULSE):
            return ()
        require_rule(game, c, state, actor, rules.PULSE)
        return tuple((x.id, x.label) for x in actor_tags(state, actor))
