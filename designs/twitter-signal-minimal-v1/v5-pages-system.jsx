const { useEffect, useMemo, useState } = React;

function AddSourceModalV5({ onClose, onComplete }) {
  const [handle, setHandle] = useState("");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  function submit(event) {
    event.preventDefault();
    const clean = handle.trim().replace("@", "");
    if (!clean) return;
    if (clean.toLowerCase() === "qinbafrank") { setStatus("error"); setMessage("这个信息源已在关注列表中。"); return; }
    if (clean.toLowerCase().includes("private")) { setStatus("error"); setMessage("该账号为私密账号，无法采集公开推文。"); return; }
    if (clean.toLowerCase().includes("missing")) { setStatus("error"); setMessage("没有找到这个 Twitter Handle，请检查拼写。"); return; }
    setStatus("checking"); setMessage("正在核对账号身份与公开状态…");
    window.setTimeout(function(){ setStatus("ready"); setMessage("账号可访问，将自动采集公开推文与图片。"); }, 520);
  }
  function finish(){ onComplete(handle.trim().replace("@", "")); }
  return <div className="modal-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <form className="modal add-source-v5" onSubmit={submit}>
      <div className="modal-head"><div><p className="eyebrow">One-step source setup</p><h2>新增信息源</h2><p>输入 Twitter Handle，系统先核对身份，再自动开始采集。</p></div><button type="button" className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></div>
      <label className="field-label" htmlFor="source-handle-v5">Twitter Handle</label>
      <div className={"handle-field " + (status === "error" ? "field-error-v5" : "")}><span>@</span><input id="source-handle-v5" autoFocus value={handle} onChange={function(event){ setHandle(event.target.value); setStatus("idle"); setMessage(""); }} placeholder="username" /></div>
      {status === "idle" && <p className="field-help">只采集公开内容。不会要求用户提供 Twitter 密码。</p>}
      {status !== "idle" && <div className={"source-check-v5 " + status}><span>{status === "checking" ? <i></i> : status === "ready" ? <Icon name="check" size={16} /> : "!"}</span><div><strong>{status === "checking" ? "正在检查" : status === "ready" ? "可以添加" : "暂时无法添加"}</strong><p>{message}</p></div></div>}
      {status === "ready" && <div className="source-preview-v5"><span className="source-avatar">{handle.slice(0,2).toUpperCase()}</span><div><strong>@{handle.replace("@", "")}</strong><small>公开账号 · 资料已核对</small></div><span>自动分析文本与图片</span></div>}
      <div className="modal-actions"><button type="button" className="quiet-button" onClick={onClose}>取消</button>{status === "ready" ? <button type="button" className="primary-button" onClick={finish}>添加并开始采集</button> : <button className="primary-button" disabled={!handle.trim() || status === "checking"}>检查账号</button>}</div>
    </form>
  </div>;
}

function AddAssetModalV5({ onClose, onComplete }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const assets = [
    { symbol: "XAU", name: "现货黄金", type: "商品", verified: true },
    { symbol: "AAPL", name: "Apple Inc.", type: "美股", verified: true },
    { symbol: "600519.SH", name: "贵州茅台", type: "A股", verified: true },
    { symbol: "WTI", name: "WTI 原油连续合约", type: "商品", verified: true, duplicate: true }
  ];
  const visible = query.trim() ? assets.filter(function(item){ return (item.symbol + item.name).toLowerCase().includes(query.toLowerCase()); }) : assets;
  return <div className="system-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <section className="asset-picker-v5" role="dialog" aria-label="添加关注标的">
      <header><div><p className="eyebrow">Watchlist</p><h2>添加关注标的</h2><span>只用于聚合博主观点，不创建行情面板。</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      <label className="asset-search-v5"><Icon name="search" size={17} /><input autoFocus value={query} onChange={function(event){ setQuery(event.target.value); setSelected(null); }} placeholder="搜索股票、原油、黄金或加密货币" /></label>
      <div className="asset-results-v5">{visible.length ? visible.map(function(item){ return <button key={item.symbol} disabled={item.duplicate} className={selected && selected.symbol === item.symbol ? "active" : ""} onClick={function(){ setSelected(item); }}><span className="result-symbol">{item.symbol}</span><div><strong>{item.name}</strong><small>{item.type} · 身份已核验</small></div><span>{item.duplicate ? "已关注" : selected && selected.symbol === item.symbol ? "已选择" : "添加"}</span></button>; }) : <div className="asset-no-result-v5"><span>?</span><strong>没有找到“{query}”</strong><p>尝试输入正式股票代码或资产名称。</p></div>}</div>
      <footer><span>{selected ? "将聚合关注博主中与 " + selected.symbol + " 相关的观点" : "选择一个已核验标的"}</span><button className="primary-button" disabled={!selected} onClick={function(){ if (selected) onComplete(selected); }}>加入关注</button></footer>
    </section>
  </div>;
}

