const { useMemo, useState } = React;

const notificationSeed = [
  { id: 1, kind: "观点升温", title: "WTI 的博主共识由观察转为偏多", detail: "3 位关注博主在过去 24 小时更新了判断。", time: "18 分钟前", target: "asset", unread: true },
  { id: 2, kind: "重要观点", title: "@qinbafrank 发布新的原油判断", detail: "供应风险重新成为影响风险资产的关键变量。", time: "46 分钟前", target: "insight", unread: true },
  { id: 3, kind: "观点分歧", title: "BTC 的方向分歧正在扩大", detail: "价格强势与杠杆风险同时增加。", time: "2 小时前", target: "asset", unread: true },
  { id: 4, kind: "验证完成", title: "一条 WTI 预测完成行情验证", detail: "结果为未命中，已写入博主历史记录。", time: "昨天", target: "prediction", unread: false }
];

function SearchOverlay({ onClose, onOpenInsight, onOpenProfile, onOpenAsset }) {
  const [query, setQuery] = useState("原油");
  const hasQuery = query.trim().length > 0;
  return <div className="system-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <section className="search-overlay-v4" role="dialog" aria-label="全局搜索">
      <header className="search-head-v4"><Icon name="search" size={19} /><input autoFocus value={query} onChange={function(event){ setQuery(event.target.value); }} placeholder="搜索博主、标的或观点" /><kbd>ESC</kbd><button onClick={onClose} aria-label="关闭搜索"><Icon name="close" size={18} /></button></header>
      {hasQuery ? <div className="search-results-v4">
        <p className="result-summary">找到与“{query}”相关的 6 条结果</p>
        <section className="result-group-v4"><div className="result-group-head"><strong>标的</strong><span>1</span></div><button className="search-result-row" onClick={function(){ onOpenAsset(watchlist[0]); }}><span className="result-symbol">WTI</span><div><strong>WTI 原油连续合约</strong><small>3 位关注博主 · 今天 3 条更新</small></div><span className="direction bullish">偏多</span><Icon name="arrow" size={16} /></button></section>
        <section className="result-group-v4"><div className="result-group-head"><strong>信息源</strong><span>1</span></div><button className="search-result-row" onClick={function(){ onOpenProfile(sources[0]); }}><span className="source-avatar">QF</span><div><strong>秦爸 Frank <i>@qinbafrank</i></strong><small>宏观 · 原油 · 美股</small></div><span className="result-note">18 条推文</span><Icon name="arrow" size={16} /></button></section>
        <section className="result-group-v4"><div className="result-group-head"><strong>观点与证据</strong><span>4</span></div><button className="search-result-row result-insight" onClick={function(){ onOpenInsight(signals[0]); }}><span className="result-symbol">WTI</span><div><strong>原油供应风险重新计价，80 美元成为短期观察位</strong><small>@qinbafrank · 18 分钟前 · 3 条证据</small></div><Icon name="arrow" size={16} /></button><button className="search-result-row result-insight" onClick={function(){ onOpenInsight(signals[0]); }}><span className="result-symbol">宏观</span><div><strong>油价与美债收益率同步上行可能压制风险资产</strong><small>@marketmemo · 3 小时前</small></div><Icon name="arrow" size={16} /></button></section>
      </div> : <div className="search-empty-v4"><span>最近搜索</span><div><button onClick={function(){ setQuery("原油"); }}>原油供应风险</button><button onClick={function(){ setQuery("qinbafrank"); }}>@qinbafrank</button><button onClick={function(){ setQuery("NVDA"); }}>NVDA</button></div><p>可搜索博主、标的、推文原文和历史观点。</p></div>}
      <footer className="search-footer-v4"><span>↑↓ 选择</span><span>Enter 打开</span><span>结果只来自已采集内容</span></footer>
    </section>
  </div>;
}

