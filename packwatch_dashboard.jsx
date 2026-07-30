import { useState, useMemo, useEffect, useRef } from "react";
import { Search, Flame, Clock, ExternalLink, Filter, ArrowUpDown, Radio } from "lucide-react";

// ---------------------------------------------------------------------------
// Sample data — shaped exactly like what the real scraper backend would emit.
// Each record: { id, game, set, product, retailer, price, shipping, url,
//   status: 'preorder_open' | 'preorder_soon' | 'in_stock' | 'low_stock',
//   releaseDate, dealScore (vs MSRP), spotted }
// ---------------------------------------------------------------------------
const GAMES = ["One Piece", "Pokémon", "Union Arena", "Dragon Ball", "Naruto"];

const DATA = [
  { id: 1, game: "One Piece", set: "OP-17 The Four Emperors", product: "Booster Box (24 packs)", retailer: "Gamers Guild AZ", price: 104.99, msrp: 119.76, shipping: 0, status: "preorder_open", releaseDate: "2026-08-26", spotted: "6h ago" },
  { id: 2, game: "One Piece", set: "OP-17 The Four Emperors", product: "Booster Box (24 packs)", retailer: "TCGPlayer (verified seller)", price: 112.5, msrp: 119.76, shipping: 4.99, status: "preorder_open", releaseDate: "2026-08-26", spotted: "1h ago" },
  { id: 3, game: "One Piece", set: "3rd Anniversary Set", product: "Premium Bandai Exclusive", retailer: "Premium Bandai", price: 89.99, msrp: 89.99, shipping: 12.0, status: "preorder_soon", releaseDate: "2026-09-01", spotted: "2d ago" },
  { id: 4, game: "Pokémon", set: "30th Celebration", product: "Elite Trainer Box", retailer: "Pokémon Center", price: 59.99, msrp: 59.99, shipping: 0, status: "preorder_soon", releaseDate: "2026-09-18", spotted: "5h ago" },
  { id: 5, game: "Pokémon", set: "Storm Emerald (JP)", product: "Booster Box", retailer: "TCGPlayer", price: 84.0, msrp: 99.99, shipping: 0, status: "preorder_open", releaseDate: "2026-08-07", spotted: "3h ago" },
  { id: 6, game: "Pokémon", set: "Mega Evolution: Pitch Black", product: "Booster Box", retailer: "Amazon", price: 89.99, msrp: 143.64, shipping: 0, status: "low_stock", releaseDate: "2026-07-17", spotted: "40m ago" },
  { id: 7, game: "Union Arena", set: "InuYasha [UA50BT]", product: "Booster Box", retailer: "N4YTCG", price: 74.99, msrp: 79.99, shipping: 0, status: "preorder_open", releaseDate: "2026-08-14", spotted: "12h ago" },
  { id: 8, game: "Union Arena", set: "Attack on Titan Vol. 2", product: "Booster Box", retailer: "TCG Corner", price: 78.5, msrp: 79.99, shipping: 6.5, status: "preorder_soon", releaseDate: "2026-09-10", spotted: "1d ago" },
  { id: 9, game: "Union Arena", set: "BLEACH Vol. 3", product: "Advanced Deck (all-foil)", retailer: "Hobbiesville", price: 34.99, msrp: 34.99, shipping: 0, status: "preorder_soon", releaseDate: "2026-11-06", spotted: "3d ago" },
  { id: 10, game: "Dragon Ball", set: "Fusion World FB05", product: "Booster Box", retailer: "PHD Games", price: 79.99, msrp: 89.99, shipping: 0, status: "in_stock", releaseDate: "2026-08-01", spotted: "9h ago" },
  { id: 11, game: "Naruto", set: "Kayou Tier 4 Wave 2", product: "Booster Box", retailer: "TCGPlayer", price: 44.99, msrp: 49.99, shipping: 3.0, status: "in_stock", releaseDate: "2026-08-05", spotted: "1d ago" },
  { id: 12, game: "Pokémon", set: "Delta Reign (Mega Rayquaza ex)", product: "Booster Box", retailer: "Pokémon Center", price: 143.64, msrp: 143.64, shipping: 0, status: "preorder_soon", releaseDate: "2026-11-06", spotted: "4d ago" },
];

