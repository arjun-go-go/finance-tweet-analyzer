const { useEffect, useMemo, useState } = React;

function MediaViewerV5({ onClose }) {
  const [active, setActive] = useState(0);
  const media = [
    { label: "价格图表", title: "WTI 突破 80 美元并站上短期均线", ocr: "WTI / 80.12 / MA50 79.46", relation: "支持正文判断", confidence: "高" },
    { label: "航运示意", title: "图片强调霍尔木兹海峡的供应路径", ocr: "Strait of Hormuz / Oil supply route", relation: "补充事件背景", confidence: "中" },
    { label: "新闻截图", title: "谈判仍存在条件分歧，未出现明确开放日期", ocr: "No confirmed reopening timeline", relation: "支持时间不确定性", confidence: "中" }
  ];
  const current = media[active];
  return <div className="system-backdrop media-backdrop-v5" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <section className="media-viewer-v5" role="dialog" aria-label="图片证据查看器">
      <header><div><p className="eyebrow">Media evidence</p><h2>图片证据</h2><span>{active + 1} / {media.length} · 来自原推文</span></div><button className="detail-close" onClick={onClose} aria-label="关闭图片证据"><Icon name="close" size={18} /></button></header>
      <div className="media-viewer-layout-v5">
        <div className="media-canvas-wrap-v5">
          <div className={"media-canvas-v5 media-canvas-" + active}><span className="media-grid-v5"></span><strong>{active === 0 ? "WTI · PRICE CONTEXT" : active === 1 ? "SUPPLY ROUTE" : "EVENT UPDATE"}</strong><i></i><small>原始图片预览 · 未裁剪</small></div>
          <div className="media-thumbs-v5">{media.map(function(item,index){ return <button key={item.label} className={active === index ? "active" : ""} onClick={function(){ setActive(index); }}><span className={"thumb-art-v5 thumb-" + index}></span><strong>{item.label}</strong></button>; })}</div>
        </div>
        <aside className="media-analysis-v5">
          <span>视觉分析结论</span><h3>{current.title}</h3>
          <div className="media-fact-v5"><span>OCR 识别</span><strong>{current.ocr}</strong></div>
          <div className="media-fact-v5"><span>与正文关系</span><strong>{current.relation}</strong></div>
          <div className="media-fact-v5"><span>识别置信度</span><strong>{current.confidence}</strong></div>
          <div className="media-warning-v5"><Icon name="check" size={15} /><p>未发现图片与正文方向冲突。图片只作为补充证据，不单独生成投资结论。</p></div>
          <button className="quiet-button" onClick={onClose}>返回完整分析</button>
        </aside>
      </div>
    </section>
  </div>;
}

function CorrectionSheetV5({ onClose, onSubmit }) {
  const [issue, setIssue] = useState("标的身份");
  const [choice, setChoice] = useState("WTI 原油");
  const issues = ["标的身份", "观点方向", "观点归属", "图片解读", "其他"];
  const choices = issue === "标的身份" ? ["WTI 原油", "CL 原油期货", "不是投资标的"]
    : issue === "观点方向" ? ["看多", "观察", "看空", "没有明确方向"]
    : issue === "观点归属" ? ["博主本人", "引用他人", "转述新闻"]
    : ["结论不准确", "遗漏关键信息", "图片与正文无关"];
  useEffect(function(){ setChoice(choices[0]); }, [issue]);
  return <div className="notification-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <aside className="correction-sheet-v5" aria-label="反馈识别错误">
      <header><div><p className="eyebrow">Improve recognition</p><h2>哪里识别有误？</h2><span>反馈不会直接改写结果，会进入复核记录。</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      <section><span className="field-label">问题类型</span><div className="correction-issues-v5">{issues.map(function(item){ return <button className={issue === item ? "active" : ""} key={item} onClick={function(){ setIssue(item); }}>{item}</button>; })}</div></section>
      <section><span className="field-label">你认为正确的是</span><div className="correction-options-v5">{choices.map(function(item){ return <button className={choice === item ? "active" : ""} key={item} onClick={function(){ setChoice(item); }}><span className="radio-v4"></span><strong>{item}</strong></button>; })}</div></section>
      <label className="correction-note-v5"><span>补充说明（可选）</span><textarea placeholder="告诉我们判断依据，便于复核。"></textarea></label>
      <footer><button className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" onClick={function(){ onSubmit(issue + "反馈已提交"); }}>提交反馈</button></footer>
    </aside>
  </div>;
}

