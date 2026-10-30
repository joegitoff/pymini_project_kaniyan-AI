"""
app.py - Kaniyan AI Streamlit dashboard.   Run with:  streamlit run app.py

This file only shows things. The logic lives in:
  data_service.py   fetching, validation, caching, freshness status
  alert_engine.py   threshold rules (current + daily alerts)
  timeline.py       next-24-hours hourly timeline and events
  risk.py           overall Low/Moderate/High/Very High classification
  activity_advice.py  activity-specific recommendations
  assessment.py     runs all of the above and returns one Assessment object
  llm_service.py    optional AI explanations and chat (grounded in the Assessment)
  ui_components.py  light-theme CSS, header, KPI cards, risk card
  charts.py         Plotly charts (white theme)
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import assessment as asm
import charts
import config
import data_service as ds
import llm_service
import recommendations
import sample_data
import timeline
import ui_components as ui
from config import Level

st.set_page_config(page_title="Kaniyan AI", page_icon="🛡️", layout="wide")
ui.inject_css()

LEVEL_ICON = {Level.INFO: "🔵", Level.CAUTION: "🟠", Level.HIGH: "🔴"}
LEVEL_KEYS = ("info", "caution", "high")
LANGUAGE_LABELS = {"English": "English", "Tamil": "தமிழ் (Tamil)"}


# ------------------------------------------------------------------ cached API --
@st.cache_resource
def get_cache() -> ds.DataCache:
    """One process-wide cache shared by all sessions (public weather data), so repeated views cost no API calls."""
    return ds.DataCache()


@st.cache_data(ttl=600, show_spinner=False)
def cached_search(query: str):
    return ds.search_locations(query, count=5)


def fmt(value, unit="", digits=1):
    """Format a number or show 'n/a' for missing values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if number != number else f"{number:.{digits}f}{unit}"


