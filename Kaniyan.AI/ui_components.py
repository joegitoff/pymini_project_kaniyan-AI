"""
ui_components.py - presentation helpers for the Kaniyan AI light dashboard (CSS, brand, header, KPI cards,
risk card, status chips).

Only presentation lives here; no calculation. Every piece of text that can come from outside (place names,
API messages) is HTML-escaped before it is placed into an HTML string. The `*_html` functions return plain
strings so they can be tested without Streamlit.

Colour palette (kept in step with charts.py):
  page #F7F8FC | card #FFFFFF | border #E3E6EF | text #1F2430 | muted #6B7280
  violet #6D28D9 (primary) | teal #0D9488 (secondary) | green #16A34A | amber #D97706 | orange #EA580C | red #DC2626
"""
from __future__ import annotations

import base64
from html import escape

import streamlit as st

import data_service as ds
from config import Level
from risk import RiskCategory

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Tamil:wght@400;500;600&display=swap');
:root{--kn-bg:#F7F8FC;--kn-card:#FFFFFF;--kn-border:#E3E6EF;--kn-text:#1F2430;--kn-muted:#6B7280;
--kn-violet:#6D28D9;--kn-violet-soft:#F3EEFF;--kn-teal:#0D9488;--kn-green:#16A34A;--kn-amber:#D97706;
--kn-orange:#EA580C;--kn-red:#DC2626;--kn-shadow:0 1px 2px rgba(31,36,48,.04),0 4px 14px rgba(31,36,48,.05)}
html,body,.stApp,[data-testid="stAppViewContainer"]{font-family:Inter,'Noto Sans Tamil','Segoe UI',system-ui,-apple-system,sans-serif;color:var(--kn-text)}
.stApp{background:var(--kn-bg)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"]{right:.5rem}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1280px}
h1,h2,h3,h4{color:var(--kn-text);letter-spacing:-.01em}
h4{font-size:1.02rem;font-weight:650;margin-top:.4rem}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid var(--kn-border)}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarUserContent"]{padding-top:1rem}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{font-size:.72rem;font-weight:650;letter-spacing:.08em;text-transform:uppercase;color:var(--kn-muted);margin:.9rem 0 .2rem}
[data-testid="stSidebar"] label p{font-size:.84rem;color:var(--kn-text)}
[data-testid="stSidebar"] hr{margin:.8rem 0;border-color:var(--kn-border)}
.kn-brand{display:flex;align-items:center;gap:.65rem;padding:.1rem 0 .6rem}
.kn-brand img{width:38px;height:38px;border-radius:10px;display:block}
.kn-brand .n{font-size:1.1rem;font-weight:700;line-height:1.15;color:var(--kn-text)}
.kn-brand .s{font-size:.74rem;color:var(--kn-muted);line-height:1.25}

/* ---------- header ---------- */
.kn-header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.8rem 1.4rem;
background:var(--kn-card);border:1px solid var(--kn-border);border-radius:16px;padding:.85rem 1.1rem;box-shadow:var(--kn-shadow)}
.kn-header .meta{display:flex;flex-wrap:wrap;gap:.5rem .6rem;align-items:center}
.kn-pill{display:inline-flex;align-items:center;gap:.4rem;padding:.28rem .7rem;border-radius:999px;border:1px solid var(--kn-border);
background:#FAFAFD;font-size:.82rem;color:var(--kn-text)}
.kn-pill img{width:15px;height:15px}
.kn-pill.muted{color:var(--kn-muted)}
.kn-notice{font-size:.8rem;color:var(--kn-muted);margin:.35rem .2rem 0}

/* ---------- KPI cards ---------- */
.kn-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:.85rem;margin:.9rem 0 1rem}
.kn-kpi{background:var(--kn-card);border:1px solid var(--kn-border);border-radius:16px;padding:.9rem 1rem;box-shadow:var(--kn-shadow);
display:flex;flex-direction:column;gap:.15rem;min-height:128px}
.kn-kpi .top{display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.kn-kpi .lab{display:flex;align-items:center;gap:.5rem;font-size:.82rem;color:var(--kn-muted);font-weight:500}
.kn-kpi .ico{width:30px;height:30px;border-radius:9px;background:var(--kn-violet-soft);display:inline-flex;align-items:center;justify-content:center}
.kn-kpi .ico img{width:17px;height:17px}
.kn-kpi .val{font-size:1.85rem;font-weight:700;line-height:1.25;margin-top:.25rem;color:var(--kn-text)}
.kn-kpi .val small{font-size:.85rem;font-weight:500;color:var(--kn-muted);margin-left:.25rem}
.kn-kpi .ctx{font-size:.8rem;color:var(--kn-muted);line-height:1.35}

/* ---------- status pills ---------- */
.kn-st{display:inline-flex;align-items:center;gap:.35rem;padding:.12rem .55rem;border-radius:999px;font-size:.72rem;font-weight:600;white-space:nowrap}
.kn-st:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.kn-st.ok{background:#ECFDF5;color:#15803D}
.kn-st.info{background:#EFF6FF;color:#1D4ED8}
.kn-st.watch{background:#FFFBEB;color:#B45309}
.kn-st.high{background:#FFF1E8;color:#C2410C}
.kn-st.severe{background:#FEF2F2;color:#B91C1C}
.kn-st.na{background:#F3F4F6;color:#6B7280}

/* ---------- risk card ---------- */
.kn-risk{background:var(--kn-card);border:1px solid var(--kn-border);border-left:5px solid var(--rc);border-radius:16px;
padding:1.1rem 1.3rem;box-shadow:var(--kn-shadow);margin:.2rem 0 1rem}
.kn-risk .eyebrow{font-size:.72rem;font-weight:650;letter-spacing:.08em;text-transform:uppercase;color:var(--kn-muted)}
.kn-risk .head{display:flex;flex-wrap:wrap;align-items:center;gap:.6rem .9rem;margin:.3rem 0 .15rem}
.kn-risk .cat{font-size:1.35rem;font-weight:700;padding:.15rem .8rem;border-radius:10px;background:var(--rt);color:var(--rc)}
.kn-risk .hl{font-size:.95rem;color:var(--kn-text)}
.kn-risk .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.4rem 1.6rem;margin-top:.7rem}
.kn-risk h5{font-size:.76rem;font-weight:650;letter-spacing:.06em;text-transform:uppercase;color:var(--kn-muted);margin:.4rem 0 .25rem}
.kn-risk ul{margin:0 0 .2rem 1.05rem;padding:0;font-size:.9rem;line-height:1.5}
.kn-risk .stats{display:flex;flex-wrap:wrap;gap:.45rem}
.kn-risk .stat{border:1px solid var(--kn-border);background:#FAFAFD;border-radius:10px;padding:.35rem .7rem;font-size:.82rem}
.kn-risk .stat b{display:block;font-size:1rem}
.kn-risk .period{font-size:.85rem;color:var(--kn-text)}
.kn-risk .cav{font-size:.8rem;color:#B45309;margin-top:.3rem}
.kn-risk .disc{font-size:.78rem;color:var(--kn-muted);margin-top:.8rem;padding-top:.6rem;border-top:1px dashed var(--kn-border)}

/* ---------- generic cards / grid / chips ---------- */
.kn-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.7rem;margin:.3rem 0 1rem}
.kn-card{background:var(--kn-card);border:1px solid var(--kn-border);border-radius:14px;padding:.7rem .95rem;box-shadow:var(--kn-shadow)}
.kn-card .l{font-size:.78rem;color:var(--kn-muted);font-weight:500}
.kn-card .v{font-size:1.35rem;font-weight:650;line-height:1.35}
.kn-card .s{font-size:.75rem;color:var(--kn-muted)}
.kn-chip{display:inline-block;padding:.15rem .65rem;border-radius:999px;border:1px solid var(--kn-border);background:var(--kn-card);font-size:.8rem;margin:.55rem .4rem .2rem 0}
.kn-tag{display:inline-block;padding:.05rem .5rem;border-radius:6px;border:1px solid var(--kn-border);font-size:.7rem;margin-left:.4rem;vertical-align:middle;color:var(--kn-muted);background:#fff}
.kn-demo{background:#F5F3FF;border:1px solid #DDD6FE;color:#5B21B6;border-radius:12px;padding:.6rem .9rem;font-size:.88rem;margin:.7rem 0 0}

/* ---------- Streamlit widgets ---------- */
button[data-baseweb="tab"]{font-weight:550;color:var(--kn-muted);padding:.55rem .9rem}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--kn-violet)}
[data-baseweb="tab-highlight"]{background-color:var(--kn-violet)!important;height:3px;border-radius:3px}
[data-baseweb="tab-list"]{gap:.1rem;border-bottom:1px solid var(--kn-border);overflow-x:auto}
.stButton>button,[data-testid="stBaseButton-secondary"]{border-radius:10px;border:1px solid var(--kn-border);background:#fff;color:var(--kn-text);font-weight:550;box-shadow:none}
.stButton>button:hover{border-color:var(--kn-violet);color:var(--kn-violet);background:var(--kn-violet-soft)}
[data-testid="stPlotlyChart"]{background:#fff;border:1px solid var(--kn-border);border-radius:16px;padding:.5rem .6rem;box-shadow:var(--kn-shadow);margin-bottom:.9rem}
[data-testid="stDataFrame"]{border:1px solid var(--kn-border);border-radius:12px;overflow:hidden}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--kn-border)!important;border-radius:12px}
[data-testid="stAlert"]{border-radius:12px}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--kn-border);border-radius:14px;padding:.7rem .9rem;box-shadow:var(--kn-shadow)}
[data-testid="stVerticalBlockBorderWrapper"]:has(.kn-chat-anchor){background:#fff;border:1px solid var(--kn-border);border-top:4px solid var(--kn-violet);border-radius:16px;box-shadow:var(--kn-shadow);padding:.4rem .5rem}

/* ---------- Ask Kaniyan AI chat card ---------- */
.kn-chat-head{display:flex;align-items:center;gap:.7rem;margin-bottom:.2rem}
.kn-chat-head img{width:40px;height:40px;border-radius:11px}
.kn-chat-head .t{font-size:1.2rem;font-weight:700;line-height:1.2}
.kn-chat-head .s{font-size:.85rem;color:var(--kn-muted)}
.kn-welcome{background:var(--kn-violet-soft);border:1px solid #E4D9FF;border-radius:12px;padding:.65rem .9rem;font-size:.88rem;margin:.5rem 0 .3rem}
.kn-note{font-size:.76rem;color:var(--kn-muted);margin-top:.2rem}
.kn-note.warn{color:#B45309}
[data-testid="stChatMessage"]{border-radius:14px;padding:.7rem .9rem;margin-bottom:.45rem;border:1px solid var(--kn-border);background:#F9FAFC}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){background:var(--kn-violet-soft);border-color:#E4D9FF}
[data-testid="stChatInput"]{border-radius:14px;border:1px solid var(--kn-border)}

@media (max-width:640px){
.block-container{padding-left:.9rem;padding-right:.9rem}
.kn-kpi{min-height:0}.kn-kpi .val{font-size:1.5rem}.kn-risk .cat{font-size:1.15rem}.kn-header{padding:.7rem .8rem}
}
</style>
"""

STATUS_ICON = {ds.STATUS_LIVE: "🟢", ds.STATUS_CACHED: "🟠", ds.STATUS_UNAVAILABLE: "🔴", ds.STATUS_DEMO: "🟣"}

# (accent colour, tint, status-pill class) for each overall category. The label is always written out too.
RISK_STYLE = {
    RiskCategory.LOW: ("#16A34A", "#ECFDF5", "ok"),
    RiskCategory.MODERATE: ("#D97706", "#FFFBEB", "watch"),
    RiskCategory.HIGH: ("#EA580C", "#FFF1E8", "high"),
    RiskCategory.VERY_HIGH: ("#DC2626", "#FEF2F2", "severe"),
}

# ------------------------------------------------------------------ icons ---
_ICONS = {
    "thermometer": '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>',
    "wind": '<path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2"/><path d="M9.6 4.6A2 2 0 1 1 11 8H2"/><path d="M12.6 19.4A2 2 0 1 0 14 16H2"/>',
    "rain": '<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M16 14v6"/><path d="M8 14v6"/><path d="M12 16v6"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    "pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
}


def _data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def icon_uri(name: str, color: str = "#6D28D9") -> str:
    """A small stroke icon as a data-URI (works inside st.markdown without relying on inline-SVG support)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
    return _data_uri(svg)


def logo_uri() -> str:
    """Kaniyan AI mark: the existing shield identity, simplified, with a small wave line for 'environment'."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="12" fill="#6D28D9"/>'
           '<g transform="translate(9 9) scale(1.25)" fill="none" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round" '
           f'stroke-linejoin="round">{_ICONS["shield"]}<path d="M8 12.5c1.4-1.8 2.8-1.8 4 0s2.6 1.8 4 0" stroke="#5EEAD4"/></g></svg>')
    return _data_uri(svg)


# ------------------------------------------------------------- pure HTML ---
def status_pill(kind: str, text: str) -> str:
    return f'<span class="kn-st {escape(kind)}">{escape(text)}</span>'


def level_status(level) -> tuple:
    """(css kind, label) for the highest rule-based alert level of one measurement. None = no rule triggered."""
    if level is None:
        return "ok", "No alert"
    return {Level.INFO: ("info", "Information"), Level.CAUTION: ("watch", "Caution"),
            Level.HIGH: ("severe", "High concern")}[Level(int(level))]


def brand_html() -> str:
    return (f'<div class="kn-brand"><img src="{logo_uri()}" alt="Kaniyan AI logo"/>'
            f'<div><div class="n">Kaniyan AI</div><div class="s">Tamil-first Environmental Intelligence</div></div></div>')


def header_html(location_label: str, updated_text: str, data_label: str = "") -> str:
    """Top header: brand on the left; location, data time and (optional) data-status on the right."""
    pills = (f'<span class="kn-pill"><img src="{icon_uri("pin")}" alt=""/>{escape(location_label)}</span>'
             f'<span class="kn-pill muted"><img src="{icon_uri("clock", "#6B7280")}" alt=""/>{escape(updated_text)}</span>')
    if data_label:
        pills += f'<span class="kn-pill muted">{escape(data_label)}</span>'
    return (f'<div class="kn-header"><div class="kn-brand" style="padding:0"><img src="{logo_uri()}" alt="Kaniyan AI logo"/>'
            f'<div><div class="n">Kaniyan AI</div><div class="s">Tamil-first Environmental Intelligence</div></div></div>'
            f'<div class="meta">{pills}</div></div>')


def kpi_card_html(icon: str, label: str, value: str, unit: str = "", context: str = "",
                  status: tuple = None) -> str:
    """One summary card. `status` is (css kind, text) or None. Missing values must be passed as 'Unavailable'."""
    pill = status_pill(*status) if status else ""
    unit_html = f"<small>{escape(unit)}</small>" if unit and value not in ("Unavailable", "n/a") else ""
    return (f'<div class="kn-kpi"><div class="top"><div class="lab"><span class="ico"><img src="{icon_uri(icon)}" alt=""/></span>'
            f'{escape(label)}</div>{pill}</div><div class="val">{escape(value)}{unit_html}</div>'
            f'<div class="ctx">{escape(context)}</div></div>')


def kpi_row_html(cards: list) -> str:
    return f'<div class="kn-kpis">{"".join(kpi_card_html(**c) for c in cards)}</div>'


def risk_card_html(overall, measurements: list, period_text: str, precautions: list) -> str:
    """Overall risk card: category, reasons, key measurements, period covered, precautions and the disclaimer."""
    accent, tint, kind = RISK_STYLE[overall.category]
    reasons = "".join(f"<li>{escape(r)}</li>" for r in overall.reasons[:5])
    steps = "".join(f"<li>{escape(p)}</li>" for p in precautions[:4])
    stats = "".join(f'<div class="stat">{escape(label)}<b>{escape(value)}</b></div>' for label, value in measurements)
    caveats = "".join(f'<div class="cav">Note: {escape(c)}</div>' for c in overall.caveats)
    return (f'<div class="kn-risk" style="--rc:{accent};--rt:{tint}" role="status">'
            f'<div class="eyebrow">Overall environmental risk (app-generated)</div>'
            f'<div class="head"><span class="cat">{escape(overall.category.label)}</span><span class="hl">{escape(overall.headline)}</span></div>'
            f'<div class="cols"><div><h5>Why this level</h5><ul>{reasons}</ul></div>'
            f'<div><h5>Recommended precautions</h5><ul><li>{escape(overall.recommendation)}</li>{steps}</ul></div></div>'
            f'<div class="cols"><div><h5>Relevant measurements</h5><div class="stats">{stats or "<span class=period>Unavailable</span>"}</div></div>'
            f'<div><h5>Forecast period covered</h5><div class="period">{escape(period_text)}</div></div></div>'
            f'{caveats}<div class="disc"><b>Not an official warning.</b> {escape(overall.disclaimer)}</div></div>')


def chat_header_html() -> str:
    return (f'<span class="kn-chat-anchor"></span><div class="kn-chat-head"><img src="{logo_uri()}" alt=""/>'
            f'<div><div class="t">Ask Kaniyan AI</div><div class="s">Understand your local environment in Tamil or English.</div></div></div>')


def welcome_html(location_label: str) -> str:
    return (f'<div class="kn-welcome"><b>Vanakkam!</b> I can explain current weather, rainfall, heat, air quality (AQI) and '
            f'precautions for <b>{escape(location_label)}</b>, using only the data shown on this dashboard. '
            f'I explain the app\'s rule-based results; I do not issue official warnings.</div>')


def metric_grid_html(items: list) -> str:
    cards = "".join(
        f'<div class="kn-card"><div class="l">{escape(i["label"])}</div>'
        f'<div class="v">{escape(str(i["value"]))}</div><div class="s">{escape(str(i.get("sub", "")))}</div></div>'
        for i in items)
    return f'<div class="kn-grid">{cards}</div>'


def status_chips_html(status_items: list) -> str:
    return "".join(f'<span class="kn-chip">{STATUS_ICON.get(i.status, "⚪")} <strong>{escape(i.name)}:</strong> '
                   f'{escape(i.label)}</span>' for i in status_items)


# --------------------------------------------------------- Streamlit wrappers ---
def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand() -> None:
    st.markdown(brand_html(), unsafe_allow_html=True)


def header(location_label: str, updated_text: str, data_label: str = "") -> None:
    st.markdown(header_html(location_label, updated_text, data_label), unsafe_allow_html=True)


def kpi_row(cards: list) -> None:
    st.markdown(kpi_row_html(cards), unsafe_allow_html=True)


def risk_card(overall, measurements: list, period_text: str, precautions: list) -> None:
    st.markdown(risk_card_html(overall, measurements, period_text, precautions), unsafe_allow_html=True)


def metric_grid(items: list, tag: str = "") -> None:
    """items: dicts with icon, label, value, sub."""
    st.markdown(metric_grid_html(items), unsafe_allow_html=True)


def section(title: str, tag: str) -> None:
    st.markdown(f'#### {title} <span class="kn-tag">{escape(tag)}</span>', unsafe_allow_html=True)


def status_chips(status_items: list) -> None:
    st.markdown(status_chips_html(status_items), unsafe_allow_html=True)


def show_chart(fig, key=None) -> None:
    """st.plotly_chart across Streamlit versions (newer: width='stretch'; older: use_container_width)."""
    try:
        st.plotly_chart(fig, width="stretch", key=key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, key=key)
