const { useState } = React;

function InsightDetailPage({ item, onBack, onAsk }) {
      const fullText = item.symbol === "WTI"
        ? "昨晚市场走弱的核心驱动，仍是霍尔木兹海峡短期内难以重新全面开放的担忧。市场对供应中断的风险定价重新回升，油价突破 80 美元，并带动美债收益率同步上行。更可能的路径是持续僵持，直到一方在国内或外部压力下让步，或达成有限妥协。"
        : item.summary + " " + item.evidence;
      return <main className="page" data-screen-label="情报详情">
        <div className="deep-page">
          <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回今日</button>
          <div className="deep-layout">
            <article className="deep-main">
              <header className="deep-hero">
                <div className="hero-tags"><span className={"direction " + item.direction}>{item.directionLabel}</span><span>{item.category}</span><span>·</span><span>{item.time}</span><span className="verified"><Icon name="check" size={12} /> 标的已核验</span></div>
                <h1>{item.title}</h1>
                <p className="hero-summary">{item.summary}</p>
                <div className="origin-line"><span className="source-avatar">{item.author.slice(0,2).toUpperCase()}</span><div><strong>@{item.author}</strong><span>博主本人观点 · 非引用观点</span></div></div>
              </header>
              <section className="truth-banner"><span>核心判断</span><p>{item.thesis}</p></section>
              <section className="analysis-section">
                <div className="section-heading-v3"><h2>为什么值得关注</h2><span>系统提取 · 可回溯</span></div>
                <ol className="reason-list">{item.points.map(function(point){ return <li key={point}>{point}</li>; })}</ol>
              </section>
              <section className="analysis-section">
                <div className="section-heading-v3"><h2>催化剂与风险边界</h2><span>不是无条件推荐</span></div>
                <div className="split-analysis">
                  <div className="analysis-box"><span>可能强化判断</span><ul><li>供应中断预期继续升温</li><li>价格在关键观察位上方保持强势</li><li>更多独立来源出现一致证据</li></ul></div>
                  <div className="analysis-box risk"><span>可能使判断失效</span><ul><li>出现明确并可执行的通航协议</li><li>风险溢价快速回吐</li><li>博主后续明确撤回或反转观点</li></ul></div>
                </div>
              </section>
              <section className="analysis-section">
                <div className="section-heading-v3"><h2>原推文与图片</h2><span>完整上下文</span></div>
                <article className="tweet-paper">
                  <div className="tweet-paper-head"><span className="source-avatar">{item.author.slice(0,2).toUpperCase()}</span><div><strong>@{item.author}</strong><span>Twitter/X 原文</span></div><small>{item.time}</small></div>
                  <p>{fullText}</p>
                  {item.imageCount > 0 && <><div className="tweet-media"><strong>{item.symbol} · PRICE CONTEXT</strong><span className="chart-line"></span><small>原推文图片 · 原型示意</small></div><div className="media-caption"><Icon name="image" size={13} />视觉分析：图片方向与正文一致，未发现相互冲突。</div></>}
                </article>
              </section>
              <section className="analysis-section">
                <div className="section-heading-v3"><h2>核验记录</h2><span>分析过程透明</span></div>
                <div className="verification-stack">
                  <div className="verification-row"><span>观点归属</span><strong>博主本人陈述，不是转述或引用</strong><b>已确认</b></div>
                  <div className="verification-row"><span>标的身份</span><strong>{item.assetName}</strong><b>已核验</b></div>
                  <div className="verification-row"><span>赞助内容</span><strong>未发现影响结论的商业推广</strong><b>无异常</b></div>
                  <div className="verification-row"><span>文本与图片</span><strong>{item.imageCount ? "方向一致，图片作为补充证据" : "本条没有关联图片"}</strong><b>{item.imageCount ? "一致" : "不适用"}</b></div>
                </div>
              </section>
            </article>
            <aside className="deep-aside">
              <section className="aside-card-v3"><span>跟踪对象</span><h3>{item.symbol}</h3><p>{item.assetName}</p><div className="aside-facts"><div>方向<strong>{item.directionLabel}</strong></div><div>观点类型<strong>{item.category}</strong></div><div>证据数量<strong>{item.evidenceCount} 条</strong></div><div>更新时间<strong>{item.time}</strong></div></div></section>
              <section className="aside-card-v3"><span>使用说明</span><h3>这是观点证据，不是交易指令</h3><p>结论会随新推文、图片和市场验证结果持续更新。</p></section>
              <div className="deep-aside-actions"><button className="quiet-button">查看原推文</button><button className="primary-button" onClick={onAsk}>向助手追问</button></div>
            </aside>
          </div>
        </div>
      </main>;
    }

