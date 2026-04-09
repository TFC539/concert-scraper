import React, { useEffect, useMemo, useRef, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

const h = React.createElement;

const PAGE_CONFIG = [
  { id: "overview", label: "Overview" },
  { id: "scrape", label: "Scrape Control" },
  { id: "concerts", label: "Concert Explorer" },
  { id: "resolution", label: "Triage Dashboard" },
  { id: "rules", label: "Notifications" },
];

const AUTH_TOKEN_KEY = "concert.signal.authToken";

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

const emptyNotificationProfile = {
  notifications_enabled: false,
  notification_email: "",
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
  const [authToken, setAuthToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY) || "");
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ username: "", email: "", password: "", username_or_email: "" });
  const [showAuthPanel, setShowAuthPanel] = useState(false);
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
  const [notificationProfile, setNotificationProfile] = useState({ ...emptyNotificationProfile });
  const [newRule, setNewRule] = useState({ ...emptyRule });
  const [scrapeScope, setScrapeScope] = useState({ ...emptyScrapeScope });

  const [unresolvedItems, setUnresolvedItems] = useState([]);
  const [mergeSuggestions, setMergeSuggestions] = useState([]);
  const [newEntityDrafts, setNewEntityDrafts] = useState({});
  const [applyGloballyFlags, setApplyGloballyFlags] = useState({});
  const [reviewReasons, setReviewReasons] = useState({});
  const [searchSuggestions, setSearchSuggestions] = useState([]);
  const [showSearchSuggestions, setShowSearchSuggestions] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [filterLabels, setFilterLabels] = useState({ performers: {}, works: {}, venues: {} });
  const mobileNavRef = useRef(null);
  const mobileNavButtonRef = useRef(null);

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
  const canManageSystemSettings = useMemo(
    () => Boolean(currentUser && String(currentUser.role || "") === "admin"),
    [currentUser]
  );
  const canReviewMerges = useMemo(
    () =>
      Boolean(
        currentUser &&
          (String(currentUser.role || "") === "admin" ||
            ["trusted", "verified"].includes(String(currentUser.trust_level || "")))
      ),
    [currentUser]
  );
  const visiblePageConfig = useMemo(() => {
    if (!currentUser) {
      return PAGE_CONFIG.filter((page) => page.id === "concerts");
    }
    if (canManageSystemSettings) {
      return PAGE_CONFIG;
    }
    return PAGE_CONFIG.filter((page) => page.id !== "scrape");
  }, [currentUser, canManageSystemSettings]);

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
    const fallback = !currentUser ? "concerts" : "overview";
    const isVisible = visiblePageConfig.some((page) => page.id === activePage);
    if (!isVisible) {
      setActivePage(fallback);
      window.location.hash = fallback;
    }
  }, [currentUser, activePage, visiblePageConfig]);

  useEffect(() => {
    if (!authToken) {
      setCurrentUser(null);
      setResolutionLoading(false);
      setUnresolvedItems([]);
      setMergeSuggestions([]);
      return;
    }

    void (async () => {
      try {
        const payload = await request("/api/auth/me", { headers: {} });
        setCurrentUser(payload.user || null);
        await refreshAll(filters);
      } catch (_) {
        // request() already handles notice and token reset on auth failures.
      }
    })();
  }, [authToken]);

  useEffect(() => {
    if (currentUser) {
      setShowAuthPanel(false);
    }
  }, [currentUser]);

  useEffect(() => {
    if (!mobileNavOpen) {
      return undefined;
    }

    const menuNode = mobileNavRef.current;
    if (menuNode) {
      const focusables = menuNode.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusables.length > 0) {
        focusables[0].focus();
      }
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
        mobileNavButtonRef.current?.focus();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const container = mobileNavRef.current;
      if (!container) {
        return;
      }
      const focusable = Array.from(
        container.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
      ).filter((node) => !node.hasAttribute("disabled"));
      if (focusable.length === 0) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileNavOpen]);

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

    if (authToken && !headers.Authorization) {
      headers.Authorization = `Bearer ${authToken}`;
    }

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(path, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      setAuthToken("");
      setCurrentUser(null);
      if (!String(path || "").startsWith("/api/auth/")) {
        setNotice({ type: "error", text: "Your contributor session expired. Please log in again." });
      }
    }

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
      setNotificationProfile({ ...emptyNotificationProfile, ...(payload.notification_profile || {}) });
      setFilterLabels(payload.filter_labels || { performers: {}, works: {}, venues: {} });
    } catch (error) {
      setNotice({ type: "error", text: `Could not load dashboard data: ${error.message}` });
    } finally {
      setLoading(false);
    }
  }

  async function loadResolutionData() {
    if (!authToken) {
      setUnresolvedItems([]);
      setMergeSuggestions([]);
      setResolutionLoading(false);
      return;
    }

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
      setActiveSuggestionIndex(-1);
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
      setActiveSuggestionIndex(-1);
    } catch (error) {
      setSearchSuggestions([]);
      setShowSearchSuggestions(false);
      setActiveSuggestionIndex(-1);
    }
  }

  async function refreshAll(nextFilters = filters) {
    await Promise.all([loadDashboard(nextFilters), loadResolutionData()]);
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);

    try {
      if (authMode === "signup") {
        const payload = await request("/api/auth/signup", {
          method: "POST",
          body: JSON.stringify({
            username: authForm.username,
            email: authForm.email,
            password: authForm.password,
          }),
        });
        const token = String(payload?.token || "").trim();
        if (!token) {
          throw new Error("Signup succeeded but no session token was returned.");
        }
        localStorage.setItem(AUTH_TOKEN_KEY, token);
        setAuthToken(token);
        setCurrentUser(payload.user || null);
        setAuthForm({ username: "", email: "", password: "", username_or_email: "" });
        setNotice({ type: "success", text: "Contributor account created and logged in." });
        await refreshAll(filters);
      } else {
        const payload = await request("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            username_or_email: authForm.username_or_email,
            password: authForm.password,
          }),
        });
        const token = String(payload?.token || "").trim();
        if (!token) {
          throw new Error("Login succeeded but no session token was returned.");
        }
        localStorage.setItem(AUTH_TOKEN_KEY, token);
        setAuthToken(token);
        setCurrentUser(payload.user || null);
        setAuthForm({ username: "", email: "", password: "", username_or_email: "" });
        setNotice({ type: "success", text: "Logged in successfully." });
        await refreshAll(filters);
      }
    } catch (error) {
      setNotice({ type: "error", text: `Authentication failed: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    try {
      await request("/api/auth/logout", { method: "POST", headers: {} });
    } catch (_) {
      // The local session is cleared below regardless of remote state.
    } finally {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      setAuthToken("");
      setCurrentUser(null);
      setBusy(false);
      setNotice({ type: "success", text: "Logged out." });
      await loadDashboard(filters);
    }
  }

  function goToPage(pageId) {
    const isVisible = visiblePageConfig.some((page) => page.id === pageId);
    if (!isVisible) {
      return;
    }

    window.location.hash = pageId;
    setActivePage(pageId);
    setMobileNavOpen(false);
  }

  function goToAuthPanel() {
    window.location.hash = "concerts";
    setActivePage("concerts");
    setShowAuthPanel(true);
    setMobileNavOpen(false);
    window.setTimeout(() => {
      const node = document.getElementById("auth-panel");
      if (node) {
        node.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 80);
  }

  function applySearchSuggestion(suggestion) {
    const nextFilters = { ...filters };
    if (suggestion.type === "performer") {
      if (!(nextFilters.performer_ids || []).includes(suggestion.id)) {
        nextFilters.performer_ids = [...(nextFilters.performer_ids || []), suggestion.id];
      }
    } else if (suggestion.type === "work") {
      if (!(nextFilters.work_ids || []).includes(suggestion.id)) {
        nextFilters.work_ids = [...(nextFilters.work_ids || []), suggestion.id];
      }
    } else if (suggestion.type === "venue") {
      if (!(nextFilters.venue_ids || []).includes(suggestion.id)) {
        nextFilters.venue_ids = [...(nextFilters.venue_ids || []), suggestion.id];
      }
    }
    setFilters(nextFilters);
    setShowSearchSuggestions(false);
    setSearchSuggestions([]);
    setActiveSuggestionIndex(-1);
    void loadDashboard(nextFilters);
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

  async function saveNotificationProfile(event) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);

    try {
      const payload = await request("/api/notifications/profile", {
        method: "PUT",
        body: JSON.stringify({
          notifications_enabled: Boolean(notificationProfile.notifications_enabled),
          notification_email: notificationProfile.notification_email || null,
        }),
      });
      setNotificationProfile({ ...emptyNotificationProfile, ...(payload.profile || {}) });
      setNotice({ type: "success", text: "Notification profile saved." });
    } catch (error) {
      setNotice({ type: "error", text: `Notification profile could not be saved: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function runScopedScrape() {
    if (!canManageSystemSettings) {
      setNotice({ type: "error", text: "Only admins can run scrapes." });
      return;
    }

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
    if (!canManageSystemSettings) {
      setNotice({ type: "error", text: "Only admins can delete concerts." });
      return;
    }

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
    if (!canManageSystemSettings) {
      setNotice({ type: "error", text: "Only admins can delete concerts." });
      return;
    }

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
    if (!canManageSystemSettings) {
      setNotice({ type: "error", text: "Only admins can delete concerts." });
      return;
    }

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

  function shouldApplyGlobally(itemId) {
    return Boolean(applyGloballyFlags[itemId]);
  }

  async function resolveWithCandidate(itemId, candidateId) {
    setBusy(true);
    setNotice(null);

    try {
      const payload = await request(`/api/resolution/unresolved/${itemId}`, {
        method: "POST",
        body: JSON.stringify({
          action: "accept_candidate",
          candidate_id: candidateId,
          value: "",
          reason: "",
          apply_globally: shouldApplyGlobally(itemId),
        }),
      });
      const batchCount = Number(payload?.batch_count || 1);
      setNotice({
        type: "success",
        text: `Accepted candidate #${candidateId}${batchCount > 1 ? ` for ${batchCount} entries` : ""}.`,
      });
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
      const payload = await request(`/api/resolution/unresolved/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action: "create_new",
          candidate_id: null,
          value,
          reason: "",
          apply_globally: shouldApplyGlobally(item.id),
        }),
      });
      setNewEntityDrafts((previous) => ({ ...previous, [item.id]: "" }));
      const batchCount = Number(payload?.batch_count || 1);
      setNotice({
        type: "success",
        text: `Created new ${item.entity_type} entity${batchCount > 1 ? ` and applied to ${batchCount} entries` : ""}.`,
      });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not create entity: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function rejectUnresolved(item) {
    const topCandidate = item.candidates && item.candidates.length > 0 ? item.candidates[0].id : null;
    const reasonKey = `u-${item.id}`;
    const reason = (reviewReasons[reasonKey] || "").trim();

    setBusy(true);
    setNotice(null);

    try {
      const payload = await request(`/api/resolution/unresolved/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action: "reject",
          candidate_id: topCandidate,
          value: "",
          reason,
          apply_globally: shouldApplyGlobally(item.id),
        }),
      });
      setReviewReasons((previous) => ({ ...previous, [reasonKey]: "" }));
      const batchCount = Number(payload?.batch_count || 1);
      setNotice({
        type: "success",
        text: `Rejected unresolved item #${item.id}${batchCount > 1 ? ` across ${batchCount} entries` : ""}.`,
      });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not reject unresolved item: ${error.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function skipUnresolved(item) {
    setBusy(true);
    setNotice(null);

    try {
      const payload = await request(`/api/resolution/unresolved/${item.id}`, {
        method: "POST",
        body: JSON.stringify({
          action: "skip",
          candidate_id: null,
          value: "",
          reason: "",
          apply_globally: shouldApplyGlobally(item.id),
        }),
      });
      const batchCount = Number(payload?.batch_count || 1);
      setNotice({
        type: "success",
        text: `Skipped unresolved item #${item.id}${batchCount > 1 ? ` for ${batchCount} entries` : ""}.`,
      });
      await refreshAll(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Could not skip unresolved item: ${error.message}` });
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

  function renderAuthPanel() {
    if (currentUser) {
      return h(
        "section",
        { className: "panel", id: "auth-panel" },
        h(
          "div",
          { className: "panel-head" },
          h("h2", null, "Contributor Access"),
          h("p", null, "Signed-in reviewer account")
        ),
        h(
          "div",
          { className: "stack" },
          h("p", { className: "muted" }, `User: ${currentUser.username}`),
          h("p", { className: "muted" }, `Role: ${currentUser.role || "contributor"}`),
          h("p", { className: "muted" }, `Trust level: ${currentUser.trust_level}`),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                disabled: busy,
                onClick: handleLogout,
              },
              "Log out"
            )
          )
        )
      );
    }

    return h(
      "section",
      { className: "panel", id: "auth-panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "Contributor Login"),
        h("p", null, "Review actions require an authenticated account.")
      ),
      h(
        "form",
        { className: "stack", onSubmit: handleAuthSubmit },
        authMode === "signup"
          ? h(
              "div",
              { className: "fields" },
              field(
                "Username",
                h("input", {
                  type: "text",
                  value: authForm.username,
                  onChange: (event) => setAuthForm({ ...authForm, username: event.target.value }),
                  required: true,
                })
              ),
              field(
                "Email",
                h("input", {
                  type: "email",
                  value: authForm.email,
                  onChange: (event) => setAuthForm({ ...authForm, email: event.target.value }),
                  required: true,
                })
              ),
              field(
                "Password",
                h("input", {
                  type: "password",
                  value: authForm.password,
                  onChange: (event) => setAuthForm({ ...authForm, password: event.target.value }),
                  required: true,
                  minLength: 10,
                })
              )
            )
          : h(
              "div",
              { className: "fields" },
              field(
                "Username or email",
                h("input", {
                  type: "text",
                  value: authForm.username_or_email,
                  onChange: (event) => setAuthForm({ ...authForm, username_or_email: event.target.value }),
                  required: true,
                })
              ),
              field(
                "Password",
                h("input", {
                  type: "password",
                  value: authForm.password,
                  onChange: (event) => setAuthForm({ ...authForm, password: event.target.value }),
                  required: true,
                })
              )
            ),
        h(
          "div",
          { className: "actions" },
          h(
            "button",
            { className: "btn-primary", type: "submit", disabled: busy },
            authMode === "signup" ? "Create account" : "Log in"
          ),
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              onClick: () => setAuthMode(authMode === "signup" ? "login" : "signup"),
            },
            authMode === "signup" ? "Use existing account" : "Create account"
          )
        )
      )
    );
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
        notificationProfile.notifications_enabled ? "Enabled" : "Disabled",
        notificationProfile.notification_email ? `To ${notificationProfile.notification_email}` : "Recipient not configured"
      )
    );
  }

  function renderSystemSettingsPanel() {
    if (!canManageSystemSettings) {
      return h(
        "section",
        { className: "panel" },
        h(
          "div",
          { className: "panel-head" },
          h("h2", null, "System Settings"),
          h("p", null, "Admin-only area")
        ),
        h(
          "p",
          { className: "muted" },
          "SMTP and OpenRouter configuration is restricted to admin accounts."
        )
      );
    }

    return h(
      "section",
      { className: "panel" },
      h(
        "div",
        { className: "panel-head" },
        h("h2", null, "System Settings"),
          h("p", null, "Configure scheduler cadence, OpenRouter extraction, and SMTP delivery.")
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
        h("h2", null, "Triage Queue"),
        h("p", null, "Sorted by lowest confidence first. Resolve now, skip for later, or reject.")
      ),
      h(
        "p",
        { className: "muted" },
        resolutionLoading
          ? "Loading unresolved queue..."
          : `${unresolvedItems.length} triage item${unresolvedItems.length === 1 ? "" : "s"}`
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
                  h(
                    "span",
                    { className: `type-pill ${item.entity_type}` },
                    `${(item.entity_type || "unknown").toUpperCase()} · ${(item.triage_bucket || "critical").toUpperCase()}`
                  ),
                  h(
                    "span",
                    { className: "rule-tag" },
                    `${Math.round((item.confidence_score || 0) * 100)}% confidence`
                  )
                ),
                h("div", { className: "review-raw" }, item.raw_text || "(empty input)"),
                item.event_title && h("div", { className: "muted" }, item.event_title),
                h(
                  "div",
                  { className: "muted" },
                  `${item.event_date ? item.event_date : `Event #${item.event_id}`}${
                    item.source ? ` · ${item.source}` : ""
                  }`
                ),
                item.source_url
                  ? h(
                      "div",
                      { className: "review-links" },
                      h(
                        "a",
                        {
                          href: item.source_url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                        },
                        "Open source"
                      )
                    )
                  : null,
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
                  "label",
                  { className: "check" },
                  h("input", {
                    type: "checkbox",
                    checked: Boolean(applyGloballyFlags[item.id]),
                    onChange: (event) =>
                      setApplyGloballyFlags((previous) => ({ ...previous, [item.id]: event.target.checked })),
                  }),
                  "Apply decision to all similar entries"
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
                    placeholder: "Reason for reject (optional)",
                    value: reviewReasons[`u-${item.id}`] || "",
                    onChange: (event) =>
                      setReviewReasons((previous) => ({ ...previous, [`u-${item.id}`]: event.target.value })),
                  }),
                  h(
                    "button",
                    {
                      className: "btn-danger small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => rejectUnresolved(item),
                    },
                    "Reject"
                  ),
                  h(
                    "button",
                    {
                      className: "btn-ghost small-btn",
                      type: "button",
                      disabled: busy,
                      onClick: () => skipUnresolved(item),
                    },
                    "Skip"
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
      !canReviewMerges &&
        h(
          "p",
          { className: "muted" },
          "Merge decisions require a trusted or verified reviewer account."
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
                  { className: "muted" },
                  `AI confidence: ${Math.round((item.confidence || 0) * 100)}%${
                    item.llm_assessment ? ` · ${item.llm_assessment}` : ""
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
                      disabled: busy || !canReviewMerges,
                      onClick: () => updateMergeSuggestion(item, "merge"),
                    },
                    "Merge"
                  ),
                  h(
                    "button",
                    {
                      className: "btn-ghost small-btn",
                      type: "button",
                      disabled: busy || !canReviewMerges,
                      onClick: () => updateMergeSuggestion(item, "reject"),
                    },
                    "Reject"
                  ),
                  h(
                    "button",
                    {
                      className: "btn-danger small-btn",
                      type: "button",
                      disabled: busy || !canReviewMerges,
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
              role: "combobox",
              "aria-expanded": showSearchSuggestions && searchSuggestions.length > 0 ? "true" : "false",
              "aria-controls": "concert-search-suggestions",
              "aria-autocomplete": "list",
              "aria-activedescendant":
                activeSuggestionIndex >= 0 && searchSuggestions[activeSuggestionIndex]
                  ? `search-suggestion-${activeSuggestionIndex}`
                  : undefined,
              placeholder: "Name, performers, hall, program",
              value: filters.q,
              onChange: (event) => {
                setFilters({ ...filters, q: event.target.value });
                void loadSearchSuggestions(event.target.value);
              },
              onKeyDown: (event) => {
                if (!showSearchSuggestions || searchSuggestions.length === 0) {
                  return;
                }
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setActiveSuggestionIndex((previous) => (previous + 1) % searchSuggestions.length);
                  return;
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActiveSuggestionIndex((previous) =>
                    previous <= 0 ? searchSuggestions.length - 1 : previous - 1
                  );
                  return;
                }
                if (event.key === "Enter") {
                  if (activeSuggestionIndex >= 0 && searchSuggestions[activeSuggestionIndex]) {
                    event.preventDefault();
                    applySearchSuggestion(searchSuggestions[activeSuggestionIndex]);
                  }
                  return;
                }
                if (event.key === "Escape") {
                  setShowSearchSuggestions(false);
                  setActiveSuggestionIndex(-1);
                }
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
                  { className: "search-suggestions", id: "concert-search-suggestions", role: "listbox" },
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
                        id: `search-suggestion-${index}`,
                        key: `${suggestion.type}-${suggestion.id}-${index}`,
                        className: `suggestion-item suggestion-${suggestion.type} ${
                          activeSuggestionIndex === index ? "active" : ""
                        }`,
                        role: "option",
                        "aria-selected": activeSuggestionIndex === index ? "true" : "false",
                        onClick: () => {
                          applySearchSuggestion(suggestion);
                        },
                        onMouseEnter: () => setActiveSuggestionIndex(index),
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
          canManageSystemSettings
            ? h(
                "button",
                {
                  className: "btn-danger",
                  type: "button",
                  disabled: busy,
                  onClick: deleteFilteredConcerts,
                },
                busy ? "Deleting filtered..." : "Delete filtered concerts"
              )
            : null,
          canManageSystemSettings
            ? h(
                "button",
                {
                  className: "btn-danger",
                  type: "button",
                  disabled: busy,
                  onClick: deleteAllConcerts,
                },
                busy ? "Deleting all..." : "Delete ALL concerts"
              )
            : null
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
                        className: "btn-ghost small-btn",
                        type: "button",
                        onClick: () => {
                          const subject = encodeURIComponent("Concert data issue report");
                          const body = encodeURIComponent(
                            `Concert ID: ${concert.id}\nSource: ${concert.source}\nTitle: ${view.title || concert.name}\nURL: ${concert.source_url}\n\nIssue description:`
                          );
                          window.location.href = `mailto:?subject=${subject}&body=${body}`;
                        },
                      },
                      "Report issue"
                    ),
                    canManageSystemSettings
                      ? h(
                          "button",
                          {
                            className: "btn-danger small-btn",
                            type: "button",
                            disabled: busy,
                            onClick: () => deleteConcert(concert),
                          },
                          "Delete"
                        )
                      : null
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
            canManageSystemSettings
              ? h(
                  "button",
                  {
                    className: "btn-neutral",
                    type: "button",
                    disabled: busy,
                    onClick: runScopedScrape,
                  },
                  busy ? "Running scoped scrape..." : "Run scoped scrape"
                )
              : null,
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
            canManageSystemSettings
              ? h(
                  "button",
                  {
                    className: "btn-ghost",
                    type: "button",
                    onClick: () => goToPage("scrape"),
                  },
                  "Open scrape controls"
                )
              : null,
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
      ),
      renderAuthPanel()
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
    if (!currentUser) {
      return h(
        "div",
        { className: "page-grid-two" },
        renderAuthPanel(),
        h(
          "section",
          { className: "panel" },
          h(
            "div",
            { className: "panel-head" },
            h("h2", null, "Reviewer Access Required"),
            h("p", null, "Log in to work through triage and proposal queues.")
          ),
          h(
            "p",
            { className: "muted" },
            "The contributor workflow includes approve, reject, skip, and batch-apply decisions."
          )
        )
      );
    }

    return h(
      "div",
      { className: "page-grid-two" },
      renderUnresolvedPanel(),
      renderMergePanel()
    );
  }

  function renderRulesPage() {
    if (!currentUser) {
      return h(
        "div",
        { className: "page-grid-two" },
        renderAuthPanel(),
        h(
          "section",
          { className: "panel" },
          h(
            "div",
            { className: "panel-head" },
            h("h2", null, "Notification Access Required"),
            h("p", null, "Log in to create your own alert rules and delivery settings.")
          )
        )
      );
    }

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
          h("h2", null, "My Notification Profile"),
          h("p", null, "Configure delivery destination and enable or disable your personal alerts.")
        ),
        h(
          "form",
          { className: "stack", onSubmit: saveNotificationProfile },
          field(
            "Notification email",
            h("input", {
              type: "email",
              value: notificationProfile.notification_email,
              onChange: (event) =>
                setNotificationProfile({ ...notificationProfile, notification_email: event.target.value }),
            })
          ),
          h(
            "label",
            { className: "check" },
            h("input", {
              type: "checkbox",
              checked: notificationProfile.notifications_enabled,
              onChange: (event) =>
                setNotificationProfile({ ...notificationProfile, notifications_enabled: event.target.checked }),
            }),
            "Enable my notifications"
          ),
          h(
            "p",
            { className: "muted" },
            "Rules on this page apply only to your account."
          ),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              {
                className: "btn-primary",
                type: "submit",
                disabled: busy,
              },
              busy ? "Saving..." : "Save notification profile"
            )
          )
        )
      )
    );
  }

  function renderActivePage() {
    if (!currentUser) {
      return renderConcertsPage();
    }
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
        h(
          "span",
          { className: "status-badge small-badge" },
          currentUser
            ? `${String(currentUser.role || "contributor").toUpperCase()} · ${currentUser.trust_level}`
            : "Contributor: signed out"
        ),
        h("div", { className: "status-note" }, `Latest sync: ${latestFetchLabel}`),
        h(
          "div",
          { className: "status-actions" },
          canManageSystemSettings
            ? h(
                "button",
                {
                  className: "btn-neutral",
                  type: "button",
                  disabled: busy,
                  onClick: runScopedScrape,
                },
                busy ? "Running scrape..." : "Run scoped scrape"
              )
            : null,
          h(
            "button",
            {
              className: "btn-ghost",
              type: "button",
              disabled: dumping,
              onClick: dumpCurrentConcerts,
            },
            dumping ? "Dumping..." : "Dump concerts"
          ),
          !currentUser
            ? h(
                "button",
                {
                  className: "btn-ghost",
                  type: "button",
                  onClick: () => {
                    if (showAuthPanel) {
                      setShowAuthPanel(false);
                      return;
                    }
                    goToAuthPanel();
                  },
                },
                showAuthPanel ? "Hide sign in" : "Sign in / Sign up"
              )
            : null
        )
      )
    ),

    notice &&
      h(
        "div",
        { className: `notice ${notice.type}`, role: "status", "aria-live": "polite" },
        h("span", null, notice.text),
        h(
          "button",
          {
            type: "button",
            className: "notice-close",
            onClick: () => setNotice(null),
            "aria-label": "Dismiss notice",
          },
          "×"
        )
      ),

    h(
      "button",
      {
        ref: mobileNavButtonRef,
        className: `hamburger ${mobileNavOpen ? "open" : ""}`,
        type: "button",
        "aria-expanded": mobileNavOpen ? "true" : "false",
        "aria-controls": "dashboard-page-nav",
        "aria-label": mobileNavOpen ? "Close navigation menu" : "Open navigation menu",
        onClick: () => setMobileNavOpen((previous) => !previous),
      },
      h("span", { className: "hamburger-line", "aria-hidden": "true" }),
      h("span", { className: "hamburger-line", "aria-hidden": "true" }),
      h("span", { className: "hamburger-line", "aria-hidden": "true" })
    ),

    mobileNavOpen ? h("button", { className: "nav-overlay", type: "button", "aria-label": "Close navigation", onClick: () => setMobileNavOpen(false) }) : null,

    !currentUser && showAuthPanel
      ? h("div", { className: "page-stack" }, renderAuthPanel())
      : null,

    h(
      "nav",
      {
        id: "dashboard-page-nav",
        ref: mobileNavRef,
        className: `page-nav ${mobileNavOpen ? "page-nav-open" : ""}`,
        "aria-label": "Dashboard pages",
      },
      h(
        "div",
        { className: "mobile-nav-header" },
        h("p", { className: "eyebrow" }, "Navigation"),
        h("div", { className: "status-note" }, `Latest sync: ${latestFetchLabel}`)
      ),
      visiblePageConfig.map((page) =>
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
      ),
      h(
        "div",
        { className: "mobile-nav-actions" },
        !currentUser
          ? h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                onClick: () => {
                  if (showAuthPanel) {
                    setShowAuthPanel(false);
                    return;
                  }
                  goToAuthPanel();
                },
              },
              showAuthPanel ? "Hide sign in" : "Sign in / Sign up"
            )
          : null
      )
    ),

    renderActivePage()
  );
}

createRoot(document.getElementById("root")).render(h(App));