function InsightDetailPageV5({ item, onBack, onAsk, onOpenProfile, onToast }) {
  const [showMedia, setShowMedia] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const fullText = item.symbol === "WTI"
    ? "昨晚市场走弱的核心驱动，仍是霍尔木兹海峡短期内难以重新全面开放的担忧。市场对供应中断的风险定价重新回升，油价突破 80 美元，并带动美债收益率同步上行。更可能的路径是持续僵持，直到一方在国内或外部压力下让步，或达成有限妥协。"
    : item.summary + " " + item.evidence;
  function submitCorrection(message) { setShowCorrection(false); onToast(message + "，我们会保留审计记录"); }
  return <>
    <main className="page" data-screen-label="情报详情增强版">
      <div className="deep-page">
        <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回今日</button>
        <div className="deep-layout">
          <article className="deep-main">
            <header className="deep-hero">
              <div className="hero-tags"><span className={"direction " + item.direction}>{item.directionLabel}</span><span>{item.category}</span><span>·</span><span>{item.time}</span><span className="verified"><Icon name="check" size={12} /> 标的已核验</span></div>
              <h1>{item.title}</h1><p className="hero-summary">{item.summary}</p>
              <button className="origin-line origin-button-v5" onClick={onOpenProfile}><span className="source-avatar">{item.author.slice(0,2).toUpperCase()}</span><div><strong>@{item.author}</strong><span>博主本人观点 · 已完成上下文归属</span></div><Icon name="arrow" size={16} /></button>
            </header>
            <section className="truth-banner"><span>核心判断</span><p>{item.thesis}</p></section>

            <section className="analysis-section">
              <div className="section-heading-v3"><h2>上下文与观点归属</h2><span>避免把引用内容算作博主观点</span></div>
              <div className="context-chain-v5">
                <article><span className="context-index-v5">01</span><div><small>引用的外部信息</small><strong>谈判接近最终阶段，但重开仍取决于条件交换</strong><p>系统保留引用来源，不把这句话视为博主预测。</p></div><span className="context-badge-v5">引用</span></article>
                <article className="active"><span className="context-index-v5">02</span><div><small>博主自己的判断</small><strong>海峡不会快速重开，供应风险可能持续更久</strong><p>第一人称判断与后续解释一致，归属为博主本人。</p></div><span className="context-badge-v5 verified">已归属</span></article>
                <article><span className="context-index-v5">03</span><div><small>系统提取</small><strong>{item.symbol} · {item.directionLabel} · 事件驱动 · 短期</strong><p>只有这一步进入观点聚合与后续验证。</p></div><span className="context-badge-v5">结构化</span></article>
              </div>
            </section>

            <section className="analysis-section">
              <div className="section-heading-v3"><h2>原推文与图片证据</h2><span>文本、图片和 Thread 联合分析</span></div>
              <article className="tweet-paper">
                <div className="tweet-paper-head"><span className="source-avatar">{item.author.slice(0,2).toUpperCase()}</span><div><strong>@{item.author}</strong><span>Twitter/X 原文 · Thread 第 3/4 条</span></div><small>{item.time}</small></div>
                <p>{fullText}</p>
                {item.imageCount > 0 && <div className="media-grid-v5">{[0,1,2].map(function(index){ return <button key={index} className={"media-tile-v5 media-tile-" + index} onClick={function(){ setShowMedia(true); }}><span></span><small>{index === 0 ? "价格图表" : index === 1 ? "航运示意" : "新闻截图"}</small></button>; })}</div>}
                <button className="media-summary-v5" onClick={function(){ setShowMedia(true); }}><Icon name="image" size={15} /><span><strong>3 张图片已联合分析</strong>图文方向一致，其中 2 张提供独立补充信息。</span><Icon name="arrow" size={16} /></button>
              </article>
            </section>

            <section className="analysis-section">
              <div className="section-heading-v3"><h2>判断边界</h2><span>不是无条件推荐</span></div>
              <div className="split-analysis"><div className="analysis-box"><span>可能强化判断</span><ul><li>供应中断预期继续升温</li><li>价格在关键观察位上方保持强势</li><li>更多独立来源出现一致证据</li></ul></div><div className="analysis-box risk"><span>可能使判断失效</span><ul><li>出现明确并可执行的通航协议</li><li>风险溢价快速回吐</li><li>博主明确撤回或反转观点</li></ul></div></div>
            </section>

            <section className="analysis-section verification-section-v5">
              <div className="section-heading-v3"><h2>核验记录</h2><button onClick={function(){ setShowCorrection(true); }}>识别有误？</button></div>
              <div className="verification-stack"><div className="verification-row"><span>观点归属</span><strong>博主本人陈述，不是转述或引用</strong><b>已确认</b></div><div className="verification-row"><span>标的身份</span><strong>{item.assetName}</strong><b>已核验</b></div><div className="verification-row"><span>文本与图片</span><strong>方向一致，图片作为补充证据</strong><b>一致</b></div><div className="verification-row"><span>分析版本</span><strong>v3 · 2026年8月26日 12:18</strong><b>可追溯</b></div></div>
            </section>
          </article>
          <aside className="deep-aside">
            <section className="aside-card-v3"><span>跟踪对象</span><h3>{item.symbol}</h3><p>{item.assetName}</p><div className="aside-facts"><div>方向<strong>{item.directionLabel}</strong></div><div>观点类型<strong>{item.category}</strong></div><div>证据数量<strong>6 条</strong></div><div>更新时间<strong>{item.time}</strong></div></div></section>
            <section className="aside-card-v3 trust-card-v5"><span>可信状态</span><div><Icon name="check" size={17} /><strong>可用于回答与聚合</strong></div><p>作者归属、标的身份与图文关系均已完成核验。</p></section>
            <div className="deep-aside-actions"><button className="quiet-button" onClick={function(){ onToast("原推文链接已准备打开（原型）"); }}>查看原推文</button><button className="primary-button" onClick={onAsk}>向助手追问</button></div>
          </aside>
        </div>
      </div>
    </main>
    {showMedia && <MediaViewerV5 onClose={function(){ setShowMedia(false); }} />}
    {showCorrection && <CorrectionSheetV5 onClose={function(){ setShowCorrection(false); }} onSubmit={submitCorrection} />}
  </>;
}

