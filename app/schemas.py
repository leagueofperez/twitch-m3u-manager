from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelOut(BaseModel):
    name: str
    url: str | None
    channel: str | None
    managed: bool


class PlaylistSummary(BaseModel):
    name: str
    count: int
    m3u: str = Field(description="URL path for the generated M3U playlist")


class ChannelLiveStatus(BaseModel):
    channel: str
    live: bool


class PlaylistDetail(BaseModel):
    name: str
    count: int
    m3u: str
    channels: list[ChannelOut]
    channel_status: list[ChannelLiveStatus] = Field(default_factory=list)


class PlaylistCreate(BaseModel):
    name: str = Field(max_length=64, examples=["twitch-local"])
    channels: list[str] | str = Field(default="", description="Comma- or whitespace-separated Twitch channel names")
    overwrite: bool = False


class AddChannelsRequest(BaseModel):
    channels: list[str] | str = Field(description="Comma- or whitespace-separated Twitch channel names")


class AddChannelsResponse(BaseModel):
    added: list[str]
    skipped: list[str]
    playlist: PlaylistDetail


