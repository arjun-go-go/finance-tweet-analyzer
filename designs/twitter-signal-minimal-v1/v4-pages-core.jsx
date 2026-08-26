const { useMemo, useState } = React;

function Sidebar({ view, setView, onSettings }) {
      const items = [
        ["today", "today", "今日", "6"],
        ["sources", "sources", "信息源", null],
        ["watch", "watch", "关注", "2"],
        ["assistant", "assistant", "助手", null]
      ];
      return <aside className="sidebar">
        <div className="brand"><span className="brand-mark"></span><div><strong>Signal</strong><span>Twitter intelligence</span></div></div>
        <nav className="nav" aria-label="主导航">
          {items.map(function(item) {
            return <button key={item[0]} className={"nav-button " + (view === item[0] ? "active" : "")} onClick={function(){ setView(item[0]); }}>
              <Icon name={item[1]} size={18} /><span>{item[2]}</span>{item[3] && <span className="nav-count">{item[3]}</span>}
            </button>;
          })}
        </nav>
        <div className="sidebar-note"><strong>只显示值得行动的信息</strong>低相关、重复和未核验内容默认折叠。</div>
        <button className="profile" onClick={onSettings}><span className="avatar">AR</span><div><strong>个人工作台</strong><span>4 个信息源 · 4 个标的</span></div><Icon name="arrow" size={14} /></button>
      </aside>;
    }