function AssistantScopeV5({ onClose, onApply }) {
  const [scope, setScope] = useState("关注信息源");
  const [period, setPeriod] = useState("近 30 天");
  return <div className="notification-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <aside className="assistant-scope-sheet-v5" aria-label="设置助手回答范围">
      <header><div><p className="eyebrow">Answer scope</p><h2>回答范围</h2><span>范围越明确，回答越少猜测。</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      <section><span>信息来源</span>{["关注信息源","全部已采集博主","仅 @qinbafrank"].map(function(item){ return <button className={scope === item ? "active" : ""} key={item} onClick={function(){ setScope(item); }}><span className="radio-v4"></span><strong>{item}</strong></button>; })}</section>
      <section><span>时间范围</span><div className="scope-chips-v5">{["24 小时","近 7 天","近 30 天","全部"].map(function(item){ return <button className={period === item ? "active" : ""} key={item} onClick={function(){ setPeriod(item); }}>{item}</button>; })}</div></section>
      <section><span>内容类型</span><div className="scope-checks-v5"><button className="active"><Icon name="check" size={14} />原推文</button><button className="active"><Icon name="check" size={14} />图片分析</button><button className="active"><Icon name="check" size={14} />历史验证</button></div></section>
      <footer><button className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" onClick={function(){ onApply(scope + " · " + period); }}>应用范围</button></footer>
    </aside>
  </div>;
}

function EvidenceDrawerV5({ kind, onClose, onOpenInsight }) {
  return <div className="notification-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <aside className="evidence-drawer-v5" aria-label="回答证据">
      <header><div><p className="eyebrow">Answer evidence</p><h2>{kind === "image" ? "图片分析证据" : "原推文证据"}</h2><span>回答中的每个判断都应能回到这里。</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      {kind === "image" ? <><div className="evidence-image-v5"><span></span><strong>WTI · PRICE CONTEXT</strong></div><section className="evidence-copy-v5"><span>视觉结论</span><h3>图表显示油价突破 80 美元并站上 50 日均线</h3><p>该图片支持正文中的价格观察，但不能单独证明供应风险会持续。</p></section></> : <><blockquote className="drawer-quote-v5">“海峡没那么快重开……更可能持续僵持，直到一方在国内或外部压力下让步。”</blockquote><section className="evidence-copy-v5"><span>为什么被引用</span><h3>直接支持“恢复通航时间重新失去确定性”</h3><p>作者归属已确认；上下文中没有否定或反讽表达。</p></section></>}
      <div className="evidence-meta-v5"><span>@qinbafrank</span><span>18 分钟前</span><span>标的已核验</span></div>
      <footer><button className="quiet-button" onClick={onClose}>返回回答</button><button className="primary-button" onClick={onOpenInsight}>查看完整分析</button></footer>
    </aside>
  </div>;
}

