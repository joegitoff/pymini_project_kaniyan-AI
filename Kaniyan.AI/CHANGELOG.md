# Change log

## v3.0 - light "Kaniyan AI" dashboard redesign

### Changed
- **UI only**: white/light theme (`.streamlit/config.toml` + CSS in `ui_components.py`), new header (logo, location, data time,
  Refresh), light sidebar, four KPI cards (temperature, US AQI, rainfall, overall risk), compact risk card with reasons,
  measurements, forecast period, precautions and a clear "not an official warning" note.
- Tabs: Overview, Next 24 Hours, 7-Day Forecast, Air Quality, Alerts & Precautions, Sources & Notes.
- **Ask Kaniyan AI** chat card moved to the bottom of the dashboard: English / Tamil reply selector (Tanglish input accepted),
  starter prompts, chat history in session state, spinner, clear error notes. Same Groq integration and rule-based fallback.
- Charts restyled (white cards, restrained colours); data and thresholds unchanged.
- `llm_service.chat_answer(..., language="English")` added; rule-based answers also cover travel/commute questions.
- Brand name shown as "Kaniyan AI". Rule engine, thresholds, data retrieval and risk classification are untouched.

## v2.0 - dashboard, 24-hour timeline, activity advice, reliability

### Added
- **Overall risk indicator** (`risk.py`): Low / Moderate / High / Very High, taken from the highest single alert level
  (never summed). *Very High* requires "High concern" in two different hazard groups at overlapping times. Always
  labelled as an app-generated classification, with reasons, contributing factors and data caveats.
- **Next-24-hours timeline** (`timeline.py`): hourly window, per-hour levels, threshold-crossing times, persistence,
  rain-probability periods, missing hours shown as gaps. Charts: risk timeline, temperature, rain probability +
  precipitation, wind, hourly US AQI (or an explicit "unavailable" message).
- **Current-condition alerts** (`alert_engine.evaluate_current_alerts`), kept separate from forecast alerts (`basis` field).
- **Activity recommendations** (`activity_advice.py`): five modes, rule-based, each recommendation shows the triggering
  condition and timing. "Lower-risk hours" appear only for activity modes and only when the hourly forecast supports them.
- **AI grounding**: the AI receives verified context (overall risk, 24 h events, today-vs-tomorrow comparison, data gaps,
  data status, selected activity). Suggested questions, "explain this chart", rule-based answers when AI is off/down.
- **Data status** everywhere: live / cached (stale) / unavailable / demonstration, retrieval time, data period, source, limitations.
- Manual **Refresh** button with a 60-second cooldown; process-wide cache (`DataCache`) with visible age.
- `assessment.py` (one place that runs all logic), `ui_components.py` (cards, banner, chips), `.env.example`, `.gitignore`,
  `.streamlit/secrets.toml.example`.
- Tests: 43 -> 217.

### Changed
- `app.py` rewritten as display-only flow; tabs: Overview, Next 24 hours, 7-day forecast, Air quality, Alerts &
  precautions, Chat, Sources & notes. Existing features kept: location search, demo mode, CSV export (now has a `basis` column),
  editable thresholds, 7-day charts, Groq chat with Python fallback.
- **Weather failure no longer stops the app**; air quality (and vice-versa) keeps working.
- **Invalid thresholds are no longer silently replaced by defaults**: alerts pause, every problem is listed, and the user
  can press "Reset thresholds to defaults".
- Threshold validation now lives in `config.py` (`ConfigError`), with documented units/ranges. **Cut-offs must now increase
  strictly** (info < caution < high); previously equal values were accepted, which made a level unreachable.
  Default threshold *values* are unchanged.
- `data_service.py`: bounded retries (2) with back-off for timeouts/connection errors/HTTP 5xx only; 429 and 4xx are not
  retried; structure validation; implausible values -> missing (with a warning); duplicate/unsorted timestamps cleaned.
  Hourly `apparent_temperature` is now requested.
- `llm_service.py`: question validation (<= 600 chars, rejected not truncated), answer cap (2,500 chars), secret
  redaction, safe handling of empty/malformed replies. Existing function signatures remain compatible.
- Demo hourly data is now derived from the demo daily values (previously constant), so the demo timeline is meaningful.

### Removed / not implemented
- No notifications of any kind (push, browser, email, SMS, scheduled/background alerting).
- "Resolved" alert state is not implemented (needs stored history between refreshes; out of scope).