function SourceControlsV5({ source, onClose, onToast, onUnfollow }) {
  const [frequency, setFrequency] = useState("重要变化");
  const [confirming, setConfirming] = useState(false);
  return <div className="notification-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <aside className="source-controls-v5" aria-label="信息源设置">
      <header><div><p className="eyebrow">Source controls</p><h2>@{source.handle}</h2><span>提醒设置不会影响采集。</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      {!confirming ? <>
        <section><span>提醒频率</span>{["重要变化","每日摘要","不提醒"].map(function(item){ return <button className={frequency === item ? "active" : ""} key={item} onClick={function(){ setFrequency(item); }}><span className="radio-v4"></span><div><strong>{item}</strong><small>{item === "重要变化" ? "观点反转、共识变化和验证完成" : item === "每日摘要" ? "每天固定时间汇总" : "仍会在今日页面显示"}</small></div></button>; })}</section>
        <section className="collection-setting-v5"><span>采集状态</span><div><strong>每 30 分钟采集公开推文</strong><small>最近成功：18 分钟前</small></div><button onClick={function(){ onToast("已暂停 @" + source.handle + " 的定时采集"); }}>暂停采集</button></section>
        <footer><button className="danger-text-v5" onClick={function(){ setConfirming(true); }}>停止关注</button><button className="primary-button" onClick={function(){ onToast("@" + source.handle + " 的提醒设置已保存"); onClose(); }}>保存设置</button></footer>
      </> : <div className="confirm-unfollow-v5"><span className="error-mark-v4">!</span><h3>停止关注 @{source.handle}？</h3><p>停止后不再定时采集。已经保存的推文、图片和分析记录不会立即删除。</p><div><button className="quiet-button" onClick={function(){ setConfirming(false); }}>返回</button><button className="danger-button-v5" onClick={onUnfollow}>确认停止关注</button></div></div>}
    </aside>
  </div>;
}

function BloggerProfilePageV5({ source, onBack, onOpenPrediction, onOpenInsight, onToast }) {
  const [tab, setTab] = useState("latest");
  const [showControls, setShowControls] = useState(false);
  return <>
    <main className="page" data-screen-label="博主档案增强版">
      <div className="deep-page">
        <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回信息源</button>
        <header className="profile-hero-v3"><span className="profile-avatar-v3">{source.initials}</span><div className="profile-identity-v3"><p className="eyebrow">Twitter source profile</p><h1>{source.name}</h1><span>@{source.handle}</span><p>{source.bio}</p><div className="focus-tags">{source.focus.map(function(item){ return <span key={item}>{item}</span>; })}</div></div><button className="primary-button" onClick={function(){ setShowControls(true); }}>已关注 · 设置</button></header>
        <div className="deep-layout deep-layout-spaced">
          <section className="deep-main">
            <div className="profile-nav-v3"><button className={tab === "latest" ? "active" : ""} onClick={function(){ setTab("latest"); }}>最新观点</button><button className={tab === "history" ? "active" : ""} onClick={function(){ setTab("history"); }}>历史验证</button><button className={tab === "source" ? "active" : ""} onClick={function(){ setTab("source"); }}>采集状态</button></div>
            {tab === "latest" && <div className="profile-opinion-list"><button className="profile-opinion profile-opinion-button-v5" onClick={onOpenInsight}><time>今天<br />18 分钟前</time><div><h3>{source.latest}</h3><p>观点已完成作者归属、标的身份和图片一致性核验。</p><div className="profile-opinion-meta"><span>{source.latestType}</span><span>6 条证据</span><span>查看完整分析 →</span></div></div></button><article className="profile-opinion"><time>昨天<br />21:40</time><div><h3>风险资产仍需要等待油价和收益率关系稳定</h3><p>被识别为宏观观察，不创建可验证预测。</p><div className="profile-opinion-meta"><span>宏观观点</span><span>美股 · 原油</span></div></div></article></div>}
            {tab === "history" && <div className="validation-list"><button className="validation-row validation-button" onClick={onOpenPrediction}><strong>WTI</strong><div><span>短期看多 · 已到期</span><small>自动行情验证完成</small></div><span className="verdict incorrect">未命中</span></button><button className="validation-row validation-button" onClick={onOpenPrediction}><strong>CL</strong><div><span>中期看多 · 还剩 29 天</span><small>身份已核验，等待验证</small></div><span className="verdict pending">跟踪中</span></button><button className="validation-row validation-button" onClick={onOpenPrediction}><strong>US</strong><div><span>宏观观察 · 方向不明确</span><small>不计入当前命中率</small></div><span className="verdict excluded-v5">已排除</span></button></div>}
            {tab === "source" && <div className="source-health-v5"><div><span className="live-dot"></span><strong>当前采集正常</strong><p>最近成功：18 分钟前 · 下次预计：12 分钟后</p></div><ol><li><span>资料同步</span><strong>已完成</strong></li><li><span>公开推文</span><strong>18 条</strong></li><li><span>关联图片</span><strong>7 张</strong></li><li><span>失败任务</span><strong>0</strong></li></ol><button className="quiet-button" onClick={function(){ onToast("已创建一次手动同步任务"); }}>立即同步一次</button></div>}
          </section>
          <aside className="deep-aside"><section className="aside-card-v3"><span>可信度状态</span><div className="sample-status"><strong>样本不足，暂不形成排名</strong><span>只有 1 条预测完成验证，不能据此判断长期能力。</span></div><div className="aside-facts"><div>已验证预测<strong>1 条</strong></div><div>等待验证<strong>2 条</strong></div><div>原始命中率<strong>0%</strong></div></div></section><section className="aside-card-v3"><span>内容特征</span><div className="aside-facts"><div>投资相关率<strong>{source.relevant}%</strong></div><div>已采集推文<strong>{source.collected} 条</strong></div><div>常见领域<strong>{source.focus.slice(0,2).join(" / ")}</strong></div></div></section><div className="deep-aside-actions"><button className="quiet-button" onClick={function(){ onToast("Twitter 主页将在新窗口打开（原型）"); }}>查看 Twitter</button><button className="primary-button" onClick={function(){ setShowControls(true); }}>调整提醒</button></div></aside>
        </div>
      </div>
    </main>
    {showControls && <SourceControlsV5 source={source} onClose={function(){ setShowControls(false); }} onToast={onToast} onUnfollow={function(){ setShowControls(false); onToast("已停止关注 @" + source.handle); onBack(); }} />}
  </>;
}