function Topbar({ onAdd, onSearch, onNotifications }) {
      return <header className="topbar">
        <span className="mobile-brand">Signal</span>
        <button className="search-trigger" aria-label="搜索情报" onClick={onSearch}><Icon name="search" size={16} /><span>搜索博主、标的或观点</span><kbd>⌘ K</kbd></button>
        <div className="top-actions">
          <button className="icon-button has-unread" aria-label="通知" onClick={onNotifications}><Icon name="bell" size={17} /></button>
          <button className="primary-button" onClick={onAdd}><Icon name="plus" size={16} /><span>信息源</span></button>
        </div>
      </header>;
    }

    function SignalItem({ item, selected, onSelect }) {
      return <button className={"signal-item " + (selected ? "selected" : "")} onClick={onSelect}>
        <span className="signal-asset"><strong>{item.symbol}</strong><span className={"direction " + item.direction}>{item.directionLabel}</span></span>
        <span className="signal-copy">
          <span className="signal-meta"><span className="source-name">@{item.author}</span><span>·</span><span>{item.time}</span><span>·</span><span>{item.category}</span><span className="verified"><Icon name="check" size={12} /> 标的已核验</span></span>
          <h3>{item.title}</h3>
          <p>{item.summary}</p>
          <span className="signal-foot"><span><Icon name="evidence" size={13} /> {item.evidenceCount} 条证据</span>{item.imageCount > 0 && <span><Icon name="image" size={13} /> {item.imageCount} 张图片</span>}<span>与你关注的标的相关</span></span>
        </span>
        <span className="signal-arrow"><Icon name="arrow" size={18} /></span>
      </button>;
    }

    function DetailPanel({ item, onClose, onOpenDetail }) {
      return <aside className="detail-panel" aria-label="情报证据详情">
        <div className="detail-head"><div><Icon name="evidence" size={16} /> 判断依据</div><button className="detail-close" onClick={onClose} aria-label="关闭详情"><Icon name="close" size={17} /></button></div>
        <div className="detail-body">
          <div className="detail-kicker"><span className={"direction " + item.direction}>{item.directionLabel}</span><span>@{item.author}</span><span>·</span><span>{item.time}</span></div>
          <h2>{item.title}</h2>
          <p className="detail-thesis">{item.thesis}</p>
          <section className="detail-section"><span>原文证据</span><blockquote className="evidence-quote">“{item.evidence}”</blockquote></section>
          <section className="detail-section"><span>标的身份</span><div className="identity-row"><div><strong>{item.symbol}</strong><span>{item.assetName}</span></div><div className="identity-check">✓ {item.identity}</div></div></section>
          <section className="detail-section"><span>继续关注什么</span><ul className="detail-list">{item.points.map(function(point){ return <li key={point}>{point}</li>; })}</ul></section>
          <div className="detail-actions"><button className="quiet-button">查看原推文</button><button className="primary-button" onClick={function(){ onOpenDetail(item); }}>完整分析</button></div>
        </div>
      </aside>;
    }

    function TodayPage({ onOpenDetail }) {
      const [selectedId, setSelectedId] = useState(function(){ return window.innerWidth > 1080 ? 1 : null; });
      const [filter, setFilter] = useState("related");
      const selected = signals.find(function(item){ return item.id === selectedId; });
      const visibleSignals = useMemo(function(){
        if (filter === "watch") return signals.filter(function(item){ return ["WTI", "NVDA", "0700.HK"].includes(item.symbol); });
        if (filter === "latest") return signals.slice().reverse();
        return signals;
      }, [filter]);
      return <>
        {selected && <div className="mobile-detail-backdrop" onClick={function(){ setSelectedId(null); }}></div>}
        <main className="page with-detail" data-screen-label="今日情报">
          <section className="page-main">
            <header className="page-heading"><div><p className="eyebrow">8月26日 · 星期三</p><h1>今天</h1><p>6 条值得看，其中 2 条与你的关注标的直接相关。</p></div><div className="freshness"><span className="live-dot"></span>刚刚更新</div></header>
            <section className="priority-brief"><span>现在最重要</span><h2>原油供应风险重新成为影响风险资产的关键变量</h2><p>来自 3 条独立证据，与你关注的 WTI 和美股相关。</p></section>
            <div className="feed-toolbar">
              <button className={"feed-filter " + (filter === "related" ? "active" : "")} onClick={function(){ setFilter("related"); }}>与你相关</button>
              <button className={"feed-filter " + (filter === "latest" ? "active" : "")} onClick={function(){ setFilter("latest"); }}>最新</button>
              <button className={"feed-filter " + (filter === "watch" ? "active" : "")} onClick={function(){ setFilter("watch"); }}>仅关注标的</button>
              <span className="feed-count">{visibleSignals.length} 条</span>
            </div>
            <div className="feed-list">{visibleSignals.map(function(item){ return <SignalItem key={item.id} item={item} selected={selectedId === item.id} onSelect={function(){ setSelectedId(item.id); }} />; })}</div>
          </section>
          {selected && <DetailPanel item={selected} onClose={function(){ setSelectedId(null); }} onOpenDetail={onOpenDetail} />}
        </main>
      </>;
    }

    function SourceDetailPanel({ source, paused, onToggle, onClose, onOpenProfile }) {
      return <aside className="detail-panel" aria-label="信息源详情">
        <div className="detail-head"><div><Icon name="sources" size={16} /> 来源档案</div><button className="detail-close" onClick={onClose} aria-label="关闭信息源详情"><Icon name="close" size={17} /></button></div>
        <div className="detail-body">
          <div className="source-profile-identity">
            <span className="source-avatar">{source.initials}</span>
            <div><h2>{source.name}</h2><p>@{source.handle}</p></div>
            <span className={"source-profile-status " + (paused ? "paused" : "")}><i></i>{paused ? "已暂停" : "采集中"}</span>
          </div>
          <p className="source-bio-v2">{source.bio}</p>
          <div className="focus-tags">{source.focus.map(function(item){ return <span key={item}>{item}</span>; })}</div>
          <section className="detail-section">
            <span>内容质量</span>
            <div className="source-facts-v2">
              <div><strong>{source.collected}</strong><span>已采集推文</span></div>
              <div><strong>{source.relevant}%</strong><span>投资相关</span></div>
              <div><strong>—</strong><span>{source.quality}</span></div>
            </div>
          </section>
          <section className="detail-section"><span>最近提取</span><div className="latest-extraction"><small>{source.latestType}</small><strong>{source.latest}</strong></div></section>
          <section className="detail-section"><span>采集设置</span><div className="identity-row"><div><strong>{paused ? "当前暂停" : source.fetch}</strong><span>只采集公开推文与关联图片</span></div><div className="identity-check">{source.update}</div></div></section>
          <div className="detail-actions"><button className="quiet-button" onClick={function(){ onOpenProfile(source); }}>完整档案</button><button className="primary-button" onClick={onToggle}>{paused ? "恢复采集" : "暂停采集"}</button></div>
        </div>
      </aside>;
    }

    function SourcesPage({ onAdd, onOpenProfile }) {
      const [selectedId, setSelectedId] = useState(function(){ return window.innerWidth > 1080 ? sources[0].id : null; });
      const [filter, setFilter] = useState("all");
      const [overrides, setOverrides] = useState({});
      function isPaused(source) { return Object.prototype.hasOwnProperty.call(overrides, source.id) ? overrides[source.id] : source.status === "已暂停"; }
      const selected = sources.find(function(source){ return source.id === selectedId; });
      const visible = sources.filter(function(source){
        if (filter === "active") return !isPaused(source);
        if (filter === "paused") return isPaused(source);
        return true;
      });
      return <>
        {selected && <div className="mobile-detail-backdrop" onClick={function(){ setSelectedId(null); }}></div>}
        <main className="page with-detail" data-screen-label="信息源">
          <section className="page-main">
            <header className="page-heading"><div><p className="eyebrow">Twitter sources</p><h1>信息源</h1><p>只保留值得长期观察的人，不把博主数量当作目标。</p></div><button className="primary-button" onClick={onAdd}><Icon name="plus" size={16} />新增信息源</button></header>
            <div className="page-note"><span><i className="live-dot"></i><strong>3 个来源正常采集</strong>，1 个已暂停</span><span>最近同步：18 分钟前</span></div>
            <div className="library-toolbar">
              <button className={"feed-filter " + (filter === "all" ? "active" : "")} onClick={function(){ setFilter("all"); }}>全部</button>
              <button className={"feed-filter " + (filter === "active" ? "active" : "")} onClick={function(){ setFilter("active"); }}>采集中</button>
              <button className={"feed-filter " + (filter === "paused" ? "active" : "")} onClick={function(){ setFilter("paused"); }}>已暂停</button>
              <span className="feed-count">{visible.length} 位博主</span>
            </div>
            <div className="source-list-v2">
              {visible.map(function(source){
                const paused = isPaused(source);
                return <button className={"source-item-v2 " + (selectedId === source.id ? "selected" : "")} key={source.id} onClick={function(){ setSelectedId(source.id); }}>
                  <span className="source-avatar">{source.initials}</span>
                  <span className="source-main-v2"><h3>{source.name}<span>@{source.handle}</span></h3><span className="source-focus-inline">{source.focus.map(function(item){ return <span key={item}>{item}</span>; })}</span></span>
                  <span className="source-relevance"><strong>{paused ? "已暂停" : source.relevant + "%"}</strong><span>{paused ? source.update : "投资相关率"}</span></span>
                  <span className="source-row-end"><Icon name="arrow" size={17} /></span>
                </button>;
              })}
            </div>
          </section>
          {selected && <SourceDetailPanel source={selected} paused={isPaused(selected)} onToggle={function(){ setOverrides(function(current){ const next = Object.assign({}, current); next[selected.id] = !isPaused(selected); return next; }); }} onClose={function(){ setSelectedId(null); }} onOpenProfile={onOpenProfile} />}
        </main>
      </>;
    }

    function WatchDetailPanel({ item, onClose, onOpenAsset }) {
      return <aside className="detail-panel" aria-label="关注标的详情">
        <div className="detail-head"><div><Icon name="watch" size={16} /> 观点变化</div><button className="detail-close" onClick={onClose} aria-label="关闭关注标的详情"><Icon name="close" size={17} /></button></div>
        <div className="detail-body">
          <div className="watch-panel-title"><div><h2>{item.symbol}</h2><p>{item.type} · {item.activity}</p></div><span className={"direction " + item.tone}>{item.stance}</span></div>
          <p className="detail-thesis" style={{marginTop:14}}>{item.thesis}</p>
          <section className="detail-section">
            <span>关注博主观点分布</span>
            <div className="stance-summary"><div><strong>{item.positive}%</strong><span>偏多</span></div><div><strong>{item.neutral}%</strong><span>观察</span></div><div><strong>{item.negative}%</strong><span>偏空 / 风险</span></div></div>
          </section>
          <section className="detail-section"><span>最近变化</span><div className="opinion-timeline">{item.timeline.map(function(entry){ return <div className="timeline-item" key={entry.join("-")}><small>{entry[0]}</small><strong>{entry[1]}</strong><p>{entry[2]}</p></div>; })}</div></section>
          <div className="detail-actions"><button className="quiet-button">向助手追问</button><button className="primary-button" onClick={function(){ onOpenAsset(item); }}>完整标的</button></div>
        </div>
      </aside>;
    }

    function WatchPage({ onOpenAsset }) {
      const [selectedId, setSelectedId] = useState(function(){ return window.innerWidth > 1080 ? watchlist[0].id : null; });
      const selected = watchlist.find(function(item){ return item.id === selectedId; });
      return <>
        {selected && <div className="mobile-detail-backdrop" onClick={function(){ setSelectedId(null); }}></div>}
        <main className="page with-detail" data-screen-label="关注标的">
          <section className="page-main">
            <header className="page-heading"><div><p className="eyebrow">Watchlist</p><h1>关注</h1><p>不重复做行情软件，只告诉你关注博主的观点发生了什么变化。</p></div><button className="quiet-button"><Icon name="plus" size={15} />添加标的</button></header>
            <div className="watch-delta"><span className="watch-delta-mark"><Icon name="watch" size={15} /></span><div><strong>过去 24 小时，2 个标的观点发生明显变化</strong><span>WTI 观点升温；BTC 的方向分歧正在扩大。</span></div><small>基于 4 个信息源</small></div>
            <div className="watch-list-v2">
              {watchlist.map(function(item){
                return <button className={"watch-item-v2 " + (selectedId === item.id ? "selected" : "")} key={item.id} onClick={function(){ setSelectedId(item.id); }}>
                  <span className="watch-symbol-v2"><strong>{item.symbol}</strong><span>{item.type} · {item.stance}</span></span>
                  <span className="watch-copy-v2"><h3>{item.headline}</h3><p>{item.detail}</p><span className="consensus"><i style={{width:item.positive + "%"}}></i><i style={{width:item.neutral + "%"}}></i><i style={{width:item.negative + "%"}}></i></span></span>
                  <span className="watch-stats-v2"><strong>{item.change}</strong><span>{item.time}</span></span>
                  <span className="source-row-end"><Icon name="arrow" size={17} /></span>
                </button>;
              })}
            </div>
          </section>
          {selected && <WatchDetailPanel item={selected} onClose={function(){ setSelectedId(null); }} onOpenAsset={onOpenAsset} />}
        </main>
      </>;
    }

    function AssistantPage() {
      const [draft, setDraft] = useState("");
      const [question, setQuestion] = useState("今天原油观点有什么变化？");
      const suggestions = ["这和我的美股关注有什么关系？", "哪些条件会让判断失效？", "只看 qinbafrank 的原文证据"];
      function submit(value) {
        const next = (value || draft).trim();
        if (!next) return;
        setQuestion(next);
        setDraft("");
      }
      return <main className="page" data-screen-label="研究助手">
        <section className="assistant-page-v2">
          <header className="assistant-header-v2"><div><p className="eyebrow">Evidence-grounded assistant</p><h1>助手</h1></div><button className="assistant-scope"><Icon name="sources" size={14} /><span>回答范围</span><strong>关注信息源</strong></button></header>
          <div className="chat-context">当前使用 <span>4 个信息源</span><span>4 个关注标的</span><span>近 30 天</span> 的已核验内容</div>
          <div className="conversation-v2">
            <div className="user-question">{question}</div>
            <article className="assistant-response">
              <div className="answer-label"><span className="assistant-orb" style={{margin:0,width:28,height:28}}><Icon name="assistant" size={14} /></span>基于 3 条证据</div>
              <h2>关注博主对原油的判断从“等待确认”转向“供应风险可能持续更久”。</h2>
              <p>主要变化不是冲突是否升级，而是霍尔木兹海峡恢复通航的时间再次失去确定性。整体观点偏多，但仍属于事件驱动判断，并非无条件推荐。</p>
              <ul className="answer-points"><li><b>1</b><span>@qinbafrank 维持短期看多，观察位在 80 美元附近。</span></li><li><b>2</b><span>油价与美债收益率同步上行，可能继续压制风险资产。</span></li><li><b>3</b><span>若出现明确通航协议，当前风险溢价可能快速回吐。</span></li></ul>
              <div className="citation-list"><button className="citation-card"><span>证据 1 · 原推文</span><strong>“海峡没那么快重开……更可能持续僵持。”</strong><small>@qinbafrank · 18 分钟前</small></button><button className="citation-card"><span>证据 2 · 图片分析</span><strong>图表显示油价突破 80 美元并站上短期均线。</strong><small>图片与正文方向一致</small></button></div>
              <div className="follow-up">{suggestions.map(function(item){ return <button key={item} onClick={function(){ submit(item); }}>{item}</button>; })}</div>
            </article>
          </div>
          <form className="composer-v2" onSubmit={function(event){ event.preventDefault(); submit(); }}><div className="composer-input-row"><input value={draft} onChange={function(event){ setDraft(event.target.value); }} placeholder="追问博主观点、标的变化或原文依据…" /><button className="composer-send" aria-label="发送"><Icon name="send" size={17} /></button></div><div className="composer-meta"><span>仅基于已采集证据</span> · 找不到依据时不会推测</div></form>
        </section>
      </main>;
    }

Object.assign(window, { Sidebar, Topbar, SignalItem, DetailPanel, TodayPage, SourceDetailPanel, SourcesPage, WatchDetailPanel, WatchPage, AssistantPage });