function NotificationCenter({ onClose, onNavigate }) {
  const [filter, setFilter] = useState("unread");
  const [readIds, setReadIds] = useState([]);
  const items = notificationSeed.filter(function(item){ return filter === "all" || (item.unread && !readIds.includes(item.id)); });
  function markAll(){ setReadIds(notificationSeed.map(function(item){ return item.id; })); }
  return <div className="notification-backdrop" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <aside className="notification-panel-v4" aria-label="提醒中心">
      <header className="notification-head-v4"><div><p className="eyebrow">Activity</p><h2>提醒</h2></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      <div className="notification-toolbar-v4"><div><button className={filter === "unread" ? "active" : ""} onClick={function(){ setFilter("unread"); }}>未读</button><button className={filter === "all" ? "active" : ""} onClick={function(){ setFilter("all"); }}>全部</button></div><button onClick={markAll}>全部已读</button></div>
      <div className="notification-list-v4">{items.length ? items.map(function(item){
        const isUnread = item.unread && !readIds.includes(item.id);
        return <button className={"notification-item-v4 " + (isUnread ? "unread" : "")} key={item.id} onClick={function(){ setReadIds(function(current){ return current.concat(item.id); }); onNavigate(item.target); }}>
          <span className="notification-dot"></span><div><span>{item.kind} · {item.time}</span><strong>{item.title}</strong><p>{item.detail}</p></div><Icon name="arrow" size={16} />
        </button>;
      }) : <div className="notification-empty-v4"><span className="assistant-orb"><Icon name="check" size={18} /></span><strong>没有未读提醒</strong><p>重要观点和验证结果会出现在这里。</p></div>}</div>
      <footer className="notification-footer-v4"><button onClick={function(){ onNavigate("settings"); }}>提醒设置</button><span>只提醒重要变化，避免打扰。</span></footer>
    </aside>
  </div>;
}

function AuthPage({ onContinue, onStartOnboarding }) {
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  return <main className="auth-v4" data-screen-label="登录注册">
    <section className="auth-story-v4"><div className="auth-brand-v4"><span className="brand-mark"></span><strong>Signal</strong></div><div><p>Twitter investment intelligence</p><h1>关注观点变化，<br />而不是信息噪音。</h1><span>从博主推文、图片和历史结果中提取可追溯、可验证的投资情报。</span></div><footer><span>证据可回溯</span><span>标的已核验</span><span>预测可验证</span></footer></section>
    <section className="auth-form-v4">
      <div className="auth-form-inner-v4">
        <div className="auth-tabs-v4"><button className={mode === "login" ? "active" : ""} onClick={function(){ setMode("login"); }}>登录</button><button className={mode === "register" ? "active" : ""} onClick={function(){ setMode("register"); }}>注册</button></div>
        <h2>{mode === "login" ? "欢迎回来" : "创建个人情报工作台"}</h2>
        <p>{mode === "login" ? "继续查看你关注的博主和标的。" : "两分钟建立你的第一份 Twitter 情报流。"}</p>
        <label className="auth-field-v4"><span>邮箱</span><input placeholder="name@example.com" defaultValue="arjun@example.com" /></label>
        {mode === "register" && <label className="auth-field-v4"><span>用户名</span><input placeholder="你的称呼" /></label>}
        <label className="auth-field-v4"><span>密码</span><div><input type={showPassword ? "text" : "password"} defaultValue="prototype123" /><button onClick={function(){ setShowPassword(!showPassword); }} type="button">{showPassword ? "隐藏" : "显示"}</button></div></label>
        {mode === "login" && <button className="forgot-v4">忘记密码？</button>}
        <button className="auth-submit-v4" onClick={mode === "login" ? onContinue : onStartOnboarding}>{mode === "login" ? "进入工作台" : "创建账户"}</button>
        <small>继续即表示你同意服务条款和隐私政策。平台内容不构成投资建议。</small>
      </div>
    </section>
  </main>;
}

