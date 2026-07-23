"""Shared report shell: the sidebar layout, theme controls, and page document.

The visual system is defined once here so single-run report pages and the
retained-run portfolio pages present an identical shell. Colors come from the
design tokens in :mod:`automation_core.reporting.design_system`; layout is
inline-styled and references those tokens through CSS custom properties.

Two navigation modes exist, matching the report design system:

* ``portfolio`` -- Portfolio / Reports / Compare, with a "Report Portfolio"
  context block.
* ``report`` -- Executive / Overview / Quality Gates / Tests / Timeline /
  Flaky / Matrix / History / Share, with a run-id context block, status pill,
  timestamp and an "All Reports" back link.
"""

from __future__ import annotations

from html import escape
from typing import Any

from automation_core.reporting.design_system import report_design_styles

# Navigation definitions -------------------------------------------------------

PORTFOLIO_NAV: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Portfolio", "index.html"),
    ("reports", "Reports", "reports.html"),
    ("compare", "Compare", "compare.html"),
)

REPORT_NAV: tuple[tuple[str, str, str], ...] = (
    ("executive", "Executive", "executive.html"),
    ("dashboard", "Overview", "index.html"),
    ("quality", "Quality Gates", "quality.html"),
    ("explore", "Tests", "explore.html"),
    ("timeline", "Timeline", "timeline.html"),
    ("flaky", "Flaky", "flaky.html"),
    ("matrix", "Matrix", "matrix.html"),
    ("history", "History", "history.html"),
    ("share", "Share", "share.html"),
)

# Brand logo glyph (bar chart) -------------------------------------------------

_LOGO_SVG = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" '
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 19V10M12 19V5M20 19v-6"/></svg>'
)


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _brand() -> str:
    return (
        '<div style="display:flex; align-items:center; gap:9px; margin-bottom:18px;">'
        '<div style="width:30px; height:30px; border-radius:8px; background:var(--accent); '
        'display:flex; align-items:center; justify-content:center; flex-shrink:0;">'
        f"{_LOGO_SVG}</div>"
        "<span style=\"font-family:'Manrope',sans-serif; font-size:14px; font-weight:700; "
        'color:var(--text); letter-spacing:-0.01em;">Automation Core</span>'
        "</div>"
    )


def _nav_items(nav: tuple[tuple[str, str, str], ...], active: str, prefix: str) -> str:
    rows = []
    for key, label, href in nav:
        is_active = key == active
        bg = "var(--accentSoft)" if is_active else "transparent"
        color = "var(--accent)" if is_active else "var(--muted)"
        bar = "var(--accent)" if is_active else "transparent"
        rows.append(
            f'<a href="{_e(prefix + href)}" class="nav-item" '
            f'style="display:flex; align-items:center; gap:10px; padding:9px 12px; '
            f"border-radius:9px; font-size:13.5px; font-weight:600; text-decoration:none; "
            f'background:{bg}; color:{color};" aria-current="{"page" if is_active else "false"}">'
            f'<span style="width:3px; height:15px; border-radius:100px; background:{bar}; '
            f'flex-shrink:0;"></span>{_e(label)}</a>'
        )
    return "".join(rows)


def _appearance() -> str:
    choices = (("system", "Auto"), ("light", "Light"), ("dark", "Dark"))
    buttons = "".join(
        f'<button type="button" data-theme-choice="{value}" '
        f'aria-pressed="{"true" if value == "system" else "false"}" '
        f'style="flex:1; text-align:center; padding:6px 0; border:0; border-radius:7px; '
        f"font-size:12px; font-weight:600; cursor:pointer; font-family:inherit; "
        f'background:transparent; color:var(--muted);">{_e(label)}</button>'
        for value, label in choices
    )
    return (
        '<div style="padding:14px 20px 20px; border-top:1px solid var(--chromeBorder);">'
        '<div style="font-size:11px; font-weight:600; letter-spacing:0.06em; '
        'text-transform:uppercase; color:var(--faint); margin-bottom:8px;">Appearance</div>'
        '<div role="group" aria-label="Appearance theme" '
        'style="display:flex; gap:4px; background:var(--surfaceAlt); padding:3px; '
        f'border-radius:9px;">{buttons}</div></div>'
    )


