const { useEffect, useState } = React;

function AppV5() {
  const [view, setView] = useState("today");
  const [showAddSource, setShowAddSource] = useState(false);
  const [showAddAsset, setShowAddAsset] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const [toast, setToast] = useState("");
  const [insightTarget, setInsightTarget] = useState(signals[0]);
  const [profileTarget, setProfileTarget] = useState(sources[0]);
  const [assetTarget, setAssetTarget] = useState(watchlist[0]);

  const primaryView = view === "insight" ? "today"
    : view === "profile" ? "sources"
      : view === "asset" || view === "prediction" ? "watch"
        : view;
  const standalone = view === "auth" || view === "onboarding";

  useEffect(function(){ window.scrollTo(0,0); }, [view]);
  useEffect(function(){
    if (!toast) return undefined;
    const timer = window.setTimeout(function(){ setToast(""); }, 2600);
    return function(){ window.clearTimeout(timer); };
  }, [toast]);
  useEffect(function(){
    function onKeyDown(event){
      if (event.key === "Escape") {
        setShowAddSource(false); setShowAddAsset(false); setShowSearch(false);
        setShowNotifications(false); setShowReview(false);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); setShowSearch(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return function(){ window.removeEventListener("keydown", onKeyDown); };
  }, []);

  function navigate(next){
    setShowSearch(false); setShowNotifications(false); setShowReview(false);
    setView(next);
  }
  function openInsight(item){ setInsightTarget(item || signals[0]); navigate("insight"); }
  function openProfile(source){ setProfileTarget(source || sources[0]); navigate("profile"); }
  function openAsset(item){ setAssetTarget(item || watchlist[0]); navigate("asset"); }
  function handleNotification(target){
    if (target === "insight") openInsight(signals[0]);
    else if (target === "asset") openAsset(watchlist[0]);
    else navigate(target);
  }

  let content = null;
  if (view === "today") content = <TodayPage onOpenDetail={openInsight} />;
  if (view === "sources") content = <SourcesPage onAdd={function(){ setShowAddSource(true); }} onOpenProfile={openProfile} />;
  if (view === "watch") content = <WatchPageV5 onOpenAsset={openAsset} onAddAsset={function(){ setShowAddAsset(true); }} onAsk={function(){ navigate("assistant"); }} />;
  if (view === "assistant") content = <AssistantPageV5 onOpenInsight={function(){ openInsight(signals[0]); }} />;
  if (view === "insight") content = <InsightDetailPageV5 item={insightTarget} onBack={function(){ navigate("today"); }} onAsk={function(){ navigate("assistant"); }} onOpenProfile={function(){ openProfile(sources[0]); }} onToast={setToast} />;
  if (view === "profile") content = <BloggerProfilePageV5 source={profileTarget} onBack={function(){ navigate("sources"); }} onOpenPrediction={function(){ navigate("prediction"); }} onOpenInsight={function(){ openInsight(signals[0]); }} onToast={setToast} />;
  if (view === "asset") content = <AssetDetailPageV5 item={assetTarget} onBack={function(){ navigate("watch"); }} onAsk={function(){ navigate("assistant"); }} onOpenPrediction={function(){ navigate("prediction"); }} onToast={setToast} />;
  if (view === "prediction") content = <PredictionDetailPageV5 onBack={function(){ navigate("profile"); }} onOpenProfile={function(){ navigate("profile"); }} onToast={setToast} />;
  if (view === "settings") content = <SettingsPageV5 onBack={function(){ navigate("today"); }} onToast={setToast} />;
  if (view === "exceptions") content = <ExceptionStatesPageV5 onBack={function(){ navigate("today"); }} onAddSource={function(){ setShowAddSource(true); }} onToast={setToast} />;

  return <>
    {view === "auth" && <AuthPageV5 onContinue={function(){ navigate("today"); }} onStartOnboarding={function(){ navigate("onboarding"); }} />}
    {view === "onboarding" && <OnboardingPageV5 onComplete={function(){ navigate("today"); setToast("研究范围已建立，首批采集已开始"); }} onBack={function(){ navigate("auth"); }} />}
    {!standalone && <div className="shell">
      <Sidebar view={primaryView} setView={navigate} onSettings={function(){ navigate("settings"); }} />
      <section className="workspace">
        <Topbar onAdd={function(){ setShowAddSource(true); }} onSearch={function(){ setShowSearch(true); }} onNotifications={function(){ setShowNotifications(true); }} />
        {content}
      </section>
    </div>}

    {showAddSource && <AddSourceModalV5 onClose={function(){ setShowAddSource(false); }} onComplete={function(handle){ setShowAddSource(false); setToast("已添加 @" + handle + "，正在采集公开推文与图片"); navigate("sources"); }} />}
    {showAddAsset && <AddAssetModalV5 onClose={function(){ setShowAddAsset(false); }} onComplete={function(asset){ setShowAddAsset(false); setToast(asset.symbol + " 已加入关注"); }} />}
    {showSearch && <SearchOverlayV5 onClose={function(){ setShowSearch(false); }} onOpenInsight={openInsight} onOpenProfile={openProfile} onOpenAsset={openAsset} />}
    {showNotifications && <NotificationCenter onClose={function(){ setShowNotifications(false); }} onNavigate={handleNotification} />}
    {showReview && <ReviewMapV5 onClose={function(){ setShowReview(false); }} onNavigate={navigate} onOpenSearch={function(){ setShowReview(false); setShowSearch(true); }} onOpenNotifications={function(){ setShowReview(false); setShowNotifications(true); }} />}
    <ReviewLauncherV5 onOpen={function(){ setShowReview(true); }} />
    {toast && <div className="toast">{toast}</div>}
  </>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<AppV5 />);
