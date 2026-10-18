// Small helpers shared by the views. Elements are built with h() and
// textContent -- never innerHTML -- because job text (goals, assumptions,
// agent messages) is written by an AI and must not be able to inject markup.

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "class") {
      el.className = value;
    } else if (key in el && key !== "list") {
      el[key] = value;
    } else {
      el.setAttribute(key, value === true ? "" : value);
    }
  }
  const add = (child) => {
    if (Array.isArray(child)) return child.forEach(add);
    if (child === null || child === undefined || child === false) return;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  };
  children.forEach(add);
  return el;
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* empty or non-JSON body */
  }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : res.statusText || "Something went wrong");
  }
  return data;
}

export function fmtTime(sec) {
  if (!Number.isFinite(sec)) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtElapsed(fromIso) {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(fromIso).getTime()) / 1000));
  return sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

export function fmtAgo(iso) {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
  return `${Math.floor(sec / 86400)} d ago`;
}

const STEP_LABELS = [
  [/^intake$/, "Understanding your request"],
  [/^resume_check$/, "Checking for earlier work"],
  [/^delegate$/, "Handing over to the specialists"],
  [/^interpret$/, "Working out what you want"],
  [/^research$/, "Finding what is trending"],
  [/^shortlist$/, "Picking the songs"],
  [/^candidate_(\d+)$/, (m) => `Getting song ${m[1]}`],
  [/^search$/, "Finding the songs"],
  [/^download_(\w+)$/, (m) => `Downloading song ${m[1]}`],
  [/^analyze_(\w+)$/, (m) => `Listening to song ${m[1]}`],
  [/^plan$/, "Planning the mix"],
  [/^approve$/, "Waiting for your OK"],
  [/^mix_(\d+)$/, (m) => `Mixing part ${m[1]}`],
  [/^smooth_check$/, "Smoothing the transitions"],
  [/^export$/, "Saving your file"],
  [/^fx_(\d+)$/, (m) => `Adding effect ${m[1]}`],
  [/^track_(\d+)$/, (m) => `Song ${m[1]}`],
  [/^transition_(\d+)_(\d+)$/, (m) => `Blending song ${m[1]} into ${m[2]}`],
  [/^report$/, "Wrapping up"],
  [/^agent_run$/, "Assistant"],
];

export function stepLabel(name) {
  for (const [re, label] of STEP_LABELS) {
    const m = name.match(re);
    if (m) return typeof label === "function" ? label(m) : label;
  }
  const spaced = name.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function humanKey(key) {
  const spaced = key.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