function AssistantPageV5({ onOpenInsight }) {
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("今天原油观点有什么变化？");
  const [mode, setMode] = useState("answer");
  const [scope, setScope] = useState("关注信息源 · 近 30 天");
  const [showScope, setShowScope] = useState(false);
  const [evidence, setEvidence] = useState(null);
  const suggestions = ["这和我的美股关注有什么关系？", "哪些条件会让判断失效？", "SpaceZ 最近有什么观点？"];
  function submit(value) {
    const next = (value || draft).trim();
    if (!next) return;
    setQuestion(next); setDraft(""); setMode("loading");
    window.setTimeout(function(){
      if (next.toLowerCase().includes("spacez")) setMode("noEvidence");
      else if (next.includes("失败")) setMode("error");
      else setMode("answer");
    }, 620);
  }
  return <>
    <main className="page" data-screen-label="研究助手增强版">
      <section className="assistant-page-v2 assistant-v5">
        <header className="assistant-header-v2"><div><p className="eyebrow">Evidence-grounded assistant</p><h1>助手</h1></div><div className="assistant-head-actions-v5"><button className="quiet-button new-chat-v5" onClick={function(){ setMode("empty"); setQuestion(""); }}>新对话</button><button className="assistant-scope" onClick={function(){ setShowScope(true); }}><Icon name="sources" size={14} /><span>回答范围</span><strong>{scope.split(" · ")[0]}</strong></button></div></header>
        <div className="chat-context">当前使用 <span>{scope}</span><span>文本 + 图片</span><span>仅已核验证据</span></div>

        {mode === "empty" && <div className="assistant-empty-v5"><span className="assistant-orb"><Icon name="assistant" size={20} /></span><h2>你想从关注博主中了解什么？</h2><p>可以问观点变化、原文依据、标的共识或预测结果。</p><div className="prompts-v5">{suggestions.slice(0,2).map(function(item){ return <button key={item} onClick={function(){ submit(item); }}>{item}</button>; })}</div></div>}

        {mode !== "empty" && <div className="conversation-v2">
          <div className="user-question">{question}</div>
          {mode === "loading" && <article className="assistant-loading-v5"><div className="answer-label"><span className="assistant-orb"><Icon name="assistant" size={14} /></span>正在组织证据</div><div className="loading-steps-v5"><span className="done"><Icon name="check" size={14} />检索关注博主内容</span><span className="done"><Icon name="check" size={14} />核对标的与作者归属</span><span className="active"><i></i>比较观点变化与图片证据</span></div><small>你可以继续浏览，回答会自动出现。</small></article>}
          {mode === "answer" && <article className="assistant-response">
            <div className="answer-label"><span className="assistant-orb" style={{margin:0,width:28,height:28}}><Icon name="assistant" size={14} /></span>基于 3 条已核验证据</div>
            <h2>关注博主对原油的判断从“等待确认”转向“供应风险可能持续更久”。</h2>
            <p>主要变化不是冲突是否升级，而是霍尔木兹海峡恢复通航的时间再次失去确定性。整体观点偏多，但仍属于事件驱动判断，并非无条件推荐。</p>
            <ul className="answer-points"><li><b>1</b><span>@qinbafrank 维持短期看多，观察位在 80 美元附近。</span></li><li><b>2</b><span>油价与美债收益率同步上行，可能继续压制风险资产。</span></li><li><b>3</b><span>若出现明确通航协议，当前风险溢价可能快速回吐。</span></li></ul>
            <div className="citation-list"><button className="citation-card" onClick={function(){ setEvidence("tweet"); }}><span>证据 1 · 原推文</span><strong>“海峡没那么快重开……更可能持续僵持。”</strong><small>@qinbafrank · 18 分钟前</small></button><button className="citation-card" onClick={function(){ setEvidence("image"); }}><span>证据 2 · 图片分析</span><strong>图表显示油价突破 80 美元并站上短期均线。</strong><small>图片与正文方向一致</small></button></div>
            <div className="answer-confidence-v5"><Icon name="check" size={14} /><span>证据覆盖充分</span><small>未使用公开网页或关注范围外内容</small></div>
            <div className="follow-up">{suggestions.map(function(item){ return <button key={item} onClick={function(){ submit(item); }}>{item}</button>; })}</div>
          </article>}
          {mode === "noEvidence" && <article className="assistant-state-v5 no-evidence-v5"><span className="state-symbol-v5">?</span><h2>当前证据不足，无法回答</h2><p>在“{scope}”范围内，没有找到 SpaceZ 的已采集内容。助手不会用同名公司或公开网页补全答案。</p><div><button className="quiet-button" onClick={function(){ setShowScope(true); }}>扩大回答范围</button><button className="primary-button" onClick={function(){ setMode("empty"); setQuestion(""); }}>换个问题</button></div></article>}
          {mode === "error" && <article className="assistant-state-v5 error-state-v5"><span className="state-symbol-v5">!</span><h2>回答暂时生成失败</h2><p>已找到 3 条证据，但模型服务暂时不可用。证据和对话没有丢失。</p><div><button className="quiet-button" onClick={function(){ setMode("empty"); }}>取消</button><button className="primary-button" onClick={function(){ submit(question); }}>重新生成</button></div></article>}
        </div>}

        <form className="composer-v2" onSubmit={function(event){ event.preventDefault(); submit(); }}><div className="composer-input-row"><input value={draft} onChange={function(event){ setDraft(event.target.value); }} placeholder="追问博主观点、标的变化或原文依据…" /><button className="composer-send" aria-label="发送"><Icon name="send" size={17} /></button></div><div className="composer-meta"><span>仅基于已采集证据</span> · 找不到依据时明确说明</div></form>
      </section>
    </main>
    {showScope && <AssistantScopeV5 onClose={function(){ setShowScope(false); }} onApply={function(next){ setScope(next); setShowScope(false); }} />}
    {evidence && <EvidenceDrawerV5 kind={evidence} onClose={function(){ setEvidence(null); }} onOpenInsight={function(){ setEvidence(null); onOpenInsight(); }} />}
  </>;
}