function WatchDetailPanelV5({ item, onClose, onOpenAsset, onAsk }) {
  return <aside className="detail-panel" aria-label="关注标的详情"><div className="detail-head"><div><Icon name="watch" size={16} />观点变化</div><button className="detail-close" onClick={onClose} aria-label="关闭关注标的详情"><Icon name="close" size={17} /></button></div><div className="detail-body"><div className="watch-panel-title"><div><h2>{item.symbol}</h2><p>{item.type} · {item.activity}</p></div><span className={"direction " + item.tone}>{item.stance}</span></div><p className="detail-thesis" style={{marginTop:14}}>{item.thesis}</p><section className="detail-section"><span>关注博主观点分布</span><div className="stance-summary"><div><strong>{item.positive}%</strong><span>偏多</span></div><div><strong>{item.neutral}%</strong><span>观察</span></div><div><strong>{item.negative}%</strong><span>偏空 / 风险</span></div></div></section><section className="detail-section"><span>最近变化</span><div className="opinion-timeline">{item.timeline.map(function(entry){ return <div className="timeline-item" key={entry.join("-")}><small>{entry[0]}</small><strong>{entry[1]}</strong><p>{entry[2]}</p></div>; })}</div></section><div className="detail-actions"><button className="quiet-button" onClick={onAsk}>向助手追问</button><button className="primary-button" onClick={function(){ onOpenAsset(item); }}>完整标的</button></div></div></aside>;
}

function WatchPageV5({ onOpenAsset, onAddAsset, onAsk }) {
  const [selectedId, setSelectedId] = useState(function(){ return window.innerWidth > 1080 ? watchlist[0].id : null; });
  const selected = watchlist.find(function(item){ return item.id === selectedId; });
  return <>{selected && <div className="mobile-detail-backdrop" onClick={function(){ setSelectedId(null); }}></div>}<main className="page with-detail" data-screen-label="关注标的增强版"><section className="page-main"><header className="page-heading"><div><p className="eyebrow">Watchlist</p><h1>关注</h1><p>只聚合关注博主的观点变化，不重复做行情软件。</p></div><button className="quiet-button" onClick={onAddAsset}><Icon name="plus" size={15} />添加标的</button></header><div className="watch-delta"><span className="watch-delta-mark"><Icon name="watch" size={15} /></span><div><strong>过去 24 小时，2 个标的观点发生明显变化</strong><span>WTI 观点升温；BTC 的方向分歧正在扩大。</span></div><small>基于 4 个信息源</small></div><div className="watch-list-v2">{watchlist.map(function(item){ return <button className={"watch-item-v2 " + (selectedId === item.id ? "selected" : "")} key={item.id} onClick={function(){ setSelectedId(item.id); }}><span className="watch-symbol-v2"><strong>{item.symbol}</strong><span>{item.type} · {item.stance}</span></span><span className="watch-copy-v2"><h3>{item.headline}</h3><p>{item.detail}</p><span className="consensus"><i style={{width:item.positive + "%"}}></i><i style={{width:item.neutral + "%"}}></i><i style={{width:item.negative + "%"}}></i></span></span><span className="watch-stats-v2"><strong>{item.change}</strong><span>{item.time}</span></span><span className="source-row-end"><Icon name="arrow" size={17} /></span></button>; })}</div></section>{selected && <WatchDetailPanelV5 item={selected} onClose={function(){ setSelectedId(null); }} onOpenAsset={onOpenAsset} onAsk={onAsk} />}</main></>;
}