function OnboardingPage({ onComplete, onBack }) {
  const [step, setStep] = useState(1);
  const [markets, setMarkets] = useState(["美股", "原油"]);
  const [chosenSources, setChosenSources] = useState(["qinbafrank", "marketmemo"]);
  const [assets, setAssets] = useState(["WTI", "NVDA"]);
  const [frequency, setFrequency] = useState("重要变化");
  const total = 5;
  function toggle(list, setList, value){ setList(list.includes(value) ? list.filter(function(item){ return item !== value; }) : list.concat(value)); }
  return <main className="onboarding-v4" data-screen-label="首次使用引导">
    <header className="onboarding-head-v4"><div className="brand"><span className="brand-mark"></span><div><strong>Signal</strong><span>Setup</span></div></div><button onClick={onBack}>返回登录</button></header>
    <div className="onboarding-progress-v4"><span style={{width:(step / total * 100) + "%"}}></span></div>
    <section className="onboarding-stage-v4">
      <p className="eyebrow">步骤 {step} / {total}</p>
      {step === 1 && <div className="onboarding-content-v4"><h1>你主要关注哪些市场？</h1><p>用于筛选相关观点，不会限制你之后搜索其他市场。</p><div className="choice-grid-v4">{["A股","港股","美股","原油","黄金","加密货币"].map(function(item){ return <button className={markets.includes(item) ? "selected" : ""} key={item} onClick={function(){ toggle(markets,setMarkets,item); }}><Icon name="watch" size={17} /><strong>{item}</strong><span>{item === "原油" ? "WTI / CL" : item === "黄金" ? "XAU" : "投资观点"}</span></button>; })}</div></div>}
      {step === 2 && <div className="onboarding-content-v4"><h1>先关注几位信息源</h1><p>建议从 2～5 位开始，数量越多不代表情报越好。</p><div className="source-choice-list-v4">{sources.slice(0,3).map(function(source){ return <button className={chosenSources.includes(source.id) ? "selected" : ""} key={source.id} onClick={function(){ toggle(chosenSources,setChosenSources,source.id); }}><span className="source-avatar">{source.initials}</span><div><strong>{source.name}</strong><small>@{source.handle} · {source.focus.join(" · ")}</small></div><span>{chosenSources.includes(source.id) ? "已选择" : "选择"}</span></button>; })}<button className="source-choice-list-v4-add"><Icon name="plus" size={16} />输入其他 Twitter Handle</button></div></div>}
      {step === 3 && <div className="onboarding-content-v4"><h1>添加你正在关注的标的</h1><p>系统只聚合这些标的的博主观点，不会变成行情面板。</p><div className="asset-choice-v4">{["WTI","NVDA","0700.HK","BTC","XAU"].map(function(item){ return <button className={assets.includes(item) ? "selected" : ""} key={item} onClick={function(){ toggle(assets,setAssets,item); }}><strong>{item}</strong><span>{assets.includes(item) ? "已关注" : "添加"}</span></button>; })}</div><label className="onboarding-search-v4"><Icon name="search" size={16} /><input placeholder="搜索其他股票、商品或加密货币" /></label></div>}
      {step === 4 && <div className="onboarding-content-v4"><h1>什么时候提醒你？</h1><p>默认只提醒有意义的观点变化，避免把产品变成另一个消息轰炸器。</p><div className="frequency-options-v4">{["重要变化","每日摘要","全部关闭"].map(function(item){ return <button className={frequency === item ? "selected" : ""} key={item} onClick={function(){ setFrequency(item); }}><span className="radio-v4"></span><div><strong>{item}</strong><small>{item === "重要变化" ? "共识形成、观点反转、验证完成" : item === "每日摘要" ? "每天固定时间汇总一次" : "仍可在今日页面查看"}</small></div></button>; })}</div></div>}
      {step === 5 && <div className="onboarding-content-v4 onboarding-ready-v4"><span className="ready-mark-v4"><Icon name="check" size={28} /></span><h1>你的情报工作台准备好了</h1><p>后台正在采集并分析首批推文，预计几分钟后出现第一批情报。</p><div className="setup-summary-v4"><div><strong>{markets.length}</strong><span>关注市场</span></div><div><strong>{chosenSources.length}</strong><span>信息源</span></div><div><strong>{assets.length}</strong><span>关注标的</span></div></div><ul><li><Icon name="check" size={14} />博主资料已加入采集队列</li><li><Icon name="check" size={14} />文本和图片将自动分析</li><li><Icon name="check" size={14} />第一份摘要生成后通知你</li></ul></div>}
      <footer className="onboarding-actions-v4"><button className="quiet-button" disabled={step === 1} onClick={function(){ setStep(Math.max(1,step-1)); }}>上一步</button>{step < total ? <button className="primary-button" onClick={function(){ setStep(step+1); }}>继续</button> : <button className="primary-button" onClick={onComplete}>进入今日情报</button>}</footer>
    </section>
  </main>;
}

function LifecycleStatesPage({ onBack }) {
  return <main className="page" data-screen-label="状态设计">
    <div className="deep-page">
      <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回今日</button>
      <header className="state-page-head-v4"><p className="eyebrow">System states</p><h1>状态设计</h1><p>这些状态出现在原页面中，不新增导航，也不让用户猜测系统是否仍在工作。</p></header>
      <div className="state-spec-grid-v4">
        <article className="state-spec-card-v4"><span>01 · 空状态</span><div className="state-preview-v4"><span className="empty-radar"><i></i></span><strong>还没有今日情报</strong><p>添加信息源后，重要观点会出现在这里。</p><button className="primary-button">新增信息源</button></div><footer>明确下一步，不只显示“暂无数据”。</footer></article>
        <article className="state-spec-card-v4"><span>02 · 首次采集</span><div className="state-preview-v4"><span className="progress-ring-v4">38%</span><strong>正在整理 @qinbafrank</strong><p>已获取资料，正在采集历史推文和图片。</p><div className="mini-progress-v4"><i style={{width:"38%"}}></i></div></div><footer>显示阶段、进度和预期结果。</footer></article>
        <article className="state-spec-card-v4"><span>03 · 分析处理中</span><div className="state-preview-v4"><span className="processing-bars-v4"><i></i><i></i><i></i></span><strong>正在提取投资观点</strong><p>文本已完成，正在识别 2 张关联图片。</p><small>你可以离开，完成后会自动更新。</small></div><footer>任务异步运行，不阻塞用户。</footer></article>
        <article className="state-spec-card-v4"><span>04 · 可恢复失败</span><div className="state-preview-v4 error"><span className="error-mark-v4">!</span><strong>这条推文暂时分析失败</strong><p>原文和图片均已保存，没有丢失数据。</p><button className="quiet-button">重新分析</button></div><footer>解释影响范围，提供明确恢复动作。</footer></article>
      </div>
    </div>
  </main>;
}