const STATUS_META = {
  preorder_open: { label: "Preorder open", color: "var(--gold)" },
  preorder_soon: { label: "Opens soon", color: "var(--cyan)" },
  in_stock: { label: "In stock", color: "var(--green)" },
  low_stock: { label: "Low stock", color: "var(--magenta)" },
};

function daysUntil(dateStr) {
  const diff = Math.ceil((new Date(dateStr) - new Date("2026-07-30")) / 86400000);
  return diff;
}

function dealPct(item) {
  if (!item.msrp || item.msrp <= 0) return 0;
  return Math.round(((item.msrp - item.price) / item.msrp) * 100);
}

// Mirrors backend/signals.py — keep thresholds in sync if you change either.
const GREEN_THRESHOLD_PCT = 10;

function buySignal(item) {
  const msrp = item.msrp;
  const effectivePrice = item.price + (item.shipping || 0);
  if (!msrp || msrp <= 0) {
    return { signal: "yellow", reason: "No MSRP on record — can't confirm this is actually a discount." };
  }
  const pct = ((msrp - effectivePrice) / msrp) * 100;

  if (pct < 0) {
    return { signal: "red", reason: `Priced ${Math.abs(pct).toFixed(0)}% ABOVE MSRP — likely marked up or scalped.` };
  }
  if (item.status === "low_stock" && pct < GREEN_THRESHOLD_PCT) {
    return { signal: "red", reason: "Low stock and not a strong discount — risk of paying near/above MSRP." };
  }
  if (pct >= GREEN_THRESHOLD_PCT && (item.status === "preorder_open" || item.status === "in_stock")) {
    return { signal: "green", reason: `${pct.toFixed(0)}% under MSRP and available to buy now.` };
  }
  if (item.status === "preorder_soon") {
    return { signal: "yellow", reason: "Preorder hasn't opened yet — price could still change once it does." };
  }
  return { signal: "yellow", reason: `Only ${pct.toFixed(0)}% under MSRP — modest discount, worth a quick price-check first.` };
}

const SIGNAL_META = {
  green: { color: "var(--green)", label: "Good buy" },
  yellow: { color: "var(--gold)", label: "Skeptical" },
  red: { color: "var(--red)", label: "Bad buy" },
};

// Original mascot design for PackWatch — not based on any existing character.
// A small "pack spirit" holding a foil card, built entirely from basic shapes.
function Mascot({ size = 48 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="mascotBody" x1="20" y1="20" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4fd1c5" />
          <stop offset="55%" stopColor="#8a7fe0" />
          <stop offset="100%" stopColor="#ff6fd8" />
        </linearGradient>
        <linearGradient id="mascotCard" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e8b04b" />
          <stop offset="100%" stopColor="#4fd1c5" />
        </linearGradient>
      </defs>
      {/* ears */}
      <ellipse cx="34" cy="30" rx="10" ry="14" fill="url(#mascotBody)" transform="rotate(-18 34 30)" />
      <ellipse cx="86" cy="30" rx="10" ry="14" fill="url(#mascotBody)" transform="rotate(18 86 30)" />
      {/* body/head blob */}
      <ellipse cx="60" cy="66" rx="40" ry="36" fill="url(#mascotBody)" />
      {/* cheeks */}
      <ellipse cx="34" cy="72" rx="7" ry="5" fill="#ff6fd8" opacity="0.5" />
      <ellipse cx="86" cy="72" rx="7" ry="5" fill="#ff6fd8" opacity="0.5" />
      {/* eyes */}
      <ellipse cx="45" cy="60" rx="8" ry="10" fill="#14161c" />
      <ellipse cx="75" cy="60" rx="8" ry="10" fill="#14161c" />
      <circle cx="47.5" cy="55.5" r="2.6" fill="#fff" />
      <circle cx="77.5" cy="55.5" r="2.6" fill="#fff" />
      {/* smile */}
      <path d="M50 78 Q60 86 70 78" stroke="#14161c" strokeWidth="3" strokeLinecap="round" fill="none" />
      {/* held foil card, tilted */}
      <g transform="rotate(-12 82 92)">
        <rect x="68" y="76" width="28" height="36" rx="4" fill="url(#mascotCard)" stroke="#14161c" strokeWidth="1.5" />
        <path d="M68 92 L96 84" stroke="#ffffff" strokeWidth="2.5" opacity="0.6" />
        <path d="M75 76 L96 108" stroke="#ffffff" strokeWidth="1.5" opacity="0.35" />
      </g>
    </svg>
  );
}