function AssetDetailPageV5({ item, onBack, onAsk, onOpenPrediction, onToast }) {
  const [tab, setTab] = useState("opinions");
  const [confirming, setConfirming] = useState(false);
  return <><main className="page" data-screen-label="标的详情增强版"><div className="deep-page"><button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回关注</button><header className="asset-hero-v3"><div className="asset-symbol-v3"><strong>{item.symbol}</strong><span>{item.type} · 身份已核验</span></div><div className="asset-state-v3"><strong>{item.change}</strong><span>最近更新：{item.time}</span></div></header><div className="deep-layout deep-layout-spaced"><section className="deep-main"><section className="consensus-hero-v3"><span>当前博主共识</span><h1>{item.headline}</h1><p>{item.thesis}</p><div className="consensus-legend"><div><strong>{item.positive}%</strong><span>偏多</span></div><div><strong>{item.neutral}%</strong><span>观察</span></div><div><strong>{item.negative}%</strong><span>偏空 / 风险</span></div></div></section><div className="profile-nav-v3"><button className={tab === "opinions" ? "active" : ""} onClick={function(){ setTab("opinions"); }}>观点变化</button><button className={tab === "predictions" ? "active" : ""} onClick={function(){ setTab("predictions"); }}>预测验证</button></div>{tab === "opinions" ? <section className="analysis-section"><div className="section-heading-v3"><h2>观点时间线</h2><span>{item.timeline.length} 条重要变化</span></div><div className="asset-stream">{item.timeline.map(function(entry,index){ return <article className="asset-opinion" key={entry.join("-")}><time>{entry[0]}</time><div><h3>{entry[1]} · {index === 0 ? item.stance : "观察"}</h3><p>{entry[2]}</p><footer><span>原文证据</span><span>标的已核验</span></footer></div></article>; })}</div></section> : <div className="validation-list"><button className="validation-row validation-button" onClick={onOpenPrediction}><strong>{item.symbol}</strong><div><span>短期看多 · @qinbafrank</span><small>自动行情验证完成</small></div><span className="verdict incorrect">未命中</span></button><button className="validation-row validation-button" onClick={onOpenPrediction}><strong>{item.symbol}</strong><div><span>中期看多 · @marketmemo</span><small>还剩 29 天</small></div><span className="verdict pending">跟踪中</span></button></div>}</section><aside className="deep-aside"><section className="aside-card-v3"><span>标的身份</span><div className="identity-proof"><span><Icon name="check" size={14} /></span><div><strong>{item.symbol} · {item.type}</strong><small>通过正式标的校验，不是同名股票</small></div></div></section><section className="aside-card-v3"><span>信息覆盖</span><div className="aside-facts"><div>关注博主<strong>{item.authors.length} 位</strong></div><div>今日更新<strong>{item.activity}</strong></div><div>当前状态<strong>{item.stance}</strong></div><div>变化趋势<strong>{item.change}</strong></div></div></section><section className="aside-card-v3"><span>使用说明</span><h3>这里只解释博主观点</h3><p>价格行情仅用于验证预测结果。</p></section><div className="deep-aside-actions"><button className="quiet-button" onClick={function(){ setConfirming(true); }}>取消关注</button><button className="primary-button" onClick={onAsk}>向助手追问</button></div></aside></div></div></main>{confirming && <div className="system-backdrop"><section className="confirm-dialog-v5" role="dialog" aria-label="取消关注标的"><span className="error-mark-v4">!</span><h2>取消关注 {item.symbol}？</h2><p>不会删除相关推文和历史分析，只是不再出现在“关注”中。</p><div><button className="quiet-button" onClick={function(){ setConfirming(false); }}>返回</button><button className="danger-button-v5" onClick={function(){ setConfirming(false); onToast("已取消关注 " + item.symbol); onBack(); }}>确认取消</button></div></section></div>}</>;
}

