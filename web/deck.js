import { h, api, fmtTime } from "./util.js";

// Live preview runs entirely in the browser (Web Audio) so knobs respond with
// no round trip. It approximates the server's render; Commit renders the
// real thing with the same settings.
const KNOBS = [
  { id: "low", label: "Bass", min: -12, max: 12, step: 0.5, def: 0, fmt: (v) => `${v > 0 ? "+" : ""}${v} dB` },
  { id: "mid", label: "Mids", min: -12, max: 12, step: 0.5, def: 0, fmt: (v) => `${v > 0 ? "+" : ""}${v} dB` },
  { id: "high", label: "Treble", min: -12, max: 12, step: 0.5, def: 0, fmt: (v) => `${v > 0 ? "+" : ""}${v} dB` },
  { id: "filter", label: "Muffle (low-pass)", min: 0, max: 100, step: 1, def: 100, fmt: (v) => (v >= 98 ? "off" : `${Math.round(cutoffFromSlider(v))} Hz`) },
  { id: "echo", label: "Echo", min: 0, max: 0.6, step: 0.02, def: 0, fmt: (v) => `${Math.round((v / 0.6) * 100)}%` },
  { id: "reverb", label: "Reverb", min: 0, max: 0.6, step: 0.02, def: 0, fmt: (v) => `${Math.round((v / 0.6) * 100)}%` },
];

function cutoffFromSlider(v) {
  // 0..100 -> 200 Hz..20 kHz on a log scale
  return 200 * Math.pow(100, v / 100);
}

function makeImpulse(ctx, seconds = 2, decay = 3) {
  const length = Math.floor(ctx.sampleRate * seconds);
  const buffer = ctx.createBuffer(2, length, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, decay);
  }
  return buffer;
}

function buildGraph(audio) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  const source = ctx.createMediaElementSource(audio);

  const low = new BiquadFilterNode(ctx, { type: "lowshelf", frequency: 200 });
  const mid = new BiquadFilterNode(ctx, { type: "peaking", frequency: 1000, Q: 1 });
  const high = new BiquadFilterNode(ctx, { type: "highshelf", frequency: 4000 });
  const filter = new BiquadFilterNode(ctx, { type: "lowpass", frequency: 20000, Q: 0.7 });
  source.connect(low).connect(mid).connect(high).connect(filter);

  filter.connect(ctx.destination); // dry path

  const delay = new DelayNode(ctx, { delayTime: 0.25, maxDelayTime: 1 });
  const feedback = new GainNode(ctx, { gain: 0.3 });
  const echoWet = new GainNode(ctx, { gain: 0 });
  filter.connect(delay);
  delay.connect(feedback).connect(delay);
  delay.connect(echoWet).connect(ctx.destination);

  const convolver = new ConvolverNode(ctx, { buffer: makeImpulse(ctx) });
  const reverbWet = new GainNode(ctx, { gain: 0 });
  filter.connect(convolver);
  convolver.connect(reverbWet).connect(ctx.destination);

  return {
    ctx,
    set(id, value) {
      const t = ctx.currentTime;
      if (id === "low") low.gain.setTargetAtTime(value, t, 0.02);
      if (id === "mid") mid.gain.setTargetAtTime(value, t, 0.02);
      if (id === "high") high.gain.setTargetAtTime(value, t, 0.02);
      if (id === "filter") filter.frequency.setTargetAtTime(value >= 98 ? 20000 : cutoffFromSlider(value), t, 0.02);
      if (id === "echo") echoWet.gain.setTargetAtTime(value, t, 0.02);
      if (id === "reverb") reverbWet.gain.setTargetAtTime(value, t, 0.02);
    },
  };
}

function chainFromValues(v) {
  const chain = [];
  if (v.low || v.mid || v.high) chain.push({ tool: "eq", params: { low_gain: v.low, mid_gain: v.mid, high_gain: v.high } });
  if (v.filter < 98) chain.push({ tool: "filter", params: { type: "lowpass", cutoff_hz: Math.round(cutoffFromSlider(v.filter)) } });
  if (v.echo > 0.01) chain.push({ tool: "delay", params: { time_ms: 250, feedback: 0.3, wet: v.echo } });
  if (v.reverb > 0.01) chain.push({ tool: "reverb", params: { room_size: 0.5, wet: v.reverb } });
  return chain;
}

