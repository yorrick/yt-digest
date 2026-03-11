# yt_digest/models.py
from datetime import datetime
from pydantic import BaseModel, computed_field


class ChannelInfo(BaseModel):
    name: str
    youtube_handle: str
    channel_id: str
    active: bool = True

    @computed_field
    @property
    def rss_url(self) -> str:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={self.channel_id}"


class VideoInfo(BaseModel):
    video_id: str
    channel_pk: int
    title: str
    published_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class VideoSummary(BaseModel):
    video_id: str
    title: str
    url: str
    summary: str
    summarizer: str
    channel_name: str


class ClusterGroup(BaseModel):
    name: str
    video_indices: list[int]


class ClusterResult(BaseModel):
    clusters: list[ClusterGroup]