function SearchOverlayV5({ onClose, onOpenInsight, onOpenProfile, onOpenAsset }) {
  const [query, setQuery] = useState("原油");
  const clean = query.trim().toLowerCase();
  const known = !clean || ["原油","wti","qinbafrank","秦爸","nvda","宏观"].some(function(item){ return item.includes(clean) || clean.includes(item); });
  return <div className="system-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}><section className="search-overlay-v4" role="dialog" aria-label="全局搜索"><header className="search-head-v4"><Icon name="search" size={19} /><input autoFocus value={query} onChange={function(event){ setQuery(event.target.value); }} placeholder="搜索博主、标的或观点" /><kbd>ESC</kbd><button onClick={onClose} aria-label="关闭搜索"><Icon name="close" size={18} /></button></header>{!clean ? <div className="search-empty-v4"><span>最近搜索</span><div><button onClick={function(){ setQuery("原油"); }}>原油供应风险</button><button onClick={function(){ setQuery("qinbafrank"); }}>@qinbafrank</button><button onClick={function(){ setQuery("NVDA"); }}>NVDA</button></div><p>可搜索博主、标的、推文原文和历史观点。</p></div> : known ? <div className="search-results-v4"><p className="result-summary">找到与“{query}”相关的 6 条结果</p><section className="result-group-v4"><div className="result-group-head"><strong>标的</strong><span>1</span></div><button className="search-result-row" onClick={function(){ onOpenAsset(watchlist[0]); }}><span className="result-symbol">WTI</span><div><strong>WTI 原油连续合约</strong><small>3 位关注博主 · 今天 3 条更新</small></div><span className="direction bullish">偏多</span><Icon name="arrow" size={16} /></button></section><section className="result-group-v4"><div className="result-group-head"><strong>信息源</strong><span>1</span></div><button className="search-result-row" onClick={function(){ onOpenProfile(sources[0]); }}><span className="source-avatar">QF</span><div><strong>秦爸 Frank <i>@qinbafrank</i></strong><small>宏观 · 原油 · 美股</small></div><span className="result-note">18 条推文</span><Icon name="arrow" size={16} /></button></section><section className="result-group-v4"><div className="result-group-head"><strong>观点与证据</strong><span>4</span></div><button className="search-result-row result-insight" onClick={function(){ onOpenInsight(signals[0]); }}><span className="result-symbol">WTI</span><div><strong>原油供应风险重新计价，80 美元成为短期观察位</strong><small>@qinbafrank · 18 分钟前 · 6 条证据</small></div><Icon name="arrow" size={16} /></button></section></div> : <div className="search-no-result-v5"><span className="state-symbol-v5">?</span><h3>没有找到“{query}”</h3><p>只搜索已经采集的博主、推文、图片分析和已核验标的，不会自动访问公开网页补全结果。</p><button className="quiet-button" onClick={function(){ setQuery(""); }}>清空搜索</button></div>}<footer className="search-footer-v4"><span>↑↓ 选择</span><span>Enter 打开</span><span>结果只来自已采集内容</span></footer></section></div>;
}

function SettingsPageV5({ onBack, onToast }) {
  const [tab, setTab] = useState("profile");
  const [important, setImportant] = useState(true);
  const [digest, setDigest] = useState(false);
  const [muted, setMuted] = useState(["@noise_trader"]);
  const tabs = [["profile","个人偏好"],["alerts","提醒"],["muted","静音列表"],["security","账户安全"]];
  return <main className="page" data-screen-label="账户设置完整状态"><div className="settings-page-v4"><button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回工作台</button><header className="state-page-head-v4"><p className="eyebrow">Preferences</p><h1>账户与偏好</h1><p>只保留影响情报范围、提醒和账户安全的必要设置。</p></header><div className="settings-layout-v4"><nav className="settings-nav-v4">{tabs.map(function(item){ return <button className={tab === item[0] ? "active" : ""} key={item[0]} onClick={function(){ setTab(item[0]); }}>{item[1]}</button>; })}</nav><section className="settings-content-v4">
    {tab === "profile" && <><div className="settings-section-v4"><h2>个人资料</h2><div className="account-row-v4"><span className="avatar">AR</span><div><strong>Arjun</strong><small>arjun@example.com</small></div><button className="quiet-button" onClick={function(){ onToast("个人资料编辑已保存（原型）"); }}>编辑</button></div></div><div className="settings-section-v4"><h2>关注市场</h2><p>用于首页筛选和助手默认回答范围。</p><div className="settings-chips-v4"><button>A股</button><button>港股</button><button className="selected">美股</button><button className="selected">原油</button><button>黄金</button><button>加密货币</button></div></div><div className="settings-section-v4"><h2>时间与语言</h2><label className="settings-select-v4"><span>时区</span><select defaultValue="Asia/Shanghai"><option>Asia/Shanghai</option><option>America/New_York</option><option>Europe/London</option></select></label><label className="settings-select-v4"><span>语言</span><select defaultValue="简体中文"><option>简体中文</option><option>English</option></select></label></div></>}
    {tab === "alerts" && <><div className="settings-section-v4"><h2>提醒原则</h2><p>默认只提醒观点反转、共识形成和预测验证完成。</p><div className="setting-row-v4"><div><strong>重要变化</strong><span>共识形成、观点反转和验证完成</span></div><button className={"toggle-v4 " + (important ? "on" : "")} onClick={function(){ setImportant(!important); }}><i></i></button></div><div className="setting-row-v4"><div><strong>每日摘要</strong><span>每天 18:00 汇总当天重要内容</span></div><button className={"toggle-v4 " + (digest ? "on" : "")} onClick={function(){ setDigest(!digest); }}><i></i></button></div></div><div className="settings-section-v4"><h2>免打扰时间</h2><label className="settings-select-v4"><span>时间段</span><select defaultValue="23:00–08:00"><option>23:00–08:00</option><option>22:00–07:00</option><option>不启用</option></select></label></div></>}
    {tab === "muted" && <div className="settings-section-v4"><h2>静音列表</h2><p>静音后继续采集，但不进入今日摘要和主动提醒。</p>{muted.length ? <div className="muted-list-v5">{muted.map(function(item){ return <div key={item}><span className="source-avatar">NT</span><div><strong>{item}</strong><small>静音原因：高重复内容</small></div><button onClick={function(){ setMuted([]); onToast(item + " 已恢复显示"); }}>取消静音</button></div>; })}</div> : <div className="settings-empty-v5"><Icon name="check" size={18} /><strong>没有静音的信息源</strong><p>所有关注博主都可以进入今日情报。</p></div>}</div>}
    {tab === "security" && <><div className="settings-section-v4"><h2>登录安全</h2><div className="security-row-v5"><div><strong>登录密码</strong><span>上次修改：从未</span></div><button className="quiet-button" onClick={function(){ onToast("密码重置邮件已发送（原型）"); }}>修改密码</button></div><div className="security-row-v5"><div><strong>邮箱验证</strong><span>arjun@example.com</span></div><b>已验证</b></div></div><div className="settings-section-v4 danger-zone-v4"><h2>账户</h2><button onClick={function(){ onToast("已退出登录（原型）"); }}>退出登录</button><span>删除账户需要二次确认并等待数据清理。</span></div></>}
  </section></div></div></main>;
}