export function deckView(root, trackId) {
  const audio = new Audio();
  audio.crossOrigin = "anonymous";
  audio.preload = "auto";
  audio.src = `/api/audio/${encodeURIComponent(trackId)}`;

  const values = Object.fromEntries(KNOBS.map((k) => [k.id, k.def]));
  let graph = null;
  let cues = [];
  let duration = 0;

  const waveInner = h("div", { class: "wave-inner", style: "position:relative;min-height:110px" });
  const waveNote = h("p", { class: "muted small hidden" }, "Could not draw the waveform for this track; playback and effects still work.");
  const canvas = h("canvas", { style: "width:100%;height:110px;display:block;cursor:pointer", "aria-label": "Waveform. Click to jump." });
  waveInner.append(canvas);
  let peaks = [];

  function drawWave() {
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = 110;
    if (!width || !peaks.length) return;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    const g = canvas.getContext("2d");
    g.scale(dpr, dpr);
    const progress = duration ? audio.currentTime / duration : 0;
    const barWidth = width / peaks.length;
    for (let i = 0; i < peaks.length; i++) {
      const barHeight = Math.max(2, peaks[i] * height * 0.95);
      g.fillStyle = i / peaks.length < progress ? "#7c5cff" : "#4b4f73";
      g.fillRect(i * barWidth, (height - barHeight) / 2, Math.max(1, barWidth - 1), barHeight);
    }
  }
  canvas.addEventListener("click", (ev) => {
    if (!duration) return;
    const rect = canvas.getBoundingClientRect();
    audio.currentTime = ((ev.clientX - rect.left) / rect.width) * duration;
  });
  window.addEventListener("resize", drawWave);

  const timeLabel = h("span", { class: "muted" }, "0:00 / 0:00");
  const playBtn = h("button", { onclick: togglePlay }, "Play");
  const cueList = h("div");
  const status = h("p", { class: "muted small" });

  function ensureGraph() {
    if (!graph) {
      try {
        graph = buildGraph(audio);
        for (const k of KNOBS) graph.set(k.id, values[k.id]);
      } catch (e) {
        status.textContent = "Live effects are not available in this browser.";
      }
    }
    if (graph && graph.ctx.state === "suspended") graph.ctx.resume();
  }

  function togglePlay() {
    ensureGraph();
    if (audio.paused) audio.play();
    else audio.pause();
  }
  audio.addEventListener("play", () => (playBtn.textContent = "Pause"));
  audio.addEventListener("pause", () => (playBtn.textContent = "Play"));
  audio.addEventListener("timeupdate", updateTime);
  audio.addEventListener("loadedmetadata", () => {
    duration = audio.duration;
    updateTime();
    renderCues();
  });
  audio.addEventListener("error", () => (status.textContent = "Could not load this track."));

  function updateTime() {
    timeLabel.textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(duration)}`;
    drawWave();
  }

  // ---- cues
  function renderCues() {
    waveInner.querySelectorAll(".cue-marker").forEach((el) => el.remove());
    if (duration) {
      for (const cue of cues) {
        waveInner.append(
          h(
            "div",
            { class: "cue-marker", style: `left:${(cue.time / duration) * 100}%`, title: cue.label, onclick: () => (audio.currentTime = cue.time) },
            h("span", {}, cue.label)
          )
        );
      }
    }
    cueList.replaceChildren(
      cues.length
        ? h(
            "ul",
            { class: "plain" },
            cues.map((cue, i) =>
              h(
                "li",
                {},
                h("a", { href: "javascript:void(0)", onclick: () => (audio.currentTime = cue.time) }, `${fmtTime(cue.time)}  ${cue.label}`),
                " ",
                h("button", { class: "secondary small", onclick: () => removeCue(i), "aria-label": `Remove ${cue.label}` }, "×")
              )
            )
          )
        : h("p", { class: "muted small" }, "No cue points yet. Press Add cue while the music plays to mark a moment.")
    );
  }

  async function saveCues() {
    try {
      await api(`/api/library/${encodeURIComponent(trackId)}/cues`, { method: "PUT", body: { cues } });
    } catch (e) {
      status.textContent = `Could not save cues: ${e.message}`;
    }
  }

  function addCue() {
    const label = window.prompt("Name this cue", `Cue ${cues.length + 1}`);
    if (label === null) return;
    cues.push({ time: Math.round(audio.currentTime * 100) / 100, label: label.trim() || `Cue ${cues.length + 1}` });
    cues.sort((a, b) => a.time - b.time);
    renderCues();
    saveCues();
  }

  function removeCue(i) {
    cues.splice(i, 1);
    renderCues();
    saveCues();
  }

  // ---- effects
  const knobEls = KNOBS.map((k) => {
    const readout = h("span", { class: "muted" }, k.fmt(k.def));
    const input = h("input", {
      type: "range",
      min: k.min,
      max: k.max,
      step: k.step,
      value: k.def,
      "aria-label": k.label,
      oninput: () => {
        values[k.id] = Number(input.value);
        readout.textContent = k.fmt(values[k.id]);
        if (graph) graph.set(k.id, values[k.id]);
      },
    });
    return { k, input, readout, el: h("div", { class: "knob" }, h("label", {}, h("span", {}, k.label), readout), input) };
  });

  function resetKnobs() {
    for (const { k, input, readout } of knobEls) {
      values[k.id] = k.def;
      input.value = k.def;
      readout.textContent = k.fmt(k.def);
      if (graph) graph.set(k.id, k.def);
    }
  }

  const commitOut = h("div");
  const commitBtn = h(
    "button",
    {
      onclick: async () => {
        const chain = chainFromValues(values);
        if (!chain.length) {
          commitOut.replaceChildren(h("p", { class: "muted small" }, "Move a knob first, then save the new version."));
          return;
        }
        commitBtn.disabled = true;
        commitOut.replaceChildren(h("p", { class: "muted small" }, "Rendering the new version…"));
        try {
          const res = await api("/api/fx/commit", { method: "POST", body: { track_id: trackId, chain } });
          commitOut.replaceChildren(
            h("p", {}, "Saved as a new version. ", h("a", { href: `#/deck/${encodeURIComponent(res.track_id)}` }, "Open it"))
          );
        } catch (e) {
          commitOut.replaceChildren(h("p", { class: "error" }, e.message));
        } finally {
          commitBtn.disabled = false;
        }
      },
    },
    "Save as new version"
  );

  // ---- export
  const exportOut = h("div");
  async function doExport(label, path, body) {
    exportOut.replaceChildren(h("p", { class: "muted small" }, `Preparing ${label}…`));
    try {
      const res = await api(path, { method: "POST", body });
      exportOut.replaceChildren(
        h("p", {}, `${label} ready: `, h("a", { href: `/api/audio/${encodeURIComponent(res.track_id)}`, download: `${res.track_id}.mp3` }, "Download"))
      );
    } catch (e) {
      exportOut.replaceChildren(h("p", { class: "error" }, e.message));
    }
  }

  root.append(
    h("h1", {}, "Deck"),
    h("p", { class: "lead muted" }, trackId),
    h(
      "div",
      { class: "card" },
      h("div", { class: "wave-wrap" }, waveInner),
      waveNote,
      h("div", { class: "row between", style: "margin-top:12px" }, h("div", { class: "row" }, playBtn, h("button", { class: "secondary", onclick: addCue }, "Add cue"), timeLabel)),
      cueList,
      status
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Sound"),
      h("p", { class: "muted small" }, "Move the knobs while it plays to hear the change instantly. The saved version is rendered at full quality."),
      h("div", { class: "knobs" }, knobEls.map((e) => e.el)),
      h("div", { class: "row", style: "margin-top:16px" }, commitBtn, h("button", { class: "secondary", onclick: resetKnobs }, "Reset")),
      commitOut
    ),
    h(
      "div",
      { class: "card" },
      h("h2", {}, "Export"),
      h(
        "div",
        { class: "row" },
        h("button", { onclick: () => doExport("MP3", "/api/export/mp3", { track_id: trackId }) }, "MP3"),
        h("button", { class: "secondary", onclick: () => doExport("Instagram clip", "/api/export/short_clip", { track_id: trackId, duration: 30, format: "ig" }) }, "Instagram clip"),
        h("button", { class: "secondary", onclick: () => doExport("TikTok clip", "/api/export/short_clip", { track_id: trackId, duration: 30, format: "tiktok" }) }, "TikTok clip"),
        h("button", { class: "secondary", onclick: () => doExport("Shorts clip", "/api/export/short_clip", { track_id: trackId, duration: 30, format: "shorts" }) }, "Shorts clip")
      ),
      exportOut,
      h("p", { class: "muted small" }, "Clips are 30 seconds, centered on the most energetic part of the track.")
    )
  );

  api(`/api/library/${encodeURIComponent(trackId)}/cues`)
    .then((data) => {
      cues = data.cues || [];
      renderCues();
    })
    .catch(() => renderCues());

  api(`/api/library/${encodeURIComponent(trackId)}/peaks`)
    .then((data) => {
      peaks = data.peaks;
      drawWave();
    })
    .catch(() => waveNote.classList.remove("hidden"));

  return () => {
    window.removeEventListener("resize", drawWave);
    audio.pause();
    if (graph) graph.ctx.close();
  };
}