def _context_portfolio() -> str:
    return (
        "<div style=\"font-family:'Manrope',sans-serif; font-size:15px; font-weight:700; "
        'color:var(--text);">Report Portfolio</div>'
        '<div style="font-size:11px; color:var(--faint); margin-top:6px; line-height:1.5;">'
        "Every retained run in one place.</div>"
    )


def _context_report(run: dict[str, Any], prefix: str) -> str:
    run_id = run.get("run_id", "")
    status_label = run.get("status_label", "Ready")
    status_color = run.get("status_color", "var(--pass)")
    status_soft = run.get("status_soft", "var(--passSoft)")
    timestamp = run.get("timestamp", "")
    back = _e(prefix + "../../index.html")
    return (
        f'<a href="{back}" style="display:inline-flex; align-items:center; gap:5px; '
        "font-size:12px; font-weight:600; color:var(--link); text-decoration:none; "
        'margin-bottom:12px;">&#8592; All Reports</a>'
        "<div style=\"font-family:'Manrope',sans-serif; font-size:14.5px; font-weight:700; "
        f'color:var(--text); overflow-wrap:anywhere; line-height:1.3;">{_e(run_id)}</div>'
        '<div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap;">'
        '<span style="display:inline-flex; align-items:center; gap:5px; padding:3px 9px; '
        f"border-radius:100px; font-size:11px; font-weight:700; letter-spacing:0.02em; "
        f'background:{status_soft}; color:{status_color};">'
        f'<span style="width:6px; height:6px; border-radius:50%; background:{status_color}; '
        f'display:inline-block;"></span>{_e(status_label)}</span>'
        "<span style=\"font-size:11px; color:var(--faint); font-family:'IBM Plex Mono',monospace;\">"
        f"{_e(timestamp)}</span></div>"
    )


def sidebar(
    mode: str,
    *,
    active: str,
    prefix: str = "",
    run: dict[str, Any] | None = None,
) -> str:
    """Render the left sidebar for ``portfolio`` or ``report`` mode."""

    if mode == "report":
        nav = REPORT_NAV
        context = _context_report(run or {}, prefix)
    else:
        nav = PORTFOLIO_NAV
        context = _context_portfolio()
    # The aside stretches to the full shell height so the ``chrome`` background
    # fills the entire left column; the inner block is sticky and viewport-tall
    # so the brand, nav and appearance control stay in view while scrolling.
    return (
        '<aside class="app-sidebar" style="width:236px; flex-shrink:0; align-self:stretch; '
        "background:var(--chrome); border-right:1px solid var(--chromeBorder); "
        'color:var(--chromeText);">'
        '<div class="app-sidebar-inner" style="position:sticky; top:0; height:100vh; '
        'overflow-y:auto; display:flex; flex-direction:column;">'
        f'<div style="padding:20px 18px 14px;">{_brand()}{context}</div>'
        '<nav class="report-nav" aria-label="Report navigation" '
        'style="flex:1; padding:8px 12px; display:flex; flex-direction:column; gap:2px;">'
        f"{_nav_items(nav, active, prefix)}</nav>"
        f"{_appearance()}"
        "</div></aside>"
    )


def _theme_bootstrap() -> str:
    return (
        "(function(){try{var m=localStorage.getItem('automation-report-theme')||'system';"
        "if(!/^(system|light|dark)$/.test(m))m='system';"
        "document.documentElement.dataset.theme=m;}catch(e){"
        "document.documentElement.dataset.theme='system';}})();"
    )