function AuthPageV5({ onContinue, onStartOnboarding }) {
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  if (mode === "recover") return <main className="auth-v4"><section className="auth-story-v4"><div className="auth-brand-v4"><span className="brand-mark"></span><strong>Signal</strong></div><div><p>Account recovery</p><h1>找回访问权限，<br />不丢失研究范围。</h1><span>重置密码不会影响关注信息源、历史情报和预测记录。</span></div></section><section className="auth-form-v4"><div className="auth-form-inner-v4"><button className="back-link" onClick={function(){ setMode("login"); }}><Icon name="arrow" size={14} />返回登录</button><p className="eyebrow">Password reset</p><h2>重置密码</h2><p>输入注册邮箱，我们会发送一次性重置链接。</p><label className="auth-field-v4"><span>邮箱</span><input placeholder="name@example.com" defaultValue="arjun@example.com" /></label><button className="auth-submit-v4" onClick={function(){ setMode("sent"); }}>发送重置邮件</button></div></section></main>;
  if (mode === "sent") return <main className="auth-v4"><section className="auth-story-v4"><div className="auth-brand-v4"><span className="brand-mark"></span><strong>Signal</strong></div></section><section className="auth-form-v4"><div className="auth-form-inner-v4 auth-success-v5"><span className="ready-mark-v4"><Icon name="check" size={26} /></span><h2>检查你的邮箱</h2><p>重置链接已发送到 arjun@example.com，30 分钟内有效。</p><button className="auth-submit-v4" onClick={function(){ setMode("login"); }}>返回登录</button></div></section></main>;
  return <main className="auth-v4" data-screen-label="登录注册完整状态"><section className="auth-story-v4"><div className="auth-brand-v4"><span className="brand-mark"></span><strong>Signal</strong></div><div><p>Twitter investment intelligence</p><h1>关注观点变化，<br />而不是信息噪音。</h1><span>从博主推文、图片和历史结果中提取可追溯、可验证的投资情报。</span></div><footer><span>证据可回溯</span><span>标的已核验</span><span>预测可验证</span></footer></section><section className="auth-form-v4"><div className="auth-form-inner-v4"><div className="auth-tabs-v4"><button className={mode === "login" ? "active" : ""} onClick={function(){ setMode("login"); }}>登录</button><button className={mode === "register" ? "active" : ""} onClick={function(){ setMode("register"); }}>注册</button></div><h2>{mode === "login" ? "欢迎回来" : "创建个人情报工作台"}</h2><p>{mode === "login" ? "继续查看你关注的博主和标的。" : "两分钟建立第一份 Twitter 情报流。"}</p><label className="auth-field-v4"><span>邮箱</span><input placeholder="name@example.com" defaultValue="arjun@example.com" /></label>{mode === "register" && <label className="auth-field-v4"><span>用户名称</span><input placeholder="你的称呼" /></label>}<label className="auth-field-v4"><span>密码</span><div><input type={showPassword ? "text" : "password"} defaultValue="prototype123" /><button onClick={function(){ setShowPassword(!showPassword); }} type="button">{showPassword ? "隐藏" : "显示"}</button></div></label>{mode === "login" && <button className="forgot-v4" onClick={function(){ setMode("recover"); }}>忘记密码？</button>}<button className="auth-submit-v4" onClick={mode === "login" ? onContinue : onStartOnboarding}>{mode === "login" ? "进入工作台" : "创建账户"}</button><small>继续即表示同意服务条款和隐私政策。平台内容不构成投资建议。</small></div></section></main>;
}

