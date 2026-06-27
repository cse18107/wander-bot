import { useEffect, useRef, useState } from "react";
import Auth from "./Auth";
import { createThread, deleteThread, forgetPreferences, getPreferences, getProfile, getThread, listPlans, listThreads, loadPlan, postJSON, postMessage, setHomeCity, streamPost } from "./api";
import type { ApprovalPayload, Budget, ChatCard, DayDetail, FlightOption, Itinerary, Selections, TransportRoute } from "./types";

function Icon({ name, className }: { name: string; className?: string }) {
  return <span className={`material-symbols-outlined${className ? " " + className : ""}`}>{name}</span>;
}
const newId = () => "p-" + Math.random().toString(36).slice(2, 10);

const STEP_META: Record<string, { icon: string; label: string }> = {
  intake: { icon: "edit_note", label: "Understanding request" },
  clarify: { icon: "event", label: "Confirming dates" },
  research: { icon: "travel_explore", label: "Researching destination" },
  flights: { icon: "flight", label: "Finding flights" },
  select_flight: { icon: "airline_seat_recline_normal", label: "Choosing flight" },
  lodging: { icon: "hotel", label: "Finding hotels" },
  activities: { icon: "confirmation_number", label: "Picking activities" },
  budget: { icon: "payments", label: "Checking budget" },
  replan: { icon: "autorenew", label: "Optimizing budget" },
  itinerary: { icon: "map", label: "Building itinerary" },
  curate_images: { icon: "photo_library", label: "Curating photos" },
  reserve: { icon: "task_alt", label: "Ready to reserve" },
  respond: { icon: "chat", label: "Need more info" },
};