def num(value):
    """A float, or None when the value is missing / not a number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def columns(spec):
    """st.columns with vertical centring where this Streamlit version supports it."""
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def reset_thresholds():
    for key, cuts in config.DEFAULT_THRESHOLDS.items():
        for level_key in LEVEL_KEYS:
            st.session_state[f"thr_{key}_{level_key}"] = float(cuts[level_key])


def request_refresh():
    """Button callback shared by the header and sidebar refresh buttons (same 60-second rule as before)."""
    allowed, wait = ds.can_refresh(st.session_state.get("last_refresh"))
    if allowed:
        st.session_state["force_refresh"] = True
        st.session_state["last_refresh"] = datetime.now(timezone.utc)
    else:
        st.session_state["refresh_notice"] = f"Data were refreshed a moment ago. Please wait {wait} s before refreshing again."


# The header is created first (so it sits at the top) and filled in once the data are known.
header_slot = st.container()
refresh_notice = st.session_state.pop("refresh_notice", None)

# --------------------------------------------------------------------- sidebar --
st.sidebar.markdown(ui.brand_html(), unsafe_allow_html=True)
demo_mode = st.sidebar.toggle("Demo mode (SAMPLE data, no internet)", value=False,
                              help="Uses invented sample data for offline demonstrations. A banner is always shown.")
location = None
if demo_mode:
    location = sample_data.SAMPLE_LOCATION
else:
    st.sidebar.subheader("Location")
    quick = st.sidebar.selectbox("Quick pick", config.QUICK_CITIES, index=0)
    typed = st.sidebar.text_input("...or type any city", value="", placeholder="e.g. Kumbakonam")
    query = typed.strip() or quick
    try:
        matches = cached_search(query)
        labels = [m.label for m in matches]
        chosen = st.sidebar.selectbox("Matching places", labels, index=0)
        location = matches[labels.index(chosen)]
    except ds.DataServiceError as exc:
        st.sidebar.error(str(exc))

st.sidebar.subheader("Your plans (optional)")
activity = st.sidebar.selectbox("Activity", list(config.ACTIVITIES), format_func=config.ACTIVITIES.get,
                                help="Only changes which precautions are shown. No personal information is needed or stored.")

if not demo_mode:
    st.sidebar.subheader("Data")
    st.sidebar.button("Refresh data", on_click=request_refresh,
                      help="Fetch fresh data now (limited to once per minute to protect the free API).")
if refresh_notice:
    st.sidebar.info(refresh_notice)
force_refresh = bool(st.session_state.pop("force_refresh", False)) and not demo_mode

for _key, _cuts in config.DEFAULT_THRESHOLDS.items():          # defaults are set once; user edits persist
    for _lk in LEVEL_KEYS:
        st.session_state.setdefault(f"thr_{_key}_{_lk}", float(_cuts[_lk]))
st.sidebar.subheader("Alerts")
with st.sidebar.expander("Alert thresholds (illustrative)"):
    st.caption(config.THRESHOLD_NOTE)
    for key, label in config.THRESHOLD_LABELS.items():
        lo, hi = config.THRESHOLD_LIMITS[key]
        st.markdown(f"**{label}**")
        cols = st.columns(3)
        for col, level_key in zip(cols, LEVEL_KEYS):
            col.number_input(level_key.capitalize(), min_value=lo, max_value=hi, step=1.0, key=f"thr_{key}_{level_key}")
    st.button("Reset thresholds to defaults", on_click=reset_thresholds)
thresholds = {key: {lk: float(st.session_state[f"thr_{key}_{lk}"]) for lk in LEVEL_KEYS} for key in config.DEFAULT_THRESHOLDS}

st.sidebar.subheader("AI assistant")
use_llm = st.sidebar.checkbox("Use Groq AI explanation (needs API key)", value=False)
if llm_service.is_configured():
    st.sidebar.caption("Groq API key found. The AI chat is active.")
else:
    st.sidebar.caption("No Groq key found - AI features use the rule-based fallback. The app works fully without an LLM.")


# ---------------------------------------------------------------------- header --
def updated_text(results, tz_name) -> str:
    stamps = [r.fetched_at for r in results if r is not None and r.fetched_at]
    if not stamps:
        return "No data retrieved yet"
    latest = max(stamps)
    try:
        local = latest.astimezone(ZoneInfo(tz_name))
    except Exception:                                   # unknown / 'auto' time zone: say UTC instead of guessing
        local = latest.astimezone(timezone.utc)
    return f"Data updated {local:%d %b, %H:%M} {local.strftime('%Z')}"


def data_label(results) -> str:
    present = [r for r in results if r is not None]
    if any(r.status == ds.STATUS_DEMO for r in present):
        return "Sample data (not live)"
    if any(r.status == ds.STATUS_CACHED for r in present):
        return "Cached (stale)"
    if present and all(r.status == ds.STATUS_LIVE for r in present):
        return "Live"
    return "Partial data" if any(r.ok for r in present) else "Unavailable"


def render_header(label, results=(), tz_name="auto"):
    with header_slot:
        left, right = columns([8, 1.4])
        with left:
            if not label:
                ui.header("No location selected", "No data retrieved yet")
            elif demo_mode:
                ui.header(label, "Sample data - not live", "Demo mode")
            else:
                ui.header(label, updated_text(results, tz_name), data_label(results))
        with right:
            st.button("Refresh", key="header_refresh", on_click=request_refresh, disabled=demo_mode,
                      help="Fetch fresh data now (limited to once per minute).")
        if refresh_notice:
            st.markdown(f'<div class="kn-notice">{escape(refresh_notice)}</div>', unsafe_allow_html=True)


if location is None:
    render_header(None)
    st.warning("Choose a valid location in the sidebar to begin (or switch on Demo mode).")
    st.stop()

# ------------------------------------------------------------------ load data --
if demo_mode:
    _w, _a = sample_data.load_sample_weather(), sample_data.load_sample_air_quality()
    weather_result = ds.FetchResult(_w, ds.STATUS_DEMO, _w.fetched_at)
    air_result = ds.FetchResult(_a, ds.STATUS_DEMO, _a.fetched_at)
    st.error("SAMPLE DATA - these numbers are invented for demonstration. They are NOT live "
             "observations or forecasts.")
else:
    with st.spinner("Fetching weather and air-quality data..."):
        weather_result = ds.fetch_with_cache(get_cache(), "weather", location, ds.fetch_weather, force=force_refresh)
        air_result = ds.fetch_with_cache(get_cache(), "air", location, ds.fetch_air_quality, force=force_refresh)

_tz = weather_result.data.timezone if weather_result.data is not None else location.timezone
render_header(location.label, (weather_result, air_result), _tz)

for name, result in (("Weather", weather_result), ("Air-quality", air_result)):
    if result.status == ds.STATUS_UNAVAILABLE:
        st.warning(f"{name} data could not be retrieved: {result.error} The other sections still work.")
    elif result.status == ds.STATUS_CACHED:
        st.warning(f"{name} data: the refresh failed ({result.error}). Showing an OLDER saved copy, "
                   f"retrieved {ds.describe_age(result.age_seconds())}. It is not live.")

if not weather_result.ok and not air_result.ok:
    st.error("No data could be retrieved from either service.")
    st.info("Tip: check your internet connection, wait a minute if you hit a rate limit, then press Refresh - "
            "or switch on Demo mode in the sidebar to see the interface with sample data.")
    st.stop()

try:
    a = asm.assess(weather_result, air_result, thresholds, location.label)
except config.ConfigError as exc:
    st.error("The alert thresholds in the sidebar are invalid, so alerts are paused. Please fix them "
             "(or press 'Reset thresholds to defaults'):")
    for problem in exc.problems:
        st.markdown(f"- {problem}")
    st.stop()
weather, air = weather_result.data, air_result.data

ui.status_chips(a.status_items)
st.caption(f"Coordinates: {location.latitude:.2f}, {location.longitude:.2f}" +
           (f" · Time zone: {weather.timezone}" if weather else ""))

tab_overview, tab_24h, tab_forecast, tab_air, tab_alerts, tab_about = st.tabs(
    ["Overview", "Next 24 Hours", "7-Day Forecast", "Air Quality", "Alerts & Precautions", "Sources & Notes"])


# ------------------------------------------------------------------ renderers --
def highest_level(alerts_or_events, keys):
    """Highest rule-based level among alerts/events with one of `keys` (None when nothing is triggered)."""
    levels = [x.level for x in alerts_or_events if x.key in keys]
    return max(levels) if levels else None


def build_kpis() -> list:
    """The four summary cards. Only real values from the loaded data; anything missing says 'Unavailable'."""
    cur = weather.current if weather is not None else {}
    aq = air.current if air is not None else {}
    win = a.window

    temp, feels = num(cur.get("temperature_2m")), num(cur.get("apparent_temperature"))
    if temp is None:
        temperature = dict(icon="thermometer", label="Current temperature", value="Unavailable",
                           context="Weather data unavailable", status=("na", "Unavailable"))
    else:
        context = " · ".join(p for p in (cur.get("weather_text"), f"feels like {feels:.1f} °C" if feels is not None else "") if p)
        temperature = dict(icon="thermometer", label="Current temperature", value=f"{temp:.1f}", unit="°C",
                           context=context or "Model estimate for this hour",
                           status=ui.level_status(highest_level(a.current_alerts, ("temperature", "feels_like"))))

    aqi = num(aq.get("us_aqi"))
    if aqi is None:
        air_card = dict(icon="wind", label="Air quality (US AQI)", value="Unavailable",
                        context="Air-quality data unavailable", status=("na", "Unavailable"))
    else:
        air_card = dict(icon="wind", label="Air quality (US AQI)", value=f"{aqi:.0f}", unit="US AQI",
                        context=f"{ds.aqi_category_us(aqi)} · model estimate, not CPCB",
                        status=ui.level_status(highest_level(a.current_alerts, ("air_quality",))))

    rain_now = num(cur.get("precipitation"))
    total = float(win.frame["precipitation"].sum()) if win is not None and win.available.get("precipitation") else None
    if total is not None:
        chance = win.frame["precipitation_probability"].max() if win.rain_probability_available else None
        parts = ["Next 24 h forecast"] + ([f"now {rain_now:.1f} mm/h"] if rain_now is not None else []) \
            + ([f"max chance {chance:.0f}%"] if chance is not None and chance == chance else [])
        rain = dict(icon="rain", label="Rainfall", value=f"{total:.1f}", unit="mm", context=" · ".join(parts),
                    status=ui.level_status(highest_level(a.events, ("rain",))))
    elif rain_now is not None:
        rain = dict(icon="rain", label="Rainfall", value=f"{rain_now:.1f}", unit="mm", context="This hour (model estimate)",
                    status=("na", "No 24 h forecast"))
    else:
        rain = dict(icon="rain", label="Rainfall", value="Unavailable", context="Rain data unavailable",
                    status=("na", "Unavailable"))

    _accent, _tint, kind = ui.RISK_STYLE[a.overall.category]
    risk = dict(icon="shield", label="Overall environmental risk", value=a.overall.category.label,
                context="App-generated rules · now and next 24 h", status=(kind, "Rule-based"))
    return [temperature, air_card, rain, risk]


def risk_measurements() -> list:
    """Key numbers shown inside the risk card (only those that are available)."""
    cur = weather.current if weather is not None else {}
    win, out = a.window, []
    if num(cur.get("temperature_2m")) is not None:
        out.append(("Temperature now", f"{num(cur.get('temperature_2m')):.1f} °C"))
    if air is not None and num(air.current.get("us_aqi")) is not None:
        out.append(("US AQI now", f"{num(air.current.get('us_aqi')):.0f}"))
    if win is not None and win.available.get("precipitation"):
        out.append(("Rain, next 24 h", f"{win.frame['precipitation'].sum():.1f} mm"))
    if win is not None and win.available.get("wind_gusts_10m"):
        out.append(("Strongest gust, next 24 h", f"{win.frame['wind_gusts_10m'].max():.0f} km/h"))
    return out


def period_text() -> str:
    win = a.window
    if win is None:
        return "Not available - no hourly forecast data were retrieved."
    return f"{win.start:%a %d %b %H:%M} to {win.end:%a %d %b %H:%M} ({win.hours} hourly steps, local time at the location)"


def render_recommendations(rec, heading="Precautions to consider"):
    st.markdown(f"#### {heading} - {config.ACTIVITIES[rec.activity]}")
    for r in rec.items:
        icon = LEVEL_ICON.get(r.level, "ℹ️") if r.level else "🌧️"
        st.markdown(f"{icon} {r.text}")
        st.caption(f"Because: {r.trigger} · When: {r.timing}")
    if rec.quiet_note:
        st.info(rec.quiet_note)
    for note in rec.notes:
        st.caption(f"Note: {note}")


def render_overview():
    ui.kpi_row(build_kpis())
    rec = a.recommendations(activity)
    ui.risk_card(a.overall, risk_measurements(), period_text(), [r.text for r in rec.items[:3]])

    if a.window is not None:
        left, right = st.columns(2)
        with left:
            ui.show_chart(charts.hourly_temperature_chart(a.window, thresholds), key="o_temp")
        with right:
            ui.show_chart(charts.hourly_rain_chart(a.window), key="o_rain")

    if weather is not None:
        cur = weather.current
        ui.section("Current conditions", "model estimate for the present hour")
        items = [
            {"label": "Feels like", "value": fmt(cur.get("apparent_temperature"), " °C"), "sub": "includes humidity and wind"},
            {"label": "Humidity", "value": fmt(cur.get("relative_humidity_2m"), " %", 0), "sub": ""},
            {"label": "Wind", "value": fmt(cur.get("wind_speed_10m"), " km/h", 0), "sub": f"gusts {fmt(cur.get('wind_gusts_10m'), ' km/h', 0)}"},
            {"label": "Rain right now", "value": fmt(cur.get("precipitation"), " mm"), "sub": "this hour"},
        ]
        ui.metric_grid(items)
        shown_time = cur.get("time") or (air.current.get("time") if air else None)
        st.caption(f"Model time of current values: {shown_time or 'n/a'} (local). 'Current' values are model estimates, not station readings.")
    else:
        st.warning("Current weather is unavailable right now.")

    glance = asm.forecast_glance(a.window)
    if glance:
        ui.section("Next 24 hours at a glance", "forecast")
        ui.metric_grid(glance)
    render_recommendations(rec)

    with st.expander("Data status details (source, period, limitations)"):
        for item in a.status_items:
            st.markdown(f"**{item.name}** - {item.label}  \n**Source:** {item.source}  \n**Last retrieved:** {item.retrieved}  \n**Period:** {item.period}")
            for text in item.problems:
                st.caption(f"Note: {text}")
            st.caption("Limitations: " + " ".join(item.limitations))
        for gap in a.data_gaps:
            st.caption(f"• {gap}")

    st.markdown("#### Explanation")
    signature = (location.label, a.overall.category.label, tuple((x.key, x.when, x.value) for x in a.all_alerts), activity, demo_mode)
    explanation = None
    if use_llm:
        if st.button("Generate AI explanation"):
            st.session_state["llm_result"] = (signature, llm_service.explain(
                location.label, weather, air, a.all_alerts, use_llm=True, assessment=a, activity=activity))
        saved = st.session_state.get("llm_result")
        explanation = saved[1] if saved and saved[0] == signature else None
    if explanation is None:     # default: ordinary Python explanation (free, instant, no key)
        explanation = llm_service.explain(location.label, weather, air, a.all_alerts, use_llm=False, assessment=a)
        if use_llm:
            explanation.note = "Press the button above to request an AI explanation."
    st.write(explanation.text)
    kind = "AI-generated explanation of the verified data above" if explanation.source == "Groq AI" else "rule-based summary"
    st.caption(f"{kind} · source: {explanation.source}" + (f" - {explanation.note}" if explanation.note else ""))


def events_table() -> pd.DataFrame:
    w = a.window
    return pd.DataFrame([{
        "Hazard": e.variable, "Highest level": f"{LEVEL_ICON[e.level]} {e.level.label}",
        "First reaches that level": timeline.fmt_time(e.first_crossed.get(e.level, e.start), w.start),
        "At/above threshold": timeline.event_span_text(e, w) + (" (about %d h)" % e.hours if not e.continues_past_window else ""),
        "Peak": f"{e.peak_value:.1f} {e.unit}", "Rule": e.rule} for e in a.events])


def render_24h():
    if a.window is None:
        st.warning("No hourly data are available, so the 24-hour timeline cannot be shown.")
        return
    st.markdown("#### What may change in the next 24 hours")
    st.caption("Forecast-based. Alerts here are app-generated from model forecasts, are not official warnings, and a "
               "forecast probability is not a certainty.")
    for line in a.summary_lines:
        st.markdown(f"- {line}")
    if a.events:
        st.dataframe(events_table(), hide_index=True)
    ui.show_chart(charts.risk_timeline_chart(a.window), key="c_risk")
    st.caption("Legend: '-' no alert · 'i' Information · 'C' Caution · 'H' High concern · '?' no data (grey). "
               "Times are local to the location. Rain uses the running 24-hour total since the window start.")
    ui.show_chart(charts.hourly_temperature_chart(a.window, thresholds), key="c_temp")
    ui.show_chart(charts.hourly_rain_chart(a.window), key="c_rain")
    ui.show_chart(charts.hourly_wind_chart(a.window, thresholds), key="c_wind")
    if a.window.air_available:
        t = thresholds["us_aqi"]
        ui.show_chart(charts.aqi_chart(a.window.frame, t["info"], t["caution"], t["high"], " - next 24 h"), key="c_aqi24")
    else:
        st.info("An hourly air-quality forecast is unavailable from the data service right now, so it is not shown. "
                "No air-quality values have been estimated.")


def render_forecast():
    if weather is None:
        st.warning("Weather forecast data are unavailable right now.")
        return
    daily = weather.daily
    table = pd.DataFrame({
        "Date": daily["date"].dt.strftime("%a %d %b"), "Condition": daily.get("weather_text"),
        "Max °C": daily.get("temperature_2m_max"), "Min °C": daily.get("temperature_2m_min"),
        "Rain mm": daily.get("precipitation_sum"), "Rain prob. max %": daily.get("precipitation_probability_max"),
        "Max gust km/h": daily.get("wind_gusts_10m_max"), "UV max": daily.get("uv_index_max")})
    st.dataframe(table, hide_index=True)
    st.caption("Blank cells mean the data service did not provide that value. All values are forecasts.")
    left, right = st.columns(2)
    with left:
        ui.show_chart(charts.temperature_chart(daily, thresholds["temp_max_c"]["caution"]), key="d_temp")
    with right:
        ui.show_chart(charts.rainfall_chart(daily, thresholds["rain_daily_mm"]["caution"]), key="d_rain")
    ui.show_chart(charts.wind_chart(daily, thresholds["wind_gust_kmh"]["caution"]), key="d_wind")


def render_air():
    if air is None:
        st.warning("Air-quality data is unavailable right now. Weather features still work.")
        return
    aq = air.current
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("US AQI (model)", fmt(aq.get("us_aqi"), "", 0), ds.aqi_category_us(aq.get("us_aqi")))
    a2.metric("PM2.5 µg/m³", fmt(aq.get("pm2_5")))
    a3.metric("PM10 µg/m³", fmt(aq.get("pm10")))
    a4.metric("Ozone µg/m³", fmt(aq.get("ozone")))
    st.info("Which index is this? **US AQI** (EPA bands) as calculated by the Open-Meteo/CAMS **model**. It is not the "
            "Indian CPCB National AQI and not a ground-station reading. European AQI (below, number only) uses a "
            "different scale - the two must not be compared.")
    st.caption(f"European AQI (different scale, model): {fmt(aq.get('european_aqi'), '', 0)} · NO₂ {fmt(aq.get('nitrogen_dioxide'))} · "
               f"SO₂ {fmt(aq.get('sulphur_dioxide'))} · CO {fmt(aq.get('carbon_monoxide'), '', 0)} (all µg/m³)")
    t = thresholds["us_aqi"]
    ui.show_chart(charts.aqi_chart(air.hourly, t["info"], t["caution"], t["high"]), key="a_aqi")
    ui.show_chart(charts.pm_chart(air.hourly), key="a_pm")
    st.caption(f"Model values at: {aq.get('time', 'n/a')} (local) · Fetched: {air.fetched_at.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC")


def alert_expander(x):
    with st.expander(f"{LEVEL_ICON[x.level]} {x.level.label} · {x.variable} · {x.when}", expanded=x.level == Level.HIGH):
        st.markdown(f"**Location:** {x.location}  \n**Value:** {x.value:g} {x.unit}  \n"
                    f"**Rule that triggered:** {x.rule}  \n**Why:** {x.explanation}")
        st.markdown("**Precautions:**\n" + "\n".join(f"- {tip}" for tip in x.advice))
        st.caption(f"Source: {x.source} · Generated: {x.generated_at} · Basis: {x.basis} · Official warning: No")


def render_alerts():
    st.info("These are **experimental, app-generated alerts** from simple threshold rules. They are not official "
            "warnings. " + asm.alert_engine.RAIN_NOTE)
    st.markdown("#### Right now (current conditions, model estimate)")
    if not a.current_alerts:
        st.success("No rule is triggered by the current values.")
    for x in a.current_alerts:
        alert_expander(x)
    st.markdown("#### Next 24 hours (forecast)")
    if not a.events:
        st.success("No rule is forecast to be triggered in the next 24 hours (based on the available data).")
    else:
        st.dataframe(events_table(), hide_index=True)
    st.markdown("#### Day-by-day forecast alerts (daily values)")
    if not a.daily_alerts:
        st.success("No daily rule is triggered in the forecast period.")
    for x in a.daily_alerts:
        alert_expander(x)
    render_recommendations(a.recommendations(activity), "Combined recommendations")
    with st.expander("What do the levels mean?"):
        for level, text in config.LEVEL_DEFINITIONS.items():
            st.markdown(f"**{level.label}** - {text}")
        st.caption(config.THRESHOLD_NOTE)
    if a.all_alerts:
        df = pd.DataFrame([x.to_dict() for x in a.all_alerts])[["level", "basis", "variable", "value", "unit", "when", "rule"]]
        st.download_button("Download alerts as CSV", df.to_csv(index=False), "kaniyan_alerts.csv", "text/csv")


def render_about():
    st.markdown("#### Data sources and timestamps")
    for item in a.status_items:
        st.markdown(f"- **{item.name}:** {item.source}  \n  Status: {item.label} · Last retrieved: {item.retrieved}")
    st.markdown("- **Geocoding:** Open-Meteo Geocoding API (GeoNames)")
    st.caption(config.ATTRIBUTION)
    st.markdown("#### What each threshold means")
    st.dataframe(pd.DataFrame([{"Rule": config.THRESHOLD_LABELS[k], "Unit": d["unit"], "Meaning": d["meaning"],
                                "Basis of default values": d["validation"]} for k, d in config.THRESHOLD_DOCS.items()]), hide_index=True)
    st.caption(f"The 'high chance of rain' level used in recommendations is {config.RAIN_PROB_NOTABLE_PERCENT:g}% "
               "(configurable, unvalidated). The overall risk category is an app-generated rule, not an official index.")
    st.warning(recommendations.GENERAL_DISCLAIMER)
    st.markdown("**Official sources to check for real decisions:** India Meteorological Department (mausam.imd.gov.in), "
                "CPCB AQI bulletins (cpcb.nic.in), and your state disaster management authority.")


def ask(text, chart=None):
    """Button callback: remember the question; the chat card answers it on the next run."""
    st.session_state["kn_pending"] = (text, chart)


def render_chat():
    """'Ask Kaniyan AI' card at the bottom of the dashboard. The AI only explains the verified data above."""
    if st.session_state.get("kaniyan_chat_location") != (location.label, demo_mode):
        st.session_state["kaniyan_chat_history"] = []        # old answers refer to the previous place's data
        st.session_state["kaniyan_chat_location"] = (location.label, demo_mode)
    history = st.session_state.setdefault("kaniyan_chat_history", [])

    with st.container(border=True):
        st.markdown(ui.chat_header_html(), unsafe_allow_html=True)
        lang_col, status_col = columns([2.2, 5])
        language = lang_col.radio("Reply language", llm_service.CHAT_LANGUAGES, format_func=LANGUAGE_LABELS.get,
                                  horizontal=True, key="kn_chat_language")
        if llm_service.is_configured():
            status_col.caption("AI answers are on (Groq). You can write in English, Tamil or Tanglish.")
        else:
            status_col.caption("No AI key found - answers are rule-based and in English. You can write in English, Tamil or Tanglish.")

        starters = st.columns(len(llm_service.CHAT_STARTERS))
        for i, (col, text) in enumerate(zip(starters, llm_service.CHAT_STARTERS)):
            col.button(text, key=f"kn_starter_{i}", on_click=ask, args=(text,))

        box = st.container(height=440) if len(history) >= 4 else st.container()
        with box:
            st.markdown(ui.welcome_html(location.label), unsafe_allow_html=True)
            for message in history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message.get("note"):
                        st.markdown(f'<div class="kn-note{" warn" if message.get("warn") else ""}">{escape(message["note"])}</div>',
                                    unsafe_allow_html=True)

        with st.expander("More questions and chart explanations"):
            cols = st.columns(2)
            for i, text in enumerate(llm_service.SUGGESTED_QUESTIONS):
                cols[i % 2].button(text, key=f"sq_{i}", on_click=ask, args=(text,))
            c1, c2 = st.columns([3, 1])
            chart_name = c1.selectbox("Explain a chart", asm.CHART_NAMES, label_visibility="collapsed")
            c2.button("Explain this chart", on_click=lambda: ask(f"Explain the '{chart_name}' chart in simple language.", chart_name))

        pending = st.session_state.pop("kn_pending", None)
        typed_question = st.chat_input("Ask about your area's weather or environmental risks...")
        question, chart = (typed_question, None) if typed_question else (pending or (None, None))
        if question:
            with box:
                with st.chat_message("user"):
                    st.markdown(question)
                with st.chat_message("assistant"):
                    with st.spinner("Kaniyan AI is preparing an answer..."):
                        result = llm_service.chat_answer(
                            question, location.label, weather, air, a.all_alerts, history=list(history), assessment=a,
                            activity=activity, chart_context=asm.describe_chart(a, chart) if chart else None,
                            language=language)
                    st.markdown(result.text)
                    api_problem = result.source == "Python fallback" and llm_service.is_configured()
                    note = f"Answer source: {result.source}" + (f" · {result.note}" if result.note else "")
                    st.markdown(f'<div class="kn-note{" warn" if api_problem else ""}">{escape(note)}</div>', unsafe_allow_html=True)
            if result.source != "Input check":
                history += [{"role": "user", "content": question},
                            {"role": "assistant", "content": result.text, "note": note, "warn": api_problem}]
        left, right = st.columns([5, 1])
        left.caption("Kaniyan AI explains the dashboard's rule-based results. It is not an official warning or emergency guidance.")
        if right.button("Clear chat", key="clear_kaniyan_chat"):
            st.session_state["kaniyan_chat_history"] = []
            st.rerun()


with tab_overview:
    render_overview()
with tab_24h:
    render_24h()
with tab_forecast:
    render_forecast()
with tab_air:
    render_air()
with tab_alerts:
    render_alerts()
with tab_about:
    render_about()

st.markdown("&nbsp;", unsafe_allow_html=True)
render_chat()
