import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import * as h3 from "h3-js";
import { createClient } from "@supabase/supabase-js";

// ─── Supabase config ──────────────────────────────────────────────────────────
const SUPABASE_URL = "https://mmjusghgeedycrrfdejg.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1tanVzZ2hnZWVkeWNycmZkZWpnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTQwMjM2MCwiZXhwIjoyMDkwOTc4MzYwfQ.iPNrIQbKZy3seMcP6dY76uRg-BAYFkGEMDhoN8o1ng8";

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const H3_RES = 8;
const CITIES = ["Chennai", "Surat", "Bangalore", "Mumbai", "Hyderabad", "Pune", "Kolkata"];
const CITIES_LOOP = [...CITIES, CITIES[0]];

// ─── Color ramp (for events only) ────────────────────────────────────────────
function getEventColor(param) {
  param = Math.max(0, Math.min(1, param));
  if (param < 0.3) {
    const x = Math.pow(param / 0.3, 2);
    return `rgb(0,${Math.round(120 + 135 * x)},0)`;
  } else if (param < 0.5) {
    const x = Math.pow((param - 0.3) / 0.2, 2);
    return `rgb(255,${Math.round(140 - 90 * x)},0)`;
  } else {
    const x = Math.pow((param - 0.5) / 0.5, 2);
    return `rgb(255,${Math.round(50 * (1 - x))},0)`;
  }
}

// ─── H3 helpers ───────────────────────────────────────────────────────────────
function boundsToH3Cells(bounds) {
  const polygon = [
    [bounds.getNorth(), bounds.getWest()],
    [bounds.getNorth(), bounds.getEast()],
    [bounds.getSouth(), bounds.getEast()],
    [bounds.getSouth(), bounds.getWest()],
    [bounds.getNorth(), bounds.getWest()],
  ];
  return h3.polygonToCells(polygon, H3_RES);
}

// ─── Supabase fetchers ────────────────────────────────────────────────────────
async function fetchEventsForCells(cells, cachedCells) {
  const toFetch = cells.filter((c) => !cachedCells.has(c));
  if (!toFetch.length) return [];

  const CHUNK_SIZE = 100;
  const chunks = [];
  for (let i = 0; i < toFetch.length; i += CHUNK_SIZE) {
    chunks.push(toFetch.slice(i, i + CHUNK_SIZE));
  }

  const results = await Promise.all(
    chunks.map(async (chunk) => {
      const { data, error } = await supabase
        .from("hexagons")
        .select("h3_index, location, parameters, event_id")
        .in("h3_index", chunk);
      if (error) { console.error("[supabase] roaddefects:", error); return []; }
      return data || [];
    })
  );

  return results.flat();
}

async function fetchFramesForEvents(eventIds) {
  if (!eventIds.length) return {};

  const { data: events, error: evErr } = await supabase
    .from("imu_events")
    .select("imu_events_id, session_id, start_time, end_time")
    .in("imu_events_id", eventIds);
  if (evErr) { console.error("[supabase] imu_events:", evErr); return {}; }

  const map = {};
  await Promise.all(
    (events || []).map(async (ev) => {
      const startMs = new Date(ev.start_time).getTime();
      const endMs   = new Date(ev.end_time).getTime();

      const { data: frames, error: frErr } = await supabase
        .from("frames")
        .select("frame_id, session_id, timestamp_ms, image_path")
        .eq("session_id", ev.session_id)
        .gte("timestamp_ms", startMs - 3500)
        .lte("timestamp_ms", endMs + 1000)
        .order("timestamp_ms", { ascending: true })
        .limit(8);
      if (frErr) { console.error("[supabase] frames:", frErr); return; }

      map[ev.imu_events_id] = (frames || []).map(f => ({
        url: f.image_path,
        timestamp_ms: f.timestamp_ms,
      }));
    })
  );
  return map;
}

