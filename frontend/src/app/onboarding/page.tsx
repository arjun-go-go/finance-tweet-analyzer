"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppIcon from "@/components/AppIcon";
import { createTracking, onboardBlogger, validateTracking, type TrackingValidation } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [handle, setHandle] = useState("");
  const [sourceAdded, setSourceAdded] = useState("");
  const [ticker, setTicker] = useState("");
  const [validation, setValidation] = useState<TrackingValidation | null>(null);
  const [assetAdded, setAssetAdded] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const addSource = async () => {
    const clean = handle.trim().replace(/^@/, "");
    if (!clean) { setStep(2); return; }
    setBusy(true); setError("");
    try { await onboardBlogger(clean); setSourceAdded(clean); setStep(2); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "信息源添加失败"); }
    finally { setBusy(false); }
  };

  const checkAsset = async () => {
    if (!ticker.trim()) { setStep(3); return; }
    setBusy(true); setError("");
    try { setValidation(await validateTracking(ticker.trim().toUpperCase())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "标的校验失败"); }
    finally { setBusy(false); }
  };

  const addAsset = async () => {
    const symbol = validation?.instrument?.symbol;
    if (!validation?.accepted || !symbol) return;
    setBusy(true); setError("");
    try { await createTracking(symbol); setAssetAdded(symbol); setStep(3); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "标的添加失败"); }
    finally { setBusy(false); }
  };

  return <main className="onboarding-prototype-page">
    <header><div className="auth-brand"><span className="workspace-brand-mark"><span /></span><strong>Signal</strong></div><button onClick={() => router.push("/")}>稍后设置</button></header>
    <div className="onboarding-progress"><span style={{ width: `${step / 3 * 100}%` }} /></div>
    <section>
      <p className="page-eyebrow">步骤 {step} / 3</p>
      {step === 1 && <div className="onboarding-stage"><h1>先关注一个 Twitter 信息源</h1><p>系统核对公开账号后，会开始采集推文、Thread 和图片。也可以先跳过。</p><label className="onboarding-input"><span>@</span><input autoFocus value={handle} onChange={(event) => setHandle(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void addSource(); }} placeholder="username" /></label><div className="onboarding-proof"><AppIcon name="check" /><span><strong>只采集公开内容</strong><small>不会要求你提供 Twitter 密码</small></span></div></div>}
      {step === 2 && <div className="onboarding-stage"><h1>添加正在关注的标的</h1><p>只用于聚合博主观点；支持 A股、港股、美股、原油、黄金和加密货币。</p><label className="onboarding-input"><AppIcon name="search" /><input autoFocus value={ticker} onChange={(event) => { setTicker(event.target.value); setValidation(null); }} onKeyDown={(event) => { if (event.key === "Enter") void checkAsset(); }} placeholder="NVDA / 600519 / WTI / XAU / BTC" /></label>{validation && <div className={`onboarding-validation ${validation.accepted ? "is-valid" : "is-invalid"}`}><b>{validation.instrument?.symbol || ticker.toUpperCase()}</b><span><strong>{validation.instrument?.resolved_name || validation.instrument?.name || "未找到正式标的"}</strong><small>{validation.accepted ? "身份已核验，可以加入关注" : validation.reason}</small></span></div>}</div>}
      {step === 3 && <div className="onboarding-stage onboarding-ready"><span><AppIcon name="check" /></span><h1>你的情报工作台准备好了</h1><p>{sourceAdded ? `@${sourceAdded} 已开始同步公开内容。` : "你可以随时从“信息源”添加 Twitter 博主。"}{assetAdded ? ` ${assetAdded} 已加入关注。` : " 也可以稍后建立标的范围。"}</p><div><div><strong>{sourceAdded ? 1 : 0}</strong><small>信息源</small></div><div><strong>{assetAdded ? 1 : 0}</strong><small>关注标的</small></div><div><strong>开启</strong><small>证据约束</small></div></div></div>}
      {error && <p className="form-message is-error">{error}</p>}
      <footer>{step > 1 && step < 3 ? <button className="button-secondary" onClick={() => { setStep(step - 1); setError(""); }}>上一步</button> : <span />}{step === 1 && <button className="button-primary" disabled={busy} onClick={() => void addSource()}>{busy ? "正在核对" : handle.trim() ? "添加并继续" : "跳过"}</button>}{step === 2 && !validation?.accepted && <button className="button-primary" disabled={busy} onClick={() => void checkAsset()}>{busy ? "正在校验" : ticker.trim() ? "校验标的" : "跳过"}</button>}{step === 2 && validation?.accepted && <button className="button-primary" disabled={busy} onClick={() => void addAsset()}>{busy ? "正在添加" : "加入关注并继续"}</button>}{step === 3 && <button className="button-primary" onClick={() => router.push("/")}>进入今日情报</button>}</footer>
    </section>
  </main>;
}
