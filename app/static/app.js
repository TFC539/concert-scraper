import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

const h = React.createElement;

const PAGE_CONFIG = [
  { id: "overview", label: "Overview" },
  { id: "scrape", label: "Scrape Control" },
  { id: "concerts", label: "Concert Explorer" },
  { id: "resolution", label: "Resolution" },
  { id: "rules", label: "Notifications" },
];

const DEFAULT_FILTERS = {
  q: "",
  source: "",
  date_start_day: "",
  date_start_month: "",
  date_start_year: "",
  date_end_day: "",
  date_end_month: "",
  date_end_year: "",
  time_start: "",
  time_end: "",
  include_maybe: false,
  performer_ids: [],
  work_ids: [],
  venue_ids: [],
};

// Helper: Convert DD-MM-YYYY fields to YYYY-MM-DD format for API
function formatDateForAPI(day, month, year) {
  if (!day || !month || !year) return "";
  const paddedDay = String(day).padStart(2, "0");
  const paddedMonth = String(month).padStart(2, "0");
  return `${year}-${paddedMonth}-${paddedDay}`;
}

function parseAPIDateToParts(value) {
  const raw = String(value || "").trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return { day: "", month: "", year: "" };
  }
  return {
    year: match[1],
    month: String(Number(match[2])).padStart(2, "0"),
    day: String(Number(match[3])).padStart(2, "0"),
  };
}

const emptyRule = {
  name_contains: "",
  performer_contains: "",
  program_contains: "",
  date_contains: "",
  time_contains: "",
  enabled: true,
};

const emptySettings = {
  scrape_interval_minutes: 60,
  smtp_host: "",
  smtp_port: 587,
  smtp_username: "",
  smtp_password: "",
  sender_email: "",
  recipient_email: "",
  notifications_enabled: false,
  openrouter_api_key: "",
  openrouter_model: "openai/gpt-4.1-mini",
  openrouter_timeout_seconds: 40,
  openrouter_max_retries: 2,
};

const emptyScrapeScope = {
  selected_sources: [],
  max_per_source: "",
  max_total: "",
};

function isValidPage(pageId) {
  return PAGE_CONFIG.some((page) => page.id === pageId);
}

function pageFromHash(hashValue) {
  const value = String(hashValue || "")
    .replace(/^#/, "")
    .trim();
  return isValidPage(value) ? value : "overview";
}

function display(value) {
  return value ? value : "-";
}

function formatTimestamp(value) {
  if (!value) {
    return "No sync yet";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "No sync yet";
  }

  return parsed.toLocaleString();
}

function parsePositiveInteger(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }

  const normalized = Math.floor(parsed);
  return normalized > 0 ? normalized : null;
}

function toDownloadStamp(dateValue = new Date()) {
  const year = String(dateValue.getFullYear());
  const month = String(dateValue.getMonth() + 1).padStart(2, "0");
  const day = String(dateValue.getDate()).padStart(2, "0");
  const hour = String(dateValue.getHours()).padStart(2, "0");
  const minute = String(dateValue.getMinutes()).padStart(2, "0");
  const second = String(dateValue.getSeconds()).padStart(2, "0");
  return `${year}${month}${day}-${hour}${minute}${second}`;
}