function BloggerProfilePage({ source, onBack, onOpenPrediction }) {
      const [tab, setTab] = useState("latest");
      return <main className="page" data-screen-label="博主档案">
        <div className="deep-page">
          <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回信息源</button>
          <header className="profile-hero-v3">
            <span className="profile-avatar-v3">{source.initials}</span>
            <div className="profile-identity-v3"><p className="eyebrow">Twitter source profile</p><h1>{source.name}</h1><span>@{source.handle}</span><p>{source.bio}</p><div className="focus-tags">{source.focus.map(function(item){ return <span key={item}>{item}</span>; })}</div></div>
            <button className="primary-button">已关注</button>
          </header>
          <div className="deep-layout deep-layout-spaced">
            <section className="deep-main">
              <div className="profile-nav-v3"><button className={tab === "latest" ? "active" : ""} onClick={function(){ setTab("latest"); }}>最新观点</button><button className={tab === "history" ? "active" : ""} onClick={function(){ setTab("history"); }}>历史验证</button></div>
              {tab === "latest" ? <div className="profile-opinion-list">
                <article className="profile-opinion"><time>今天<br />18 分钟前</time><div><h3>{source.latest}</h3><p>观点已完成作者归属、标的身份和图片一致性核验。</p><div className="profile-opinion-meta"><span>{source.latestType}</span><span>3 条证据</span><span>查看完整分析 →</span></div></div></article>
                <article className="profile-opinion"><time>昨天<br />21:40</time><div><h3>风险资产仍需要等待油价和收益率关系稳定</h3><p>被识别为宏观观察，不创建可验证预测。</p><div className="profile-opinion-meta"><span>宏观观点</span><span>美股 · 原油</span></div></div></article>
                <article className="profile-opinion"><time>8月22日<br />09:15</time><div><h3>市场正在低估供应恢复所需的时间</h3><p>观点方向与当前判断一致，但当时证据不足，未触发重要提醒。</p><div className="profile-opinion-meta"><span>观点</span><span>WTI</span><span>低置信度</span></div></div></article>
              </div> : <div className="validation-list">
                <button className="validation-row validation-button" onClick={onOpenPrediction}><strong>WTI</strong><div><span>短期看多 · 已到期</span><small>发布于 8月11日 · 自动行情验证</small></div><span className="verdict incorrect">未命中</span></button>
                <div className="validation-row"><strong>CL</strong><div><span>中期看多 · 还剩 29 天</span><small>身份已核验，等待验证窗口结束</small></div><span className="verdict pending">跟踪中</span></div>
                <div className="validation-row"><strong>NVDA</strong><div><span>中期观点 · 尚未成熟</span><small>不计入当前命中率</small></div><span className="verdict pending">跟踪中</span></div>
              </div>}
            </section>
            <aside className="deep-aside">
              <section className="aside-card-v3"><span>可信度状态</span><div className="sample-status"><strong>样本不足，暂不形成排名</strong><span>只有 1 条预测完成验证，不能据此判断博主长期能力。</span></div><div className="profile-score-empty"><strong>—</strong><span>可信度评分</span></div><div className="aside-facts"><div>已验证预测<strong>1 条</strong></div><div>等待验证<strong>2 条</strong></div><div>原始命中率<strong>0%</strong></div></div></section>
              <section className="aside-card-v3"><span>内容特征</span><div className="aside-facts"><div>投资相关率<strong>{source.relevant}%</strong></div><div>已采集推文<strong>{source.collected} 条</strong></div><div>常见领域<strong>{source.focus.slice(0,2).join(" / ")}</strong></div></div></section>
              <div className="deep-aside-actions"><button className="quiet-button">查看 Twitter</button><button className="primary-button">调整提醒</button></div>
            </aside>
          </div>
        </div>
      </main>;
    }