const predictionStatesV5 = {
  completed: { label: "验证完成", title: "未命中", tone: "incorrect", mark: "×", summary: "验证窗口结束时，价格相对起始价下跌 2.1%，不满足短期看多规则。", stat: "计入历史结果" },
  pending: { label: "等待验证", title: "还剩 29 天", tone: "pending", mark: "29", summary: "中期验证窗口尚未结束。系统会在完整交易日数据成熟后自动判定。", stat: "暂不计入命中率" },
  excluded: { label: "规则排除", title: "不计入统计", tone: "excluded", mark: "—", summary: "原文表达的是宏观风险观察，没有足够明确的价格方向，因此不创建有效预测。", stat: "保留审计记录" },
  corrected: { label: "人工修正", title: "修正后待验证", tone: "corrected", mark: "↺", summary: "系统最初把 CL 识别为同名股票；复核后修正为 WTI 原油期货，并重新建立验证窗口。", stat: "使用修正后身份" }
};

function PredictionDetailPageV5({ onBack, onOpenProfile, onToast }) {
  const [status, setStatus] = useState("completed");
  const state = predictionStatesV5[status];
  return <main className="page" data-screen-label="预测验证全状态">
    <div className="deep-page">
      <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回历史验证</button>
      <div className="prototype-state-bar-v5"><span>原型状态预览</span><div>{Object.entries(predictionStatesV5).map(function(entry){ return <button className={status === entry[0] ? "active" : ""} key={entry[0]} onClick={function(){ setStatus(entry[0]); }}>{entry[1].label}</button>; })}</div></div>
      <div className="deep-layout">
        <article className="deep-main">
          <header className="prediction-hero-v4"><div className="hero-tags"><span className="direction bullish">看多</span><span>{status === "pending" ? "中期" : "短期"}</span><span>·</span><span>@qinbafrank</span></div><h1>{status === "excluded" ? "油价上涨可能继续压制风险资产" : "WTI 供应风险可能推动价格继续走高"}</h1><p>发布于 2026年8月11日 · {state.label}</p></header>
          <section className={"prediction-verdict-v4 prediction-verdict-v5 " + state.tone}><span className="verdict-mark-v4">{state.mark}</span><div><span>{state.label}</span><h2>{state.title}</h2><p>{state.summary}</p></div></section>

          {status === "completed" && <section className="analysis-section"><div className="section-heading-v3"><h2>行情路径</h2><span>使用完整日线</span></div><div className="price-path-v4"><div className="price-path-head-v4"><div><span>起始价</span><strong>$79.84</strong><small>8月12日开盘后</small></div><div><span>验证价</span><strong>$78.16</strong><small>8月18日收盘</small></div><div><span>区间变化</span><strong className="negative-value-v4">−2.1%</strong><small>低于判定阈值</small></div></div><div className="price-chart-v4"><span className="price-chart-line-v4"></span><i className="chart-start-v4">79.84</i><i className="chart-end-v4">78.16</i></div></div></section>}
          {status === "pending" && <section className="analysis-section"><div className="section-heading-v3"><h2>验证进度</h2><span>中期 · 30 个交易日</span></div><div className="prediction-progress-v5"><div><strong>1 / 30</strong><span>已完成交易日</span></div><span><i style={{width:"3.3%"}}></i></span><p>预计 9月22日后可验证。期间不会用盘中价格提前判定。</p></div></section>}
          {status === "excluded" && <section className="analysis-section"><div className="section-heading-v3"><h2>为什么被排除</h2><span>规则可解释</span></div><div className="exclusion-reasons-v5"><div><Icon name="check" size={15} /><span><strong>作者归属明确</strong><small>确认为博主本人表达</small></span></div><div className="failed"><b>×</b><span><strong>方向不够明确</strong><small>讨论风险传导，不等于看空美股</small></span></div><div><Icon name="check" size={15} /><span><strong>原文仍会保留</strong><small>可用于情报阅读，但不进入命中率</small></span></div></div></section>}
          {status === "corrected" && <section className="analysis-section"><div className="section-heading-v3"><h2>修正内容</h2><span>原记录不会覆盖</span></div><div className="correction-diff-v5"><div><span>系统原识别</span><strong>CL · Colgate-Palmolive 股票</strong><small>同名代码导致错误匹配</small></div><Icon name="arrow" size={20} /><div className="correct"><span>复核后</span><strong>CL · WTI 原油期货</strong><small>结合全文语义与商品身份修正</small></div></div></section>}

          <section className="analysis-section"><div className="section-heading-v3"><h2>判定规则</h2><span>每一步可回溯</span></div><div className="rule-steps-v4"><div><b>1</b><span><strong>确认观点归属</strong><small>博主本人表达，不是引用</small></span></div><div><b>2</b><span><strong>核验标的与方向</strong><small>{status === "excluded" ? "标的明确，但方向不满足要求" : "WTI 原油 · 看多"}</small></span></div><div><b>3</b><span><strong>建立验证窗口</strong><small>{status === "pending" ? "30 个完整交易日" : status === "excluded" ? "未建立" : "5 个完整交易日"}</small></span></div><div><b>4</b><span><strong>写入统计</strong><small>{state.stat}</small></span></div></div></section>
          <section className="analysis-section"><div className="section-heading-v3"><h2>审计记录</h2><span>所有变更均保留</span></div><div className="audit-record-v4"><div><time>8月11日 21:04</time><p>从推文创建候选预测并保存分析版本。</p></div>{status === "corrected" && <div><time>8月11日 22:16</time><p>管理员修正同名标的身份，原识别结果保留。</p></div>}<div><time>{status === "completed" ? "8月18日 16:31" : "当前"}</time><p>{status === "completed" ? "行情窗口成熟，结果写入博主统计。" : status === "excluded" ? "因方向不明确被规则排除。" : status === "pending" ? "等待验证窗口结束。" : "使用修正后的商品身份重新等待验证。"}</p></div></div></section>
        </article>
        <aside className="deep-aside">
          <section className="aside-card-v3"><span>预测身份</span><div className="aside-facts"><div>标的<strong>{status === "corrected" ? "CL 原油" : "WTI 原油"}</strong></div><div>方向<strong>{status === "excluded" ? "不明确" : "看多"}</strong></div><div>期限<strong>{status === "pending" ? "中期" : "短期"}</strong></div><div>状态<strong>{state.label}</strong></div></div></section>
          <section className="aside-card-v3"><span>统计影响</span><h3>{state.stat}</h3><p>{status === "completed" ? "满足归属、方向、期限和标的要求。" : "状态成熟或满足规则后才会进入博主统计。"}</p></section>
          <div className="deep-aside-actions"><button className="quiet-button" onClick={function(){ onToast("原推文链接已准备打开（原型）"); }}>查看原推文</button><button className="primary-button" onClick={onOpenProfile}>查看博主档案</button></div>
        </aside>
      </div>
    </div>
  </main>;
}

Object.assign(window, {
  MediaViewerV5,
  CorrectionSheetV5,
  InsightDetailPageV5,
  AssistantScopeV5,
  EvidenceDrawerV5,
  AssistantPageV5,
  PredictionDetailPageV5
});