function fmtPrice(amount: number, currency?: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD", maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${amount.toFixed(0)} ${currency || ""}`.trim();
  }
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function itemIcon(text: string): string {
  const t = text.toLowerCase();
  if (/(food|eat|dinner|lunch|breakfast|cuisine|snack|tea|restaurant|momo|taste|dine)/.test(t)) return "restaurant";
  if (/(train|railway|toy train|cable|ropeway)/.test(t)) return "train";
  if (/(depart|check.?out|leave|airport|fly back)/.test(t)) return "luggage";
  if (/(check.?in|hostel|hotel|accommodation|arrive|arrival)/.test(t)) return "concierge";
  if (/(museum|temple|monastery|church|heritage|fort|palace|observatory|shrine)/.test(t)) return "account_balance";
  if (/(market|shopping|bazaar|mall|chowrasta|street|boutique)/.test(t)) return "shopping_bag";
  if (/(view|sunrise|hill|peak|garden|park|scenic|valley|estate|cruise|river|mountain)/.test(t)) return "landscape";
  if (/(walk|stroll|explore|relax|wander)/.test(t)) return "directions_walk";
  return "place";
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("va-token"));
  const [email, setEmail] = useState(() => localStorage.getItem("va-email") || "");
  const [plans, setPlans] = useState<any[]>([]);
  const [screen, setScreen] = useState<"home" | "plan">("home");
  const [planId, setPlanId] = useState("");

  const [input, setInput] = useState("");
  const [, setAssistant] = useState("");
  const [steps, setSteps] = useState<string[]>([]);
  const [selections, setSelections] = useState<Selections | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [images, setImages] = useState<string[]>([]);
  const [dayImages, setDayImages] = useState<{ hero?: string; days?: string[] } | null>(null);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [clarify, setClarify] = useState<{ question: string } | null>(null);
  const [flightOptions, setFlightOptions] = useState<FlightOption[] | null>(null);
  const [noFlights, setNoFlights] = useState<{ date: string | null; destination?: string | null; nearby?: FlightOption[]; transport?: TransportRoute[] } | null>(null);
  const [changingDate, setChangingDate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prefs, setPrefs] = useState<string[]>([]);
  const [lightbox, setLightbox] = useState<number | null>(null);
  const [theme, setTheme] = useState<string>(() => localStorage.getItem("va-theme") || "dark");
  const [dayDetail, setDayDetail] = useState<DayDetail | null>(null);
  const [dayOpen, setDayOpen] = useState(false);
  const [dayLoading, setDayLoading] = useState(false);
  const [convo, setConvo] = useState<{ role: string; text: string; cards?: ChatCard[] }[]>([]);
  const [chatImg, setChatImg] = useState<string | null>(null);
  const [askBusy, setAskBusy] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);
  const [homeCity, setHomeCityState] = useState("");
  const [clarifyField, setClarifyField] = useState("");
  const [chatThreadId, setChatThreadId] = useState<string | null>(null);
  const [chatThreads, setChatThreads] = useState<any[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const clarifyInput = useRef<HTMLInputElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => { chatRef.current?.scrollTo(0, chatRef.current.scrollHeight); }, [convo, askBusy]);

  // Load chat threads when a plan is open; auto-open the latest conversation.
  useEffect(() => {
    if (screen !== "plan" || !planId) return;
    let active = true;
    listThreads(planId).then(async (ts) => {
      if (!active) return;
      setChatThreads(ts);
      if (ts.length && !chatThreadId) {
        const t = await getThread(ts[0].id);
        if (active) { setChatThreadId(t.id); setConvo(t.messages || []); }
      }
    });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, planId]);

  async function refreshThreads() { if (planId) setChatThreads(await listThreads(planId)); }

  function newChat() { setChatThreadId(null); setConvo([]); setHistoryOpen(false); }

  async function loadThread(id: string) {
    const t = await getThread(id);
    setChatThreadId(t.id); setConvo(t.messages || []); setHistoryOpen(false);
  }
  async function removeThread(id: string) {
    await deleteThread(id);
    if (id === chatThreadId) newChat();
    refreshThreads();
  }

  async function ask() {
    const q = input.trim();
    if (!q || askBusy) return;
    setInput(""); setConvo((c) => [...c, { role: "user", text: q }]); setAskBusy(true);
    try {
      let tid = chatThreadId;
      if (!tid) { tid = (await createThread(planId)).id; setChatThreadId(tid); }
      const r = await postMessage(tid, q);
      setConvo((c) => [...c, { role: "assistant", text: r.answer, cards: r.cards || undefined }]);
      if (r.plan) {
        if (r.plan.itinerary) setItinerary(r.plan.itinerary);
        if (r.plan.selections) setSelections(r.plan.selections);
        if (r.plan.budget) setBudget(r.plan.budget);
        fetchPlans();
      }
      refreshThreads();
    } catch {
      setConvo((c) => [...c, { role: "assistant", text: "Sorry, I couldn't answer that." }]);
    } finally {
      setAskBusy(false);
    }
  }

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("va-theme", theme); }, [theme]);
  useEffect(() => { if (token) { fetchPlans(); refreshPrefs(); getProfile().then((p) => setHomeCityState(p.home_city || "")); } }, [token]);

  async function fetchPlans() { setPlans(await listPlans()); }
  async function editHomeCity() {
    const v = window.prompt("Your home city / nearest airport (used as your default departure):", homeCity);
    if (v != null) { await setHomeCity(v.trim()); setHomeCityState(v.trim()); }
  }
  async function refreshPrefs() { setPrefs(await getPreferences()); }

  function resetPlan() {
    setSteps([]); setItinerary(null); setSelections(null); setImages([]); setDayImages(null);
    setAssistant(""); setClarify(null); setApproval(null); setFlightOptions(null); setNoFlights(null);
    setChangingDate(false); setBudget(null); setConvo([]); setProgressOpen(false);
    setChatThreadId(null); setChatThreads([]); setHistoryOpen(false);
  }

  function logout() { localStorage.removeItem("va-token"); localStorage.removeItem("va-email"); setToken(null); setPlans([]); }

  const ThemeToggle = () => (
    <button className="theme-toggle" title="Toggle theme" onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>
      <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
    </button>
  );

  function handleEvent(event: string, data: string) {
    switch (event) {
      case "step": setSteps((s) => [...s, JSON.parse(data).node]); break;
      case "images": setImages(JSON.parse(data)); break;
      case "day_images": setDayImages(JSON.parse(data)); break;
      case "selections": setSelections(JSON.parse(data)); break;
      case "budget": setBudget(JSON.parse(data)); break;
      case "itinerary": setItinerary(JSON.parse(data)); break;
      case "message": setAssistant(data); break;
      case "clarification_required": { const c = JSON.parse(data); setClarify(c); setClarifyField(c.field || ""); break; }
      case "flight_options": setFlightOptions(JSON.parse(data)); break;
      case "no_flights": setNoFlights(JSON.parse(data)); break;
      case "approval_required": setApproval(JSON.parse(data)); break;
      case "error": setAssistant("⚠️ " + data); break;
    }
  }

  async function startPlan(message: string) {
    const id = newId();
    setPlanId(id); resetPlan(); setScreen("plan"); setBusy(true);
    await streamPost("/api/plan", { message, thread_id: id }, handleEvent);
    setBusy(false); fetchPlans();
  }
  async function refinePlan() {
    if (!input.trim() || busy) return;
    const message = input.trim(); setInput(""); resetPlan(); setBusy(true);
    await streamPost("/api/plan", { message, thread_id: planId }, handleEvent);
    setBusy(false); fetchPlans();
  }

  async function openSavedPlan(p: any) {
    const full = await loadPlan(p.id);
    const d = full.data || {};
    setPlanId(p.id); resetPlan();
    setItinerary(d.itinerary || null);
    setSelections(d.selections || null);
    setBudget(d.budget || null);
    setImages(d.images || []);
    setDayImages(d.day_images || null);
    setSteps(["intake", "research", "flights", "lodging", "budget", "itinerary", "reserve"]);
    setScreen("plan");
  }

  async function submitClarify() {
    const answer = clarifyInput.current?.value?.trim();
    if (!answer || busy) return;
    setClarify(null); setBusy(true);
    await streamPost("/api/plan/clarify", { thread_id: planId, answer }, handleEvent);
    setBusy(false); fetchPlans();
  }
  async function pickFlight(flight_id: string | null) {
    setFlightOptions(null); setNoFlights(null); setBusy(true);
    await streamPost("/api/plan/select_flight", { thread_id: planId, flight_id }, handleEvent);
    setBusy(false); fetchPlans();
  }
  async function changeStartDate() {
    const answer = clarifyInput.current?.value?.trim();
    if (!answer || busy) return;
    setNoFlights(null); setChangingDate(false); setBusy(true);
    await streamPost("/api/plan/change_date", { thread_id: planId, answer }, handleEvent);
    setBusy(false); fetchPlans();
  }
  async function decide(decision: "approved" | "declined") {
    setApproval(null); setBusy(true);
    await streamPost("/api/plan/approve", { thread_id: planId, decision }, handleEvent);
    setBusy(false); fetchPlans();
  }

  async function openDay(index: number) {
    setDayOpen(true); setDayDetail(null); setDayLoading(true);
    try { setDayDetail(await postJSON<DayDetail>("/api/plan/day_detail", { thread_id: planId, day: index + 1 })); }
    catch { setDayDetail(null); }
    finally { setDayLoading(false); }
  }
  function weatherIcon(cond?: string): string {
    const c = (cond || "").toLowerCase();
    if (/rain|wet/.test(c)) return "rainy";
    if (/wind/.test(c)) return "air";
    if (/hot|sunny/.test(c)) return "sunny";
    if (/cold/.test(c)) return "ac_unit";
    return "partly_cloudy_day";
  }
  const prevImg = () => setLightbox((l) => (l === null ? null : (l - 1 + images.length) % images.length));
  const nextImg = () => setLightbox((l) => (l === null ? null : (l + 1) % images.length));
  useEffect(() => {
    if (lightbox === null) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setLightbox(null); else if (e.key === "ArrowLeft") prevImg(); else if (e.key === "ArrowRight") nextImg(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lightbox, images.length]);

  if (!token) return <Auth onAuthed={(t, e) => { setToken(t); setEmail(e); }} />;

  const visibleSteps = steps.filter((s) => s !== "supervisor" && s !== "__interrupt__");
  const hero = dayImages?.hero || images[0];
  const dayImg = (i: number): string | undefined => dayImages?.days?.[i] || images[(i + 1) % Math.max(images.length, 1)];
  const flight = selections?.flight ?? null;
  const hotel = selections?.hotel ?? null;
  const within = budget && budget.target ? budget.total <= budget.target : true;

  const TripList = () => (
    <div className="trips">
      <div className="rail-title">My Trips</div>
      {plans.length === 0 && <div className="muted small">No saved trips yet.</div>}
      {plans.map((p) => (
        <button key={p.id} className={`trip ${p.id === planId ? "on" : ""}`} onClick={() => openSavedPlan(p)}>
          <div className="trip-thumb" style={p.hero ? { backgroundImage: `url(${p.hero})` } : undefined}><Icon name="luggage" /></div>
          <div className="trip-meta"><b>{p.title || "Trip"}</b><span>{p.destination || ""}</span></div>
        </button>
      ))}
    </div>
  );

  // ---------- HOME ----------
  if (screen === "home") {
    return (
      <div className="layout home">
        <aside className="rail">
          <div className="rail-top"><div className="brand"><Icon name="rocket_launch" className="brand-ic" /> <span>Voyager AI</span></div><ThemeToggle /></div>
          <button className="newplan" onClick={() => { setPlanId(""); resetPlan(); setScreen("plan"); }}><Icon name="add" /> New Plan</button>
          <div className="rail-spacer-sm" /><TripList />
          <div className="rail-spacer" />
          <div className="rail-bottom">
            <button className="home-from" onClick={editHomeCity}><Icon name="home_pin" /><span>{homeCity ? `Departing from ${homeCity}` : "Set your home city"}</span><Icon name="edit" /></button>
            <div className="acct"><Icon name="account_circle" /><span className="muted small">{email}</span><button className="link" onClick={logout}>Log out</button></div>
          </div>
        </aside>
        <main className="home-center">
          <h1>Plan your next escape</h1>
          <p className="muted">Describe your trip — real flights, hotels, a day-by-day itinerary, all saved to your account.</p>
          <div className="center-composer">
            <input autoFocus value={input} placeholder="e.g. 5 days in Darjeeling, food and tea gardens"
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && input.trim() && startPlan(input.trim())} />
            <button onClick={() => input.trim() && startPlan(input.trim())}>Plan</button>
          </div>
          <div className="examples">
            {["4 days in Darjeeling, food and tea", "7 days in London in August from JFK", "10 days in Tokyo, mid-range"].map((ex) => (
              <button key={ex} className="ghost" onClick={() => setInput(ex)}>{ex}</button>
            ))}
          </div>
        </main>
      </div>
    );
  }

  // ---------- PLAN ----------
  return (
    <div className="layout">
      <aside className="rail chatrail">
        <div className="rail-top"><button className="back" onClick={() => { setScreen("home"); fetchPlans(); }}><Icon name="arrow_back" /> Trips</button><ThemeToggle /></div>
        <div className="chat-head">
          <span className="chat-title"><Icon name="forum" /> Trip Assistant</span>
          <div className="chat-actions">
            <button className="chat-act" title="New chat" onClick={newChat}><Icon name="add_comment" /></button>
            <button className={`chat-act ${historyOpen ? "on" : ""}`} title="Chat history" onClick={() => setHistoryOpen((o) => !o)}><Icon name="history" /></button>
          </div>
        </div>
        {historyOpen && (
          <div className="chat-history">
            <div className="ch-title">Chat history</div>
            {chatThreads.length === 0 && <div className="muted small ch-empty">No past chats yet.</div>}
            {chatThreads.map((t) => (
              <div key={t.id} className={`ch-item ${t.id === chatThreadId ? "on" : ""}`}>
                <button className="ch-load" onClick={() => loadThread(t.id)}><Icon name="chat_bubble" /> {t.title || "New chat"}</button>
                <button className="ch-del" title="Delete" onClick={() => removeThread(t.id)}><Icon name="close" /></button>
              </div>
            ))}
          </div>
        )}
        <div className="rail-chat" ref={chatRef}>
          {convo.length === 0 && !askBusy && (
            <div className="chat-empty">
              <Icon name="travel_explore" className="chat-empty-ic" />
              <p className="muted">Ask anything about your trip, search the web, or change the plan.</p>
              <div className="chat-suggest">
                {["What should I pack?", "Find a vegetarian dinner near day 2", "Change day 3 to be more relaxed", "I don't want this hotel"].map((s) => (
                  <button key={s} className="ghost" onClick={() => { setInput(s); }}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {convo.map((m, i) => (
            <div key={i} className={`rbubble ${m.role}`}>
              {m.text}
              {m.cards && m.cards.length > 0 && (
                <div className="chat-cards">
                  {m.cards.map((card, ci) => {
                    if (card.kind === "options") {
                      return (
                        <div key={ci} className="opt-group">
                          {(card.options || []).map((o, oi) => (
                            <div key={oi} className="opt-card">
                              <div className="opt-mode"><Icon name={o.icon || "trip_origin"} /></div>
                              <div className="opt-body">
                                <div className="opt-top">
                                  <span className="opt-title">{o.title}</span>
                                  {o.note && <span className="opt-tag">{o.note}</span>}
                                </div>
                                {(o.from_label || o.to_label) && (
                                  <div className="opt-route">
                                    <span className="opt-end opt-from" title={o.from_label || ""}>{o.from_label || ""}</span>
                                    <span className="opt-line"><span className="opt-dot" /><span className="opt-track" /><Icon name="navigation" className="opt-arrow" /></span>
                                    <span className="opt-end opt-to" title={o.to_label || ""}>{o.to_label || ""}</span>
                                  </div>
                                )}
                                {o.stats && o.stats.length > 0 && (
                                  <div className="opt-stats">
                                    {o.stats.map((s, si) => (
                                      <span key={si} className="opt-chip"><Icon name={s.icon || "info"} /> {s.value}</span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      );
                    }
                    const imgs = card.images || [];
                    return imgs.length <= 1 ? (
                      <button key={ci} className="hotel-tile" onClick={() => imgs[0] && setChatImg(imgs[0])}>
                        <div className="ht-thumb" style={imgs[0] ? { backgroundImage: `url(${imgs[0]})` } : undefined}>{!imgs[0] && <Icon name="hotel" />}</div>
                        <div className="ht-info">
                          <div className="ht-name">{card.label}</div>
                          {card.note && <div className="ht-note">{card.note}</div>}
                          {card.price != null && <div className="ht-price"><Icon name="sell" /> {fmtPrice(card.price, card.currency)}</div>}
                        </div>
                        {imgs[0] && <Icon name="zoom_in" className="ht-zoom" />}
                      </button>
                    ) : (
                      <div key={ci} className="gallery-card">
                        <div className="cc-label-row">{card.label && <span className="cc-label">{card.label}</span>}{card.price != null && <span className="ht-price"><Icon name="sell" /> {fmtPrice(card.price, card.currency)}</span>}</div>
                        <div className="cc-imgs">{imgs.map((url, ui) => <button key={ui} className="cc-img" style={{ backgroundImage: `url(${url})` }} onClick={() => setChatImg(url)} />)}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
          {askBusy && <div className="rbubble assistant typing">…</div>}
        </div>
        <div className="rail-bottom">
          {budget && (
            <div className="bar-wrap">
              <div className="bar"><div className={`fill ${within ? "ok" : "over"}`} style={{ width: budget.target ? `${Math.min(100, (budget.total / budget.target) * 100)}%` : "45%" }} /></div>
              <small>{budget.total.toFixed(0)} {budget.currency}{budget.target ? ` / ${budget.target.toFixed(0)}` : ""}{budget.local_currency && budget.local_currency !== budget.currency && budget.local_total != null ? ` · ≈ ${budget.local_total.toFixed(0)} ${budget.local_currency}` : ""}</small>
            </div>
          )}
          <div className="composer">
            <input value={input} placeholder={itinerary ? "Ask or change anything…" : "Refine…"} disabled={askBusy || busy}
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (itinerary ? ask() : refinePlan())} />
            <button onClick={() => (itinerary ? ask() : refinePlan())} disabled={askBusy || busy}>{itinerary ? <Icon name="send" /> : "Plan"}</button>
          </div>
        </div>
      </aside>

      <main className="stage">
        {clarify && (
          <div className="clarify"><Icon name="event" className="clarify-icon" /><h2>{clarify.question}</h2>
            <div className="clarify-input"><input ref={clarifyInput} autoFocus placeholder={clarifyField === "origin" ? "e.g. Kolkata or CCU" : "e.g. August 5 or 2026-08-05"} onKeyDown={(e) => e.key === "Enter" && submitClarify()} /><button onClick={submitClarify}>Continue</button></div>
          </div>
        )}

        {!clarify && flightOptions && !itinerary && (
          <div className="flight-pick">
            <h2><Icon name="flight" /> Choose your flight</h2>
            <p className="muted">{flightOptions.length} option{flightOptions.length !== 1 ? "s" : ""} found — pick one to continue.</p>
            <div className="fp-list">{flightOptions.map((f) => (
              <button key={f.id} className="fp-card" onClick={() => pickFlight(f.id)} disabled={busy}>
                <div className="fp-route"><div className="fp-end"><b>{f.origin}</b><span>{fmtTime(f.depart)}</span></div><div className="fp-mid"><span className="line" /><small>{f.carrier}{f.number} · {f.stops === 0 ? "NON-STOP" : `${f.stops} stop`}</small></div><div className="fp-end"><b>{f.destination}</b><span>{fmtTime(f.arrive)}</span></div></div>
                <div className="fp-price">{f.price.amount.toFixed(0)} {f.price.currency}</div>
              </button>))}
            </div>
          </div>
        )}

        {!clarify && noFlights && !itinerary && (
          <div className="flight-pick">
            <h2><Icon name="flight_takeoff" /> No direct flights to {noFlights.destination || "your destination"}</h2>
            {noFlights.nearby && noFlights.nearby.length > 0 ? (<><p className="muted">But here are flights on nearby days — pick one to shift your trip:</p>
              <div className="fp-list">{noFlights.nearby.map((f) => (
                <button key={f.id} className="fp-card" onClick={() => pickFlight(f.id)} disabled={busy}>
                  <div className="fp-date"><Icon name="event" />{f.date}</div>
                  <div className="fp-route"><div className="fp-end"><b>{f.origin}</b><span>{fmtTime(f.depart)}</span></div><div className="fp-mid"><span className="line" /><small>{f.carrier}{f.number} · {f.stops === 0 ? "NON-STOP" : `${f.stops} stop`}</small></div><div className="fp-end"><b>{f.destination}</b><span>{fmtTime(f.arrive)}</span></div></div>
                  <div className="fp-price">{f.price.amount.toFixed(0)} {f.price.currency}</div>
                </button>))}</div></>) : <p className="muted">No flights on nearby days either{noFlights.transport && noFlights.transport.length > 0 ? " — here are ways to get there by road and rail:" : "."}</p>}

            {noFlights.transport && noFlights.transport.length > 0 && (
              <div className="tr-list">
                {noFlights.transport.map((r, ri) => (
                  <button key={ri} className="tr-card" onClick={() => pickFlight(null)} disabled={busy} title="Proceed with this route">
                    <div className="tr-head">
                      <span className="tr-title">{r.title}</span>
                      {r.note && <span className="tr-tag">{r.note}</span>}
                    </div>
                    <div className="tr-legs">
                      {r.legs.map((l, li) => (
                        <div key={li} className="tr-leg">
                          <span className="tr-leg-ic"><Icon name={l.icon || "trip_origin"} /></span>
                          <div className="tr-leg-body">
                            <div className="tr-leg-route">{l.from_place} <Icon name="arrow_forward" className="tr-arrow" /> {l.to_place}</div>
                            <div className="tr-leg-meta">
                              <span className="tr-mode">{l.mode}</span>
                              {l.duration && <span><Icon name="schedule" /> {l.duration}</span>}
                              {l.cost && <span><Icon name="payments" /> {l.cost}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="tr-foot">
                      {r.total_duration && <span><Icon name="schedule" /> {r.total_duration} total</span>}
                      {r.total_cost && <span className="tr-total"><Icon name="sell" /> {r.total_cost}</span>}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {!changingDate ? (<div className="np-actions"><button className="ghost" onClick={() => pickFlight(null)} disabled={busy}>Proceed without a flight</button><button onClick={() => setChangingDate(true)} disabled={busy}>Change start date</button></div>) : (<div className="clarify-input"><input ref={clarifyInput} autoFocus placeholder="New start date" onKeyDown={(e) => e.key === "Enter" && changeStartDate()} /><button onClick={changeStartDate}>Update</button></div>)}
          </div>
        )}

        {!clarify && !flightOptions && !noFlights && busy && !itinerary && (
          <div className="loading"><div className="orbit"><span /><span /><span /></div><h2>Generating your plan…</h2><p className="muted">{visibleSteps.length ? (STEP_META[visibleSteps[visibleSteps.length - 1]]?.label ?? "Working") : "Thinking"}</p></div>
        )}

        {!clarify && itinerary && (
          <div className="plan">
            <section className="hero" style={hero ? { backgroundImage: `url(${hero})` } : undefined}>
              <div className="hero-overlay" />
              <div className="hero-content">
                <span className="pill">AI CO-PILOT ACTIVE · v2.4</span>
                <h1>{itinerary.headline || itinerary.summary.split(".")[0]}</h1>
                <p className="hero-sub">{itinerary.summary}</p>
                <div className="params">
                  <div className="param"><span>Duration</span><b>{itinerary.days.length} Days</b></div>
                  {budget && budget.total > 0 && <div className="param"><span>Estimated</span><b>{budget.total.toFixed(0)} {budget.currency}</b></div>}
                  {budget && budget.local_currency && budget.local_total != null && budget.local_currency !== budget.currency && <div className="param"><span>In local currency</span><b>≈ {budget.local_total.toFixed(0)} {budget.local_currency}</b></div>}
                </div>
              </div>
            </section>

            <div className={`card flight${flight ? "" : " inactive"}`}>
              <div className="card-tag"><Icon name="flight" /> FLIGHT</div>
              {flight ? (() => { const segs = flight.segments; const out = segs[0]; const rt = segs.length > 1 && segs[segs.length - 1]?.destination === out?.origin; return (<><div className="route"><div className="end"><b>{out?.origin}</b><span>{fmtTime(out?.departure_at)}</span></div><div className="mid"><span className="line" /><small>{out?.carrier}{out?.flight_number} · {flight.stops === 0 ? "NON-STOP" : `${flight.stops} stop`}{rt ? " · round trip" : ""}</small></div><div className="end"><b>{out?.destination}</b><span>{fmtTime(out?.arrival_at)}</span></div></div><div className="price">{flight.price.amount.toFixed(0)} {flight.price.currency}</div></>); })()
                : <div className="muted">No flight selected for this trip.</div>}
            </div>

            {itinerary.days.map((d, i) => (
              <div className="day" key={d.day}>
                <div className="daybadge"><b>{String(d.day).padStart(2, "0")}</b><span>DAY</span></div>
                <div className="daycard clickable" onClick={() => openDay(i)}>
                  {dayImg(i) && <div className="dayimg" style={{ backgroundImage: `url(${dayImg(i)})` }} />}
                  <div className="daybody"><h3>{d.title}</h3>{d.items.map((it, k) => <div className="iline" key={k}><Icon name={itemIcon(it)} className="ii" /><span>{it}</span></div>)}<div className="day-more">Deep dive <Icon name="chevron_right" /></div></div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <aside className="side2">
        {visibleSteps.length > 0 && (
          <div className="scard">
            <button className="scard-toggle" onClick={() => setProgressOpen((o) => !o)}>
              <span className="scard-h-inline"><Icon name="checklist" /> Plan progress</span>
              <Icon name={progressOpen ? "expand_less" : "expand_more"} />
            </button>
            {progressOpen && (
              <div className="prog-steps">
                {visibleSteps.map((s, i) => {
                  const meta = STEP_META[s] ?? { icon: "radio_button_unchecked", label: s };
                  const active = i === visibleSteps.length - 1 && busy;
                  return <div key={i} className={`stepline ${active ? "active" : "done"}`}><span className="ic"><Icon name={active ? "progress_activity" : meta.icon} /></span><span>{meta.label}</span></div>;
                })}
              </div>
            )}
          </div>
        )}
        {images.length > 0 && (<div className="scard"><div className="scard-h"><Icon name="photo_library" /> Gallery</div><div className="thumbs">{images.slice(0, 6).map((src, i) => (<button key={i} className="thumb" style={{ backgroundImage: `url(${src})` }} onClick={() => setLightbox(i)}>{i === 5 && images.length > 6 && <span className="more">+{images.length - 6}</span>}</button>))}</div></div>)}
        {itinerary?.description && (<div className="scard"><div className="scard-h"><Icon name="menu_book" /> About</div><p className="desc">{itinerary.description}</p>{itinerary.best_known_for && <div className="kv"><span><Icon name="star" /> Known for</span><b>{itinerary.best_known_for}</b></div>}{itinerary.local_language && <div className="kv"><span><Icon name="translate" /> Language</span><b>{itinerary.local_language}</b></div>}{itinerary.local_currency && <div className="kv"><span><Icon name="payments" /> Currency</span><b>{itinerary.local_currency}</b></div>}</div>)}
        {hotel && (<div className={`scard${hotel.bookable === false ? " inactive" : ""}`}><div className="scard-h"><Icon name="hotel" /> Stay</div><b>{hotel.name}</b>{hotel.bookable === false ? (<div className="muted small">{hotel.price.amount > 0 ? `~${hotel.price.amount.toFixed(0)} ${hotel.price.currency} (est.)` : "price unavailable"}<span className="badge" title={hotel.note ?? "Live availability not available"}>not available ⓘ</span></div>) : (<div className="muted small">{hotel.price.amount.toFixed(0)} {hotel.price.currency} · {hotel.check_in} → {hotel.check_out}</div>)}</div>)}
        {itinerary?.local_food?.length ? (<div className="scard"><div className="scard-h"><Icon name="restaurant" /> Famous food</div>{itinerary.local_food.map((f, i) => <div className="iline" key={i}><Icon name="restaurant_menu" className="ii" /><span>{f}</span></div>)}</div>) : null}
        {itinerary?.occasions?.length ? (<div className="scard"><div className="scard-h"><Icon name="celebration" /> While you're there</div>{itinerary.occasions.map((o, i) => <div className="iline" key={i}><Icon name="festival" className="ii" /><span>{o}</span></div>)}</div>) : null}
        {prefs.length > 0 && (<div className="scard"><div className="scard-h"><Icon name="psychology" /> Preferences <button className="link" onClick={async () => { await forgetPreferences(); refreshPrefs(); }}>Forget</button></div>{prefs.map((p, i) => <span key={i} className="chip soft">{p}</span>)}</div>)}
      </aside>

      {dayOpen && (
        <div className="drawer-bg" onClick={() => setDayOpen(false)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head"><div>{dayDetail ? <><span className="dd-day">Day {dayDetail.day}</span><h2>{dayDetail.title}</h2></> : <h2>Loading…</h2>}</div><button className="theme-toggle" onClick={() => setDayOpen(false)}><Icon name="close" /></button></div>
            {dayLoading && <div className="dd-loading"><div className="orbit"><span /><span /><span /></div><p className="muted">Gathering details, weather &amp; photos…</p></div>}
            {dayDetail && !dayLoading && (
              <div className="drawer-body">
                {dayDetail.weather && <div className="dd-weather"><Icon name={weatherIcon(dayDetail.weather_detail?.condition)} className="dd-wic" /><div><b>{dayDetail.weather_detail?.condition || "Seasonal weather"}</b><div className="muted small">{dayDetail.weather}</div></div></div>}
                {dayDetail.images.length > 0 && <div className="dd-gallery">{dayDetail.images.map((src, i) => <div key={i} className="dd-thumb" style={{ backgroundImage: `url(${src})` }} />)}</div>}
                {dayDetail.places.length > 0 && <div className="dd-section"><h4><Icon name="place" /> Places &amp; how to reach</h4>{dayDetail.places.map((p, i) => (<div className="dd-place" key={i}>{p.image && <div className="dd-place-img" style={{ backgroundImage: `url(${p.image})` }} />}<div><b>{p.name}</b>{p.how_to_reach && <div className="muted small">{p.how_to_reach}</div>}{p.best_vehicle && <div className="dd-vehicle"><Icon name="directions" /> {p.best_vehicle}</div>}</div></div>))}</div>}
                {dayDetail.walkable.length > 0 && <div className="dd-section"><h4><Icon name="directions_walk" /> Within walking distance</h4>{dayDetail.walkable.map((w, i) => <div className="iline" key={i}><Icon name="schedule" className="ii" /><span>{w.name} · <b>{w.walk_time_min} min</b></span></div>)}</div>}
                {dayDetail.street_food.length > 0 && <div className="dd-section"><h4><Icon name="lunch_dining" /> Street food to try</h4><div className="dd-chips">{dayDetail.street_food.map((f, i) => <span key={i} className="chip soft">{f}</span>)}</div></div>}
                {dayDetail.restaurants.length > 0 && <div className="dd-section"><h4><Icon name="restaurant" /> Recommended restaurants</h4>{dayDetail.restaurants.map((r, i) => <div className="iline" key={i}><Icon name="restaurant_menu" className="ii" /><span>{r}</span></div>)}</div>}
              </div>
            )}
          </div>
        </div>
      )}

      {chatImg && (
        <div className="lightbox" onClick={() => setChatImg(null)}>
          <button className="lb-close" onClick={() => setChatImg(null)}><Icon name="close" /></button>
          <img className="lb-img" src={chatImg} alt="" onClick={(e) => e.stopPropagation()} />
        </div>
      )}

      {lightbox !== null && images[lightbox] && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <button className="lb-close" onClick={() => setLightbox(null)}><Icon name="close" /></button>
          <button className="lb-nav prev" onClick={(e) => { e.stopPropagation(); prevImg(); }}><Icon name="chevron_left" /></button>
          <img className="lb-img" src={images[lightbox]} alt="" onClick={(e) => e.stopPropagation()} />
          <button className="lb-nav next" onClick={(e) => { e.stopPropagation(); nextImg(); }}><Icon name="chevron_right" /></button>
          <div className="lb-count">{lightbox + 1} / {images.length}</div>
        </div>
      )}

      {approval && (
        <div className="modal-bg"><div className="modal"><h3>Approve this plan</h3><p>Total <b>{approval.total.toFixed(0)}</b> · flight {approval.flight ?? "—"} · hotel {approval.hotel ?? "—"}</p><p className="muted">This records your approval only — <b>no real booking, payment, or ticketing</b> is performed in this demo.</p><div className="modal-actions"><button className="ghost" onClick={() => decide("declined")}>Decline</button><button onClick={() => decide("approved")}>Approve plan</button></div></div></div>
      )}
    </div>
  );
}