function ExceptionStatesPageV5({ onBack, onAddSource, onToast }) {
  const cards = [
    ["01","账号不存在","没有找到 @missing_user","检查拼写后重新输入。","修改 Handle"],
    ["02","私密账号","该账号没有可公开访问的推文","只有账号公开后才能开始采集。","了解限制"],
    ["03","平台限流","采集暂时延迟，不会重复创建任务","系统将在 12 分钟后自动重试。","查看状态"],
    ["04","图片部分失败","正文已完成分析，2 张图片暂未识别","正文结果可以阅读，图片完成后自动补充。","重试图片"],
    ["05","没有投资内容","采集成功，但近期推文与投资无关","不会为了填满首页而生成低质量情报。","查看原推文"],
    ["06","搜索无结果","只搜索已采集内容，不使用公开网页补全","可以新增信息源或调整关键词。","新增信息源"]
  ];
  return <main className="page" data-screen-label="业务异常状态"><div className="deep-page"><button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回今日</button><header className="state-page-head-v4"><p className="eyebrow">Operational states</p><h1>异常与恢复</h1><p>不新增导航，只在原页面解释影响范围和下一步动作。</p></header><div className="exception-grid-v5">{cards.map(function(card,index){ return <article key={card[0]}><header><span>{card[0]} · {card[1]}</span><b className={index === 2 || index === 3 ? "waiting" : ""}>{index === 2 ? "自动恢复" : index === 3 ? "部分可用" : "需要处理"}</b></header><div><span className={"exception-art-v5 art-" + index}>{index === 2 ? "↻" : index === 3 ? "½" : index === 4 ? "0" : "!"}</span><strong>{card[2]}</strong><p>{card[3]}</p><button className={index === 5 ? "primary-button" : "quiet-button"} onClick={index === 5 ? onAddSource : function(){ onToast(card[4] + "（原型）"); }}>{card[4]}</button></div></article>; })}</div></div></main>;
}

function OnboardingPageV5({ onComplete, onBack }) {
  const [step, setStep] = useState(1);
  const [markets, setMarkets] = useState(["美股", "原油"]);
  const [chosenSources, setChosenSources] = useState(["qinbafrank", "marketmemo"]);
  const [assets, setAssets] = useState(["WTI", "NVDA"]);
  const [frequency, setFrequency] = useState("重要变化");
  const [customSource, setCustomSource] = useState("");
  const [showSourceInput, setShowSourceInput] = useState(false);
  const [assetQuery, setAssetQuery] = useState("");
  const total = 5;
  function toggle(list, setList, value){ setList(list.includes(value) ? list.filter(function(item){ return item !== value; }) : list.concat(value)); }
  function addCustomSource(){ const clean = customSource.trim().replace("@", ""); if (!clean) return; setChosenSources(function(current){ return current.concat(clean); }); setCustomSource(""); setShowSourceInput(false); }
  function addAsset(){ const clean = assetQuery.trim().toUpperCase(); if (!clean) return; setAssets(function(current){ return current.includes(clean) ? current : current.concat(clean); }); setAssetQuery(""); }
  return <main className="onboarding-v4" data-screen-label="首次使用引导闭环版">
    <header className="onboarding-head-v4"><div className="brand"><span className="brand-mark"></span><div><strong>Signal</strong><span>Setup</span></div></div><button onClick={onBack}>返回登录</button></header><div className="onboarding-progress-v4"><span style={{width:(step / total * 100) + "%"}}></span></div>
    <section className="onboarding-stage-v4"><p className="eyebrow">步骤 {step} / {total}</p>
      {step === 1 && <div className="onboarding-content-v4"><h1>你主要关注哪些市场？</h1><p>用于筛选相关观点，不会限制之后的搜索。</p><div className="choice-grid-v4">{["A股","港股","美股","原油","黄金","加密货币"].map(function(item){ return <button className={markets.includes(item) ? "selected" : ""} key={item} onClick={function(){ toggle(markets,setMarkets,item); }}><Icon name="watch" size={17} /><strong>{item}</strong><span>{item === "原油" ? "WTI / CL" : item === "黄金" ? "XAU" : "投资观点"}</span></button>; })}</div></div>}
      {step === 2 && <div className="onboarding-content-v4"><h1>先关注几位信息源</h1><p>建议从 2～5 位开始，数量越多不代表情报越好。</p><div className="source-choice-list-v4">{sources.slice(0,3).map(function(source){ return <button className={chosenSources.includes(source.id) ? "selected" : ""} key={source.id} onClick={function(){ toggle(chosenSources,setChosenSources,source.id); }}><span className="source-avatar">{source.initials}</span><div><strong>{source.name}</strong><small>@{source.handle} · {source.focus.join(" · ")}</small></div><span>{chosenSources.includes(source.id) ? "已选择" : "选择"}</span></button>; })}{chosenSources.filter(function(id){ return !sources.some(function(source){ return source.id === id; }); }).map(function(id){ return <button className="selected" key={id}><span className="source-avatar">{id.slice(0,2).toUpperCase()}</span><div><strong>@{id}</strong><small>自定义 Twitter Handle</small></div><span>已添加</span></button>; })}{showSourceInput ? <div className="inline-add-v5"><span>@</span><input autoFocus value={customSource} onChange={function(event){ setCustomSource(event.target.value); }} placeholder="username" /><button onClick={addCustomSource}>添加</button></div> : <button className="source-choice-list-v4-add" onClick={function(){ setShowSourceInput(true); }}><Icon name="plus" size={16} />输入其他 Twitter Handle</button>}</div></div>}
      {step === 3 && <div className="onboarding-content-v4"><h1>添加你正在关注的标的</h1><p>系统只聚合这些标的的博主观点。</p><div className="asset-choice-v4">{["WTI","NVDA","0700.HK","BTC","XAU"].map(function(item){ return <button className={assets.includes(item) ? "selected" : ""} key={item} onClick={function(){ toggle(assets,setAssets,item); }}><strong>{item}</strong><span>{assets.includes(item) ? "已关注" : "添加"}</span></button>; })}{assets.filter(function(item){ return !["WTI","NVDA","0700.HK","BTC","XAU"].includes(item); }).map(function(item){ return <button className="selected" key={item}><strong>{item}</strong><span>已关注</span></button>; })}</div><div className="onboarding-search-v4 onboarding-search-action-v5"><Icon name="search" size={16} /><input value={assetQuery} onChange={function(event){ setAssetQuery(event.target.value); }} placeholder="输入其他股票或商品代码" /><button onClick={addAsset}>添加</button></div></div>}
      {step === 4 && <div className="onboarding-content-v4"><h1>什么时候提醒你？</h1><p>默认只提醒有意义的观点变化。</p><div className="frequency-options-v4">{["重要变化","每日摘要","全部关闭"].map(function(item){ return <button className={frequency === item ? "selected" : ""} key={item} onClick={function(){ setFrequency(item); }}><span className="radio-v4"></span><div><strong>{item}</strong><small>{item === "重要变化" ? "观点反转、共识变化和验证完成" : item === "每日摘要" ? "每天固定时间汇总" : "仍可在今日页面查看"}</small></div></button>; })}</div></div>}
      {step === 5 && <div className="onboarding-content-v4 onboarding-ready-v4"><span className="ready-mark-v4"><Icon name="check" size={28} /></span><h1>你的情报工作台准备好了</h1><p>后台正在采集并分析首批推文，完成后自动更新。</p><div className="setup-summary-v4"><div><strong>{markets.length}</strong><span>关注市场</span></div><div><strong>{chosenSources.length}</strong><span>信息源</span></div><div><strong>{assets.length}</strong><span>关注标的</span></div></div><ul><li><Icon name="check" size={14} />账号身份将在入队前核对</li><li><Icon name="check" size={14} />文本、Thread 和图片联合分析</li><li><Icon name="check" size={14} />失败任务会解释原因并自动重试</li></ul></div>}
      <footer className="onboarding-actions-v4"><button className="quiet-button" disabled={step === 1} onClick={function(){ setStep(Math.max(1,step-1)); }}>上一步</button>{step < total ? <button className="primary-button" onClick={function(){ setStep(step+1); }}>继续</button> : <button className="primary-button" onClick={onComplete}>进入今日情报</button>}</footer>
    </section>
  </main>;
}