def _shell_script() -> str:
    # Theme toggle + mobile drawer + share-link copy. Page-specific behaviour is
    # injected separately by each renderer.
    return """
function setupTheme(){
  var allowed={system:1,light:1,dark:1};
  var key='automation-report-theme';
  var saved;try{saved=localStorage.getItem(key)||'system';}catch(e){saved='system';}
  function apply(mode){
    var t=allowed[mode]?mode:'system';
    document.documentElement.dataset.theme=t;
    if(document.body)document.body.dataset.theme=t;
    document.querySelectorAll('[data-theme-choice]').forEach(function(b){
      var on=b.dataset.themeChoice===t;
      b.setAttribute('aria-pressed',on?'true':'false');
      b.style.background=on?'var(--surface)':'transparent';
      b.style.color=on?'var(--text)':'var(--muted)';
      b.style.boxShadow=on?'0 1px 2px rgba(15,23,42,0.12)':'none';
    });
    try{localStorage.setItem(key,t);}catch(e){}
  }
  document.querySelectorAll('[data-theme-choice]').forEach(function(b){
    b.addEventListener('click',function(){apply(b.dataset.themeChoice);});
  });
  apply(saved);
}
function setupDrawer(){
  var t=document.querySelector('[data-drawer-toggle]');
  var shell=document.querySelector('[data-app-shell]');
  if(!t||!shell)return;
  t.addEventListener('click',function(){shell.classList.toggle('drawer-open');});
}
function setupShareLinks(){
  document.querySelectorAll('[data-copy-share-link]').forEach(function(b){
    b.addEventListener('click',function(){
      var v=b.dataset.copyShareLink||window.location.href;
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(v).then(function(){b.textContent='Copied';})
          .catch(function(){window.prompt('Copy report link',v);});
      }else{window.prompt('Copy report link',v);}
    });
  });
}
function setupTrendPoints(){
  // Each trend data point is one run: hover shows its id + pass rate, click opens that run.
  var tip=document.createElement('div');
  tip.style.cssText='position:fixed;z-index:200;pointer-events:none;opacity:0;transition:opacity .1s ease;'
    +'background:var(--text);color:var(--bg);font:600 11.5px/1.4 \\'IBM Plex Mono\\',monospace;'
    +'padding:6px 9px;border-radius:7px;box-shadow:0 6px 20px -6px rgba(0,0,0,0.4);white-space:nowrap;max-width:70vw;overflow:hidden;text-overflow:ellipsis;';
  document.body.appendChild(tip);
  var over=function(t){tip.textContent=t.getAttribute('data-trend-label')||'';tip.style.opacity='1';};
  document.addEventListener('mouseover',function(e){var t=e.target.closest('[data-trend-label]');if(t)over(t);});
  document.addEventListener('mousemove',function(e){if(tip.style.opacity==='1'){var x=Math.min(e.clientX+14,window.innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=Math.max(8,e.clientY-34)+'px';}});
  document.addEventListener('mouseout',function(e){if(e.target.closest('[data-trend-label]'))tip.style.opacity='0';});
  document.addEventListener('click',function(e){var t=e.target.closest('[data-trend-href]');if(t){var h=t.getAttribute('data-trend-href');if(h)window.location.href=h;}});
}
"""


_RESPONSIVE_CSS = """
.app-main{flex:1; min-width:0; padding:32px 40px 64px;}
.app-main-inner{max-width:1320px; margin:0 auto;}
.drawer-toggle{display:none;}
@media (max-width: 900px){
  .app-shell{flex-direction:column !important;}
  .app-sidebar{align-self:auto !important; width:100% !important;
    border-right:0 !important; border-bottom:1px solid var(--chromeBorder) !important;}
  .app-sidebar-inner{position:static !important; height:auto !important; overflow:visible !important;}
  .app-sidebar .report-nav{flex-direction:row !important; flex-wrap:wrap !important;}
  .app-main{padding:20px !important;}
  .grid-2,.grid-3,.grid-4,.grid-5{grid-template-columns:1fr !important;}
}
@media (max-width: 560px){
  .app-main{padding:16px !important;}
}
"""


def document(
    title: str,
    *,
    sidebar_html: str,
    main_html: str,
    extra_scripts: str = "",
    data_json_script: str = "",
) -> str:
    """Assemble a full report document with the shared shell."""

    return f"""<!doctype html>
<html lang="en" data-theme="system">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <script>{_theme_bootstrap()}</script>
  <style>{report_design_styles()}{_RESPONSIVE_CSS}</style>
</head>
<body>
  <div class="app-shell" data-app-shell style="background:var(--bg); color:var(--text); \
min-height:100vh; display:flex; font-family:'IBM Plex Sans',sans-serif;">
    {sidebar_html}
    <main class="app-main"><div class="app-main-inner">{main_html}</div></main>
  </div>
  {data_json_script}
  <script>
{_shell_script()}
{extra_scripts}
  document.addEventListener('DOMContentLoaded', function(){{
    setupTheme(); setupDrawer(); setupShareLinks(); setupTrendPoints();
    if (typeof setupPage === 'function') setupPage();
  }});
  </script>
</body>
</html>
"""