function AssetDetailPage({ item, onBack, onAsk, onOpenPrediction }) {
      const [tab, setTab] = useState("opinions");
      return <main className="page" data-screen-label="标的详情">
        <div className="deep-page">
          <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回关注</button>
          <header className="asset-hero-v3"><div className="asset-symbol-v3"><strong>{item.symbol}</strong><span>{item.type} · 身份已核验</span></div><div className="asset-state-v3"><strong>{item.change}</strong><span>最近更新：{item.time}</span></div></header>
          <div className="deep-layout deep-layout-spaced">
            <section className="deep-main">
              <section className="consensus-hero-v3"><span>当前博主共识</span><h1>{item.headline}</h1><p>{item.thesis}</p><div className="consensus-legend"><div><strong>{item.positive}%</strong><span>偏多</span></div><div><strong>{item.neutral}%</strong><span>观察</span></div><div><strong>{item.negative}%</strong><span>偏空 / 风险</span></div></div></section>
              <div className="profile-nav-v3"><button className={tab === "opinions" ? "active" : ""} onClick={function(){ setTab("opinions"); }}>观点变化</button><button className={tab === "predictions" ? "active" : ""} onClick={function(){ setTab("predictions"); }}>预测验证</button></div>
              {tab === "opinions" ? <>
                <section className="analysis-section"><div className="section-heading-v3"><h2>观点时间线</h2><span>{item.timeline.length} 条重要变化</span></div><div className="asset-stream">{item.timeline.map(function(entry, index){ return <article className="asset-opinion" key={entry.join("-")}><time>{entry[0]}</time><div><h3>{entry[1]} · {index === 0 ? item.stance : "观察"}</h3><p>{entry[2]}</p><footer><span>原文证据</span><span>标的已核验</span></footer></div></article>; })}</div></section>
                <section className="analysis-section"><div className="section-heading-v3"><h2>接下来关注什么</h2><span>条件变化优先于价格变化</span></div><div className="split-analysis"><div className="analysis-box"><span>共识可能继续强化</span><ul><li>新的独立来源确认供应风险</li><li>关键观察位连续保持强势</li><li>事件时间表继续推迟</li></ul></div><div className="analysis-box risk"><span>共识可能反转</span><ul><li>出现明确、可执行的通航协议</li><li>主导博主撤回原判断</li><li>供应风险没有反映在后续数据中</li></ul></div></div></section>
              </> : <div className="validation-list">
                <button className="validation-row validation-button" onClick={onOpenPrediction}><strong>{item.symbol}</strong><div><span>短期看多 · @qinbafrank</span><small>发布于 8月11日 · 自动行情验证完成</small></div><span className="verdict incorrect">未命中</span></button>
                <div className="validation-row"><strong>{item.symbol}</strong><div><span>中期看多 · @marketmemo</span><small>验证窗口尚未结束</small></div><span className="verdict pending">跟踪中</span></div>
              </div>}
            </section>
            <aside className="deep-aside">
              <section className="aside-card-v3"><span>标的身份</span><div className="identity-proof"><span><Icon name="check" size={14} /></span><div><strong>{item.symbol} · {item.type}</strong><small>通过正式标的校验，不是同名股票</small></div></div></section>
              <section className="aside-card-v3"><span>信息覆盖</span><div className="aside-facts"><div>关注博主<strong>{item.authors.length} 位</strong></div><div>今日更新<strong>{item.activity}</strong></div><div>当前状态<strong>{item.stance}</strong></div><div>变化趋势<strong>{item.change}</strong></div></div></section>
              <section className="aside-card-v3"><span>使用说明</span><h3>这里只解释博主观点</h3><p>价格行情用于验证预测结果，不替代专业行情终端。</p></section>
              <div className="deep-aside-actions"><button className="quiet-button">取消关注</button><button className="primary-button" onClick={onAsk}>向助手追问</button></div>
            </aside>
          </div>
        </div>
      </main>;
    }

    function AddSourceModal({ onClose, onComplete }) {
      const [handle, setHandle] = useState("");
      function submit(event) {
        event.preventDefault();
        if (!handle.trim()) return;
        onComplete(handle.replace("@", ""));
      }
      return <div className="modal-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
        <form className="modal" onSubmit={submit}>
          <div className="modal-head"><div><h2>新增信息源</h2><p>输入 Twitter Handle，其余步骤自动完成。</p></div><button type="button" className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></div>
          <label className="field-label" htmlFor="source-handle">Twitter Handle</label>
          <div className="handle-field"><span>@</span><input id="source-handle" autoFocus value={handle} onChange={function(event){ setHandle(event.target.value); }} placeholder="username" /></div>
          <p className="field-help">系统会获取资料、开始采集，并自动分析文本和图片。</p>
          <div className="modal-actions"><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={!handle.trim()}>添加并关注</button></div>
        </form>
      </div>;
    }

Object.assign(window, { InsightDetailPage, BloggerProfilePage, AssetDetailPage, AddSourceModal });
