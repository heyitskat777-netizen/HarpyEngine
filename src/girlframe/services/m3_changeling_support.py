"""Finite Changeling body and identity ports; specialized effects retain source ownership."""

from girlframe.services.m3_changeling_body import appearance_choices as appearance_choices
from girlframe.services.m3_changeling_body import brain as brain
from girlframe.services.m3_changeling_body import change_body as change_body
from girlframe.services.m3_changeling_body import context as context
from girlframe.services.m3_changeling_body import recheck_access as recheck_access
from girlframe.services.m3_changeling_body import (
    reconditioning_candidates as reconditioning_candidates,
)
from girlframe.services.m3_changeling_body import validate_access as validate_access
from girlframe.services.m3_changeling_body import validate_start_brain as validate_start_brain
from girlframe.services.m3_changeling_effects import effect_detail as effect_detail
from girlframe.services.m3_changeling_effects import fingers_effect as fingers_effect
from girlframe.services.m3_changeling_effects import force_damage as force_damage
from girlframe.services.m3_changeling_effects import fry as fry
from girlframe.services.m3_changeling_effects import recent_loss as recent_loss
from girlframe.services.m3_changeling_effects import sex_complete as sex_complete
from girlframe.services.m3_changeling_effects import synchronize as synchronize
from girlframe.services.m3_changeling_identity import can_lower_status as can_lower_status
from girlframe.services.m3_changeling_identity import copy_choices as copy_choices
from girlframe.services.m3_changeling_identity import erase_identities as erase_identities
from girlframe.services.m3_changeling_identity import grant_blank as grant_blank
from girlframe.services.m3_changeling_identity import identity_options as identity_options
from girlframe.services.m3_changeling_identity import identity_requirements as identity_requirements
from girlframe.services.m3_changeling_identity import replace_blank as replace_blank
from girlframe.services.m3_changeling_identity import status as status