function PredictionDetailPage({ onBack }) {
  return <main className="page" data-screen-label="预测验证详情">
    <div className="deep-page">
      <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回历史验证</button>
      <div className="deep-layout">
        <article className="deep-main">
          <header className="prediction-hero-v4"><div className="hero-tags"><span className="direction bullish">看多</span><span>短期</span><span>·</span><span>@qinbafrank</span></div><h1>WTI 供应风险可能推动价格继续走高</h1><p>发布于 2026年8月11日 · 验证窗口已结束</p></header>
          <section className="prediction-verdict-v4 incorrect"><span className="verdict-mark-v4">×</span><div><span>自动验证结果</span><h2>未命中</h2><p>验证窗口结束时，价格相对起始价下跌 2.1%，不满足短期看多规则。</p></div></section>
          <section className="analysis-section"><div className="section-heading-v3"><h2>行情路径</h2><span>使用完成日线，不使用盘中未完成价格</span></div><div className="price-path-v4"><div className="price-path-head-v4"><div><span>起始价</span><strong>$79.84</strong><small>8月12日开盘后</small></div><div><span>验证价</span><strong>$78.16</strong><small>8月18日收盘</small></div><div><span>区间变化</span><strong className="negative-value-v4">−2.1%</strong><small>低于判定阈值</small></div></div><div className="price-chart-v4"><span className="price-chart-line-v4"></span><i className="chart-start-v4">79.84</i><i className="chart-end-v4">78.16</i></div></div></section>
          <section className="analysis-section"><div className="section-heading-v3"><h2>为什么这样判定</h2><span>规则可解释</span></div><div className="rule-steps-v4"><div><b>1</b><span><strong>识别预测方向</strong><small>博主本人观点 · WTI · 看多 · 短期</small></span></div><div><b>2</b><span><strong>确定验证窗口</strong><small>下一个完整交易日起，5 个交易日</small></span></div><div><b>3</b><span><strong>获取行情并比较</strong><small>起始价 $79.84，结束价 $78.16</small></span></div><div><b>4</b><span><strong>应用资产阈值</strong><small>实际 −2.1%，结果判定为未命中</small></span></div></div></section>
          <section className="analysis-section"><div className="section-heading-v3"><h2>审计记录</h2><span>所有修正都会保留</span></div><div className="audit-record-v4"><div><time>8月11日 21:04</time><p>从推文创建预测，标的身份核验为 WTI 商品。</p></div><div><time>8月18日 16:30</time><p>行情窗口成熟，自动验证任务完成。</p></div><div><time>8月18日 16:31</time><p>结果写入博主统计；未发生人工修正。</p></div></div></section>
        </article>
        <aside className="deep-aside">
          <section className="aside-card-v3"><span>预测身份</span><div className="aside-facts"><div>标的<strong>WTI 原油</strong></div><div>方向<strong>看多</strong></div><div>期限<strong>短期</strong></div><div>结果<strong className="negative-value-v4">未命中</strong></div></div></section>
          <section className="aside-card-v3"><span>统计影响</span><h3>计入博主历史结果</h3><p>该预测满足作者归属、方向、期限和标的核验要求，因此进入命中率统计。</p></section>
          <section className="aside-card-v3"><span>数据来源</span><p>行情来自正式数据提供方；原始推文、分析版本和验证尝试均保留审计记录。</p></section>
          <div className="deep-aside-actions"><button className="quiet-button">查看原推文</button><button className="primary-button">查看博主档案</button></div>
        </aside>
      </div>
    </div>
  </main>;
}

