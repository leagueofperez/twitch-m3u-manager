"""JSON endpoints under /api."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from .. import m3u
from ..extraction import check_channels_live
from ..schemas import (
    AddChannelsRequest,
    AddChannelsResponse,
    ChannelOut,
    ChannelLiveStatus,
    PlaylistCreate,
    PlaylistDetail,
    PlaylistSummary,
)
from ..security import require_auth

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_auth)])


def detail(
    name: str,
    entries: list[m3u.Entry],
    channel_status: list[ChannelLiveStatus] | None = None,
) -> PlaylistDetail:
    return PlaylistDetail(
        name=name,
        count=len(entries),
        m3u=f"/m3u/{name}.m3u",
        channels=[
            ChannelOut(
                name=entry.name,
                url=entry.url,
                channel=entry.channel,
                managed=entry.managed,
            )
            for entry in entries
        ],
        channel_status=channel_status or [],
    )


@router.get("/playlists", response_model=list[PlaylistSummary], summary="List playlists")
def list_playlists() -> list[PlaylistSummary]:
    return [
        PlaylistSummary(name=playlist.name, count=playlist.count, m3u=f"/m3u/{playlist.name}.m3u")
        for playlist in m3u.list_playlists()
    ]


@router.post(
    "/playlists",
    response_model=PlaylistDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create playlist",
)
def create_playlist(body: PlaylistCreate) -> PlaylistDetail:
    m3u.normalize_playlist_name(body.name)
    if m3u.playlist_exists(body.name) and not body.overwrite:
        raise m3u.Conflict(f"La lista '{body.name}' ya existe")
    channels = m3u.parse_channel_names(body.channels)
    statuses = check_channels_live(channels)
    entries = m3u.create_playlist(body.name, channels, overwrite=body.overwrite)
    return detail(
        body.name,
        entries,
        [ChannelLiveStatus(channel=channel, live=statuses[channel.casefold()]) for channel in channels],
    )


@router.get("/playlists/{name}", response_model=PlaylistDetail, summary="Get playlist")
def get_playlist(name: str) -> PlaylistDetail:
    return detail(name, m3u.load_playlist(name))


@router.delete(
    "/playlists/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete playlist",
)
def delete_playlist(name: str) -> Response:
    m3u.delete_playlist(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/playlists/{name}/channels",
    response_model=AddChannelsResponse,
    summary="Add Twitch channels",
)
def add_channels(name: str, body: AddChannelsRequest) -> AddChannelsResponse:
    current = m3u.load_playlist(name)
    channels = m3u.parse_channel_names(body.channels)
    existing = {(entry.channel or entry.name).casefold() for entry in current}
    channels_to_check = [channel for channel in channels if channel.casefold() not in existing]
    statuses = check_channels_live(channels_to_check) if channels_to_check else {}
    added, skipped, entries = m3u.add_channels(name, channels)
    return AddChannelsResponse(
        added=added,
        skipped=skipped,
        playlist=detail(
            name,
            entries,
            [
                ChannelLiveStatus(channel=channel, live=statuses[channel.casefold()])
                for channel in channels_to_check
            ],
        ),
    )


@router.delete(
    "/playlists/{name}/channels/{channel}",
    response_model=PlaylistDetail,
    summary="Remove channel or entry",
)
def delete_channel(name: str, channel: str) -> PlaylistDetail:
    return detail(name, m3u.remove_channel(name, channel))