function ReviewLauncherV5({ onOpen }) { return <button className="review-launcher-v4 review-launcher-v5" onClick={onOpen}><span>V5</span>完整闭环审核</button>; }

function ReviewMapV5({ onClose, onNavigate, onOpenSearch, onOpenNotifications }) {
  const groups = [
    { title:"首次体验", items:[["auth","登录 / 注册 / 找回"],["onboarding","首次使用引导"],["exceptions","异常与恢复"]] },
    { title:"一级页面", items:[["today","今日"],["sources","信息源"],["watch","关注"],["assistant","助手全状态"]] },
    { title:"证据详情", items:[["insight","情报 / Thread / 多图"],["profile","博主档案与设置"],["asset","标的详情"],["prediction","预测四种状态"]] },
    { title:"系统入口", items:[["search","搜索与无结果"],["notifications","提醒中心"],["settings","账户四个设置区"]] }
  ];
  function choose(id){ if (id === "search") onOpenSearch(); else if (id === "notifications") onOpenNotifications(); else onNavigate(id); }
  return <div className="system-backdrop review-backdrop-v4" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}><section className="review-map-v4 review-map-v5" role="dialog" aria-label="v5 完整闭环审核"><header><div><p className="eyebrow">Prototype review map</p><h2>v5 完整闭环审核</h2><span>14 组页面与状态 · 不增加主导航</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header><div className="review-groups-v4">{groups.map(function(group){ return <section key={group.title}><span>{group.title}</span><div>{group.items.map(function(item){ return <button key={item[0]} onClick={function(){ choose(item[0]); }}><strong>{item[1]}</strong><small>{item[0] === "search" || item[0] === "notifications" ? "弹层" : "页面"} · 已闭环</small><Icon name="arrow" size={15} /></button>; })}</div></section>; })}</div><footer><span>建议先审核助手、情报详情和预测状态，再检查管理操作。</span><button className="primary-button" onClick={function(){ choose("assistant"); }}>从助手开始</button></footer></section></div>;
}
Object.assign(window, {
  AddSourceModalV5,
  AddAssetModalV5,
  SourceControlsV5,
  BloggerProfilePageV5,
  WatchDetailPanelV5,
  WatchPageV5,
  AssetDetailPageV5,
  SearchOverlayV5,
  SettingsPageV5,
  AuthPageV5,
  OnboardingPageV5,
  ExceptionStatesPageV5,
  ReviewLauncherV5,
  ReviewMapV5
});
