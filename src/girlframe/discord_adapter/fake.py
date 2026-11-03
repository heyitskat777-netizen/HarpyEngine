"""In-memory transport for offline tests; not a Discord API emulator."""

from girlframe.discord_adapter.transport import PrivateResponse


class FakeDiscordTransport:
    def __init__(self) -> None:
        self.responses: list[PrivateResponse] = []

    async def respond_private(self, response: PrivateResponse) -> None:
        self.responses.append(response)
