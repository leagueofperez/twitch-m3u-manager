class TwitchError(RuntimeError):
    """Error con mensaje apto para mostrar al usuario (nunca contiene tokens)."""


class ChannelOffline(TwitchError):
    """The requested channel is not currently live."""


class ChannelNotFound(TwitchError):
    """The requested Twitch channel does not exist."""


class TwitchRateLimited(TwitchError):
    """Twitch is throttling API requests."""

    def __init__(self, retry_after: str | None = None):
        super().__init__("Twitch is rate limiting requests. Please retry later.")
        self.retry_after = retry_after if retry_after and retry_after.isdigit() else None
