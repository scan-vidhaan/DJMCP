import { h, api, fmtElapsed, fmtAgo, stepLabel, humanKey } from "./util.js";
import { deckView } from "./deck.js";

const root = document.getElementById("app");
let timers = [];

function every(fn, ms) {
  fn();
  timers.push(setInterval(fn, ms));
}

function stopTimers() {
  timers.forEach(clearInterval);
  timers = [];
}

const EXAMPLES = [
  "Make a mashup of the trending Bollywood songs",
  "Create a 20 minute chill house set",
  "Mix two upbeat Hindi songs into one smooth track",
  "Put the vocals of Kesariya over a trending Punjabi beat",
];

const STATUS_LABEL = {
  open: "Working",
  waiting_input: "Needs your input",
  done: "Done",
  failed: "Stopped",
};

function statusPill(status) {
  const cls = status === "open" ? "working" : status;
  return h("span", { class: `pill ${cls}` }, STATUS_LABEL[status] || status);
}

// ---------------------------------------------------------------- home

async function homeView() {
  const textarea = h("textarea", {
    placeholder: "Example: make a mashup of the trending Bollywood songs",
    "aria-label": "What would you like to make?",
  });
  const autopilot = h("input", { type: "checkbox", id: "autopilot" });
  try {
    autopilot.checked = localStorage.getItem("djmcp.autopilot") === "1";
  } catch (_) {
    /* storage unavailable */
  }
  const error = h("p", { class: "error hidden" });
  const start = h("button", { onclick: submit }, "Make it");

  async function submit() {
    const text = textarea.value.trim();
    if (!text) {
      error.textContent = "Tell me what you would like to make first.";
      error.classList.remove("hidden");
      return;
    }
    start.disabled = true;
    error.classList.add("hidden");
    try {
      localStorage.setItem("djmcp.autopilot", autopilot.checked ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    try {
      const { job_id } = await api("/api/requests", { method: "POST", body: { text, autopilot: autopilot.checked } });
      location.hash = `#/job/${job_id}`;
    } catch (e) {
      error.textContent = e.message;
      error.classList.remove("hidden");
      start.disabled = false;
    }
  }

  const prefill = new URLSearchParams(location.hash.split("?")[1] || "").get("text");
  if (prefill) textarea.value = prefill;

  const banner = h("div");
  api("/api/system/check")
    .then((check) => {
      if (check.available) return;
      banner.append(
        h(
          "div",
          { class: "banner" },
          h("strong", {}, "One-time setup needed. "),
          check.error,
          " Until then you can still open finished mixes in My mixes."
        )
      );
    })
    .catch(() => {});

  const unfinished = h("div");
  const recent = h("div");

  root.append(
    h("h1", {}, "What would you like to make?"),
    h("p", { class: "lead" }, "Describe it in your own words. I will find the songs, mix them and let you know if I need anything."),
    banner,
    h(
      "div",
      { class: "card" },
      textarea,
      h(
        "div",
        { class: "chips" },
        EXAMPLES.map((ex) =>
          h("button", { class: "chip secondary", type: "button", onclick: () => (textarea.value = ex) }, ex)
        )
      ),
      h(
        "div",
        { class: "row between" },
        h(
          "label",
          { class: "switch", for: "autopilot" },
          autopilot,
          h("span", {}, "Autopilot ", h("span", { class: "muted small" }, "(do not ask me questions, just choose for me)"))
        ),
        start
      ),
      error
    ),
    unfinished,
    recent
  );

  try {
    const open = await api("/api/state/jobs?open=true");
    if (open.length) {
      unfinished.append(
        h(
          "div",
          { class: "card" },
          h("h2", {}, "Unfinished"),
          h(
            "table",
            {},
            h("tbody", {}, open.map((j) => jobRow(j, j.status === "waiting_input" ? "Answer" : "Open")))
          )
        )
      );
    }
    const done = await api("/api/state/jobs?open=false");
    if (done.length) {
      recent.append(
        h(
          "div",
          { class: "card" },
          h("h2", {}, "Recently finished"),
          h("table", {}, h("tbody", {}, done.slice(0, 5).map((j) => jobRow(j, "Open"))))
        )
      );
    }
  } catch (_) {
    /* lists are a convenience */
  }
}

function jobRow(job, label) {
  return h(
    "tr",
    {},
    h("td", {}, job.goal),
    h("td", {}, statusPill(job.status)),
    h("td", { class: "muted small" }, fmtAgo(job.updated_at)),
    h("td", {}, h("a", { href: `#/job/${job.job_id}` }, label))
  );
}

// ----------------------------------------------------------------- job

function renderPlan(plan) {
  if (plan === null || plan === undefined) return null;
  if (typeof plan === "string") return h("p", {}, plan);
  const rows = Object.entries(plan).map(([key, value]) => {
    let shown;
    if (Array.isArray(value)) {
      shown = h("ul", { class: "plain" }, value.map((v) => h("li", {}, typeof v === "object" ? JSON.stringify(v) : v)));
    } else if (value && typeof value === "object") {
      shown = JSON.stringify(value);
    } else {
      shown = String(value);
    }
    return h("div", {}, h("strong", {}, humanKey(key), ": "), shown);
  });
  return h("div", {}, rows);
}

function questionCard(jobId, question) {
  const hasOptions = question.options && question.options.length;
  let getAnswer;
  let controls;
  if (hasOptions) {
    const name = `q-${question.key}`;
    const inputs = question.options.map((opt) =>
      h("input", { type: "radio", name, value: opt, checked: opt === question.default })
    );
    if (!inputs.some((i) => i.checked)) inputs[0].checked = true;
    controls = h(
      "div",
      { class: "options", role: "radiogroup" },
      inputs.map((input) => h("label", { class: "option" }, input, h("span", {}, input.value)))
    );
    getAnswer = () => (inputs.find((i) => i.checked) || inputs[0]).value;
  } else {
    const input = h("input", { type: "text", value: question.default || "" });
    controls = h("div", { class: "options" }, input);
    getAnswer = () => input.value;
  }
  const error = h("p", { class: "error hidden" });
  const button = h(
    "button",
    {
      onclick: async () => {
        button.disabled = true;
        try {
          await api(`/api/requests/${jobId}/answer`, { method: "POST", body: { key: question.key, answer: getAnswer() } });
        } catch (e) {
          error.textContent = e.message;
          error.classList.remove("hidden");
          button.disabled = false;
        }
      },
    },
    "Continue"
  );
  return h("div", { class: "card accent" }, h("h2", {}, question.prompt), controls, button, error);
}

async function jobView(jobId) {
  const header = h("div");
  const body = h("div");
  const logBox = h("div", { class: "log", role: "log" });
  const logCard = h("details", { class: "card" }, h("summary", {}, "What the assistant is doing"), logBox);
  root.append(header, body, logCard);

  let signature = "";
  let logNext = 0;
  let running = false;
  let current = null;
  const elapsed = h("span", { class: "muted small" });

  async function tick() {
    let job;
    try {
      job = await api(`/api/state/jobs/${jobId}`);
      const log = await api(`/api/requests/${jobId}/log?since=${logNext}`);
      running = log.running;
      logNext = log.next;
      for (const ev of log.events) {
        if (ev.kind === "say") logBox.append(h("div", {}, ev.text));
        else if (ev.kind === "tool") logBox.append(h("div", { class: "small" }, `→ ${stepLabel(ev.name.replace(/^mcp__djmcp__/, ""))}`));
        else if (ev.kind === "result" && ev.error) logBox.append(h("div", { class: "error" }, ev.text));
      }
      if (log.events.length) logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {
      body.replaceChildren(h("div", { class: "card bad" }, h("p", { class: "error" }, e.message)));
      return;
    }
    current = job;
    elapsed.textContent = job.status === "open" || job.status === "waiting_input" ? `Started ${fmtElapsed(job.created_at)} ago` : "";

    const sig = JSON.stringify([job, running]);
    if (sig === signature) return;
    signature = sig;
    render(job);
  }

  function render(job) {
    if (job.status === "done" && job.result && job.result.continued_job) {
      location.hash = `#/job/${job.result.continued_job}`; // the earlier job carries on
      return;
    }
    header.replaceChildren(
      h("h1", {}, job.goal),
      h("div", { class: "row", style: "margin-bottom:18px" }, statusPill(job.status), elapsed)
    );

    const parts = [];

    if (job.status === "waiting_input" && job.question) parts.push(questionCard(jobId, job.question));

    if (job.status === "failed") {
      parts.push(
        h(
          "div",
          { class: "card bad" },
          h("h2", {}, "This stopped before it finished"),
          h("p", {}, job.error || "Something went wrong."),
          h(
            "div",
            { class: "row" },
            h("button", { onclick: () => api(`/api/requests/${jobId}/resume`, { method: "POST" }).then(() => (signature = "")) }, "Resume"),
            h("a", { class: "btn secondary", href: `#/?text=${encodeURIComponent(job.goal)}` }, "Start over")
          )
        )
      );
    }

    if (job.status === "done" && job.result && job.result.track_id) {
      const id = job.result.track_id;
      parts.push(
        h(
          "div",
          { class: "card accent" },
          h("h2", {}, "Your mix is ready"),
          h("audio", { controls: true, src: `/api/audio/${id}`, preload: "metadata" }),
          h(
            "div",
            { class: "row" },
            h("a", { class: "btn", href: `/api/audio/${id}`, download: `${id}.mp3` }, "Download MP3"),
            h("a", { class: "btn secondary", href: `#/deck/${id}` }, "Fine-tune in the deck"),
            h("a", { class: "btn secondary", href: `#/?text=${encodeURIComponent("Make a variation of: " + job.goal)}` }, "Make a variation")
          )
        )
      );
    }

    const plan = renderPlan(job.plan);
    if (plan) parts.push(h("div", { class: "card" }, h("h2", {}, "The plan"), plan));

    if (job.assumptions.length) {
      parts.push(
        h(
          "div",
          { class: "card" },
          h("h2", {}, "Choices I made for you"),
          h("ul", { class: "plain" }, job.assumptions.map((a) => h("li", {}, a)))
        )
      );
    }

    const steps = job.steps.filter((s) => s.step !== "agent_run");
    const active = job.status === "open";
    const showNext = active && job.next_step && !steps.some((s) => s.step === job.next_step);
    const stuck = job.status === "open" && !running && Date.now() - new Date(job.updated_at).getTime() > 120000;
    if (steps.length || showNext || active) {
      parts.push(
        h(
          "div",
          { class: "card" },
          h("h2", {}, "Progress"),
          h(
            "ul",
            { class: "steps" },
            steps.map((s, i) => {
              const isActive = active && s.status !== "done" && s.status !== "failed";
              return h(
                "li",
                {},
                h("span", { class: `dot ${isActive ? "active" : s.status}` }),
                h("span", {}, stepLabel(s.step)),
                s.artifacts && (s.artifacts.title || s.artifacts.summary)
                  ? h("span", { class: "muted small" }, s.artifacts.title || s.artifacts.summary)
                  : null
              );
            }),
            showNext ? h("li", {}, h("span", { class: "dot active" }), h("span", {}, stepLabel(job.next_step))) : null,
            active && !steps.length && !showNext
              ? h("li", {}, h("span", { class: "dot active" }), h("span", {}, "Getting started"))
              : null
          ),
          active ? h("p", { class: "muted small" }, "Mixing separates vocals from instruments, which can take a few minutes per song.") : null,
          stuck
            ? h(
                "p",
                {},
                "This looks paused. ",
                h("button", { class: "small", onclick: () => api(`/api/requests/${jobId}/resume`, { method: "POST" }).then(() => (signature = "")) }, "Resume")
              )
            : null
        )
      );
    }

    if (job.status === "open" || job.status === "waiting_input") {
      parts.push(
        h(
          "p",
          {},
          h("button", { class: "secondary small", onclick: () => confirm("Stop this job?") && api(`/api/requests/${jobId}/cancel`, { method: "POST" }) }, "Stop")
        )
      );
    }

    body.replaceChildren(...parts);
  }

  every(tick, 1500);
}

// ------------------------------------------------------------- library

async function libraryView() {
  root.append(h("h1", {}, "My mixes"), h("p", { class: "lead" }, "Everything you have made. Open one to fine-tune or download it."));
  const holder = h("div", { class: "card" }, "Loading…");
  root.append(holder);
  try {
    const items = await api("/api/library/processed");
    if (!items.length) {
      holder.replaceChildren(h("p", { class: "muted" }, "Nothing here yet. "), h("a", { href: "#/" }, "Make your first mix"));
      return;
    }
    holder.replaceChildren(
      h(
        "table",
        {},
        h("thead", {}, h("tr", {}, ["Mix", "Tempo", "Key", "Made for", ""].map((t) => h("th", {}, t)))),
        h(
          "tbody",
          {},
          items.map((t) =>
            h(
              "tr",
              {},
              h("td", {}, t.track_id.length > 48 ? `${t.track_id.slice(0, 48)}…` : t.track_id),
              h("td", {}, t.bpm ? `${Math.round(t.bpm)} BPM` : "–"),
              h("td", {}, t.camelot || t.key || "–"),
              h("td", { class: "muted small" }, t.job ? t.job.goal : "–"),
              h("td", {}, h("a", { href: `#/deck/${t.track_id}` }, "Open"))
            )
          )
        )
      )
    );
  } catch (e) {
    holder.replaceChildren(h("p", { class: "error" }, e.message));
  }
}

// -------------------------------------------------------------- router

let cleanup = null;

async function route() {
  stopTimers();
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  root.replaceChildren();
  const path = location.hash.replace(/^#/, "").split("?")[0] || "/";
  const parts = path.split("/").filter(Boolean);
  window.scrollTo(0, 0);
  if (parts[0] === "job" && parts[1]) return jobView(parts[1]);
  if (parts[0] === "deck" && parts[1]) {
    const stop = await deckView(root, decodeURIComponent(parts[1]));
    if (location.hash.includes(parts[1])) cleanup = stop;
    else stop();
    return;
  }
  if (parts[0] === "library") return libraryView();
  return homeView();
}

window.addEventListener("hashchange", route);
route();

// Tell the server this page is open (so agents do not open a second tab) and
// follow an agent that asks us to jump to a job.
let lastFocusSeq = null;
setInterval(async () => {
  try {
    await api("/api/ui/ping", { method: "POST" });
    const status = await api("/api/ui/status");
    if (lastFocusSeq !== null && status.focus_seq !== lastFocusSeq && status.focus_job) {
      location.hash = `#/job/${status.focus_job}`;
    }
    lastFocusSeq = status.focus_seq;
  } catch (_) {
    /* server restarting; try again next beat */
  }
}, 4000);
api("/api/ui/ping", { method: "POST" }).catch(() => {});
