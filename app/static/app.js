import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

const h = React.createElement;

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
};

function App() {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [filters, setFilters] = useState({ q: "", source: "", date_filter: "", include_maybe: false });
  const [sources, setSources] = useState([]);
  const [concerts, setConcerts] = useState([]);
  const [maybeHiddenCount, setMaybeHiddenCount] = useState(0);
  const [rules, setRules] = useState([]);
  const [settings, setSettings] = useState(emptySettings);
  const [newRule, setNewRule] = useState(emptyRule);

  const activeRuleCount = useMemo(() => rules.filter((rule) => rule.enabled).length, [rules]);
  const sourceCount = useMemo(() => sources.length, [sources]);

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

  useEffect(() => {
    loadDashboard();
  }, []);

  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
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
      if (nextFilters.date_filter) params.set("date_filter", nextFilters.date_filter);
      if (nextFilters.include_maybe) params.set("include_maybe", "true");
      const query = params.toString();
      const payload = await request(`/api/dashboard${query ? `?${query}` : ""}`, {
        headers: {},
      });

      setFilters(payload.filters || { q: "", source: "", date_filter: "", include_maybe: false });
      setSources(payload.sources || []);
      setConcerts(payload.concerts || []);
      setMaybeHiddenCount(payload.maybe_hidden_count || 0);
      setRules(payload.rules || []);
      setSettings(payload.settings || emptySettings);
    } catch (error) {
      setNotice({ type: "error", text: `Could not load dashboard data: ${error.message}` });
    } finally {
      setLoading(false);
    }
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

  async function triggerScrape() {
    setBusy(true);
    setNotice(null);

    try {
      await request("/api/scrape-now", { method: "POST", body: JSON.stringify({}) });
      setNotice({ type: "success", text: "Scrape finished and list refreshed." });
      await loadDashboard(filters);
    } catch (error) {
      setNotice({ type: "error", text: `Scrape failed: ${error.message}` });
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
      setNewRule(emptyRule);
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
          "Monitor scraped listings, control alert rules, and run manual updates from one modern command surface."
        )
      ),
      h(
        "div",
        { className: "status-stack" },
        h("span", { className: "status-badge" }, `${activeRuleCount} active rules`),
        h("div", { className: "status-note" }, `Latest sync: ${latestFetchLabel}`),
        h(
          "button",
          {
            className: "btn-neutral",
            type: "button",
            disabled: busy,
            onClick: triggerScrape,
          },
          busy ? "Running scrape..." : "Run scrape now"
        )
      )
    ),

    notice && h("div", { className: `notice ${notice.type}` }, notice.text),

    h(
      "section",
      { className: "metrics" },
      metricCard("Concerts", String(concerts.length), "Current filtered result"),
      metricCard("Sources", String(sourceCount), "Distinct source values"),
      metricCard("Rules", String(rules.length), `${activeRuleCount} enabled`),
      metricCard(
        "Notifications",
        settings.notifications_enabled ? "Enabled" : "Disabled",
        settings.recipient_email ? `To ${settings.recipient_email}` : "Recipient not configured"
      )
    ),

    h(
      "div",
      { className: "workspace-grid" },
      h(
        "div",
        { className: "left-column" },
        h(
          "section",
          { className: "panel" },
          h(
            "div",
            { className: "panel-head" },
            h("h2", null, "Scraper Settings"),
            h("p", null, "Update scheduler and SMTP details for notifications.")
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
                  onChange: (e) => setSettings({ ...settings, scrape_interval_minutes: e.target.value }),
                })
              ),
              field(
                "SMTP host",
                h("input", {
                  type: "text",
                  value: settings.smtp_host,
                  onChange: (e) => setSettings({ ...settings, smtp_host: e.target.value }),
                })
              ),
              field(
                "SMTP port",
                h("input", {
                  type: "number",
                  value: settings.smtp_port,
                  onChange: (e) => setSettings({ ...settings, smtp_port: e.target.value }),
                })
              ),
              field(
                "SMTP username",
                h("input", {
                  type: "text",
                  value: settings.smtp_username,
                  onChange: (e) => setSettings({ ...settings, smtp_username: e.target.value }),
                })
              ),
              field(
                "SMTP password",
                h("input", {
                  type: "password",
                  value: settings.smtp_password,
                  onChange: (e) => setSettings({ ...settings, smtp_password: e.target.value }),
                })
              ),
              field(
                "Sender email",
                h("input", {
                  type: "email",
                  value: settings.sender_email,
                  onChange: (e) => setSettings({ ...settings, sender_email: e.target.value }),
                })
              ),
              field(
                "Recipient email",
                h("input", {
                  type: "email",
                  value: settings.recipient_email,
                  onChange: (e) => setSettings({ ...settings, recipient_email: e.target.value }),
                })
              )
            ),
            h(
              "label",
              { className: "check" },
              h("input", {
                type: "checkbox",
                checked: settings.notifications_enabled,
                onChange: (e) => setSettings({ ...settings, notifications_enabled: e.target.checked }),
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
        ),

        h(
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
                  onChange: (e) => setNewRule({ ...newRule, name_contains: e.target.value }),
                })
              ),
              field(
                "Performer contains",
                h("input", {
                  type: "text",
                  value: newRule.performer_contains,
                  onChange: (e) => setNewRule({ ...newRule, performer_contains: e.target.value }),
                })
              ),
              field(
                "Program contains",
                h("input", {
                  type: "text",
                  value: newRule.program_contains,
                  onChange: (e) => setNewRule({ ...newRule, program_contains: e.target.value }),
                })
              ),
              field(
                "Date contains",
                h("input", {
                  type: "text",
                  value: newRule.date_contains,
                  onChange: (e) => setNewRule({ ...newRule, date_contains: e.target.value }),
                })
              ),
              field(
                "Time contains",
                h("input", {
                  type: "text",
                  value: newRule.time_contains,
                  onChange: (e) => setNewRule({ ...newRule, time_contains: e.target.value }),
                })
              )
            ),
            h(
              "label",
              { className: "check" },
              h("input", {
                type: "checkbox",
                checked: newRule.enabled,
                onChange: (e) => setNewRule({ ...newRule, enabled: e.target.checked }),
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
                      `name: ${display(rule.name_contains)} | performer: ${display(rule.performer_contains)} | program: ${display(
                        rule.program_contains
                      )} | date: ${display(rule.date_contains)} | time: ${display(rule.time_contains)}`
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
        )
      ),

      h(
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
            field(
              "Search",
              h("input", {
                type: "text",
                placeholder: "Name, performers, hall, program",
                value: filters.q,
                onChange: (e) => setFilters({ ...filters, q: e.target.value }),
              })
            ),
            field(
              "Source",
              h(
                "select",
                {
                  value: filters.source,
                  onChange: (e) => setFilters({ ...filters, source: e.target.value }),
                },
                h("option", { value: "" }, "All sources"),
                sources.map((source) => h("option", { key: source, value: source }, source))
              )
            ),
            field(
              "Date contains",
              h("input", {
                type: "text",
                placeholder: "for example 2026 or Apr",
                value: filters.date_filter,
                onChange: (e) => setFilters({ ...filters, date_filter: e.target.value }),
              })
            )
          ),
          h(
            "label",
            { className: "check maybe-check" },
            h("input", {
              type: "checkbox",
              checked: filters.include_maybe,
              onChange: (e) => setFilters({ ...filters, include_maybe: e.target.checked }),
            }),
            'Show tagged "maybe a concert" entries'
          ),
          h(
            "div",
            { className: "actions" },
            h(
              "button",
              { className: "btn-primary", type: "submit", disabled: loading },
              loading ? "Loading..." : "Apply filters"
            ),
            h(
              "button",
              {
                className: "btn-ghost",
                type: "button",
                disabled: loading,
                onClick: async () => {
                  const reset = { q: "", source: "", date_filter: "", include_maybe: false };
                  setFilters(reset);
                  await loadDashboard(reset);
                },
              },
              "Reset"
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
          { className: "table-wrap" },
          h(
            "table",
            null,
            h(
              "thead",
              null,
              h(
                "tr",
                null,
                h("th", null, "Source"),
                h("th", null, "Name"),
                h("th", null, "Program"),
                h("th", null, "Performers"),
                h("th", null, "Hall"),
                h("th", null, "Date"),
                h("th", null, "Time"),
                h("th", null, "Tag"),
                h("th", null, "Link")
              )
            ),
            h(
              "tbody",
              null,
              loading && concerts.length === 0
                ? h(
                    "tr",
                    null,
                    h("td", { className: "empty-row", colSpan: 9 }, "Loading concerts...")
                  )
                : concerts.length === 0
                ? h("tr", null, h("td", { className: "empty-row", colSpan: 9 }, "No concerts found for this filter."))
                : concerts.map((concert) =>
                    h(
                      "tr",
                      { key: concert.id },
                      h("td", null, h("span", { className: "source-chip" }, concert.source)),
                      h("td", null, concert.name),
                      h("td", null, display(concert.program)),
                      h("td", null, display(concert.performers)),
                      h("td", null, display(concert.hall)),
                      h("td", null, display(concert.date_normalized || concert.date)),
                      h("td", null, display(concert.time)),
                      h(
                        "td",
                        null,
                        concert.maybe_concert ? h("span", { className: "row-tag maybe" }, "maybe a concert") : "-"
                      ),
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
                    )
                  )
            )
          )
        )
      )
    )
  );
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

createRoot(document.getElementById("root")).render(h(App));
