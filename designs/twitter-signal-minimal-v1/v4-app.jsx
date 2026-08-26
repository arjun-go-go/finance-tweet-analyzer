const { useEffect, useState } = React;

function App() {
  const [view, setView] = useState("today");
  const [showAdd, setShowAdd] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const [toast, setToast] = useState("");
  const [insightTarget, setInsightTarget] = useState(signals[0]);
  const [profileTarget, setProfileTarget] = useState(sources[0]);
  const [assetTarget, setAssetTarget] = useState(watchlist[0]);

  const primaryView = view === "insight"
    ? "today"
    : view === "profile"
      ? "sources"
      : view === "asset" || view === "prediction"
        ? "watch"
        : view;
  const standalone = view === "auth" || view === "onboarding";

  useEffect(function(){ window.scrollTo(0, 0); }, [view]);
  useEffect(function(){
    if (!toast) return undefined;
    const timer = window.setTimeout(function(){ setToast(""); }, 2400);
    return function(){ window.clearTimeout(timer); };
  }, [toast]);
  useEffect(function(){
    function onKeyDown(event) {
      if (event.key === "Escape") {
        setShowSearch(false);
        setShowNotifications(false);
        setShowReview(false);
        setShowAdd(false);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShowSearch(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return function(){ window.removeEventListener("keydown", onKeyDown); };
  }, []);

  function navigate(nextView) {
    setShowSearch(false);
    setShowNotifications(false);
    setShowReview(false);
    setView(nextView);
  }

  function completeAdd(handle) {
    setShowAdd(false);
    setToast("已添加 @" + handle + "，正在获取资料");
    setView("sources");
  }

  function openInsight(item) {
    setInsightTarget(item || signals[0]);
    navigate("insight");
  }

  function openProfile(source) {
    setProfileTarget(source || sources[0]);
    navigate("profile");
  }

  function openAsset(item) {
    setAssetTarget(item || watchlist[0]);
    navigate("asset");
  }

  function handleNotification(target) {
    if (target === "insight") openInsight(signals[0]);
    else if (target === "asset") openAsset(watchlist[0]);
    else navigate(target);
  }

  let content = null;
  if (view === "today") content = <TodayPage onOpenDetail={openInsight} />;
  if (view === "sources") content = <SourcesPage onAdd={function(){ setShowAdd(true); }} onOpenProfile={openProfile} />;
  if (view === "watch") content = <WatchPage onOpenAsset={openAsset} />;
  if (view === "assistant") content = <AssistantPage />;
  if (view === "insight") content = <InsightDetailPage item={insightTarget} onBack={function(){ navigate("today"); }} onAsk={function(){ navigate("assistant"); }} />;
  if (view === "profile") content = <BloggerProfilePage source={profileTarget} onBack={function(){ navigate("sources"); }} onOpenPrediction={function(){ navigate("prediction"); }} />;
  if (view === "asset") content = <AssetDetailPage item={assetTarget} onBack={function(){ navigate("watch"); }} onAsk={function(){ navigate("assistant"); }} onOpenPrediction={function(){ navigate("prediction"); }} />;
  if (view === "prediction") content = <PredictionDetailPage onBack={function(){ navigate("profile"); }} />;
  if (view === "settings") content = <SettingsPage onBack={function(){ navigate("today"); }} />;
  if (view === "states") content = <LifecycleStatesPage onBack={function(){ navigate("today"); }} />;

  return <>
    {view === "auth" && <AuthPage onContinue={function(){ navigate("today"); }} onStartOnboarding={function(){ navigate("onboarding"); }} />}
    {view === "onboarding" && <OnboardingPage onComplete={function(){ navigate("today"); setToast("研究范围已建立"); }} onBack={function(){ navigate("auth"); }} />}
    {!standalone && <div className="shell">
      <Sidebar view={primaryView} setView={navigate} onSettings={function(){ navigate("settings"); }} />
      <section className="workspace">
        <Topbar
          onAdd={function(){ setShowAdd(true); }}
          onSearch={function(){ setShowSearch(true); }}
          onNotifications={function(){ setShowNotifications(true); }}
        />
        {content}
      </section>
    </div>}

    {showAdd && <AddSourceModal onClose={function(){ setShowAdd(false); }} onComplete={completeAdd} />}
    {showSearch && <SearchOverlay onClose={function(){ setShowSearch(false); }} onOpenInsight={openInsight} onOpenProfile={openProfile} onOpenAsset={openAsset} />}
    {showNotifications && <NotificationCenter onClose={function(){ setShowNotifications(false); }} onNavigate={handleNotification} />}
    {showReview && <ReviewMap
      onClose={function(){ setShowReview(false); }}
      onNavigate={navigate}
      onOpenSearch={function(){ setShowReview(false); setShowSearch(true); }}
      onOpenNotifications={function(){ setShowReview(false); setShowNotifications(true); }}
    />}
    <ReviewLauncher onOpen={function(){ setShowReview(true); }} />
    {toast && <div className="toast">{toast}</div>}
  </>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