async function reverseGeocodeCityLocality(lat, lon) {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=16`,
      { headers: { "Accept-Language": "en" } }
    );
    const data = await res.json();
    const a = data.address || {};
    const city = a.city || a.town || a.village || a.county || a.state || data.display_name?.split(",")[0] || "Unknown";
    const locality = a.suburb || a.neighbourhood || a.locality || a.road || a.residential || null;
    return { city, locality };
  } catch (e) {
    console.error("[reverse-geocode]", e);
    return { city: "Unknown", locality: null };
  }
}

const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000;

function formatISTDate(utcDateInput) {
  const utcMs = new Date(utcDateInput).getTime();
  const ist = new Date(utcMs + IST_OFFSET_MS);
  const pad = (n) => String(n).padStart(2, "0");
  return `${ist.getUTCFullYear()}-${pad(ist.getUTCMonth() + 1)}-${pad(ist.getUTCDate())} ` +
         `${pad(ist.getUTCHours())}:${pad(ist.getUTCMinutes())} IST`;
}

function applyWatermark(url, timestamp_ms, rotation = 90) {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const rad = (rotation * Math.PI) / 180;
      const sin = Math.abs(Math.sin(rad));
      const cos = Math.abs(Math.cos(rad));
      const W = Math.round(img.width * cos + img.height * sin);
      const H = Math.round(img.width * sin + img.height * cos);

      const canvas = document.createElement("canvas");
      canvas.width  = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d");
      ctx.translate(W / 2, H / 2);
      ctx.rotate(rad);
      ctx.drawImage(img, -img.width / 2, -img.height / 2);
      ctx.setTransform(1, 0, 0, 1, 0, 0);

      const dt = new Date(timestamp_ms);
      const pad = (n) => String(n).padStart(2, "0");
      const dtStr =
        `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())} ` +
        `${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}.` +
        String(dt.getMilliseconds()).padStart(3, "0");
      const lines = [dtStr, "captured by vehnicate"];

      let fontSize = Math.round(H * 0.035);
      const minFont = 12;
      const maxLineW = W * 0.45;
      ctx.font = `${fontSize}px monospace`;
      while (fontSize > minFont) {
        const widest = Math.max(...lines.map(l => ctx.measureText(l).width));
        if (widest <= maxLineW) break;
        fontSize -= 2;
        ctx.font = `${fontSize}px monospace`;
      }

      const lineH   = fontSize * 1.35;
      const padding = 20;
      const offsets = [[2,2],[-2,-2],[2,-2],[-2,2],[0,2],[2,0],[-2,0],[0,-2]];

      ctx.font      = `${fontSize}px monospace`;
      ctx.textBaseline = "top";

      lines.forEach((line, i) => {
        const y = padding + i * lineH;
        ctx.fillStyle = "rgba(0,0,0,0.9)";
        offsets.forEach(([ox, oy]) => ctx.fillText(line, padding + ox, y + oy));
        ctx.fillStyle = "white";
        ctx.fillText(line, padding, y);
      });

      resolve(canvas.toDataURL("image/jpeg", 0.88));
    };
    img.onerror = () => resolve(url);
    img.src = url;
  });
}

async function buildImagePopupHTML(row, param, frames) {
  const color   = getEventColor(param);
  const lastEid = row.event_id[row.event_id.length - 1];
  const tsStr   = frames.length > 0
    ? (() => {
        const d = new Date(frames[0].timestamp_ms);
        const p = (n) => String(n).padStart(2,"0");
        return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} `+
              `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
      })()
    : null;

  const processed = await Promise.all(
    frames.slice(0, 8).map(f => applyWatermark(f.url, f.timestamp_ms))
  );

  let html = `<div style="font-family:monospace;max-width:500px;">`;
  html += `
    <div style="border-left:3px solid ${color};padding:8px 12px;
      margin-bottom:10px;background:rgba(255,255,255,0.04);border-radius:0 6px 6px 0;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        ${tsStr
          ? `<span style="font-size:11px;color:#ccc;">${tsStr}</span>`
          : `<span style="font-size:11px;color:#ccc;">Event ${lastEid}</span>`}
        <span style="font-size:12px;font-weight:700;color:${color};
          background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:99px;">
          ⬡ ${param.toFixed(3)}
        </span>
      </div>`;

  if (processed.length > 0) {
    html += `<div style="display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;
      scrollbar-width:thin;scrollbar-color:#fff transparent;">`;
    for (const dataUrl of processed) {
      html += `<img src="${dataUrl}" style="height:120px;border-radius:6px;flex-shrink:0;
        object-fit:cover;cursor:pointer;" onclick="window.open('${dataUrl}','_blank')"/>`;
    }
    html += `</div>`;
  } else {
    html += `<div style="font-size:11px;color:#555;font-style:italic;">No frames</div>`;
  }

  html += `</div></div>`;
  return html;
}

function buildHoverHTML(row, param) {
  const color = getEventColor(param);
  const lastEid = row.event_id[row.event_id.length - 1];
  return `
    <div style="font-family:monospace;font-size:12px;min-width:180px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="color:#ccc;font-weight:600;">Event ID: </span>
        <span style="color:#fff;">${lastEid}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="color:#ccc;font-weight:600;">Parameter</span>
        <span style="font-weight:700;color:${color};">${param.toFixed(3)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="color:#ccc;font-weight:600;">Detections</span>
        <span style="color:#a855f7;font-weight:700;">${row.parameters.length}</span>
      </div>
    </div>`;
}

