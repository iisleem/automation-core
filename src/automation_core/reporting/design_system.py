from __future__ import annotations


def report_design_styles() -> str:
    return """
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  color-scheme: light dark;
  --sidebar-width: 236px;
  --content-max: 1320px;
  --bg: oklch(98% 0.004 240);
  --surface: oklch(100% 0 0);
  --surfaceAlt: oklch(96.5% 0.006 240);
  --border: oklch(89% 0.008 240);
  --text: oklch(23% 0.02 250);
  --muted: oklch(46% 0.02 250);
  --faint: oklch(62% 0.014 250);
  --accent: oklch(52% 0.13 220);
  --accentSoft: oklch(93% 0.035 220);
  --secondary: oklch(58% 0.15 75);
  --secondarySoft: oklch(94% 0.045 75);
  --chrome: oklch(99% 0.003 240);
  --chromeText: var(--text);
  --chromeBorder: var(--border);
  --pass: oklch(52% 0.14 155);
  --passSoft: oklch(94% 0.045 155);
  --fail: oklch(54% 0.19 25);
  --failSoft: oklch(94% 0.045 25);
  --broken: oklch(50% 0.15 300);
  --brokenSoft: oklch(94% 0.045 300);
  --skip: oklch(55% 0.01 250);
  --skipSoft: oklch(94% 0.01 250);
  --flaky: oklch(58% 0.15 75);
  --flakySoft: oklch(94% 0.045 75);
  --link: oklch(50% 0.15 235);
  --shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px -14px rgba(15,23,42,0.16);
  --heroShadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.14);
  --radius-card: 16px;
  --radius-inner: 12px;
  --radius-control: 9px;

  /* Compatibility aliases for older generated markup. */
  --ink: var(--text);
  --heading: var(--text);
  --line: var(--border);
  --panel: var(--surface);
  --panel-soft: var(--surfaceAlt);
  --input-bg: var(--surface);
  --table-head: var(--surfaceAlt);
  --accent-2: var(--secondary);
  --danger: var(--fail);
  --warn: var(--flaky);
  --ok: var(--pass);
  --hero-title: var(--text);
  --hero-text: var(--muted);
  --sidebar-bg: var(--chrome);
  --sidebar-ink: var(--chromeText);
  --nav-active-bg: var(--accentSoft);
  --nav-active-ink: var(--accent);
  --nav-hover: var(--surfaceAlt);
  --soft-shadow: var(--shadow);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: oklch(19% 0.014 255);
    --surface: oklch(24% 0.016 255);
    --surfaceAlt: oklch(28% 0.018 255);
    --border: oklch(34% 0.02 255);
    --text: oklch(93% 0.006 240);
    --muted: oklch(72% 0.015 245);
    --faint: oklch(58% 0.015 245);
    --accent: oklch(75% 0.12 210);
    --accentSoft: oklch(32% 0.06 210);
    --secondary: oklch(75% 0.14 80);
    --secondarySoft: oklch(32% 0.06 80);
    --chrome: oklch(15% 0.015 255);
    --pass: oklch(72% 0.15 155);
    --passSoft: oklch(30% 0.06 155);
    --fail: oklch(70% 0.18 25);
    --failSoft: oklch(30% 0.07 25);
    --broken: oklch(72% 0.14 300);
    --brokenSoft: oklch(31% 0.06 300);
    --skip: oklch(65% 0.012 250);
    --skipSoft: oklch(31% 0.012 250);
    --flaky: oklch(75% 0.14 80);
    --flakySoft: oklch(32% 0.06 80);
    --link: oklch(75% 0.12 235);
    --shadow: 0 1px 2px rgba(0,0,0,0.22), 0 10px 28px -16px rgba(0,0,0,0.62);
    --heroShadow: 0 1px 2px rgba(0,0,0,0.24), 0 12px 30px -14px rgba(0,0,0,0.68);
  }
}

:root[data-theme="light"] {
  color-scheme: light;
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: oklch(19% 0.014 255);
  --surface: oklch(24% 0.016 255);
  --surfaceAlt: oklch(28% 0.018 255);
  --border: oklch(34% 0.02 255);
  --text: oklch(93% 0.006 240);
  --muted: oklch(72% 0.015 245);
  --faint: oklch(58% 0.015 245);
  --accent: oklch(75% 0.12 210);
  --accentSoft: oklch(32% 0.06 210);
  --secondary: oklch(75% 0.14 80);
  --secondarySoft: oklch(32% 0.06 80);
  --chrome: oklch(15% 0.015 255);
  --pass: oklch(72% 0.15 155);
  --passSoft: oklch(30% 0.06 155);
  --fail: oklch(70% 0.18 25);
  --failSoft: oklch(30% 0.07 25);
  --broken: oklch(72% 0.14 300);
  --brokenSoft: oklch(31% 0.06 300);
  --skip: oklch(65% 0.012 250);
  --skipSoft: oklch(31% 0.012 250);
  --flaky: oklch(75% 0.14 80);
  --flakySoft: oklch(32% 0.06 80);
  --link: oklch(75% 0.12 235);
  --shadow: 0 1px 2px rgba(0,0,0,0.22), 0 10px 28px -16px rgba(0,0,0,0.62);
  --heroShadow: 0 1px 2px rgba(0,0,0,0.24), 0 12px 30px -14px rgba(0,0,0,0.68);
}

* {
  box-sizing: border-box;
}

html,
body {
  width: 100%;
  max-width: 100%;
  min-height: 100%;
}

html {
  background: var(--bg);
}

body {
  margin: 0;
  color: var(--text);
  background: var(--bg);
  font-family: "IBM Plex Sans", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
  letter-spacing: 0;
  overflow-x: hidden;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, color-mix(in oklch, var(--surfaceAlt) 35%, transparent), transparent 420px);
  z-index: -1;
}

h1,
h2,
h3,
.nav-brand strong {
  color: var(--text);
  font-family: "Manrope", "IBM Plex Sans", system-ui, sans-serif;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

h1 {
  margin: 0 0 6px;
  font-size: 28px;
  line-height: 1.14;
  font-weight: 800;
}

h2 {
  margin: 0 0 14px;
  font-size: 16px;
  line-height: 1.3;
  font-weight: 700;
}

h3 {
  margin: 0 0 10px;
  font-size: 14.5px;
  line-height: 1.35;
  font-weight: 700;
}

p {
  margin: 0;
  overflow-wrap: anywhere;
}

ul,
ol {
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

li {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

a {
  color: var(--link);
  text-decoration: none;
  overflow-wrap: anywhere;
  word-break: break-word;
}

a:hover {
  text-decoration: underline;
}

code,
pre,
.metric strong,
.hbar-label,
.heat-name,
.test-name-cell a,
.test-name-cell .muted,
.scope-cell,
.signal-cell,
.run-id,
.eyebrow,
td,
.status {
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.eyebrow {
  color: var(--faint);
  font-size: 11px;
  line-height: 1.3;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  font-weight: 700;
}

.muted {
  color: var(--muted);
}

[hidden] {
  display: none !important;
}

.nav-shell {
  z-index: 40;
}

.mobile-nav-toggle {
  display: none;
}

.app-nav {
  min-width: 0;
}

.app-nav a {
  color: var(--chromeText);
  text-decoration: none;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding: 0 6px 14px;
}

.nav-brand strong {
  display: block;
  font-size: 14px;
  font-weight: 800;
}

.nav-brand small {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.35;
}

.nav-logo {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  font-family: "Manrope", sans-serif;
  font-weight: 800;
  box-shadow: 0 8px 18px -12px color-mix(in oklch, var(--accent) 72%, black);
}

.nav-logo {
  font-size: 0;
}

.nav-logo::before {
  content: "";
  width: 16px;
  height: 16px;
  display: block;
  background:
    linear-gradient(#fff, #fff) 2px 8px / 3px 6px no-repeat,
    linear-gradient(#fff, #fff) 7px 4px / 3px 10px no-repeat,
    linear-gradient(#fff, #fff) 12px 10px / 3px 4px no-repeat;
  opacity: 0.95;
}

.app-nav a:not(.nav-brand) {
  position: relative;
  display: block;
  padding: 9px 12px 9px 22px;
  border-radius: 9px;
  color: var(--chromeText);
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.25;
}

.app-nav a:not(.nav-brand)::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 99px;
  background: transparent;
}

.app-nav a:not(.nav-brand):hover {
  background: var(--surfaceAlt);
  text-decoration: none;
}

.app-nav a.active {
  color: var(--accent);
  background: var(--accentSoft);
  text-decoration: none;
}

.app-nav a.active::before {
  background: var(--accent);
}

.theme-panel {
  display: grid;
  gap: 8px;
}

.theme-label {
  color: var(--faint);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.theme-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  background: var(--surfaceAlt);
  border: 1px solid color-mix(in oklch, var(--border) 80%, transparent);
}

.theme-options button {
  border: 0;
  border-radius: 8px;
  padding: 8px 6px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.theme-options button.active,
.theme-options button[aria-pressed="true"] {
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow);
}

.hero,
section {
  width: min(var(--content-max), calc(100vw - var(--sidebar-width) - 72px));
  max-width: var(--content-max);
  margin-inline: auto;
}

.hero {
  color: var(--muted);
  padding: 34px 0 8px;
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.hero.compact {
  padding-top: 30px;
}

.hero p:not(.eyebrow) {
  font-size: 14px;
  color: var(--muted);
}

.hero > .status {
  flex: 0 0 auto;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

section {
  margin-top: 22px;
  margin-bottom: 22px;
}

article,
.metric,
.toolbar,
.report-card,
.test-card,
.empty-state {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow);
}

article {
  padding: 20px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 14px;
}

.metrics.compact {
  margin-bottom: 12px;
}

.metric {
  padding: 18px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.metric strong {
  display: block;
  max-width: 100%;
  margin-bottom: 2px;
  color: var(--text);
  font-size: 26px;
  line-height: 1.05;
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.metric .muted {
  display: block;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.metric span,
.metric {
  color: var(--muted);
}

.grid {
  display: grid;
  gap: 18px;
}

.grid.two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.grid.three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.grid.four {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.overview-hero {
  align-items: stretch;
}

.health-card,
.pass-card {
  padding: 24px;
  box-shadow: var(--heroShadow);
}

.health-card-main {
  display: flex;
  align-items: center;
  gap: 22px;
}

.health-card-main .muted {
  margin-top: 12px;
  max-width: 520px;
}

.pass-card {
  display: grid;
  gap: 14px;
}

.card-label {
  color: var(--faint);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hero-number {
  color: var(--text);
  font-family: "Manrope", sans-serif;
  font-size: 44px;
  line-height: 1;
  font-weight: 800;
}

.delta-pill {
  display: inline-flex;
  vertical-align: middle;
  margin-left: 8px;
  padding: 3px 8px;
  border-radius: 100px;
  color: var(--fail);
  background: var(--failSoft);
  font-family: "IBM Plex Mono", monospace;
  font-size: 12px;
  font-weight: 700;
}

.mini-sparkline {
  width: 100%;
  min-height: 48px;
}

.mini-stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.mini-stat-row span {
  min-width: 0;
  color: var(--faint);
  font-size: 12px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.mini-stat-row strong {
  display: block;
  color: var(--text);
  font-family: "IBM Plex Mono", monospace;
  font-size: 17px;
  line-height: 1.15;
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.mini-stat-row .failed-stat strong {
  color: var(--fail);
}

.mini-stat-row .flaky-stat strong {
  color: var(--flaky);
}

.signal-chip-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  margin-bottom: 12px;
}

.signal-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 100px;
  color: var(--muted);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.signal-chip strong {
  color: var(--text);
  font-family: "IBM Plex Mono", monospace;
}

.status-segments {
  display: flex;
  height: 10px;
  margin-top: 22px;
  border-radius: 100px;
  background: var(--surfaceAlt);
  overflow: hidden;
}

.status-segments .segment {
  min-width: 3px;
}

.segment-passed {
  background: var(--pass);
}

.segment-failed {
  background: var(--fail);
}

.segment-skipped {
  background: var(--skip);
}

.segment-flaky {
  background: var(--flaky);
}

.segment-legend {
  margin-top: 12px;
}

.insight-pair .insight-card {
  border-radius: var(--radius-card);
}

.insight-card.key-wins {
  background: color-mix(in oklch, var(--passSoft) 78%, var(--surface));
  border-color: color-mix(in oklch, var(--pass) 26%, var(--border));
}

.insight-card.focus-areas {
  background: color-mix(in oklch, var(--failSoft) 76%, var(--surface));
  border-color: color-mix(in oklch, var(--fail) 28%, var(--border));
}

.insight-card.key-wins h2::before,
.insight-card.focus-areas h2::before {
  display: inline-block;
  margin-right: 8px;
  font-family: "IBM Plex Sans", sans-serif;
}

.insight-card.key-wins h2::before {
  content: "✓";
  color: var(--pass);
}

.insight-card.focus-areas h2::before {
  content: "△";
  color: var(--fail);
}

.insight-card ul {
  margin: 0;
  padding-left: 18px;
}

.insight-card li + li {
  margin-top: 8px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  padding: 18px;
}

.toolbar label,
.result-strip label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
  color: var(--faint);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.search-box {
  flex: 1 1 320px;
}

input,
select,
button,
.button {
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 10px 14px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
}

input,
select {
  min-height: 40px;
}

input:focus,
select:focus,
button:focus-visible,
.button:focus-visible,
a:focus-visible,
summary:focus-visible {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px var(--accentSoft);
}

button,
.button {
  cursor: pointer;
  font-weight: 700;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  text-decoration: none;
  color: var(--accent);
}

.button:hover,
button:hover {
  border-color: var(--accent);
  background: var(--accentSoft);
  text-decoration: none;
}

.button.inverse {
  color: #fff;
  border-color: var(--accent);
  background: var(--accent);
}

.result-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 9px;
  border-radius: 100px;
  font-size: 11px;
  line-height: 1.25;
  font-weight: 700;
  text-transform: uppercase;
  white-space: nowrap;
  overflow-wrap: normal;
}

.status::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: 0 0 auto;
  background: currentColor;
}

.passed,
.ready,
.success,
.low {
  color: var(--pass);
  background: var(--passSoft);
}

.failed,
.error,
.blocked,
.high {
  color: var(--fail);
  background: var(--failSoft);
}

.broken {
  color: var(--broken);
  background: var(--brokenSoft);
}

.skipped,
.warning,
.medium,
.not_configured {
  color: var(--flaky);
  background: var(--flakySoft);
}

.unknown {
  color: var(--skip);
  background: var(--skipSoft);
}

.score-ring {
  width: 112px;
  aspect-ratio: 1;
  border-radius: 50%;
  display: grid;
  place-items: center;
  margin: 0 0 16px;
  background: conic-gradient(var(--pass) 0 75%, var(--surfaceAlt) 75% 100%);
  box-shadow: inset 0 0 0 16px var(--surface);
}

.score-ring strong {
  color: var(--pass);
  font-family: "Manrope", sans-serif;
  font-size: 26px;
  line-height: 1;
  font-weight: 800;
}

.score-ring span {
  color: var(--faint);
  font-size: 10px;
  text-transform: uppercase;
  font-weight: 700;
}

.score-ring.status-warning {
  background: conic-gradient(var(--flaky) 0 62%, var(--surfaceAlt) 62% 100%);
}

.score-ring.status-warning strong {
  color: var(--flaky);
}

.score-ring.status-failed {
  background: conic-gradient(var(--fail) 0 45%, var(--surfaceAlt) 45% 100%);
}

.score-ring.status-failed strong {
  color: var(--fail);
}

.score-ring.status-unknown {
  background: conic-gradient(var(--skip) 0 20%, var(--surfaceAlt) 20% 100%);
}

.score-ring.status-unknown strong {
  color: var(--skip);
}

.bar,
.hbar-track {
  height: 8px;
  min-width: 80px;
  border-radius: 100px;
  background: var(--surfaceAlt);
  overflow: hidden;
}

.bar span,
.hbar-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}

.hbar-row {
  display: grid;
  grid-template-columns: minmax(110px, 1.2fr) minmax(100px, 2fr) auto;
  gap: 12px;
  align-items: center;
  margin: 10px 0;
  min-width: 0;
}

.truncate {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hbar-label {
  min-width: 0;
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  white-space: normal;
}

.table-wrap {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  border-radius: var(--radius-card);
  scrollbar-gutter: stable;
  -webkit-overflow-scrolling: touch;
  box-shadow: var(--shadow);
}

.table-wrap table {
  box-shadow: none;
}

.table-wrap.wide table,
.compare-table table {
  min-width: 920px;
}

.matrix-table table,
.kv-table {
  min-width: 760px;
}

.explore-table-wrap table {
  min-width: 1080px;
}

table {
  width: 100%;
  min-width: 0;
  border-collapse: collapse;
  table-layout: fixed;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
}

th,
td {
  min-width: 0;
  padding: 12px 14px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
  overflow-wrap: anywhere;
  word-break: break-word;
}

th {
  background: var(--surfaceAlt);
  color: var(--faint);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

tr:hover td {
  background: color-mix(in oklch, var(--surfaceAlt) 46%, transparent);
}

.kv-table {
  min-width: 0;
}

.kv-table th {
  width: 34%;
  max-width: 180px;
}

.kv-table td {
  width: 66%;
}

.test-name-cell a {
  display: -webkit-box;
  color: var(--link);
  font-weight: 600;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  white-space: normal;
}

.test-name-cell .muted,
.scope-cell span,
.signal-cell span {
  display: block;
  line-height: 1.3;
}

.test-name-cell .muted {
  margin-top: 3px;
  font-size: 12px;
}

.scope-cell span + span,
.signal-cell span + span {
  margin-top: 3px;
}

pre {
  max-width: 100%;
  max-height: 420px;
  padding: 14px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  background: var(--surfaceAlt);
  border: 1px solid var(--border);
  border-radius: var(--radius-inner);
}

pre span[data-line],
code {
  display: block;
  max-width: 100%;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

summary {
  cursor: pointer;
  color: var(--link);
  font-weight: 700;
}

.donut-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.donut {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  box-shadow: inset 0 0 0 24px var(--surface);
}

.donut strong {
  min-width: 72px;
  padding: 18px 10px;
  text-align: center;
  border-radius: 999px;
  background: var(--surface);
}

.legend,
.risk-list,
.coverage-list,
.export-links,
.attention-list,
.impact-list {
  display: grid;
  gap: 8px;
}

.legend span {
  display: inline-flex;
  gap: 7px;
  align-items: center;
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}

.risk-list {
  max-height: 360px;
  overflow: auto;
  padding-right: 4px;
}

.risk,
.attention-item,
.impact-item {
  min-width: 0;
  padding: 10px 12px;
  border-radius: var(--radius-inner);
  background: var(--surfaceAlt);
  overflow: hidden;
}

.risk {
  border-left: 4px solid var(--secondary);
}

.risk.high,
.attention-item,
.impact-item {
  border-left: 4px solid var(--fail);
  background: color-mix(in oklch, var(--failSoft) 62%, var(--surface));
}

.risk.medium {
  border-left-color: var(--flaky);
}

.share-banner {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  padding: 14px 16px;
  border-radius: var(--radius-card);
  color: var(--pass);
  background: color-mix(in oklch, var(--passSoft) 62%, var(--surface));
  border: 1px solid color-mix(in oklch, var(--pass) 28%, var(--border));
}

.safe-badge,
.tag,
.impact-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: 100%;
  border-radius: 100px;
  padding: 5px 9px;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.safe-badge {
  color: var(--pass);
  background: var(--passSoft);
  border: 1px solid color-mix(in oklch, var(--pass) 28%, var(--border));
  font-weight: 700;
}

.tag,
.impact-pill {
  color: var(--muted);
  background: var(--surfaceAlt);
  border: 1px solid var(--border);
}

.matrix-page,
.report-card-grid,
.explore-card-grid,
.print-summary {
  display: grid;
  gap: 16px;
}

.report-card-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));
}

.explore-card-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr));
}

.matrix-heatmap {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

body[data-matrix-view="table"] .matrix-heatmap {
  display: none;
}

body[data-matrix-view="heatmap-only"] .matrix-table {
  display: none;
}

.heat-cell {
  display: grid;
  gap: 12px;
  align-content: start;
  min-width: 0;
  padding: 18px;
  border-radius: var(--radius-card);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.heat-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.heat-name {
  min-width: 0;
  color: var(--text);
  font-size: 14px;
  line-height: 1.35;
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.heat-value {
  flex: 0 0 auto;
  white-space: nowrap;
  font-weight: 700;
}

.heat-bar {
  height: 8px;
  margin: 2px 0;
  border-radius: 100px;
  background: var(--surfaceAlt);
  overflow: hidden;
}

.heat-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--flaky);
}

.heat-cell.status-passed .heat-bar span {
  background: var(--pass);
}

.heat-cell.status-failed .heat-bar span {
  background: var(--fail);
}

.heat-cell.status-skipped .heat-bar span,
.heat-cell.status-unknown .heat-bar span {
  background: var(--skip);
}

.heat-details,
.heat-failures {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.heat-details {
  display: grid;
  gap: 3px;
}

.empty-state {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 128px;
  padding: 28px;
  color: var(--muted);
  text-align: center;
  border-style: dashed;
}

img.preview,
video,
svg {
  max-width: 100%;
  height: auto;
}

img.preview {
  border: 1px solid var(--border);
  border-radius: var(--radius-inner);
}

@media (min-width: 901px) {
  body {
    padding-left: var(--sidebar-width);
  }

  .nav-shell {
    position: fixed;
    inset: 0 auto 0 0;
    width: var(--sidebar-width);
    display: flex;
    flex-direction: column;
    padding: 20px 12px;
    overflow-y: auto;
    background: var(--chrome);
    border-right: 1px solid var(--chromeBorder);
  }

  .app-nav {
    display: flex;
    min-height: 100%;
    flex-direction: column;
    gap: 4px;
  }

  .theme-panel {
    margin-top: auto;
    padding: 16px 8px 0;
    border-top: 1px solid var(--chromeBorder);
  }
}

@media (max-width: 1100px) {
  .grid.three,
  .grid.four {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  body {
    padding-left: 0;
  }

  .hero,
  section {
    width: auto;
    margin-left: 16px;
    margin-right: 16px;
  }

  .hero {
    flex-direction: column;
    padding-top: 24px;
  }

  .nav-shell {
    position: sticky;
    top: 0;
    display: grid;
    gap: 8px;
    padding: 10px 12px;
    background: color-mix(in oklch, var(--surface) 94%, transparent);
    border-bottom: 1px solid var(--border);
    box-shadow: var(--shadow);
    backdrop-filter: blur(12px);
  }

  .mobile-nav-toggle {
    display: flex;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    font-weight: 800;
    background: var(--surface);
  }

  .mobile-nav-toggle::after {
    content: "Open";
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
  }

  .nav-shell.open .mobile-nav-toggle::after {
    content: "Close";
  }

  .app-nav {
    display: none;
    max-height: min(72vh, 520px);
    overflow: auto;
    gap: 4px;
    padding: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-inner);
  }

  .nav-shell.open .app-nav {
    display: grid;
  }

  .nav-brand {
    margin: 0 0 8px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }

  .theme-panel {
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }

  .grid.two,
  .grid.three,
  .grid.four {
    grid-template-columns: 1fr;
  }

  .toolbar label,
  .result-strip label,
  .search-box {
    flex: 1 1 100%;
    min-width: 0;
  }

  .hbar-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .metrics {
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  }
}

@media (max-width: 560px) {
  body {
    font-size: 13px;
  }

  h1 {
    font-size: 24px;
  }

  article,
  .metric,
  .toolbar {
    padding: 16px;
  }

  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mini-stat-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 14px;
  }

  .mini-stat-row strong {
    font-size: 15px;
  }

  .metric strong {
    font-size: 22px;
  }

  .table-wrap table {
    min-width: 760px;
  }
}

@media print {
  body {
    padding-left: 0;
    background: white;
  }

  .nav-shell,
  .toolbar,
  .hero-actions,
  .button,
  button {
    display: none !important;
  }

  .hero,
  section {
    width: auto;
    max-width: none;
    margin: 18px 0;
  }

  article,
  .metric,
  .table-wrap {
    box-shadow: none;
  }
}
"""
