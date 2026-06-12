from datetime import datetime

from pydantic import BaseModel, model_validator

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