// ─── Styles ───────────────────────────────────────────────────────────────────
// BUBBLE COLOR LOGIC:
//   • Dark theme  → bubbles are WHITE / light-surface (opposite of the dark map)
//   • Light theme → bubbles are DARK / near-black (opposite of the light map)
// The .theme-light selector on #rdm-container drives the flip.
const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Ledger&display=swap');

  #rdm-container {
    position: absolute;
    inset: 0;
    overflow: hidden;
  }

  #rdm-map {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }

  /* Light theme tile filter — transitions smoothly on the pane itself */
  #rdm-map .leaflet-tile-pane {
    transition: filter 0.75s ease;
  }
  #rdm-container.theme-light #rdm-map .leaflet-tile-pane {
    filter: invert(1) hue-rotate(180deg) brightness(1.04) contrast(0.92) saturate(0.85);
  }

  /* ── Iris transition layer ─────────────────────────────────────────────────
     A clip-path circle that grows from the toggle button outward. It carries
     only a very soft radial glow — not a solid colour — so the actual map
     tiles show through as they cross-fade via their own filter transition.
     The iris is a graceful eye-catcher, not a curtain. */
  #rdm-iris-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 8000;
    overflow: hidden;
    clip-path: circle(0% at 50% 50%);
    will-change: clip-path;
  }

  /* ── Watermark ── */
  #rdm-watermark {
    position: absolute;
    bottom: 40px;
    right: 50px;
    font-family: 'Ledger', serif;
    font-size: 24px;
    color: white;
    letter-spacing: 1px;
    pointer-events: none;
    z-index: 1000;
    transition: color 0.3s ease;
  }
  .theme-light #rdm-watermark {
    color: #1a1a22;
  }

  /* ═══════════════════════════════════════════════════════════════
     BUBBLE BASE — dark theme: white/frosted bubbles
     ═══════════════════════════════════════════════════════════════ */

  /* ── Road Scout Badge ── */
  #rdm-badge {
    position: absolute;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 24px;
    border-radius: 22px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    z-index: 1000;
    pointer-events: none;
    white-space: nowrap;
    transition: background 0.3s ease, border-color 0.3s ease;
  }
  #rdm-badge span {
    font-size: 16px;
    font-weight: 600;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  /* ── Last-detected badge ── */
  #rdm-last-detected {
    position: absolute;
    top: 64px;
    left: 50%;
    transform: translateX(-50%);
    padding: 6px 18px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.15);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.22);
    z-index: 999;
    pointer-events: none;
    white-space: nowrap;
    font-size: 11.5px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.85);
    letter-spacing: 0.2px;
    transition: background 0.3s ease, border-color 0.3s ease, color 0.3s ease;
  }
  #rdm-last-detected b {
    color: #fff;
    font-weight: 700;
  }

  /* ── Search wrapper ── */
  #rdm-search-wrap {
    position: absolute;
    top: 20px;
    left: 20px;
    width: 340px;
    z-index: 1000;
  }

  #rdm-search-box {
    width: 100%;
    height: 48px;
    display: flex;
    align-items: center;
    padding-left: 58px;
    padding-right: 16px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(18px);
    border-radius: 20px;
    position: relative;
    box-shadow: 0 8px 30px rgba(0,0,0,0.25);
    transition: background 0.3s ease;
  }

  /* Gradient border */
  #rdm-search-box::before {
    content: "";
    position: absolute;
    inset: -2px;
    border-radius: 22px;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    pointer-events: none;
    z-index: 0;
  }

  /* Logo — dark theme uses the dark-bg logo (white icon) */
  #rdm-search-box::after {
    content: "";
    position: absolute;
    left: 5px;
    width: 46px;
    height: 46px;
    background: url('/hn-logo_light.png') no-repeat center;
    background-size: contain;
    border-radius: 14px;
    z-index: 1;
    transition: background-image 0.3s ease;
  }

  #rdm-search-input {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    color: white;
    font-size: 14px;
    font-weight: 500;
    caret-color: #a855f7;
    position: relative;
    z-index: 2;
  }

  #rdm-placeholder {
    position: absolute;
    left: 58px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
    color: rgba(255, 255, 255, 0.55);
    pointer-events: none;
    display: flex;
    gap: 5px;
    align-items: center;
    white-space: nowrap;
    z-index: 1;
    transition: color 0.3s ease;
  }

  #rdm-city-rotator {
    height: 20px;
    overflow: hidden;
  }

  #rdm-city-inner {
    display: flex;
    flex-direction: column;
    animation: rdm-scroll 18.6s infinite;
  }

  @keyframes rdm-scroll {
    0%         { transform: translateY(0px); }
    13.4%      { transform: translateY(0px); }
    16.7%      { transform: translateY(-20px); }
    29.9%      { transform: translateY(-20px); }
    33.2%      { transform: translateY(-40px); }
    46.4%      { transform: translateY(-40px); }
    49.7%      { transform: translateY(-60px); }
    62.9%      { transform: translateY(-60px); }
    66.2%      { transform: translateY(-80px); }
    79.4%      { transform: translateY(-80px); }
    82.7%      { transform: translateY(-100px); }
    96.1%      { transform: translateY(-100px); }
    96.2%      { transform: translateY(0px); }
    100%       { transform: translateY(0px); }
  }

  #rdm-city-inner span {
    height: 20px;
    line-height: 20px;
    display: block;
  }

  /* Dropdown */
  #rdm-dropdown {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    right: 0;
    background: rgba(20, 20, 30, 0.96);
    backdrop-filter: blur(16px);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 8px 25px rgba(0,0,0,0.5);
    border: 1px solid rgba(255, 255, 255, 0.12);
    transition: background 0.3s ease, border-color 0.3s ease;
  }

  .rdm-result {
    padding: 11px 18px;
    color: rgba(255, 255, 255, 0.85);
    font-size: 13px;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .rdm-result:hover {
    background: rgba(168, 85, 247, 0.18);
    color: white;
  }

  /* ── Top-right control row ── */
  #rdm-controls-row {
    position: absolute;
    top: 20px;
    right: 20px;
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  /* ── Theme toggle ── */
  #rdm-theme-toggle {
    position: relative;
    width: 32px;
    height: 58px;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    cursor: pointer;
    flex-shrink: 0;
    padding: 4px;
    box-sizing: border-box;
    transition: border-color 0.3s ease, background 0.3s ease;
  }
  #rdm-theme-toggle:hover {
    border-color: rgba(168, 85, 247, 0.7);
  }

  #rdm-theme-track-icon-top,
  #rdm-theme-track-icon-bottom {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    width: 13px;
    height: 13px;
    pointer-events: none;
    transition: opacity 0.25s ease;
  }
  #rdm-theme-track-icon-top { top: 7px; opacity: 0.45; }
  #rdm-theme-track-icon-bottom { bottom: 7px; opacity: 0.25; }
  .theme-light #rdm-theme-track-icon-top { opacity: 0.25; }
  .theme-light #rdm-theme-track-icon-bottom { opacity: 0.45; }

  #rdm-theme-knob {
    position: absolute;
    left: 4px;
    right: 4px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2a2a38, #1a1a24);
    border: 1px solid rgba(255, 255, 255, 0.12);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    transition: transform 0.32s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.32s ease;
    transform: translateY(26px);
  }
  .theme-light #rdm-theme-knob {
    transform: translateY(0);
    background: linear-gradient(135deg, #fff7d6, #ffe89e);
    border: 1px solid rgba(250, 204, 21, 0.5);
  }
  #rdm-theme-knob svg {
    width: 15px;
    height: 15px;
  }

  /* ── Refresh button — dark theme: white bubble ── */
  #rdm-refresh {
    height: 42px;
    padding: 0 16px;
    border-radius: 22px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: border-color 0.2s, background 0.3s ease, color 0.3s ease;
    white-space: nowrap;
    flex-shrink: 0;
  }
  #rdm-refresh:hover {
    background: rgba(255, 255, 255, 0.28);
    border-color: rgba(168, 85, 247, 0.7);
  }
  #rdm-refresh:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  #rdm-refresh .spin {
    display: inline-block;
    animation: rdm-spin 0.8s linear infinite;
  }
  @keyframes rdm-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }

  /* ── Filter panel — dark theme: white bubble, dark text ── */
  #rdm-filter-panel {
    position: absolute;
    /* Moved down to 90px so it clears the theme toggle (58px tall + 20px top + gap) */
    top: 90px;
    right: 20px;
    width: 240px;
    z-index: 999;
    padding: 14px 16px 16px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    transition: background 0.3s ease, border-color 0.3s ease;
  }
  #rdm-filter-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.65);
    margin-bottom: 10px;
    transition: color 0.3s ease;
  }
  #rdm-filter-value-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
  }
  #rdm-filter-label {
    font-size: 12.5px;
    color: rgba(255, 255, 255, 0.88);
    font-weight: 500;
    transition: color 0.3s ease;
  }
  #rdm-filter-value {
    font-size: 13px;
    font-weight: 700;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  #rdm-filter-slider {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 4px;
    border-radius: 99px;
    background: rgba(255, 255, 255, 0.25);
    outline: none;
    cursor: pointer;
    transition: background 0.3s ease;
  }
  #rdm-filter-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(168,85,247,0.5);
    border: 2px solid rgba(255,255,255,0.9);
  }
  #rdm-filter-slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(168,85,247,0.5);
    border: 2px solid rgba(255,255,255,0.9);
  }
  #rdm-filter-bounds {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    font-size: 10px;
    color: rgba(255, 255, 255, 0.45);
    transition: color 0.3s ease;
  }
  #rdm-filter-disabled-note {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.5);
    font-style: italic;
    margin-top: 2px;
    transition: color 0.3s ease;
  }

  /* ── Legend — dark theme: white bubble ── */
  #rdm-legend {
    position: absolute;
    bottom: 24px;
    left: 20px;
    z-index: 999;
    padding: 12px 16px 10px;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    transition: background 0.3s ease, border-color 0.3s ease;
  }
  #rdm-legend-track-row {
    display: flex;
    align-items: center;
  }
  #rdm-legend-track-row svg {
    display: block;
  }
  #rdm-legend-captions {
    display: flex;
    justify-content: space-between;
    margin-top: 5px;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.2px;
    color: rgba(255, 255, 255, 0.75);
    transition: color 0.3s ease;
  }

  /* ═══════════════════════════════════════════════════════════════
     LIGHT THEME OVERRIDES — flip to dark/opaque bubbles
     ═══════════════════════════════════════════════════════════════ */

  /* Badge */
  .theme-light #rdm-badge {
    background: rgba(18, 18, 28, 0.82);
    border: 1px solid rgba(0, 0, 0, 0.18);
  }

  /* Last detected */
  .theme-light #rdm-last-detected {
    background: rgba(18, 18, 28, 0.76);
    border: 1px solid rgba(0, 0, 0, 0.14);
    color: rgba(255, 255, 255, 0.82);
  }
  .theme-light #rdm-last-detected b {
    color: #fff;
  }

  /* Search box */
  .theme-light #rdm-search-box {
    background: rgba(18, 18, 28, 0.82);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.18);
  }
  /* Switch to the light-bg logo (dark icon) */
  .theme-light #rdm-search-box::after {
    background-image: url('/hn-logo_light.png');
  }
  .theme-light #rdm-search-input {
    color: #fff;
  }
  .theme-light #rdm-placeholder {
    color: rgba(255, 255, 255, 0.45);
  }

  /* Dropdown */
  .theme-light #rdm-dropdown {
    background: rgba(18, 18, 28, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }
  .theme-light .rdm-result {
    color: rgba(255, 255, 255, 0.85);
  }
  .theme-light .rdm-result:hover {
    color: #fff;
  }

  /* Theme toggle */
  .theme-light #rdm-theme-toggle {
    background: rgba(18, 18, 28, 0.82);
    border: 1px solid rgba(0, 0, 0, 0.18);
  }
  .theme-light #rdm-theme-toggle:hover {
    border-color: rgba(168, 85, 247, 0.7);
  }

  /* Refresh */
  .theme-light #rdm-refresh {
    background: rgba(18, 18, 28, 0.82);
    border: 1px solid rgba(0, 0, 0, 0.18);
    color: #fff;
  }
  .theme-light #rdm-refresh:hover {
    background: rgba(18, 18, 28, 0.92);
    border-color: rgba(168, 85, 247, 0.7);
  }

  /* Filter panel */
  .theme-light #rdm-filter-panel {
    background: rgba(18, 18, 28, 0.82);
    border: 1px solid rgba(0, 0, 0, 0.18);
  }
  .theme-light #rdm-filter-title {
    color: rgba(255, 255, 255, 0.55);
  }
  .theme-light #rdm-filter-label {
    color: rgba(255, 255, 255, 0.88);
  }
  .theme-light #rdm-filter-slider {
    background: rgba(255, 255, 255, 0.2);
  }
  .theme-light #rdm-filter-bounds {
    color: rgba(255, 255, 255, 0.4);
  }
  .theme-light #rdm-filter-disabled-note {
    color: rgba(255, 255, 255, 0.45);
  }

  /* Legend */
  .theme-light #rdm-legend {
    background: rgba(18, 18, 28, 0.82);
    border: 1px solid rgba(0, 0, 0, 0.18);
  }
  .theme-light #rdm-legend-captions {
    color: rgba(255, 255, 255, 0.75);
  }

  /* ── Mobile overrides ── */
  @media (max-width: 640px) {
    #rdm-search-wrap {
      top: 110px;
      left: 50%;
      transform: translateX(-50%);
      width: calc(100vw - 40px);
      max-width: 340px;
    }
    #rdm-watermark {
      font-size: 14px;
      bottom: 12px;
      right: 12px;
    }
    #rdm-badge {
      padding: 8px 18px;
    }
    #rdm-badge span {
      font-size: 14px;
    }
    #rdm-last-detected {
      top: 58px;
      font-size: 10.5px;
      padding: 5px 14px;
    }
    #rdm-filter-panel {
      top: 90px;
      right: 12px;
      width: calc(100vw - 40px);
      max-width: 280px;
    }
    #rdm-theme-toggle {
      width: 28px;
      height: 50px;
    }
    #rdm-theme-knob {
      width: 20px;
      height: 20px;
      transform: translateY(22px);
    }
    .theme-light #rdm-theme-knob {
      transform: translateY(0);
    }
    #rdm-controls-row {
      top: 20px;
      right: 12px;
      gap: 8px;
    }
    #rdm-refresh {
      height: 36px;
      padding: 0 12px;
      font-size: 12px;
    }
    #rdm-legend {
      bottom: 16px;
      left: 12px;
      padding: 10px 14px 8px;
    }
    .leaflet-popup {
      max-width: 92vw !important;
    }
    .leaflet-popup-content-wrapper {
      max-width: 92vw !important;
    }
    .leaflet-popup-content {
      margin: 10px !important;
    }
  }

  /* ── Leaflet popup / tooltip overrides (always dark) ── */
  .leaflet-popup-content-wrapper {
    background: #12121a !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6) !important;
    color: #e0e0e0 !important;
    padding: 0 !important;
  }
  .leaflet-popup-content { margin: 14px !important; }
  .leaflet-popup-tip { background: #12121a !important; }
  .leaflet-popup-close-button {
    color: #aaa !important;
    font-size: 18px !important;
    top: 6px !important;
    right: 8px !important;
  }
  .leaflet-tooltip {
    background: rgba(10,10,18,0.97) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 8px !important;
    color: #fff !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.6) !important;
    padding: 8px 12px !important;
  }
  .leaflet-tooltip-top:before {
    border-top-color: rgba(255,255,255,0.15) !important;
  }
  .leaflet-popup-content div::-webkit-scrollbar { height: 4px; }
  .leaflet-popup-content div::-webkit-scrollbar-track { background: transparent; }
  .leaflet-popup-content div::-webkit-scrollbar-thumb {
    background: #fff;
    border-radius: 99px;
  }

  /* ── Search-result pin pulse ── */
  .rdm-search-pin-wrap {
    position: relative;
    width: 26px;
    height: 26px;
  }
  .rdm-search-pin-pulse {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(236,72,153,0.35);
    animation: rdm-pin-pulse 1.8s ease-out infinite;
  }
  @keyframes rdm-pin-pulse {
    0%   { transform: scale(0.5); opacity: 0.9; }
    100% { transform: scale(2.2); opacity: 0; }
  }
`;

// ─── Sun / Moon icons ──────────────────────────────────────────────────────────
function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#facc15" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4.2" />
      <line x1="12" y1="2.5" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="21.5" />
      <line x1="4.2" y1="4.2" x2="6" y2="6" />
      <line x1="18" y1="18" x2="19.8" y2="19.8" />
      <line x1="2.5" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="21.5" y2="12" />
      <line x1="4.2" y1="19.8" x2="6" y2="18" />
      <line x1="18" y1="6" x2="19.8" y2="4.2" />
    </svg>
  );
}
function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="#c4b5fd" stroke="#c4b5fd" strokeWidth="1" strokeLinejoin="round">
      <path d="M20.5 14.2c-1.1.45-2.3.7-3.6.7-5.1 0-9.2-4.1-9.2-9.2 0-1.3.25-2.5.7-3.6C4.9 3.5 2.5 7.2 2.5 11.5 2.5 17.3 7.2 22 13 22c4.3 0 8-2.4 9.5-5.9-.6.1-1.3.15-2 .1z" />
    </svg>
  );
}

// ─── Bumpiness legend track ───────────────────────────────────────────────────
function LegendTrack() {
  const width   = 168;
  const height  = 22;
  const padX    = 11;
  const usable  = width - padX * 2;
  const dotsN   = 12;
  const y       = height / 2;

  const dots = Array.from({ length: dotsN }, (_, i) => {
    const t = i / (dotsN - 1);
    const x = padX + t * usable;
    return { x, color: getEventColor(t) };
  });

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <line
        x1={padX} y1={y} x2={width - padX} y2={y}
        stroke="rgba(255,255,255,0.18)" strokeWidth="3" strokeLinecap="round"
      />
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={y} r="3.4" fill={d.color} />
      ))}
    </svg>
  );
}

// ─── Search bar ───────────────────────────────────────────────────────────────
function SearchBar({ onSelect }) {
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState([]);
  const [focused, setFocused] = useState(false);
  const timerRef = useRef(null);

  const search = useCallback(async (q) => {
    if (q.length < 3) { setResults([]); return; }
    try {
      const res  = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5`,
        { headers: { "Accept-Language": "en" } }
      );
      const data = await res.json();
      setResults(data.map((r) => ({
        label: r.display_name,
        lat:   parseFloat(r.lat),
        lon:   parseFloat(r.lon),
      })));
    } catch (e) {
      console.error("[geocode]", e);
    }
  }, []);

  const handleChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(val), 400);
  };

  const handlePick = (r) => {
    onSelect(r.lat, r.lon, r.label.split(",")[0]);
    setQuery(r.label.split(",")[0]);
    setResults([]);
  };

  return (
    <div id="rdm-search-wrap">
      <div id="rdm-search-box">
        <input
          id="rdm-search-input"
          type="text"
          value={query}
          onChange={handleChange}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 200)}
          autoComplete="off"
        />
        {!focused && !query && (
          <div id="rdm-placeholder">
            <span>Search</span>
            <div id="rdm-city-rotator">
              <div id="rdm-city-inner">
                {CITIES_LOOP.map((c, i) => (
                  <span key={i}>{c}</span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {results.length > 0 && focused && (
        <div id="rdm-dropdown">
          {results.map((r, i) => (
            <div key={i} className="rdm-result" onMouseDown={() => handlePick(r)}>
              {r.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function RoadDefectsMap() {
  const mapRef        = useRef(null);
  const mapDivRef     = useRef(null);
  const layerCacheRef = useRef({});
  const eventCacheRef = useRef({});
  const imageCacheRef = useRef({});
  const fetchedCells  = useRef(new Set());
  const isFetchingRef = useRef(false);
  const searchPinRef  = useRef(null);
  const toggleBtnRef  = useRef(null);   // ref to the theme toggle button for iris origin
  const irisLayerRef  = useRef(null);   // ref to the iris overlay div

  // ── Theme ───────────────────────────────────────────────────────────────────
  const [theme, setTheme] = useState("dark");

  // ── Iris reveal transition ─────────────────────────────────────────────────
  // Instead of covering the screen with a coloured circle, we build a real
  // clone of the new theme's appearance, clip it to a circle of radius 0
  // centred on the toggle button, then CSS-transition the clip to full screen.
  // Once it lands, we swap the underlying theme and tear down the iris layer.
  const isAnimatingRef = useRef(false);

  const toggleTheme = useCallback(() => {
    if (isAnimatingRef.current) return;

    const btn = toggleBtnRef.current;
    const iris = irisLayerRef.current;
    const container = document.getElementById("rdm-container");
    if (!btn || !iris || !container) {
      setTheme(t => t === "dark" ? "light" : "dark");
      return;
    }

    isAnimatingRef.current = true;
    const nextTheme = container.classList.contains("theme-light") ? "dark" : "light";

    // 1. Immediately flip the real container class so tiles start cross-fading
    if (nextTheme === "light") {
      container.classList.add("theme-light");
    } else {
      container.classList.remove("theme-light");
    }

    // 2. Play the iris glow over the top
    const cRect = container.getBoundingClientRect();
    const bRect = btn.getBoundingClientRect();
    const cx = ((bRect.left - cRect.left + bRect.width  / 2) / cRect.width  * 100).toFixed(2) + "%";
    const cy = ((bRect.top  - cRect.top  + bRect.height / 2) / cRect.height * 100).toFixed(2) + "%";

    iris.style.setProperty("--iris-gx", cx);
    iris.style.setProperty("--iris-gy", cy);

    // Set glow colour based on nextTheme (can't rely on React state here)
    const glowDiv = document.getElementById("rdm-iris-glow");
    if (glowDiv) {
      glowDiv.style.background = nextTheme === "light"
        ? "radial-gradient(circle at var(--iris-gx,50%) var(--iris-gy,50%), rgba(255,252,240,0.55) 0%, rgba(255,252,240,0.1) 40%, transparent 70%)"
        : "radial-gradient(circle at var(--iris-gx,50%) var(--iris-gy,50%), rgba(8,8,20,0.55) 0%, rgba(8,8,20,0.1) 40%, transparent 70%)";
    }

    iris.style.transition = "none";
    iris.style.clipPath = `circle(0% at ${cx} ${cy})`;
    void iris.offsetWidth;
    iris.style.transition = "clip-path 0.72s cubic-bezier(0.4, 0, 0.2, 1)";
    iris.style.clipPath = `circle(150% at ${cx} ${cy})`;

    // 3. Collapse iris instantly before React re-renders, then sync state
    setTimeout(() => {
      iris.style.transition = "none";
      iris.style.clipPath = "circle(0% at 50% 50%)";
      setTheme(nextTheme);
      isAnimatingRef.current = false;
    }, 750);
  }, []);

  // ── Detections filter ──────────────────────────────────────────────────────
  const [minDetections, setMinDetections] = useState(1);
  const [maxDetections, setMaxDetections] = useState(1);

  // ── Last detected badge ────────────────────────────────────────────────────
  const [lastDetected, setLastDetected] = useState(null);
  const lastDetectedKeyRef = useRef(null);

  // ── Recompute slider max ───────────────────────────────────────────────────
  const recomputeMaxAndApplyFilter = useCallback((minOverride) => {
    const allRows = Object.values(eventCacheRef.current).flat();
    const max = allRows.reduce((m, r) => Math.max(m, r.parameters.length), 1);
    setMaxDetections(max);

    const min = minOverride ?? minDetections;
    setMinDetections((prev) => {
      const next = minOverride ?? Math.min(prev, max);
      return next;
    });

    applyFilterToLayers(min > max ? max : min);
  }, [minDetections]);

  function applyFilterToLayers(min) {
    const map = mapRef.current;
    if (!map) return;
    for (const [hexId, rows] of Object.entries(eventCacheRef.current)) {
      const layers = layerCacheRef.current[hexId];
      if (!layers) continue;
      rows.forEach((row, i) => {
        const marker = layers[i + 1];
        if (!marker) return;
        const count = row.parameters.length;
        const shouldShow = count >= min;
        const has = map.hasLayer(marker);
        if (shouldShow && !has) marker.addTo(map);
        if (!shouldShow && has) map.removeLayer(marker);
      });
    }
  }

  const handleSliderChange = (e) => {
    const val = parseInt(e.target.value, 10);
    setMinDetections(val);
    applyFilterToLayers(val);
  };

  // ── Last detected badge update ─────────────────────────────────────────────
  const maybeUpdateLastDetected = useCallback(async (rows) => {
    if (!rows.length) return;

    const candidateEids = [...new Set(rows.map((r) => r.event_id[r.event_id.length - 1]))];

    const { data: events, error } = await supabase
      .from("imu_events")
      .select("imu_events_id, start_time")
      .in("imu_events_id", candidateEids);
    if (error) { console.error("[supabase] imu_events (last-detected):", error); return; }
    if (!events || !events.length) return;

    const startTimeByEid = {};
    for (const ev of events) startTimeByEid[ev.imu_events_id] = ev.start_time;

    let best = null;
    let bestTime = -Infinity;
    for (const row of rows) {
      const eid = row.event_id[row.event_id.length - 1];
      const st = startTimeByEid[eid];
      if (!st) continue;
      const ms = new Date(st).getTime();
      if (ms > bestTime) { bestTime = ms; best = { row, eid, startTime: st }; }
    }
    if (!best) return;

    if (lastDetectedKeyRef.current === best.eid) return;
    lastDetectedKeyRef.current = best.eid;

    const [lat, lon] = best.row.location;
    const { city, locality } = await reverseGeocodeCityLocality(lat, lon);
    const dateStr = formatISTDate(best.startTime);
    setLastDetected({ city, locality, dateStr });
  }, []);

  // ── Initialize Leaflet ─────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current) return;

    const init = () => {
      const map = L.map(mapDivRef.current, {
        center: [13.05, 80.22],
        zoom: 13,
        zoomControl: false,
      });

      L.control.zoom({ position: "bottomright" }).addTo(map);

      L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        { attribution: "© OpenStreetMap contributors © CARTO", subdomains: "abcd", maxZoom: 20 }
      ).addTo(map);

      mapRef.current = map;
      setTimeout(() => map.invalidateSize(), 100);

      loadViewport();

      let moveTimer = null;
      map.on("moveend", () => {
        clearTimeout(moveTimer);
        moveTimer = setTimeout(loadViewport, 300);
      });
    };

    requestAnimationFrame(init);

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // ── Viewport loader ────────────────────────────────────────────────────────
  const loadViewport = useCallback(async () => {
    const map = mapRef.current;
    if (!map || isFetchingRef.current) return;
    isFetchingRef.current = true;

    try {
      const cells   = boundsToH3Cells(map.getBounds());
      const toFetch = cells.filter((c) => !fetchedCells.current.has(c));

      const newEvents = await fetchEventsForCells(toFetch, new Set());
      toFetch.forEach((c) => fetchedCells.current.add(c));

      console.log("2. New events returned:", newEvents.length, newEvents);

      cells.forEach((c) => fetchedCells.current.add(c));
      if (!newEvents.length) return;

      const allEventIds = newEvents.map((e) => e.event_id[e.event_id.length - 1]);
      const newFrames = await fetchFramesForEvents(allEventIds);
      Object.assign(imageCacheRef.current, newFrames);

      const byHex = {};
      for (const ev of newEvents) {
        if (!ev.h3_index) continue;
        if (!byHex[ev.h3_index]) byHex[ev.h3_index] = [];
        byHex[ev.h3_index].push(ev);
      }
      for (const [hexId, events] of Object.entries(byHex)) {
        if (!eventCacheRef.current[hexId]) eventCacheRef.current[hexId] = [];
        eventCacheRef.current[hexId].push(...events);
        drawHex(hexId, eventCacheRef.current[hexId]);
      }

      recomputeMaxAndApplyFilter();
      maybeUpdateLastDetected(newEvents);
    } catch (err) {
      console.error("[loadViewport]", err);
    } finally {
      isFetchingRef.current = false;
    }
  }, [recomputeMaxAndApplyFilter, maybeUpdateLastDetected]);

  // ── Draw hex ───────────────────────────────────────────────────────────────
  function drawHex(hexId, rows) {
    const map = mapRef.current;
    if (!map) return;

    if (layerCacheRef.current[hexId]) {
      layerCacheRef.current[hexId].forEach(l => map.removeLayer(l));
    }

    const layers = [];

    const latLngs = h3.cellToBoundary(hexId).map(([lat, lng]) => [lat, lng]);
    const hexPolygon = L.polygon(latLngs, {
      color: "#4a71b0",
      fillColor: "#3b82f6",
      fillOpacity: 0.15,
      weight: 1.5,
      opacity: 0.5,
    });
    hexPolygon.addTo(map);
    layers.push(hexPolygon);

    for (const row of rows) {
      const [lat, lon] = row.location;
      const param   = parseFloat(row.parameters[row.parameters.length - 1]);
      const lastEid = row.event_id[row.event_id.length - 1];
      const color   = getEventColor(param);

      const marker = L.circle([lat, lon], {
        radius: 4,
        color: color,
        fillColor: color,
        fillOpacity: 0.9,
        weight: 1.5,
      });

      marker.on("mouseover", (e) => {
        marker.bindTooltip(buildHoverHTML(row, param), {
          sticky: true, opacity: 1, className: "rdm-tooltip",
        }).openTooltip(e.latlng);
        marker.setStyle({ fillOpacity: 1, weight: 3 });
      });

      marker.on("mouseout", () => {
        marker.closeTooltip();
        marker.setStyle({ fillOpacity: 0.9, weight: 1.5 });
      });

      marker.on("click", async () => {
        if (!imageCacheRef.current[lastEid]) {
          Object.assign(imageCacheRef.current, await fetchFramesForEvents([lastEid]));
        }
        const html = await buildImagePopupHTML(row, param, imageCacheRef.current[lastEid] || []);
        marker.bindPopup(html, { maxWidth: 520, maxHeight: 460 }).openPopup();
      });

      marker.addTo(map);
      layers.push(marker);
    }

    layerCacheRef.current[hexId] = layers;
    applyFilterToLayers(minDetections);
  }

  // ── Search → fly to place ──────────────────────────────────────────────────
  const handleSearchSelect = useCallback((lat, lon, label) => {
    const map = mapRef.current;
    if (!map) return;

    map.setView([lat, lon], 14, { animate: true, duration: 1.5 });

    if (searchPinRef.current) {
      map.removeLayer(searchPinRef.current);
      searchPinRef.current = null;
    }

    const pinIcon = L.divIcon({
      className: "",
      html: `
        <div class="rdm-search-pin-wrap">
          <div class="rdm-search-pin-pulse"></div>
          <svg width="26" height="26" viewBox="0 0 26 26" style="position:relative;">
            <path d="M13 2C8.6 2 5 5.6 5 10c0 6 8 14 8 14s8-8 8-14c0-4.4-3.6-8-8-8z"
              fill="url(#rdmPinGrad)" stroke="white" stroke-width="1.2"/>
            <circle cx="13" cy="10" r="3" fill="white"/>
            <defs>
              <linearGradient id="rdmPinGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#a855f7"/>
                <stop offset="100%" stop-color="#ec4899"/>
              </linearGradient>
            </defs>
          </svg>
        </div>`,
      iconSize: [26, 26],
      iconAnchor: [13, 24],
    });

    const pin = L.marker([lat, lon], { icon: pinIcon, zIndexOffset: 2000 }).addTo(map);
    if (label) pin.bindTooltip(label, { direction: "top", offset: [0, -22] });
    searchPinRef.current = pin;
  }, []);

  // ── Refresh ────────────────────────────────────────────────────────────────
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    const map = mapRef.current;
    if (!map || refreshing) return;
    setRefreshing(true);

    Object.values(layerCacheRef.current).forEach((layers) =>
      layers.forEach(l => map.removeLayer(l))
    );

    layerCacheRef.current = {};
    eventCacheRef.current = {};
    imageCacheRef.current = {};
    fetchedCells.current  = new Set();
    isFetchingRef.current = false;

    try {
      const cells     = boundsToH3Cells(map.getBounds());
      const newEvents = await fetchEventsForCells(cells, fetchedCells.current);
      cells.forEach((c) => fetchedCells.current.add(c));

      if (newEvents.length) {
        const allEventIds = newEvents.map((e) => e.event_id[e.event_id.length - 1]);
        const newFrames = await fetchFramesForEvents(allEventIds);
        Object.assign(imageCacheRef.current, newFrames);

        const byHex = {};
        for (const ev of newEvents) {
          if (!ev.h3_index) continue;
          if (!byHex[ev.h3_index]) byHex[ev.h3_index] = [];
          byHex[ev.h3_index].push(ev);
        }
        for (const [hexId, events] of Object.entries(byHex)) {
          eventCacheRef.current[hexId] = events;
          drawHex(hexId, events);
        }
        recomputeMaxAndApplyFilter(1);
        maybeUpdateLastDetected(newEvents);
      } else {
        setMaxDetections(1);
        setMinDetections(1);
      }
    } catch (err) {
      console.error("[refresh]", err);
    }

    setRefreshing(false);
  }, [refreshing, recomputeMaxAndApplyFilter, maybeUpdateLastDetected]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{styles}</style>
      <div id="rdm-container" className={theme === "light" ? "theme-light" : ""}>
        <div id="rdm-map" ref={mapDivRef} />

        {/* Iris reveal layer — soft radial glow that leads the tile-filter crossfade */}
        <div id="rdm-iris-layer" ref={irisLayerRef}>
          <div id="rdm-iris-glow" style={{
            position: "absolute", inset: 0,
          }} />
        </div>

        <SearchBar onSelect={handleSearchSelect} />

        <div id="rdm-badge"><span>road-scout</span></div>

        {lastDetected && (
          <div id="rdm-last-detected">
            last detected: <b>{lastDetected.city}</b>
            {lastDetected.locality ? <>, {lastDetected.locality}</> : null}, {lastDetected.dateStr}
          </div>
        )}

        <div id="rdm-controls-row">
          <div
            id="rdm-theme-toggle"
            ref={toggleBtnRef}
            onClick={toggleTheme}
            role="button"
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            <div id="rdm-theme-track-icon-top"><SunIcon /></div>
            <div id="rdm-theme-track-icon-bottom"><MoonIcon /></div>
            <div id="rdm-theme-knob">
              {theme === "dark" ? <MoonIcon /> : <SunIcon />}
            </div>
          </div>
          <button id="rdm-refresh" onClick={handleRefresh} disabled={refreshing}>
            {refreshing
              ? <><span className="spin">↻</span> Refreshing…</>
              : <>↻</>}
          </button>
        </div>

        <div id="rdm-filter-panel">
          <div id="rdm-filter-title">Filter by detections</div>
          <div id="rdm-filter-value-row">
            <span id="rdm-filter-label">Detections ≥</span>
            <span id="rdm-filter-value">{minDetections}</span>
          </div>
          <input
            id="rdm-filter-slider"
            type="range"
            min={1}
            max={Math.max(1, maxDetections)}
            value={Math.min(minDetections, Math.max(1, maxDetections))}
            onChange={handleSliderChange}
            disabled={maxDetections <= 1}
          />
          <div id="rdm-filter-bounds">
            <span>1</span>
            <span>{Math.max(1, maxDetections)}</span>
          </div>
          {maxDetections <= 1 && (
            <div id="rdm-filter-disabled-note">No range in this view yet</div>
          )}
        </div>

        <div id="rdm-legend">
          <div id="rdm-legend-track-row">
            <LegendTrack />
          </div>
          <div id="rdm-legend-captions">
            <span>least bumpy</span>
            <span>most bumpy</span>
          </div>
        </div>

        <div id="rdm-watermark">vehnicate</div>
      </div>
    </>
  );
}