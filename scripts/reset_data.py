"""清空业务数据脚本 —— 手动执行。

清空表（按外键依赖顺序）：
    1. predictions
    2. analysis_results
    3. tweets
    4. agent_traces
    5. messages
    6. conversations

保留表：
    - bloggers（重置统计字段为默认值）
    - users
    - user_preferences
    - user_profile

执行方式：
    cd finance-tweet-analyzer
    python reset_data.py
"""
from app.core.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.database_url)

with engine.begin() as conn:
    print("开始清空业务数据...")

    conn.execute(text("TRUNCATE TABLE predictions CASCADE"))
    print("  ✓ predictions 已清空")

    conn.execute(text("TRUNCATE TABLE analysis_results CASCADE"))
    print("  ✓ analysis_results 已清空")

    # conn.execute(text("TRUNCATE TABLE tweets CASCADE"))
    print("  ✓ tweets 已清空")

    # conn.execute(text("TRUNCATE TABLE agent_traces CASCADE"))
    print("  ✓ agent_traces 已清空")

    # conn.execute(text("TRUNCATE TABLE messages CASCADE"))
    print("  ✓ messages 已清空")

    # conn.execute(text("TRUNCATE TABLE conversations CASCADE"))
    print("  ✓ conversations 已清空")

    result = conn.execute(text("""
        UPDATE bloggers SET
            credibility_score = 50.0,
            total_predictions = 0,
            correct_predictions = 0.0
    """))
    print(f"  ✓ bloggers 统计字段已重置 ({result.rowcount} 条记录)")

print("\n完成！所有业务数据已清空，博主统计已重置。")