function Ticker({ rows }) {
  const hot = useMemo(
    () =>
      [...rows]
        .sort((a, b) => dealPct(b) - dealPct(a))
        .slice(0, 6)
        .map((d) => `${d.set} · ${dealPct(d) > 0 ? `${dealPct(d)}% under MSRP` : "just spotted"} @ ${d.retailer}`),
    [rows]
  );
  if (hot.length === 0) return null;
  const text = hot.join("   ///   ");
  return (
    <div className="ticker-wrap">
      <div className="ticker-label">
        <Radio size={13} strokeWidth={2.5} />
        LIVE
      </div>
      <div className="ticker-track">
        <div className="ticker-content">{text}&nbsp;&nbsp;&nbsp;///&nbsp;&nbsp;&nbsp;{text}</div>
      </div>
    </div>
  );
}

// Point this at your deployed API (see api.py) or a hosted deals.json export
// (see export_json.py) once you've deployed. Left blank, the dashboard runs
// entirely on the bundled sample data below — safe to ship as-is.
const LIVE_DATA_URL = ""; // e.g. "https://your-api.onrender.com/deals"

export default function App() {
  const [activeGame, setActiveGame] = useState("All");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("deal");
  const [statusFilter, setStatusFilter] = useState("all");
  const [signalFilter, setSignalFilter] = useState("all");
  const [rows, setRows] = useState(DATA);
  const [liveStatus, setLiveStatus] = useState(LIVE_DATA_URL ? "connecting" : "sample");

  useEffect(() => {
    if (!LIVE_DATA_URL) return;
    let cancelled = false;
    fetch(LIVE_DATA_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json) => {
        if (cancelled) return;
        const incoming = Array.isArray(json) ? json : json.deals || [];
        if (incoming.length > 0) {
          setRows(incoming);
          setLiveStatus("live");
        } else {
          setLiveStatus("sample");
        }
      })
      .catch(() => {
        if (!cancelled) setLiveStatus("sample");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    let out = rows.filter((d) => {
      if (activeGame !== "All" && d.game !== activeGame) return false;
      if (statusFilter !== "all" && d.status !== statusFilter) return false;
      if (signalFilter !== "all" && buySignal(d).signal !== signalFilter) return false;
      if (query && !`${d.set} ${d.product} ${d.retailer}`.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
    out.sort((a, b) => {
      if (sortBy === "deal") return dealPct(b) - dealPct(a);
      if (sortBy === "price") return a.price + a.shipping - (b.price + b.shipping);
      if (sortBy === "soonest") return daysUntil(a.releaseDate) - daysUntil(b.releaseDate);
      return 0;
    });
    return out;
  }, [rows, activeGame, query, sortBy, statusFilter, signalFilter]);

  return (
    <div className="pw-root">
      <div className="pw-bg" aria-hidden="true">
        <div className="pw-bg-speedlines" />
        <div className="pw-bg-halftone" />
        <div className="pw-bg-holo" />
        {/* CC0 / public domain illustration — "Trio of Chibi Anime Characters" by DG-RA, freesvg.org.
            Not tied to any franchise, safe to use commercially without permission or credit,
            though DG-RA is credited here as good practice. */}
        <img
          className="pw-bg-illustration"
          src="https://freesvg.org/img/1697389064Chibis_trio__02_DG-RA_FreeSVG.png"
          alt=""
          loading="lazy"
        />
      </div>
      <style>{`
        .pw-root {
          --bg: #12141c;
          --panel: #1a1d29;
          --panel-2: #20232f;
          --line: #2b2f3d;
          --text: #f1f0ec;
          --text-dim: #9498a8;
          --gold: #e8b04b;
          --cyan: #4fd1c5;
          --magenta: #ff6fd8;
          --red: #ef4444;
          --green: #7ee08a;
          font-family: 'Inter', -apple-system, sans-serif;
          background: var(--bg);
          color: var(--text);
          min-height: 100vh;
          padding: 0 0 48px;
          position: relative;
          isolation: isolate;
          overflow: hidden;
        }
        .pw-root .mono { font-family: 'JetBrains Mono', 'Courier New', monospace; }

        /* ---- Background art: original manga/foil motifs, no licensed imagery ---- */
        .pw-bg {
          position: fixed;
          inset: 0;
          z-index: -1;
          overflow: hidden;
          pointer-events: none;
        }
        .pw-bg-speedlines {
          position: absolute;
          top: -20%;
          right: -20%;
          width: 140%;
          height: 140%;
          background: repeating-conic-gradient(
            from 0deg at 100% 0%,
            rgba(79, 209, 197, 0.05) 0deg 1.2deg,
            transparent 1.2deg 6deg
          );
          transform-origin: 100% 0%;
        }
        .pw-bg-halftone {
          position: absolute;
          inset: 0;
          opacity: 0.35;
          background-image: radial-gradient(circle, rgba(255,255,255,0.06) 1px, transparent 1.4px);
          background-size: 14px 14px;
          background-position: 0 0;
          mask-image: radial-gradient(ellipse 80% 60% at 30% 20%, black 0%, transparent 70%);
          -webkit-mask-image: radial-gradient(ellipse 80% 60% at 30% 20%, black 0%, transparent 70%);
        }
        .pw-bg-holo {
          position: absolute;
          inset: -10%;
          background: linear-gradient(
            115deg,
            transparent 20%,
            rgba(79, 209, 197, 0.06) 35%,
            rgba(255, 111, 216, 0.07) 45%,
            rgba(232, 176, 75, 0.05) 55%,
            transparent 70%
          );
          background-size: 250% 250%;
          animation: holo-sweep 18s ease-in-out infinite;
        }
        @keyframes holo-sweep {
          0%   { background-position: 0% 20%; }
          50%  { background-position: 100% 80%; }
          100% { background-position: 0% 20%; }
        }
        @media (prefers-reduced-motion: reduce) {
          .pw-bg-holo { animation: none; }
        }
        .pw-bg-illustration {
          position: absolute;
          bottom: -4%;
          right: -3%;
          width: 340px;
          max-width: 40vw;
          opacity: 0.1;
          filter: saturate(0.7) brightness(1.3);
          mix-blend-mode: luminosity;
          pointer-events: none;
        }

        .pw-header {
          padding: 28px 28px 18px;
          border-bottom: 1px solid var(--line);
        }
        .pw-brand {
          display: flex;
          align-items: baseline;
          gap: 10px;
        }
        .pw-brand h1 {
          font-family: 'Archivo Black', 'Arial Black', sans-serif;
          font-size: 26px;
          letter-spacing: -0.5px;
          margin: 0;
          background: linear-gradient(90deg, var(--cyan), var(--magenta));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        .pw-brand .tag {
          font-size: 11px;
          color: var(--text-dim);
          text-transform: uppercase;
          letter-spacing: 1.5px;
        }
        .pw-sub { color: var(--text-dim); font-size: 13px; margin-top: 6px; }

        .ticker-wrap {
          display: flex;
          align-items: stretch;
          background: #0d0f16;
          border-bottom: 1px solid var(--line);
          overflow: hidden;
        }
        .ticker-label {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 6px;
          background: var(--magenta);
          color: #14161c;
          font-weight: 800;
          font-size: 11px;
          letter-spacing: 1px;
          padding: 8px 14px;
        }
        .ticker-track { overflow: hidden; flex: 1; display: flex; align-items: center; }
        .ticker-content {
          white-space: nowrap;
          padding-left: 100%;
          font-family: 'JetBrains Mono', monospace;
          font-size: 12.5px;
          color: var(--gold);
          animation: scroll-left 32s linear infinite;
        }
        @keyframes scroll-left {
          0% { transform: translateX(0); }
          100% { transform: translateX(-100%); }
        }
        @media (prefers-reduced-motion: reduce) {
          .ticker-content { animation: none; padding-left: 16px; }
        }

        .pw-controls {
          padding: 20px 28px 0;
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
        }
        .pw-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
        .pw-tab {
          background: var(--panel);
          border: 1px solid var(--line);
          color: var(--text-dim);
          padding: 7px 14px;
          border-radius: 999px;
          font-size: 13px;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .pw-tab.active { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
        .pw-tab:hover:not(.active) { border-color: var(--text-dim); color: var(--text); }

        .pw-search {
          display: flex;
          align-items: center;
          gap: 8px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 7px 12px;
          margin-left: auto;
          min-width: 220px;
        }
        .pw-search input {
          background: transparent;
          border: none;
          outline: none;
          color: var(--text);
          font-size: 13px;
          width: 100%;
        }
        .pw-search input::placeholder { color: var(--text-dim); }

        .pw-filters-row {
          padding: 12px 28px 0;
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
          align-items: center;
          font-size: 12.5px;
          color: var(--text-dim);
        }
        .pw-select {
          background: var(--panel);
          border: 1px solid var(--line);
          color: var(--text);
          border-radius: 6px;
          padding: 5px 9px;
          font-size: 12.5px;
        }
        .pw-count { margin-left: auto; }

        .pw-grid {
          padding: 18px 28px 0;
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 14px;
        }
        .pw-card {
          background: rgba(26, 29, 41, 0.82);
          backdrop-filter: blur(6px);
          -webkit-backdrop-filter: blur(6px);
          border: 1px solid var(--line);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          transition: border-color 0.15s ease, transform 0.15s ease;
        }
        .pw-card:hover { border-color: var(--text-dim); transform: translateY(-2px); }
        .pw-card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
        .pw-game-pill {
          font-size: 10.5px;
          text-transform: uppercase;
          letter-spacing: 0.6px;
          color: var(--text-dim);
        }
        .pw-status-pill {
          font-size: 10.5px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 999px;
          white-space: nowrap;
        }
        .pw-set-name { font-size: 15px; font-weight: 700; line-height: 1.3; }
        .pw-product { font-size: 12.5px; color: var(--text-dim); }

        .pw-price-row { display: flex; align-items: baseline; gap: 8px; margin-top: 2px; }
        .pw-price { font-family: 'JetBrains Mono', monospace; font-size: 21px; font-weight: 700; }
        .pw-msrp { font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--text-dim); text-decoration: line-through; }
        .pw-deal-badge {
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          font-weight: 700;
          color: var(--green);
          background: rgba(126,224,138,0.12);
          padding: 2px 7px;
          border-radius: 5px;
        }

        .pw-meta-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: var(--text-dim);
          border-top: 1px solid var(--line);
          padding-top: 10px;
          margin-top: 2px;
        }
        .pw-countdown { display: flex; align-items: center; gap: 4px; }
        .pw-link {
          display: flex;
          align-items: center;
          gap: 5px;
          color: var(--cyan);
          font-size: 12.5px;
          font-weight: 600;
          text-decoration: none;
          cursor: pointer;
        }
        .pw-spotted { font-size: 10.5px; color: var(--text-dim); opacity: 0.7; }

        .pw-empty {
          padding: 60px 28px;
          text-align: center;
          color: var(--text-dim);
        }

        .pw-footnote {
          padding: 28px 28px 0;
          font-size: 11.5px;
          color: var(--text-dim);
          line-height: 1.6;
          border-top: 1px solid var(--line);
          margin-top: 24px;
        }
      `}</style>

      <div className="pw-header">
        <div className="pw-brand">
          <Mascot size={44} />
          <h1>PackWatch</h1>
          <span className="tag">anime tcg preorder + deal radar</span>
        </div>
        <div className="pw-sub">
          Tracking One Piece, Pokémon, Union Arena, Dragon Ball &amp; Naruto across major retailers.{" "}
          <span style={{ color: liveStatus === "live" ? "var(--green)" : "var(--text-dim)" }}>
            {liveStatus === "live" ? "● Live data connected" : liveStatus === "connecting" ? "connecting to live feed…" : "showing sample data — connect an API to go live"}
          </span>
        </div>
      </div>

      <Ticker rows={rows} />

      <div className="pw-controls">
        <div className="pw-tabs">
          {["All", ...GAMES].map((g) => (
            <button key={g} className={`pw-tab ${activeGame === g ? "active" : ""}`} onClick={() => setActiveGame(g)}>
              {g}
            </button>
          ))}
        </div>
        <div className="pw-search">
          <Search size={14} color="#9498a8" />
          <input placeholder="Search set, product, retailer…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>

      <div className="pw-filters-row">
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <Filter size={12} /> Status
        </span>
        <select className="pw-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="preorder_open">Preorder open</option>
          <option value="preorder_soon">Opens soon</option>
          <option value="in_stock">In stock</option>
          <option value="low_stock">Low stock</option>
        </select>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)", display: "inline-block" }} />
          Signal
        </span>
        <select className="pw-select" value={signalFilter} onChange={(e) => setSignalFilter(e.target.value)}>
          <option value="all">All signals</option>
          <option value="green">🟢 Good buy</option>
          <option value="yellow">🟡 Skeptical</option>
          <option value="red">🔴 Bad buy</option>
        </select>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <ArrowUpDown size={12} /> Sort
        </span>
        <select className="pw-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="deal">Best deal (% under MSRP)</option>
          <option value="price">Lowest total price</option>
          <option value="soonest">Releasing soonest</option>
        </select>
        <span className="pw-count">{filtered.length} result{filtered.length !== 1 ? "s" : ""}</span>
      </div>

      {filtered.length === 0 ? (
        <div className="pw-empty">
          <Mascot size={56} />
          <div style={{ marginTop: 10 }}>Nothing matches those filters yet. Try a different game or clear the search.</div>
        </div>
      ) : (
        <div className="pw-grid">
          {filtered.map((d) => {
            const pct = dealPct(d);
            const days = daysUntil(d.releaseDate);
            const meta = STATUS_META[d.status];
            return (
              <div className="pw-card" key={d.id}>
                <div className="pw-card-top">
                  <span className="pw-game-pill">{d.game}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      title={buySignal(d).reason}
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: SIGNAL_META[buySignal(d).signal].color,
                        flexShrink: 0,
                        cursor: "help",
                      }}
                    />
                    <span className="pw-status-pill" style={{ color: meta.color, background: `${meta.color}22` }}>
                      {meta.label}
                    </span>
                  </div>
                </div>
                <div>
                  <div className="pw-set-name">{d.set}</div>
                  <div className="pw-product">{d.product}</div>
                </div>
                <div className="pw-price-row">
                  <span className="pw-price">${(d.price + d.shipping).toFixed(2)}</span>
                  {pct > 0 && <span className="pw-msrp">${d.msrp.toFixed(2)}</span>}
                  {pct > 0 && (
                    <span className="pw-deal-badge">
                      <Flame size={10} style={{ display: "inline", marginRight: 2, verticalAlign: -1 }} />
                      {pct}% off
                    </span>
                  )}
                </div>
                <div className="pw-meta-row">
                  <span className="pw-countdown">
                    <Clock size={12} />
                    {days > 0 ? `${days}d to release` : days === 0 ? "Releases today" : "Released"}
                  </span>
                  <a className="pw-link" href={d.url || "#"} onClick={(e) => e.preventDefault()}>
                    {d.retailer} <ExternalLink size={11} />
                  </a>
                </div>
                <div className="pw-spotted">spotted {d.spotted} · shipping {d.shipping === 0 ? "free" : `$${d.shipping.toFixed(2)}`}</div>
                <div className="pw-spotted" style={{ color: SIGNAL_META[buySignal(d).signal].color, opacity: 0.9 }}>
                  {SIGNAL_META[buySignal(d).signal].label}: {buySignal(d).reason}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="pw-footnote">
        This view is running on sample data structured to match the real scraper output. Wire it up to a live backend (see the accompanying scraper + API code) to replace DATA with a fetch() call and get real-time results.
        <br />
        As an Amazon Associate and affiliate for other retailers, PackWatch may earn a commission on qualifying purchases made through links on this site, at no extra cost to you.
      </div>
    </div>
  );
}
