"""Seed sample tweet data for development and demo."""
import httpx

SAMPLE_TWEETS = [
    {
        "tweet_id": "seed_001",
        "author_handle": "@btc_master",
        "author_name": "BTC大师",
        "content": "BTC突破70000关键阻力位，放量上攻。建议入场69500，目标75000，止损67000。短线波段机会。",
        "published_at": "2026-05-26T08:00:00Z",
        "metrics": {"likes": 1200, "retweets": 350},
    },
    {
        "tweet_id": "seed_002",
        "author_handle": "@eth_whale",
        "author_name": "以太坊巨鲸",
        "content": "ETH/BTC汇率见底反弹，ETH有望补涨。目前3800附近建仓，看4500。",
        "published_at": "2026-05-26T09:15:00Z",
        "metrics": {"likes": 800, "retweets": 200},
    },
    {
        "tweet_id": "seed_003",
        "author_handle": "@stock_tiger",
        "author_name": "美股之虎",
        "content": "NVDA财报超预期，AI算力需求持续爆发。回调到950可以接，中线目标1200。",
        "published_at": "2026-05-26T10:00:00Z",
        "metrics": {"likes": 2000, "retweets": 500},
    },
    {
        "tweet_id": "seed_004",
        "author_handle": "@forex_pro",
        "author_name": "外汇达人",
        "content": "美元指数走弱，非美货币全线反弹。EUR/USD看涨至1.12，当前1.085入场。",
        "published_at": "2026-05-26T11:30:00Z",
        "metrics": {"likes": 600, "retweets": 150},
    },
    {
        "tweet_id": "seed_005",
        "author_handle": "@btc_master",
        "author_name": "BTC大师",
        "content": "今天天气真好，带孩子去公园了。周末愉快！",
        "published_at": "2026-05-26T14:00:00Z",
        "metrics": {"likes": 300, "retweets": 20},
    },
    {
        "tweet_id": "seed_006",
        "author_handle": "@a_share_king",
        "author_name": "A股之王",
        "content": "贵州茅台跌破1600支撑位，短期看空。但长期价值投资者可以在1500附近分批建仓。",
        "published_at": "2026-05-26T09:45:00Z",
        "metrics": {"likes": 1500, "retweets": 400},
    },
    {
        "tweet_id": "seed_007",
        "author_handle": "@crypto_degen",
        "author_name": "加密赌狗",
        "content": "SOL生态太火了！BONK下一个100x！梭哈！",
        "published_at": "2026-05-26T12:00:00Z",
        "metrics": {"likes": 5000, "retweets": 2000},
    },
    {
        "tweet_id": "seed_008",
        "author_handle": "@macro_view",
        "author_name": "宏观视角",
        "content": "美联储6月大概率暂停加息，风险资产短期利好。但通胀粘性依然存在，下半年不确定性大。整体中性偏多。",
        "published_at": "2026-05-26T07:30:00Z",
        "metrics": {"likes": 3000, "retweets": 800},
    },
]

API_BASE = "http://localhost:8000"


def seed():
    response = httpx.post(
        f"{API_BASE}/api/tweets/import",
        json={"tweets": SAMPLE_TWEETS},
        timeout=10,
    )
    print(f"Import result: {response.json()}")

    response = httpx.post(f"{API_BASE}/api/analysis/trigger", timeout=120)
    print(f"Analysis result: {response.json()}")


if __name__ == "__main__":
    seed()
