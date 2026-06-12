from pydantic import BaseModel


class DashboardOverview(BaseModel):
    total_tweets: int
    pending_tweets: int
    analyzed_tweets: int
    total_analyses: int
    total_bloggers: int
    pending_predictions: int = 0
    top_tickers: list[dict]