function SettingsPage({ onBack }) {
  const [important, setImportant] = useState(true);
  const [digest, setDigest] = useState(false);
  const [timezone, setTimezone] = useState("Asia/Shanghai");
  return <main className="page" data-screen-label="账户设置">
    <div className="settings-page-v4">
      <button className="back-link" onClick={onBack}><Icon name="arrow" size={14} />返回工作台</button>
      <header className="state-page-head-v4"><p className="eyebrow">Preferences</p><h1>账户与偏好</h1><p>只保留影响情报范围和提醒方式的必要设置。</p></header>
      <div className="settings-layout-v4">
        <nav className="settings-nav-v4"><button className="active">个人偏好</button><button>提醒</button><button>静音列表</button><button>账户安全</button></nav>
        <section className="settings-content-v4">
          <div className="settings-section-v4"><h2>个人资料</h2><div className="account-row-v4"><span className="avatar">AR</span><div><strong>Arjun</strong><small>arjun@example.com</small></div><button className="quiet-button">编辑</button></div></div>
          <div className="settings-section-v4"><h2>关注市场</h2><p>用于首页筛选和助手默认回答范围。</p><div className="settings-chips-v4"><button>A股</button><button>港股</button><button className="selected">美股</button><button className="selected">原油</button><button>黄金</button><button>加密货币</button></div></div>
          <div className="settings-section-v4"><h2>提醒方式</h2><div className="setting-row-v4"><div><strong>重要变化</strong><span>共识形成、观点反转和验证完成</span></div><button className={"toggle-v4 " + (important ? "on" : "")} onClick={function(){ setImportant(!important); }}><i></i></button></div><div className="setting-row-v4"><div><strong>每日摘要</strong><span>每天 18:00 汇总当天重要内容</span></div><button className={"toggle-v4 " + (digest ? "on" : "")} onClick={function(){ setDigest(!digest); }}><i></i></button></div></div>
          <div className="settings-section-v4"><h2>时间与语言</h2><label className="settings-select-v4"><span>时区</span><select value={timezone} onChange={function(event){ setTimezone(event.target.value); }}><option>Asia/Shanghai</option><option>America/New_York</option><option>Europe/London</option></select></label><label className="settings-select-v4"><span>语言</span><select defaultValue="简体中文"><option>简体中文</option><option>English</option></select></label></div>
          <div className="settings-section-v4 danger-zone-v4"><h2>账户</h2><button>退出登录</button><span>删除账户需要再次确认，不会出现在主操作路径中。</span></div>
        </section>
      </div>
    </div>
  </main>;
}

function ReviewLauncher({ onOpen }) {
  return <button className="review-launcher-v4" onClick={onOpen}><span>V4</span>整体页面审核</button>;
}

function ReviewMap({ onClose, onNavigate, onOpenSearch, onOpenNotifications }) {
  const groups = [
    { title: "首次体验", items: [["auth","登录 / 注册"],["onboarding","首次使用引导"],["states","空与任务状态"]] },
    { title: "一级页面", items: [["today","今日"],["sources","信息源"],["watch","关注"],["assistant","助手"]] },
    { title: "二级详情", items: [["insight","情报详情"],["profile","博主档案"],["asset","标的详情"],["prediction","预测验证详情"]] },
    { title: "系统入口", items: [["search","全局搜索"],["notifications","提醒中心"],["settings","账户与偏好"]] }
  ];
  function choose(id){
    if (id === "search") onOpenSearch();
    else if (id === "notifications") onOpenNotifications();
    else onNavigate(id);
  }
  return <div className="system-backdrop review-backdrop-v4" onMouseDown={function(event){ if (event.target === event.currentTarget) onClose(); }}>
    <section className="review-map-v4" role="dialog" aria-label="整体页面审核">
      <header><div><p className="eyebrow">Prototype review map</p><h2>整体页面审核</h2><span>14 组 C 端页面与状态 · 套餐和后台暂缓</span></div><button className="detail-close" onClick={onClose}><Icon name="close" size={18} /></button></header>
      <div className="review-groups-v4">{groups.map(function(group){ return <section key={group.title}><span>{group.title}</span><div>{group.items.map(function(item){ return <button key={item[0]} onClick={function(){ choose(item[0]); }}><strong>{item[1]}</strong><small>{item[0] === "search" || item[0] === "notifications" ? "弹层" : "页面"} · 已设计</small><Icon name="arrow" size={15} /></button>; })}</div></section>; })}</div>
      <footer><span>审核建议：先看首次体验，再按一级页面进入对应详情。</span><button className="primary-button" onClick={function(){ choose("today"); }}>从今日开始</button></footer>
    </section>
  </div>;
}

Object.assign(window, {
  SearchOverlay,
  NotificationCenter,
  AuthPage,
  OnboardingPage,
  LifecycleStatesPage,
  PredictionDetailPage,
  SettingsPage,
  ReviewLauncher,
  ReviewMap
});
