const { useEffect, useMemo, useState } = React;

    const signals = [
      {
        id: 1,
        symbol: "WTI",
        direction: "bullish",
        directionLabel: "看多",
        author: "qinbafrank",
        time: "18 分钟前",
        category: "宏观观点",
        title: "原油供应风险重新计价，80 美元成为短期观察位",
        summary: "霍尔木兹海峡重开节奏再次变得不清晰，市场开始重新计入供应中断持续更久的可能性。",
        thesis: "核心变化不在于冲突是否升级，而在于恢复通航的时间路径再次失去确定性。油价与美债收益率的同步抬升，可能继续压制风险资产。",
        evidence: "海峡没那么快重开……更可能持续僵持，直到一方在国内或外部压力下让步。",
        assetName: "WTI 原油连续合约",
        identity: "商品 · 已核验",
        evidenceCount: 3,
        imageCount: 1,
        points: ["关注 80 美元上方能否连续站稳", "观察供应风险是否继续传导至美债收益率", "若出现明确通航协议，当前判断可能快速失效"]
      },
      {
        id: 2,
        symbol: "NVDA",
        direction: "bullish",
        directionLabel: "看多",
        author: "marketmemo",
        time: "46 分钟前",
        category: "公司观点",
        title: "AI 资本开支预期仍在抬升，但估值分歧同步扩大",
        summary: "博主维持中期看好，同时强调短期上涨空间越来越依赖下一轮盈利预期上修。",
        thesis: "方向仍偏积极，但这不是无条件推荐。接下来的关键证据是大型云厂商资本开支指引，而不是单纯的价格动量。",
        evidence: "只要资本开支没有下修，产业趋势就没有改变；真正需要警惕的是预期先于盈利跑得太远。",
        assetName: "NVIDIA Corporation",
        identity: "美股 · 已核验",
        evidenceCount: 2,
        imageCount: 0,
        points: ["等待下一轮资本开支指引", "区分产业趋势与短期估值风险", "观点期限为中期，不适合作为日内信号"]
      },
      {
        id: 3,
        symbol: "0700.HK",
        direction: "neutral",
        directionLabel: "观察",
        author: "hkfocus",
        time: "1 小时前",
        category: "资金观察",
        title: "资金回流迹象出现，但暂不足以确认趋势反转",
        summary: "连续两日的资金流改善提供了积极信号，博主仍将其定义为观察条件而不是买入建议。",
        thesis: "这是一个待确认信号。只有资金流改善与盈利预期同时发生，才足以把当前状态从观察升级为看多。",
        evidence: "两天的流入只能说明情绪回暖，不能证明趋势已经扭转，下一步看盈利预期是否跟上。",
        assetName: "腾讯控股有限公司",
        identity: "港股 · 已核验",
        evidenceCount: 2,
        imageCount: 1,
        points: ["当前不创建可验证预测", "继续观察盈利预期变化", "避免把资金流单因素解读为明确推荐"]
      },
      {
        id: 4,
        symbol: "BTC",
        direction: "bearish",
        directionLabel: "谨慎",
        author: "chainbrief",
        time: "2 小时前",
        category: "风险提示",
        title: "短期杠杆重新堆积，价格上行与风险同步增加",
        summary: "链上与交易所数据出现分歧，博主提示不要把突破本身理解为风险下降。",
        thesis: "短期价格方向可能继续向上，但杠杆增加意味着回撤幅度也会放大。该观点被识别为风险提示，而非做空推荐。",
        evidence: "突破之后未平仓合约增长更快，这不是看空理由，但意味着追高的容错率正在下降。",
        assetName: "Bitcoin",
        identity: "加密货币 · 已核验",
        evidenceCount: 4,
        imageCount: 2,
        points: ["风险提示不等于方向预测", "关注资金费率与未平仓合约", "下游不会计入博主预测命中率"]
      }
    ];

    const sources = [
      {
        id: "qinbafrank", initials: "QF", name: "秦爸 Frank", handle: "qinbafrank",
        focus: ["宏观", "原油", "美股"], status: "采集中", update: "18 分钟前",
        bio: "长期跟踪全球宏观、能源供需与风险资产之间的传导关系。",
        collected: 18, relevant: 72, quality: "样本积累中",
        latest: "原油供应风险重新计价，80 美元成为短期观察位",
        latestType: "观点 · WTI · 看多", fetch: "每 30 分钟"
      },
      {
        id: "marketmemo", initials: "MM", name: "Market Memo", handle: "marketmemo",
        focus: ["美股", "科技", "AI"], status: "采集中", update: "46 分钟前",
        bio: "关注科技公司基本面、资本开支与估值预期差。",
        collected: 9, relevant: 81, quality: "样本积累中",
        latest: "AI 资本开支预期仍在抬升，但估值分歧同步扩大",
        latestType: "观点 · NVDA · 看多", fetch: "每 60 分钟"
      },
      {
        id: "hkfocus", initials: "HF", name: "HK Focus", handle: "hkfocus",
        focus: ["港股", "中概", "资金流"], status: "采集中", update: "1 小时前",
        bio: "观察港股资金流、盈利预期变化与中概股风险偏好。",
        collected: 7, relevant: 64, quality: "数据不足",
        latest: "资金回流迹象出现，但暂不足以确认趋势反转",
        latestType: "观察 · 0700.HK", fetch: "每 60 分钟"
      },
      {
        id: "chainbrief", initials: "CB", name: "Chain Brief", handle: "chainbrief",
        focus: ["加密货币", "链上数据"], status: "已暂停", update: "昨天",
        bio: "通过交易所与链上指标跟踪加密市场杠杆和流动性。",
        collected: 5, relevant: 76, quality: "数据不足",
        latest: "短期杠杆重新堆积，价格上行与风险同步增加",
        latestType: "风险 · BTC", fetch: "已暂停"
      }
    ];

    const watchlist = [
      {
        id: "wti", symbol: "WTI", type: "原油", stance: "偏多", tone: "bullish",
        headline: "供应风险重新成为主导变量",
        detail: "3 位关注博主提及，2 位偏多，1 位强调事件风险。",
        activity: "3 条更新", time: "今天", change: "观点升温",
        positive: 67, neutral: 33, negative: 0,
        authors: ["QF", "MM", "HF"],
        thesis: "过去 24 小时，关注博主从“等待通航进展”转向“供应中断可能持续更久”。共识明显升温，但仍高度依赖事件路径。",
        timeline: [
          ["18 分钟前", "@qinbafrank", "恢复通航时间再次失去确定性，维持短期看多。"],
          ["3 小时前", "@marketmemo", "油价与收益率联动可能继续压制风险资产。"],
          ["昨天", "@hkfocus", "若谈判出现明确进展，风险溢价可能快速回吐。"]
        ]
      },
      {
        id: "nvda", symbol: "NVDA", type: "美股", stance: "偏多", tone: "bullish",
        headline: "中期偏多，短期估值分歧扩大",
        detail: "2 位关注博主观点一致，尚无明确价格目标。",
        activity: "2 条更新", time: "今天", change: "方向稳定",
        positive: 74, neutral: 26, negative: 0,
        authors: ["MM", "QF"],
        thesis: "博主共识仍是产业趋势未变，但短期上涨越来越依赖盈利预期继续上修。当前更适合跟踪条件，而不是直接给出买卖结论。",
        timeline: [
          ["46 分钟前", "@marketmemo", "资本开支没有下修，产业趋势仍然成立。"],
          ["昨天", "@qinbafrank", "估值风险上升，但暂未形成方向反转证据。"]
        ]
      },
      {
        id: "tencent", symbol: "0700.HK", type: "港股", stance: "观察", tone: "neutral",
        headline: "资金改善，但趋势尚未确认",
        detail: "目前只有单一来源观点，不形成共识判断。",
        activity: "1 条更新", time: "今天", change: "新出现",
        positive: 38, neutral: 62, negative: 0,
        authors: ["HF"],
        thesis: "资金流改善是值得观察的新信号，但来源和证据都不足。系统不会把它升级为明确推荐或可验证预测。",
        timeline: [
          ["1 小时前", "@hkfocus", "两天流入说明情绪回暖，暂不能证明趋势反转。"]
        ]
      },
      {
        id: "btc", symbol: "BTC", type: "加密", stance: "分歧", tone: "bearish",
        headline: "价格方向与杠杆风险出现分歧",
        detail: "2 位偏多，2 位提示风险，观点差异正在扩大。",
        activity: "4 条更新", time: "6 小时内", change: "分歧扩大",
        positive: 45, neutral: 10, negative: 45,
        authors: ["CB", "MM", "QF"],
        thesis: "价格强势没有消失，但杠杆堆积使追高容错率下降。该状态更适合定义为风险升高，而不是直接转为空头判断。",
        timeline: [
          ["2 小时前", "@chainbrief", "突破后未平仓合约增长更快，回撤风险放大。"],
          ["5 小时前", "@marketmemo", "趋势仍向上，但应降低单次风险暴露。"]
        ]
      }
    ];

    const iconPaths = {
      today: <><path d="M4 5h16v15H4z"></path><path d="M8 3v4M16 3v4M4 10h16"></path></>,
      sources: <><circle cx="12" cy="8" r="3"></circle><path d="M5 20a7 7 0 0 1 14 0"></path></>,
      watch: <><path d="M4 19V9m6 10V5m6 14v-7m5 7H3"></path></>,
      assistant: <><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 5 5M10.5 7v7m-3.5-3.5h7"></path></>,
      search: <><circle cx="11" cy="11" r="7"></circle><path d="m16 16 5 5"></path></>,
      plus: <><path d="M12 5v14M5 12h14"></path></>,
      bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"></path></>,
      arrow: <><path d="m9 18 6-6-6-6"></path></>,
      close: <><path d="m6 6 12 12M18 6 6 18"></path></>,
      evidence: <><path d="M5 4h14v16H5z"></path><path d="M8 8h8M8 12h8M8 16h5"></path></>,
      check: <><circle cx="12" cy="12" r="9"></circle><path d="m8 12 2.5 2.5L16 9"></path></>,
      image: <><rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="m7 16 4-4 3 3 2-2 2 3M8.5 9h.01"></path></>,
      send: <><path d="m3 3 18 9-18 9 4-9z"></path><path d="M7 12h14"></path></>
    };

    function Icon({ name, size = 18 }) {
      return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]}</svg>;
    }

Object.assign(window, { signals, sources, watchlist, Icon });

