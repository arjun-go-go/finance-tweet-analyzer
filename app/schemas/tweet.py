from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.blogger import BloggerProfile


class TweetImportItem(BaseModel):
    tweet_id: str
    author_handle: str
    author_name: str = ""
    content: str
    published_at: datetime
    metrics: dict | None = None
    media_urls: list[dict] | None = None
    raw_json: dict | None = None
    tweet_type: str = "original"
    conversation_tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    quoted_tweet_id: str | None = None
    reposted_tweet_id: str | None = None
    referenced_tweets: list[dict] = Field(default_factory=list)


class TweetImportRequest(BaseModel):
    tweets: list[TweetImportItem]
    blogger: BloggerProfile | None = None

    @model_validator(mode="after")
    def _check_blogger_handle_matches(self) -> "TweetImportRequest":
        if self.blogger is None:
            return self
        for t in self.tweets:
            if t.author_handle != self.blogger.handle:
                raise ValueError(
                    f"tweet author_handle {t.author_handle!r} does not match "
                    f"blogger.handle {self.blogger.handle!r}"
                )
        return self


class TweetImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = []


class TweetMediaItem(BaseModel):
    id: str
    width: int | None = None
    height: int | None = None
    content_type: str | None = None