function triggerJsonDownload(fileName, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function field(label, control) {
  return h("label", null, label, control);
}

function metricCard(label, value, foot) {
  return h(
    "article",
    { className: "metric-card" },
    h("span", { className: "metric-label" }, label),
    h("strong", { className: "metric-value" }, value),
    h("span", { className: "metric-foot" }, foot)
  );
}

function uniqueStrings(values) {
  const seen = new Set();
  const output = [];

  for (const value of values || []) {
    const text = String(value || "").trim();
    if (!text) {
      continue;
    }

    const normalized = text.toLowerCase();
    if (seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);
    output.push(text);
  }

  return output;
}

function limitTags(tags, maxVisible = 10) {
  const values = Array.isArray(tags) ? tags : [];
  const visible = values.slice(0, maxVisible);
  const hiddenCount = Math.max(0, values.length - visible.length);
  return { visible, hiddenCount };
}

function workTagLabel(work) {
  const label = String(work?.label || "").trim();
  if (label) {
    return label;
  }

  const composer = String(work?.composer || "").trim();
  const title = String(work?.title || "").trim();
  if (composer && title) {
    return `${composer} - ${title}`;
  }

  return composer || title;
}

function normalizeConcertView(concert) {
  const normalized = concert?.normalized || {};

  const performerTags = uniqueStrings(
    Array.isArray(normalized.performers) ? normalized.performers.map((item) => String(item?.name || "").trim()) : []
  );
  const performerIds = Array.isArray(normalized.performers) ? normalized.performers.map((item) => Number(item?.id || 0)).filter((id) => id > 0) : [];

  const workTags = uniqueStrings(
    Array.isArray(normalized.works) ? normalized.works.map((work) => workTagLabel(work)) : []
  );
  const workIds = Array.isArray(normalized.works) ? normalized.works.map((work) => Number(work?.id || 0)).filter((id) => id > 0) : [];

  const venueName = String(normalized?.venue?.name || "").trim();
  const venueId = Number(normalized?.venue?.id || 0);

  const title = String(normalized?.title || concert?.name || "").trim();
  const dateLabel = String(normalized?.date || concert?.date_normalized || concert?.date || "").trim();
  const unresolvedTotal = Number(normalized?.unresolved?.total || 0);
  const soldOut = Boolean(normalized?.sold_out);
  const priceTags = uniqueStrings(Array.isArray(normalized?.price_tags) ? normalized.price_tags : []);

  return {
    title,
    dateLabel,
    venueName,
    venueId,
    performerTags,
    performerIds,
    workTags,
    workIds,
    soldOut,
    priceTags,
    unresolvedTotal,
  };
}

function App() {
  const [activePage, setActivePage] = useState(pageFromHash(window.location.hash));
  const [loading, setLoading] = useState(true);
  const [resolutionLoading, setResolutionLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dumping, setDumping] = useState(false);
  const [notice, setNotice] = useState(null);

  const [filters, setFilters] = useState({ ...DEFAULT_FILTERS });
  const [sources, setSources] = useState([]);
  const [scrapeSources, setScrapeSources] = useState([]);
  const [concerts, setConcerts] = useState([]);
  const [maybeHiddenCount, setMaybeHiddenCount] = useState(0);
  const [rules, setRules] = useState([]);
  const [settings, setSettings] = useState({ ...emptySettings });
  const [newRule, setNewRule] = useState({ ...emptyRule });
  const [scrapeScope, setScrapeScope] = useState({ ...emptyScrapeScope });

  const [unresolvedItems, setUnresolvedItems] = useState([]);
  const [mergeSuggestions, setMergeSuggestions] = useState([]);
  const [newEntityDrafts, setNewEntityDrafts] = useState({});
  const [reviewReasons, setReviewReasons] = useState({});
  const [searchSuggestions, setSearchSuggestions] = useState([]);
  const [showSearchSuggestions, setShowSearchSuggestions] = useState(false);
  const [filterLabels, setFilterLabels] = useState({ performers: {}, works: {}, venues: {} });

  const activeRuleCount = useMemo(() => rules.filter((rule) => rule.enabled).length, [rules]);
  const sourceCount = useMemo(() => sources.length, [sources]);
  const unresolvedOpenCount = useMemo(
    () => unresolvedItems.filter((item) => item.status === "open").length,
    [unresolvedItems]
  );
  const mergePendingCount = useMemo(
    () => mergeSuggestions.filter((item) => item.status === "pending").length,
    [mergeSuggestions]
  );

  const latestFetchLabel = useMemo(() => {
    const latest = concerts.reduce((memo, concert) => {
      if (!concert.fetched_at) {
        return memo;
      }
      const currentDate = new Date(concert.fetched_at);
      if (Number.isNaN(currentDate.getTime())) {
        return memo;
      }
      if (!memo || currentDate > memo) {
        return currentDate;
      }
      return memo;
    }, null);

    return latest ? formatTimestamp(latest.toISOString()) : "No sync yet";
  }, [concerts]);

  const scrapeScopeLabel = useMemo(() => {
    const selected = scrapeScope.selected_sources.length;
    const total = scrapeSources.length;
    const selectedText = selected > 0 ? `${selected}/${total || selected} sources` : "no source selected";

    const maxPerSource = parsePositiveInteger(scrapeScope.max_per_source);
    const maxTotal = parsePositiveInteger(scrapeScope.max_total);

    const parts = [selectedText];
    if (maxPerSource) {
      parts.push(`max ${maxPerSource} per source`);
    }
    if (maxTotal) {
      parts.push(`max ${maxTotal} total`);
    }
    return parts.join(" · ");
  }, [scrapeScope, scrapeSources]);

  useEffect(() => {
    const onHashChange = () => {
      setActivePage(pageFromHash(window.location.hash));
    };

    window.addEventListener("hashchange", onHashChange);
    onHashChange();
    refreshAll();

    return () => {
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  useEffect(() => {
    if (scrapeSources.length === 0) {
      return;
    }

    setScrapeScope((previous) => {
      const current = Array.isArray(previous.selected_sources) ? previous.selected_sources : [];
      const filtered = current.filter((source) => scrapeSources.includes(source));
      const selected = filtered.length > 0 ? filtered : [...scrapeSources];

      const unchanged =
        selected.length === current.length &&
        selected.every((source, index) => source === current[index]);

      if (unchanged) {
        return previous;
      }

      return {
        ...previous,
        selected_sources: selected,
      };
    });
  }, [scrapeSources]);

  async function request(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
    };

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(path, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const data = await response.json();
        if (data?.detail) {
          message = data.detail;
        }
      } catch (_) {
        // Keep fallback message for non-JSON responses.
      }
      throw new Error(message);
    }

    if (response.status === 204) {
      return null;
    }

    return response.json();
  }

  async function loadDashboard(nextFilters = filters) {
    setLoading(true);

    try {
      const params = new URLSearchParams();
      if (nextFilters.q) params.set("q", nextFilters.q);
      if (nextFilters.source) params.set("source", nextFilters.source);
      
      // Convert DD-MM-YYYY to YYYY-MM-DD for API
      const dateStart = formatDateForAPI(nextFilters.date_start_day, nextFilters.date_start_month, nextFilters.date_start_year);
      const dateEnd = formatDateForAPI(nextFilters.date_end_day, nextFilters.date_end_month, nextFilters.date_end_year);
      if (dateStart) params.set("date_start", dateStart);
      if (dateEnd) params.set("date_end", dateEnd);
      
      if (nextFilters.time_start) params.set("time_start", nextFilters.time_start);
      if (nextFilters.time_end) params.set("time_end", nextFilters.time_end);
      if (nextFilters.include_maybe) params.set("include_maybe", "true");
      if (nextFilters.performer_ids && nextFilters.performer_ids.length > 0) {
        params.set("performer_ids", nextFilters.performer_ids.join(","));
      }
      if (nextFilters.work_ids && nextFilters.work_ids.length > 0) {
        params.set("work_ids", nextFilters.work_ids.join(","));
      }
      if (nextFilters.venue_ids && nextFilters.venue_ids.length > 0) {
        params.set("venue_ids", nextFilters.venue_ids.join(","));
      }

      const query = params.toString();
      const payload = await request(`/api/dashboard${query ? `?${query}` : ""}`, {
        headers: {},
      });

      const incomingFilters = payload.filters || {};
      const dateStartParts = parseAPIDateToParts(incomingFilters.date_start);
      const dateEndParts = parseAPIDateToParts(incomingFilters.date_end);

      setFilters({
        ...DEFAULT_FILTERS,
        ...incomingFilters,
        date_start_day: dateStartParts.day,
        date_start_month: dateStartParts.month,
        date_start_year: dateStartParts.year,
        date_end_day: dateEndParts.day,
        date_end_month: dateEndParts.month,
        date_end_year: dateEndParts.year,
      });
      setSources(payload.sources || []);
      setScrapeSources(payload.scrape_sources || []);
      setConcerts(payload.concerts || []);
      setMaybeHiddenCount(payload.maybe_hidden_count || 0);
      setRules(payload.rules || []);
      setSettings({ ...emptySettings, ...(payload.settings || {}) });
      setFilterLabels(payload.filter_labels || { performers: {}, works: {}, venues: {} });
    } catch (error) {
      setNotice({ type: "error", text: `Could not load dashboard data: ${error.message}` });
    } finally {
      setLoading(false);
    }
  }

  async function loadResolutionData() {
    setResolutionLoading(true);

    try {
      const [unresolvedPayload, mergePayload] = await Promise.all([
        request("/api/resolution/unresolved", { headers: {} }),
        request("/api/resolution/merge-suggestions", { headers: {} }),
      ]);
      setUnresolvedItems(unresolvedPayload.items || []);
      setMergeSuggestions(mergePayload.items || []);
    } catch (error) {
      setNotice({ type: "error", text: `Could not load resolution queues: ${error.message}` });
    } finally {
      setResolutionLoading(false);
    }
  }

  async function loadSearchSuggestions(query) {
    if (!query || !query.trim()) {
      setSearchSuggestions([]);
      setShowSearchSuggestions(false);
      return;
    }

    try {
      const params = new URLSearchParams();
      params.set("q", query);
      params.set("limit", "20");

      const payload = await request(`/api/search/suggestions?${params.toString()}`, {
        headers: {},
      });

      setSearchSuggestions(payload.suggestions || []);
      setShowSearchSuggestions((payload.suggestions || []).length > 0);
    } catch (error) {
      setSearchSuggestions([]);
      setShowSearchSuggestions(false);
    }
  }

  async function refreshAll(nextFilters = filters) {
    await Promise.all([loadDashboard(nextFilters), loadResolutionData()]);
  }

  function goToPage(pageId) {
    if (!isValidPage(pageId)) {
      return;
    }

    window.location.hash = pageId;
    setActivePage(pageId);
  }

  function toggleScrapeSource(source) {
    setScrapeScope((previous) => {
      const selected = previous.selected_sources.includes(source)
        ? previous.selected_sources.filter((item) => item !== source)
        : [...previous.selected_sources, source];
      return { ...previous, selected_sources: selected };
    });
  }

  function selectAllScrapeSources() {
    setScrapeScope((previous) => ({ ...previous, selected_sources: [...scrapeSources] }));
  }

  function clearScrapeSources() {
    setScrapeScope((previous) => ({ ...previous, selected_sources: [] }));
  }

  async function saveSettings(event) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);

    try {
      await request("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          ...settings,
          scrape_interval_minutes: Number(settings.scrape_interval_minutes || 1),
          smtp_port: Number(settings.smtp_port || 587),
          openrouter_timeout_seconds: Number(settings.openrouter_timeout_seconds || 40),
          openrouter_max_retries: Number(settings.openrouter_max_retries || 2),
          sender_email: settings.sender_email ? settings.sender_email : null,
          recipient_email: settings.recipient_email ? settings.recipient_email : null,
        }),
      });
      setNotice({ type: "success", text: "Settings saved." });
      await loadDashboard(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Settings could not be saved: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function runScopedScrape() {
    const selectedSources = scrapeScope.selected_sources.filter((source) => scrapeSources.includes(source));
    if (selectedSources.length === 0) {
      setNotice({ type: "error", text: "Select at least one source before running a scoped scrape." });
      return;
    }

    const maxPerSource = parsePositiveInteger(scrapeScope.max_per_source);
    const maxTotal = parsePositiveInteger(scrapeScope.max_total);

    setBusy(true);
    setNotice(null);

    try {
      const payload = {
        sources: selectedSources,
        max_per_source: maxPerSource,
        max_total: maxTotal,
      };

      const response = await request("/api/scrape-now", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const inserted = Number(response?.inserted || 0);
      setNotice({
        type: "success",
        text: `Scoped scrape finished. Inserted ${inserted} new concert${inserted === 1 ? "" : "s"}.`,
      });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Scrape failed: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function dumpCurrentConcerts() {
    setDumping(true);
    setNotice(null);

    try {
      const params = new URLSearchParams();
      if (filters.q) params.set("q", filters.q);
      if (filters.source) params.set("source", filters.source);
      if (filters.date_filter) params.set("date_filter", filters.date_filter);
      if (filters.include_maybe) params.set("include_maybe", "true");
      params.set("limit", "20000");

      const payload = await request(`/api/concerts/dump?${params.toString()}`, { headers: {} });
      const items = payload.items || [];

      if (items.length === 0) {
        setNotice({ type: "error", text: "No concerts to dump for the current filter." });
        return;
      }

      const fileName = `concerts-dump-${toDownloadStamp()}.json`;
      triggerJsonDownload(fileName, items);
      setNotice({ type: "success", text: `Dumped ${items.length} concert${items.length === 1 ? "" : "s"} to ${fileName}.` });
    } catch (error) {
      setNotice({ type: "error", text: `Could not dump concerts: ${error.message}` });
    } finally {
      setDumping(false);
    }
  }

  async function deleteConcert(concert) {
    const confirmed = window.confirm(`Delete concert \"${concert.name}\"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }

    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/concerts/${concert.id}`, {
        method: "DELETE",
        headers: {},
      });
      setNotice({ type: "success", text: "Concert deleted." });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not delete concert: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function deleteFilteredConcerts() {
    const confirmed = window.confirm("Delete all currently filtered concerts? This cannot be undone.");
    if (!confirmed) {
      return;
    }

    setBusy(true);
    setNotice(null);

    try {
      const params = new URLSearchParams();
      params.set("mode", "filtered");
      if (filters.q) params.set("q", filters.q);
      if (filters.source) params.set("source", filters.source);
      if (filters.date_filter) params.set("date_filter", filters.date_filter);
      if (filters.include_maybe) params.set("include_maybe", "true");

      const payload = await request(`/api/concerts?${params.toString()}`, {
        method: "DELETE",
        headers: {},
      });

      const deleted = Number(payload?.deleted || 0);
      setNotice({ type: "success", text: `Deleted ${deleted} filtered concert${deleted === 1 ? "" : "s"}.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not delete filtered concerts: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function deleteAllConcerts() {
    const confirmed = window.confirm("Delete ALL concerts from the database? This cannot be undone.");
    if (!confirmed) {
      return;
    }

    setBusy(true);
    setNotice(null);

    try {
      const payload = await request("/api/concerts?mode=all", {
        method: "DELETE",
        headers: {},
      });

      const deleted = Number(payload?.deleted || 0);
      setNotice({ type: "success", text: `Deleted ${deleted} concert${deleted === 1 ? "" : "s"} in total.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not delete all concerts: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function addRule(event) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);

    try {
      await request("/api/rules", {
        method: "POST",
        body: JSON.stringify(newRule),
      });
      setNewRule({ ...emptyRule });
      setNotice({ type: "success", text: "Rule added." });
      await loadDashboard(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Rule could not be added: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function removeRule(ruleId) {
    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/rules/${ruleId}`, { method: "DELETE", headers: {} });
      setNotice({ type: "success", text: `Rule #${ruleId} removed.` });
      await loadDashboard(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Rule could not be removed: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function applyFilters(event) {
    event.preventDefault();
    await loadDashboard(filters);
  }

  async function resetFilters() {
    const nextFilters = { ...DEFAULT_FILTERS };
    setFilters(nextFilters);
    await loadDashboard(nextFilters);
  }

  async function applyTagFilter(rawValue, mode = "q", entityType = null, entityId = null) {
    const value = String(rawValue || "").trim();
    if (!value && !entityId) {
      return;
    }

    const nextFilters = { ...filters };

    if (entityType && entityId) {
      // Entity-based filtering
      if (entityType === "performer") {
        nextFilters.performer_ids = [...(nextFilters.performer_ids || []), entityId];
      } else if (entityType === "work") {
        nextFilters.work_ids = [...(nextFilters.work_ids || []), entityId];
      } else if (entityType === "venue") {
        nextFilters.venue_ids = [...(nextFilters.venue_ids || []), entityId];
      }
    } else {
      // Text-based filtering
      nextFilters.q = mode === "q" ? value : nextFilters.q;
      nextFilters.source = mode === "source" ? value : nextFilters.source;
      nextFilters.date_filter = mode === "date" ? value : nextFilters.date_filter;
    }

    setFilters(nextFilters);
    await loadDashboard(nextFilters);
  }

  async function resolveWithCandidate(itemId, candidateId) {
    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/resolution/unresolved/${itemId}`, {
        method: "POST",
        body: JSON.stringify({
          action: "accept_candidate",
          candidate_id: candidateId,
          value: "",
          reason: "",
        }),
      });
      setNotice({ type: "success", text: `Accepted candidate #${candidateId}.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not accept candidate: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function createEntityForUnresolved(item) {
    const draftValue = (newEntityDrafts[item.id] || "").trim();
    const value = draftValue || item.raw_text;

    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/resolution/unresolved/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action: "create_new",
          candidate_id: null,
          value,
          reason: "",
        }),
      });
      setNewEntityDrafts((previous) => ({ ...previous, [item.id]: "" }));
      setNotice({ type: "success", text: `Created new ${item.entity_type} entity.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not create entity: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function markDistinct(item) {
    const topCandidate = item.candidates && item.candidates.length > 0 ? item.candidates[0].id : null;
    const reasonKey = `u-${item.id}`;
    const reason = (reviewReasons[reasonKey] || "").trim();

    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/resolution/unresolved/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action: "mark_distinct",
          candidate_id: topCandidate,
          value: "",
          reason,
        }),
      });
      setReviewReasons((previous) => ({ ...previous, [reasonKey]: "" }));
      setNotice({ type: "success", text: `Marked unresolved item #${item.id} as distinct.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not mark distinct: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function updateMergeSuggestion(item, action) {
    const reasonKey = `m-${item.id}`;
    const reason = (reviewReasons[reasonKey] || "").trim();

    setBusy(true);
    setNotice(null);

    try {
      await request(`/api/resolution/merge-suggestions/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action,
          reason,
        }),
      });

      const actionLabel =
        action === "do_not_merge"
          ? "Marked as do-not-merge"
          : action === "merge"
          ? "Entities merged"
          : "Suggestion rejected";

      setReviewReasons((previous) => ({ ...previous, [reasonKey]: "" }));
      setNotice({ type: "success", text: `${actionLabel}.` });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not update merge suggestion: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  function renderMetricsSection() {
    return h(
      "section",
      { className: "metrics" },
      metricCard("Concerts", String(concerts.length), "Current filtered result"),
      metricCard("Sources", String(sourceCount), "Distinct source values"),
      metricCard("Resolution", String(unresolvedOpenCount), `${mergePendingCount} merge suggestions`),
      metricCard("Rules", String(rules.length), `${activeRuleCount} enabled`),
      metricCard(
        "Notifications",
        settings.notifications_enabled ? "Enabled" : "Disabled",
        settings.recipient_email ? `To ${settings.recipient_email}` : "Recipient not configured"
      )
    );
  }

  function renderSystemSettingsPanel() {
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "System Settings"),
          h("p", null, "Configure scheduler cadence, OpenRouter extraction, and SMTP notifications.")
      ),
      h(
        "form",
        { className: "stack", onSubmit: saveSettings },
        h(
          "div",
          { className: "fields" },
          field(
            "Interval (minutes)",
            h("input", {
              type: "number",
              min: 1,
              value: settings.scrape_interval_minutes,
              onChange: (event) => setSettings({ ...settings, scrape_interval_minutes: event.target.value }),
            })
          ),
          field(
            "SMTP host",
            h("input", {
              type: "text",
              value: settings.smtp_host,
              onChange: (event) => setSettings({ ...settings, smtp_host: event.target.value }),
            })
          ),
          field(
            "SMTP port",
            h("input", {
              type: "number",
              value: settings.smtp_port,
              onChange: (event) => setSettings({ ...settings, smtp_port: event.target.value }),
            })
          ),
          field(
            "SMTP username",
            h("input", {
              type: "text",
              value: settings.smtp_username,
              onChange: (event) => setSettings({ ...settings, smtp_username: event.target.value }),
            })
          ),
          field(
            "SMTP password",
            h("input", {
              type: "password",
              value: settings.smtp_password,
              onChange: (event) => setSettings({ ...settings, smtp_password: event.target.value }),
            })
          ),
          field(
            "Sender email",
            h("input", {
              type: "email",
              value: settings.sender_email,
              onChange: (event) => setSettings({ ...settings, sender_email: event.target.value }),
            })
          ),
          field(
            "Recipient email",
            h("input", {
              type: "email",
              value: settings.recipient_email,
              onChange: (event) => setSettings({ ...settings, recipient_email: event.target.value }),
            })
          ),
          field(
            "OpenRouter API key",
            h("input", {
              type: "password",
              value: settings.openrouter_api_key,
              onChange: (event) => setSettings({ ...settings, openrouter_api_key: event.target.value }),
            })
          ),
          field(
            "OpenRouter model",
            h("input", {
              type: "text",
              placeholder: "openai/gpt-4.1-mini",
              value: settings.openrouter_model,
              onChange: (event) => setSettings({ ...settings, openrouter_model: event.target.value }),
            })
          ),
          field(
            "OpenRouter timeout (seconds)",
            h("input", {
              type: "number",
              min: 5,
              value: settings.openrouter_timeout_seconds,
              onChange: (event) => setSettings({ ...settings, openrouter_timeout_seconds: event.target.value }),
            })
          ),
          field(
            "OpenRouter max retries",
            h("input", {
              type: "number",
              min: 0,
              value: settings.openrouter_max_retries,
              onChange: (event) => setSettings({ ...settings, openrouter_max_retries: event.target.value }),
            })
          )
        ),
        h(
          "label",
          { className: "check" },
          h("input", {
            type: "checkbox",
            checked: settings.notifications_enabled,
            onChange: (event) => setSettings({ ...settings, notifications_enabled: event.target.checked }),
          }),
          "Enable email notifications"
        ),
        h(
          "div",
          { className: "actions" },
          h(
            "button",
            { className: "btn-primary", type: "submit", disabled: busy },
            busy ? "Saving..." : "Save settings"
          )
        )
      )
    );
  }

  function renderScopedScrapePanel() {
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Scoped Scrape Run"),
        h("p", null, "Choose one or more sources and optionally cap how many concerts to ingest.")
      ),
      h(
        "div",
        { className: "stack" },
        h("p", { className: "muted" }, `Current scope: ${scrapeScopeLabel}`),
        h(
          "div",
          { className: "source-grid" },
          scrapeSources.length === 0
            ? h("div", { className: "muted" }, "No scrape sources available.")
            : scrapeSources.map((source) =>
                h(
                  "label",
                  {
                    key: source,
                    className: `source-option ${
                      scrapeScope.selected_sources.includes(source) ? "active" : ""
                    }`,
                  },
                  h("input", {
                    type: "checkbox",
                    checked: scrapeScope.selected_sources.includes(source),
                    onChange: () => toggleScrapeSource(source),
                  }),
                  h("span", null, source)
                )
              )
        ),
        h(
          "div",
          { className: "actions" },
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              disabled: busy || scrapeSources.length === 0,
              onClick: selectAllScrapeSources,
            },
            "Select all"
          ),
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              disabled: busy || scrapeSources.length === 0,
              onClick: clearScrapeSources,
            },
            "Clear"
          )
        ),
        h(
          "div",
          { className: "fields" },
          field(
            "Only scrape X per selected source",
            h("input", {
              type: "number",
              min: 1,
              placeholder: "No per-source cap",
              value: scrapeScope.max_per_source,
              onChange: (event) =>
                setScrapeScope({
                  ...scrapeScope,
                  max_per_source: event.target.value,
                }),
            })
          ),
          field(
            "Max total concerts for this run",
            h("input", {
              type: "number",
              min: 1,
              placeholder: "No global cap",
              value: scrapeScope.max_total,
              onChange: (event) =>
                setScrapeScope({
                  ...scrapeScope,
                  max_total: event.target.value,
                }),
            })
          )
        ),
        h(
          "div",
          { className: "actions" },
          h(
            "button",
            {
              className: "btn-neutral",
              type: "button",
              disabled: busy,
              onClick: runScopedScrape,
            },
            busy ? "Running scoped scrape..." : "Run scoped scrape"
          )
        )
      )
    );
  }

  function renderRulesPanel() {
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Notification Rules"),
        h("p", null, "Create match rules against concert title, date, performers, and program.")
      ),
      h(
        "form",
        { className: "stack", onSubmit: addRule },
        h(
          "div",
          { className: "fields" },
          field(
            "Name contains",
            h("input", {
              type: "text",
              value: newRule.name_contains,
              onChange: (event) => setNewRule({ ...newRule, name_contains: event.target.value }),
            })
          ),
          field(
            "Performer contains",
            h("input", {
              type: "text",
              value: newRule.performer_contains,
              onChange: (event) => setNewRule({ ...newRule, performer_contains: event.target.value }),
            })
          ),
          field(
            "Program contains",
            h("input", {
              type: "text",
              value: newRule.program_contains,
              onChange: (event) => setNewRule({ ...newRule, program_contains: event.target.value }),
            })
          ),
          field(
            "Date contains",
            h("input", {
              type: "text",
              value: newRule.date_contains,
              onChange: (event) => setNewRule({ ...newRule, date_contains: event.target.value }),
            })
          ),
          field(
            "Time contains",
            h("input", {
              type: "text",
              value: newRule.time_contains,
              onChange: (event) => setNewRule({ ...newRule, time_contains: event.target.value }),
            })
          )
        ),
        h(
          "label",
          { className: "check" },
          h("input", {
            type: "checkbox",
            checked: newRule.enabled,
            onChange: (event) => setNewRule({ ...newRule, enabled: event.target.checked }),
          }),
          "Rule enabled"
        ),
        h(
          "div",
          { className: "actions" },
          h(
            "button",
            { className: "btn-primary", type: "submit", disabled: busy },
            busy ? "Saving..." : "Add rule"
          )
        )
      ),
      h(
        "ul",
        { className: "rule-list" },
        rules.length === 0
          ? h("li", { className: "rule-item" }, h("div", { className: "rule-line" }, "No rules yet."))
          : rules.map((rule) =>
              h(
                "li",
                { className: "rule-item", key: rule.id },
                h(
                  "div",
                  { className: "rule-line" },
                  `name: ${display(rule.name_contains)} | performer: ${display(
                    rule.performer_contains
                  )} | program: ${display(rule.program_contains)} | date: ${display(
                    rule.date_contains
                  )} | time: ${display(rule.time_contains)}`
                ),
                h(
                  "div",
                  { className: "rule-meta" },
                  h("span", { className: "rule-tag" }, `Rule #${rule.id} - ${rule.enabled ? "enabled" : "disabled"}`),
                  h(
                    "button",
                    {
                      className: "btn-ghost",
                      type: "button",
                      disabled: busy,
                      onClick: () => removeRule(rule.id),
                    },
                    "Delete"
                  )
                )
              )
            )
      )
    );
  }

  function renderUnresolvedPanel() {
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Unresolved Review"),
        h("p", null, "Accept candidates, create entities, or mark items as distinct.")
      ),
      h(
        "p",
        { className: "muted" },
        resolutionLoading
          ? "Loading unresolved queue..."
          : `${unresolvedItems.length} unresolved item${unresolvedItems.length === 1 ? "" : "s"}`
      ),
      h(
        "ul",
        { className: "review-list" },
        resolutionLoading
          ? h("li", { className: "review-item" }, "Loading unresolved items...")
          : unresolvedItems.length === 0
          ? h("li", { className: "review-item" }, "No unresolved entities right now.")
          : unresolvedItems.map((item) =>
              h(
                "li",
                { className: "review-item", key: item.id },
                h(
                  "div",
                  { className: "review-header" },
                  h("span", { className: `type-pill ${item.entity_type}` }, (item.entity_type || "unknown").toUpperCase()),
                  h(
                    "span",
                    { className: "rule-tag" },
                    item.event_date ? `${item.event_date}` : `Event #${item.event_id}`
                  )
                ),
                h("div", { className: "review-raw" }, item.raw_text || "(empty input)"),
                item.event_title && h("div", { className: "muted" }, item.event_title),
                h(
                  "div",
                  { className: "review-candidates" },
                  !item.candidates || item.candidates.length === 0
                    ? h("div", { className: "muted" }, "No candidates available.")
                    : item.candidates.map((candidate) =>
                        h(
                          "div",
                          { className: "candidate-row", key: `${item.id}-${candidate.id}` },
                          h(
                            "div",
                            { className: "candidate-text" },
                            `${candidate.label || `ID ${candidate.id}`} (${Math.round((candidate.score || 0) * 100)}%)`
                          ),
                          h(
                            "button",
                            {
                              className: "btn-ghost small-btn",
                              type: "button",
                              disabled: busy,
                              onClick: () => resolveWithCandidate(item.id, candidate.id),
                            },
                            "Accept"
                          )
                        )
                      )
                ),
                h(
                  "div",
                  { className: "inline-actions" },
                  h("input", {
                    type: "text",
                    placeholder: "Value for create_new (optional)",
                    value: newEntityDrafts[item.id] || "",
                    onChange: (event) =>
                      setNewEntityDrafts((previous) => ({ ...previous, [item.id]: event.target.value })),
                  }),
                  h(
                    "button",
                    {
                      className: "btn-primary small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => createEntityForUnresolved(item),
                    },
                    "Create new"
                  )
                ),
                h(
                  "div",
                  { className: "inline-actions" },
                  h("input", {
                    type: "text",
                    placeholder: "Reason for mark_distinct (optional)",
                    value: reviewReasons[`u-${item.id}`] || "",
                    onChange: (event) =>
                      setReviewReasons((previous) => ({ ...previous, [`u-${item.id}`]: event.target.value })),
                  }),
                  h(
                    "button",
                    {
                      className: "btn-ghost small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => markDistinct(item),
                    },
                    "Mark distinct"
                  )
                )
              )
            )
      )
    );
  }

  function renderMergePanel() {
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Merge Suggestions"),
        h("p", null, "Merge, reject, or protect candidate pairs with do-not-merge.")
      ),
      h(
        "p",
        { className: "muted" },
        resolutionLoading
          ? "Loading merge suggestions..."
          : `${mergeSuggestions.length} pending suggestion${mergeSuggestions.length === 1 ? "" : "s"}`
      ),
      h(
        "ul",
        { className: "review-list" },
        resolutionLoading
          ? h("li", { className: "review-item" }, "Loading merge suggestions...")
          : mergeSuggestions.length === 0
          ? h("li", { className: "review-item" }, "No merge suggestions right now.")
          : mergeSuggestions.map((item) =>
              h(
                "li",
                { className: "review-item", key: item.id },
                h(
                  "div",
                  { className: "review-header" },
                  h("span", { className: `type-pill ${item.entity_type}` }, (item.entity_type || "unknown").toUpperCase()),
                  h("span", { className: "rule-tag" }, `${Math.round((item.score || 0) * 100)}% score`)
                ),
                h(
                  "div",
                  { className: "review-raw" },
                  `${item.candidate_a_label || `ID ${item.candidate_a_id}`} ↔ ${
                    item.candidate_b_label || `ID ${item.candidate_b_id}`
                  }`
                ),
                h(
                  "div",
                  { className: "review-links" },
                  item.candidate_a_concert?.source_url
                    ? h(
                        "a",
                        {
                          href: item.candidate_a_concert.source_url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                        },
                        `Concert A: ${item.candidate_a_concert.name || `#${item.candidate_a_concert.id}`}`
                      )
                    : h("span", { className: "muted" }, "Concert A: no linked concert"),
                  item.candidate_b_concert?.source_url
                    ? h(
                        "a",
                        {
                          href: item.candidate_b_concert.source_url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                        },
                        `Concert B: ${item.candidate_b_concert.name || `#${item.candidate_b_concert.id}`}`
                      )
                    : h("span", { className: "muted" }, "Concert B: no linked concert")
                ),
                h("div", { className: "muted" }, item.reason || "No reason provided."),
                h(
                  "div",
                  { className: "inline-actions" },
                  h("input", {
                    type: "text",
                    placeholder: "Reason (optional)",
                    value: reviewReasons[`m-${item.id}`] || "",
                    onChange: (event) =>
                      setReviewReasons((previous) => ({ ...previous, [`m-${item.id}`]: event.target.value })),
                  })
                ),
                h(
                  "div",
                  { className: "actions" },
                  h(
                    "button",
                    {
                      className: "btn-primary small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => updateMergeSuggestion(item, "merge"),
                    },
                    "Merge"
                  ),
                  h(
                    "button",
                    {
                      className: "btn-ghost small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => updateMergeSuggestion(item, "reject"),
                    },
                    "Reject"
                  ),
                  h(
                    "button",
                    {
                      className: "btn-danger small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => updateMergeSuggestion(item, "do_not_merge"),
                    },
                    "Do not merge"
                  )
                )
              )
            )
      )
    );
  }

  function renderConcertPanel() {
    const MAX_VISIBLE_TAGS = 10;

    function renderFilterChip(label, key, mode = "q", className = "token-chip", entityType = null, entityId = null) {
      const text = String(label || "").trim();
      if (!text) {
        return null;
      }

      return h(
        "button",
        {
          key,
          type: "button",
          className,
          title: `Filter by ${text}`,
          onClick: () => {
            void applyTagFilter(text, mode, entityType, entityId);
          },
        },
        text
      );
    }

    return h(
      "section",
      { className: "panel concert-panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Concert Explorer"),
        h("p", null, "Search and filter the latest 500 scraped entries.")
      ),
      h(
        "form",
        { className: "stack", onSubmit: applyFilters },
        h(
          "div",
          { className: "fields" },
          h(
            "div",
            { className: "field-with-suggestions" },
            h("label", null, "Search"),
            h("input", {
              type: "text",
              placeholder: "Name, performers, hall, program",
              value: filters.q,
              onChange: (event) => {
                setFilters({ ...filters, q: event.target.value });
                void loadSearchSuggestions(event.target.value);
              },
              onBlur: () => {
                setTimeout(() => setShowSearchSuggestions(false), 200);
              },
              onFocus: () => {
                if (filters.q && searchSuggestions.length > 0) {
                  setShowSearchSuggestions(true);
                }
              },
            }),
            showSearchSuggestions && searchSuggestions.length > 0
              ? h(
                  "ul",
                  { className: "search-suggestions" },
                  searchSuggestions.map((suggestion, index) => {
                    const label =
                      suggestion.type === "performer"
                        ? `${suggestion.label}${suggestion.matched_alias ? ` (alias: ${suggestion.matched_alias})` : ""} - Performer`
                        : suggestion.type === "work"
                        ? `${suggestion.label} - Work`
                        : `${suggestion.label} - Venue`;

                    return h(
                      "li",
                      {
                        key: `${suggestion.type}-${suggestion.id}-${index}`,
                        className: `suggestion-item suggestion-${suggestion.type}`,
                        onClick: () => {
                          const nextFilters = { ...filters };
                          if (suggestion.type === "performer") {
                            nextFilters.performer_ids = [...(nextFilters.performer_ids || []), suggestion.id];
                          } else if (suggestion.type === "work") {
                            nextFilters.work_ids = [...(nextFilters.work_ids || []), suggestion.id];
                          } else if (suggestion.type === "venue") {
                            nextFilters.venue_ids = [...(nextFilters.venue_ids || []), suggestion.id];
                          }
                          setFilters(nextFilters);
                          setShowSearchSuggestions(false);
                          setSearchSuggestions([]);
                          void loadDashboard(nextFilters);
                        },
                      },
                      h("span", { className: "suggestion-type" }, suggestion.type),
                      h("span", { className: "suggestion-label" }, label)
                    );
                  })
                )
              : null
          ),
          field(
            "Source",
            h(
              "select",
              {
                value: filters.source,
                onChange: (event) => setFilters({ ...filters, source: event.target.value }),
              },
              h("option", { value: "" }, "All sources"),
              sources.map((source) => h("option", { key: source, value: source }, source))
            )
          ),
          field(
            "Date Range",
            h(
              "div",
              { className: "date-range-container" },
              h(
                "div",
                { className: "date-range-group" },
                h("label", { className: "date-input-label" }, "From"),
                h(
                  "div",
                  { className: "date-inputs" },
                  h("input", {
                    type: "text",
                    className: "date-input date-input-day",
                    placeholder: "DD",
                    maxLength: "2",
                    value: filters.date_start_day,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || (parseInt(val) >= 1 && parseInt(val) <= 31)) {
                        setFilters({ ...filters, date_start_day: val });
                      }
                    },
                  }),
                  h("span", { className: "date-separator" }, "/"),
                  h("input", {
                    type: "text",
                    className: "date-input date-input-month",
                    placeholder: "MM",
                    maxLength: "2",
                    value: filters.date_start_month,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || (parseInt(val) >= 1 && parseInt(val) <= 12)) {
                        setFilters({ ...filters, date_start_month: val });
                      }
                    },
                  }),
                  h("span", { className: "date-separator" }, "/"),
                  h("input", {
                    type: "text",
                    className: "date-input date-input-year",
                    placeholder: "YYYY",
                    maxLength: "4",
                    value: filters.date_start_year,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || val.length <= 4) {
                        setFilters({ ...filters, date_start_year: val });
                      }
                    },
                  })
                )
              ),
              h(
                "div",
                { className: "date-range-group" },
                h("label", { className: "date-input-label" }, "To"),
                h(
                  "div",
                  { className: "date-inputs" },
                  h("input", {
                    type: "text",
                    className: "date-input date-input-day",
                    placeholder: "DD",
                    maxLength: "2",
                    value: filters.date_end_day,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || (parseInt(val) >= 1 && parseInt(val) <= 31)) {
                        setFilters({ ...filters, date_end_day: val });
                      }
                    },
                  }),
                  h("span", { className: "date-separator" }, "/"),
                  h("input", {
                    type: "text",
                    className: "date-input date-input-month",
                    placeholder: "MM",
                    maxLength: "2",
                    value: filters.date_end_month,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || (parseInt(val) >= 1 && parseInt(val) <= 12)) {
                        setFilters({ ...filters, date_end_month: val });
                      }
                    },
                  }),
                  h("span", { className: "date-separator" }, "/"),
                  h("input", {
                    type: "text",
                    className: "date-input date-input-year",
                    placeholder: "YYYY",
                    maxLength: "4",
                    value: filters.date_end_year,
                    onChange: (event) => {
                      const val = event.target.value.replace(/[^0-9]/g, "");
                      if (val === "" || val.length <= 4) {
                        setFilters({ ...filters, date_end_year: val });
                      }
                    },
                  })
                )
              )
            )
          ),
          field(
            "Time Range",
            h(
              "div",
              { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
              h("input", {
                type: "time",
                placeholder: "Start time",
                value: filters.time_start,
                onChange: (event) => setFilters({ ...filters, time_start: event.target.value }),
                style: { flex: "1", minWidth: "120px" },
              }),
              h("span", { style: { fontSize: "12px", color: "#666" } }, "to"),
              h("input", {
                type: "time",
                placeholder: "End time",
                value: filters.time_end,
                onChange: (event) => setFilters({ ...filters, time_end: event.target.value }),
                style: { flex: "1", minWidth: "120px" },
              })
            )
          )
        ),
        h(
          "div",
          { className: "active-filters" },
          [
            ...(filters.performer_ids || []).map((performerId) =>
              h(
                "div",
                { className: "filter-pill" },
                h("span", { className: "filter-pill-label" }, `Performer: ${filterLabels.performers?.[performerId] || `#${performerId}`}`),
                h(
                  "button",
                  {
                    type: "button",
                    className: "filter-pill-remove",
                    onClick: () => {
                      const nextFilters = {
                        ...filters,
                        performer_ids: (filters.performer_ids || []).filter((id) => id !== performerId),
                      };
                      setFilters(nextFilters);
                      void loadDashboard(nextFilters);
                    },
                  },
                  "×"
                )
              )
            ),
            ...(filters.work_ids || []).map((workId) =>
              h(
                "div",
                { className: "filter-pill" },
                h("span", { className: "filter-pill-label" }, `Work: ${filterLabels.works?.[workId] || `#${workId}`}`),
                h(
                  "button",
                  {
                    type: "button",
                    className: "filter-pill-remove",
                    onClick: () => {
                      const nextFilters = {
                        ...filters,
                        work_ids: (filters.work_ids || []).filter((id) => id !== workId),
                      };
                      setFilters(nextFilters);
                      void loadDashboard(nextFilters);
                    },
                  },
                  "×"
                )
              )
            ),
            ...(filters.venue_ids || []).map((venueId) =>
              h(
                "div",
                { className: "filter-pill" },
                h("span", { className: "filter-pill-label" }, `Venue: ${filterLabels.venues?.[venueId] || `#${venueId}`}`),
                h(
                  "button",
                  {
                    type: "button",
                    className: "filter-pill-remove",
                    onClick: () => {
                      const nextFilters = {
                        ...filters,
                        venue_ids: (filters.venue_ids || []).filter((id) => id !== venueId),
                      };
                      setFilters(nextFilters);
                      void loadDashboard(nextFilters);
                    },
                  },
                  "×"
                )
              )
            ),
          ].filter((el) => el)
        ),
        h(
          "label",
          { className: "check maybe-check" },
          h("input", {
            type: "checkbox",
            checked: filters.include_maybe,
            onChange: (event) => setFilters({ ...filters, include_maybe: event.target.checked }),
          }),
          'Show tagged "maybe a concert" entries'
        ),
        h(
          "div",
          { className: "actions" },
          h("button", { className: "btn-primary", type: "submit", disabled: loading }, loading ? "Loading..." : "Apply filters"),
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              disabled: loading,
              onClick: resetFilters,
            },
            "Reset"
          ),
          h(
            "button",
            {
              className: "btn-neutral",
              type: "button",
              disabled: dumping,
              onClick: dumpCurrentConcerts,
            },
            dumping ? "Dumping..." : "Dump current concerts"
          ),
          h(
            "button",
            {
              className: "btn-danger",
              type: "button",
              disabled: busy,
              onClick: deleteFilteredConcerts,
            },
            busy ? "Deleting filtered..." : "Delete filtered concerts"
          ),
          h(
            "button",
            {
              className: "btn-danger",
              type: "button",
              disabled: busy,
              onClick: deleteAllConcerts,
            },
            busy ? "Deleting all..." : "Delete ALL concerts"
          )
        )
      ),
      h(
        "p",
        { className: "muted" },
        filters.include_maybe
          ? `${concerts.length} concerts shown`
          : `${concerts.length} concerts shown (${maybeHiddenCount} tagged as maybe a concert hidden)`
      ),
      h(
        "div",
        { className: "concert-grid" },
        loading && concerts.length === 0
          ? h("article", { className: "concert-card empty-card" }, h("p", { className: "muted" }, "Loading concerts..."))
          : concerts.length === 0
          ? h("article", { className: "concert-card empty-card" }, h("p", { className: "muted" }, "No concerts found for this filter."))
          : concerts.map((concert) => {
              const view = normalizeConcertView(concert);

              return h(
                "article",
                { className: "concert-card", key: concert.id },
                h(
                  "div",
                  { className: "concert-card-head" },
                  h(
                    "div",
                    { className: "chip-cloud" },
                    renderFilterChip(concert.source || "Unknown source", `${concert.id}-source`, "source", "source-chip source-chip-btn"),
                    concert.maybe_concert ? h("span", { className: "row-tag maybe" }, "maybe a concert") : null,
                    view.soldOut ? h("span", { className: "row-tag sold-out" }, "sold out") : null,
                    view.unresolvedTotal > 0 ? h("span", { className: "row-tag pending" }, `${view.unresolvedTotal} unresolved`) : null
                  ),
                  h(
                    "div",
                    { className: "row-actions" },
                    h(
                      "a",
                      {
                        href: concert.source_url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                      },
                      "Open"
                    ),
                    h(
                      "button",
                      {
                        className: "btn-danger small-btn",
                        type: "button",
                        disabled: busy,
                        onClick: () => deleteConcert(concert),
                      },
                      "Delete"
                    )
                  )
                ),
                h("h3", { className: "concert-title" }, view.title || concert.name || "Untitled concert"),
                h(
                  "div",
                  { className: "chip-cloud concert-meta-cloud" },
                  view.dateLabel ? renderFilterChip(view.dateLabel, `${concert.id}-date`, "date", "token-chip meta-chip") : null,
                  concert.time ? renderFilterChip(concert.time, `${concert.id}-time`, "q", "token-chip meta-chip") : null,
                  view.venueName
                    ? renderFilterChip(view.venueName, `${concert.id}-venue`, "q", "token-chip meta-chip", "venue", view.venueId > 0 ? view.venueId : null)
                    : h("span", { className: "muted" }, "No normalized venue")
                ),
                h(
                  "div",
                  { className: "tag-section" },
                  h("span", { className: "tag-label" }, "Pieces"),
                  h(
                    "div",
                    { className: "chip-cloud" },
                    view.workTags.length === 0
                      ? h("span", { className: "muted" }, "No normalized pieces")
                      : (() => {
                          const { visible, hiddenCount } = limitTags(view.workTags, MAX_VISIBLE_TAGS);
                          return [
                            ...visible.map((tag, index) => {
                              const workId = view.workIds[index];
                              return renderFilterChip(tag, `${concert.id}-work-${index}`, "q", "token-chip entity-chip", "work", workId > 0 ? workId : null);
                            }),
                            hiddenCount > 0
                              ? h(
                                  "span",
                                  {
                                    key: `${concert.id}-work-more`,
                                    className: "token-chip more-chip",
                                    title: `${hiddenCount} additional normalized pieces hidden`,
                                  },
                                  `+${hiddenCount} more`
                                )
                              : null,
                          ];
                        })()
                  )
                ),
                h(
                  "div",
                  { className: "tag-section" },
                  h("span", { className: "tag-label" }, "Prices"),
                  h(
                    "div",
                    { className: "chip-cloud" },
                    view.priceTags.length === 0
                      ? h("span", { className: "muted" }, "No extracted price tags")
                      : (() => {
                          const { visible, hiddenCount } = limitTags(view.priceTags, MAX_VISIBLE_TAGS);
                          return [
                            ...visible.map((tag, index) =>
                              renderFilterChip(tag, `${concert.id}-price-${index}`, "q", "token-chip price-chip")
                            ),
                            hiddenCount > 0
                              ? h(
                                  "span",
                                  {
                                    key: `${concert.id}-price-more`,
                                    className: "token-chip more-chip",
                                    title: `${hiddenCount} additional extracted price tags hidden`,
                                  },
                                  `+${hiddenCount} more`
                                )
                              : null,
                          ];
                        })()
                  )
                ),
                h(
                  "div",
                  { className: "tag-section" },
                  h("span", { className: "tag-label" }, "Performers"),
                  h(
                    "div",
                    { className: "chip-cloud" },
                    view.performerTags.length === 0
                      ? h("span", { className: "muted" }, "No normalized performers")
                      : (() => {
                          const { visible, hiddenCount } = limitTags(view.performerTags, MAX_VISIBLE_TAGS);
                          return [
                            ...visible.map((tag, index) => {
                              const performerId = view.performerIds[index];
                              return renderFilterChip(tag, `${concert.id}-performer-${index}`, "q", "token-chip entity-chip", "performer", performerId > 0 ? performerId : null);
                            }),
                            hiddenCount > 0
                              ? h(
                                  "span",
                                  {
                                    key: `${concert.id}-performer-more`,
                                    className: "token-chip more-chip",
                                    title: `${hiddenCount} additional normalized performers hidden`,
                                  },
                                  `+${hiddenCount} more`
                                )
                              : null,
                          ];
                        })()
                  )
                )
              );
            })
      )
    );
  }

  function renderRecentConcertsPanel() {
    const recent = concerts.slice(0, 8);
    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Recent Concert Snapshot"),
        h("p", null, "Latest entries from your current filter view.")
      ),
      h(
        "div",
        { className: "table-wrap mini-table-wrap" },
        h(
          "table",
          null,
          h(
            "thead",
            null,
            h("tr", null, h("th", null, "Source"), h("th", null, "Name"), h("th", null, "Date"), h("th", null, "Link"))
          ),
          h(
            "tbody",
            null,
            recent.length === 0
              ? h("tr", null, h("td", { className: "empty-row", colSpan: 4 }, "No concerts in current view."))
              : recent.map((concert) =>
                  {
                    const view = normalizeConcertView(concert);
                    return h(
                      "tr",
                      { key: `recent-${concert.id}` },
                      h("td", null, h("span", { className: "source-chip" }, concert.source)),
                      h("td", null, view.title || concert.name),
                      h("td", null, display(view.dateLabel || concert.date_normalized || concert.date)),
                      h(
                        "td",
                        null,
                        h(
                          "a",
                          {
                            href: concert.source_url,
                            target: "_blank",
                            rel: "noopener noreferrer",
                          },
                          "Open"
                        )
                      )
                    );
                  }
                )
          )
        )
      )
    );
  }

  function renderOverviewPage() {
    return h(
      "div",
      { className: "page-stack" },
      renderMetricsSection(),
      h(
        "div",
        { className: "page-grid-two" },
        h(
          "section",
          { className: "panel" },
          h(
            "div",
            { className: "panel-head" },
            h("h2", null, "Quick Actions"),
            h("p", null, "Run core operations without leaving the dashboard.")
          ),
          h("p", { className: "muted" }, `Manual scrape scope: ${scrapeScopeLabel}`),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              {
                className: "btn-neutral",
                type: "button",
                disabled: busy,
                onClick: runScopedScrape,
              },
              busy ? "Running scoped scrape..." : "Run scoped scrape"
            ),
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                disabled: dumping,
                onClick: dumpCurrentConcerts,
              },
              dumping ? "Dumping..." : "Dump current concerts"
            )
          ),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                onClick: () => goToPage("scrape"),
              },
              "Open scrape controls"
            ),
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                onClick: () => goToPage("concerts"),
              },
              "Open concert explorer"
            ),
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                onClick: () => goToPage("resolution"),
              },
              "Open resolution queue"
            )
          )
        ),
        renderRecentConcertsPanel()
      )
    );
  }

  function renderScrapePage() {
    return h(
      "div",
      { className: "page-grid-two" },
      renderScopedScrapePanel(),
      renderSystemSettingsPanel()
    );
  }

  function renderConcertsPage() {
    return h("div", { className: "page-stack" }, renderConcertPanel());
  }

  function renderResolutionPage() {
    return h(
      "div",
      { className: "page-grid-two" },
      renderUnresolvedPanel(),
      renderMergePanel()
    );
  }

  function renderRulesPage() {
    return h(
      "div",
      { className: "page-grid-two" },
      renderRulesPanel(),
      h(
        "section",
        { className: "panel" },
        h(
          "div",
          { className: "panel-head" },
          h("h2", null, "Notification Status"),
          h("p", null, "Current email delivery configuration snapshot.")
        ),
        h(
          "div",
          { className: "stack" },
          h("p", { className: "muted" }, `Notifications: ${settings.notifications_enabled ? "enabled" : "disabled"}`),
          h("p", { className: "muted" }, `SMTP host: ${display(settings.smtp_host)}`),
          h("p", { className: "muted" }, `Sender: ${display(settings.sender_email)}`),
          h("p", { className: "muted" }, `Recipient: ${display(settings.recipient_email)}`),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                onClick: () => goToPage("scrape"),
              },
              "Edit system settings"
            )
          )
        )
      )
    );
  }

  function renderActivePage() {
    if (activePage === "scrape") {
      return renderScrapePage();
    }
    if (activePage === "concerts") {
      return renderConcertsPage();
    }
    if (activePage === "resolution") {
      return renderResolutionPage();
    }
    if (activePage === "rules") {
      return renderRulesPage();
    }
    return renderOverviewPage();
  }

  return h(
    "div",
    { className: "app-shell" },
    h(
      "header",
      { className: "masthead" },
      h(
        "div",
        null,
        h("p", { className: "eyebrow" }, "Concert Intelligence Desk"),
        h("h1", null, "Signal Desk"),
        h(
          "p",
          null,
          "A multi-page control center for scraping, entity resolution, filtering, and notifications."
        )
      ),
      h(
        "div",
        { className: "status-stack" },
        h("span", { className: "status-badge" }, `${activeRuleCount} active rules`),
        h("div", { className: "status-note" }, `Latest sync: ${latestFetchLabel}`),
        h(
          "div",
          { className: "status-actions" },
          h(
            "button",
            {
              className: "btn-neutral",
              type: "button",
              disabled: busy,
              onClick: runScopedScrape,
            },
            busy ? "Running scrape..." : "Run scoped scrape"
          ),
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              disabled: dumping,
              onClick: dumpCurrentConcerts,
            },
            dumping ? "Dumping..." : "Dump concerts"
          )
        )
      )
    ),

    notice && h("div", { className: `notice ${notice.type}` }, notice.text),

    h(
      "nav",
      { className: "page-nav", "aria-label": "Dashboard pages" },
      PAGE_CONFIG.map((page) =>
        h(
          "button",
          {
            key: page.id,
            type: "button",
            className: `page-link ${activePage === page.id ? "active" : ""}`,
            onClick: () => goToPage(page.id),
          },
          page.label
        )
      )
    ),

    renderActivePage()
  );
}

createRoot(document.getElementById("root")).render(h(App));
