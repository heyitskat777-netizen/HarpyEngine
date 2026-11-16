"""Private review referrals are distinct from mechanical outcome proposals."""

from girlframe.ai.contracts import Contract


class PlayReferral(Contract):
    play_id: str
    rule_id: str
    title: str
    adapter: str
    module_enabled: bool
