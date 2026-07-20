"""Design-faithful renderers for the retained-run portfolio pages.

These build the Portfolio Dashboard, Reports gallery and Compare pages on top of
the shared sidebar shell (:mod:`automation_core.reporting.shell`). Aggregate
views are hydrated client-side from the embedded ``portfolio-data.json`` so the
search / status / platform filters stay reactive without a server round-trip,
mirroring the design's behaviour. All colours reference design tokens.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from automation_core.reporting import shell

PLATFORM_COLORS = {"web": "var(--accent)", "mobile": "var(--flaky)", "api": "var(--broken)"}


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _json_for_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _page_header(eyebrow: str, title: str, subtitle: str, *, action: str = "") -> str:
    action_html = f'<div style="margin-left:auto;">{action}</div>' if action else ""
    return (
        '<div style="display:flex; align-items:flex-start; gap:16px; margin-bottom:24px;">'
        "<div>"
        '<div style="font-size:12px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; '
        f'color:var(--faint); margin-bottom:6px;">{_e(eyebrow)}</div>'
        "<h1 style=\"font-family:'Manrope',sans-serif; font-size:28px; font-weight:800; margin:0 0 6px; "
        f'color:var(--text); letter-spacing:-0.01em;">{_e(title)}</h1>'
        f'<p style="font-size:14px; color:var(--muted); margin:0; max-width:60ch;">{_e(subtitle)}</p>'
        "</div>"
        f"{action_html}</div>"
    )


def _filter_bar() -> str:
    input_style = (
        "flex:1; min-width:200px; padding:10px 14px; border-radius:9px; border:1px solid var(--border); "
        "background:var(--surface); color:var(--text); font-size:14px; font-family:inherit;"
    )
    select_style = (
        "padding:9px 12px; border-radius:8px; border:1px solid var(--border); background:var(--surface); "
        "color:var(--text); font-size:13px; font-family:inherit; cursor:pointer;"
    )
    btn_style = (
        "padding:9px 16px; border-radius:8px; border:1px solid var(--border); background:var(--surface); "
        "color:var(--text); font-size:13px; font-weight:600; cursor:pointer; font-family:inherit;"
    )
    return (
        '<div style="background:var(--surface); border:1px solid var(--border); border-radius:16px; '
        "box-shadow:var(--shadow); padding:18px; margin-bottom:22px; display:flex; gap:12px; "
        'flex-wrap:wrap; align-items:center;">'
        f'<input id="pf-search" type="search" placeholder="Search run id" style="{input_style}">'
        f'<select id="pf-status" style="{select_style}">'
        '<option value="">All statuses</option><option value="ready">Ready</option>'
        '<option value="blocked">Blocked</option></select>'
        f'<select id="pf-platform" style="{select_style}">'
        '<option value="">All platforms</option><option value="web">Web</option>'
        '<option value="mobile">Mobile</option><option value="api">API</option></select>'
        f'<button type="button" id="pf-reset" style="{btn_style}">Reset</button>'
        "</div>"
    )


def _card(inner: str, *, pad: int = 20, extra: str = "") -> str:
    return (
        f'<div style="background:var(--surface); border:1px solid var(--border); border-radius:16px; '
        f'box-shadow:var(--shadow); padding:{pad}px; {extra}">{inner}</div>'
    )


def _data_script(data: dict[str, Any]) -> str:
    return f'<script type="application/json" id="portfolio-data">{_json_for_script(data)}</script>'


# --- Dashboard --------------------------------------------------------------


def render_dashboard(data: dict[str, Any]) -> str:
    browse_btn = (
        '<a href="reports.html" style="display:inline-flex; align-items:center; gap:8px; padding:11px 18px; '
        "background:var(--accent); color:#fff; border-radius:10px; font-size:14px; font-weight:700; "
        "text-decoration:none; font-family:'Manrope',sans-serif;\">Browse All Reports &#8594;</a>"
    )
    main = (
        _page_header(
            "Report Portfolio",
            "Portfolio Dashboard",
            "History and health across every retained run — web, mobile, and API.",
        )
        + _filter_bar()
        + '<div id="pf-hero" style="margin-bottom:22px;"></div>'
        + '<div id="pf-insights" style="display:grid; grid-template-columns:1fr 1fr; gap:20px; '
        'margin-bottom:22px;" class="grid-2"></div>'
        + '<div id="pf-kpis" style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:22px;"></div>'
        + '<div style="display:grid; grid-template-columns:1.3fr 1fr; gap:20px; margin-bottom:22px;" class="grid-2">'
        + _card(
            "<h2 style=\"font-family:'Manrope',sans-serif; font-size:16px; font-weight:700; margin:0 0 16px;\">"
            'Pass Rate Trend</h2><div id="pf-trend"></div>'
            '<p style="font-size:11.5px; color:var(--faint); margin:14px 0 0; line-height:1.5;">'
            "Each line is one platform's pass rate across every run that included it, oldest → newest.</p>"
        )
        + _card(
            "<h2 style=\"font-family:'Manrope',sans-serif; font-size:16px; font-weight:700; margin:0 0 16px;\">"
            'Run Outcomes</h2><div id="pf-outcomes"></div>'
        )
        + "</div>"
        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:24px;" class="grid-2">'
        + _card(
            "<h2 style=\"font-family:'Manrope',sans-serif; font-size:16px; font-weight:700; margin:0 0 16px;\">"
            'Platform Coverage</h2><div id="pf-coverage"></div>'
        )
        + _card(
            "<h2 style=\"font-family:'Manrope',sans-serif; font-size:16px; font-weight:700; margin:0 0 16px;\">"
            'Runs Needing Attention</h2><div id="pf-attention"></div>'
        )
        + "</div>"
        + browse_btn
    )
    sidebar_html = shell.sidebar("portfolio", active="dashboard")
    return shell.document(
        "Portfolio Dashboard",
        sidebar_html=sidebar_html,
        main_html=main,
        data_json_script=_data_script(data),
        extra_scripts=_DASHBOARD_JS,
    )


# --- Reports gallery --------------------------------------------------------


def render_reports(data: dict[str, Any]) -> str:
    main = (
        _page_header(
            "Report Portfolio",
            "All Reports",
            "Open a run, or add up to 5 to a side-by-side comparison.",
        )
        + _filter_bar()
        + '<div id="pf-count" style="font-size:13px; color:var(--muted); margin-bottom:14px;"></div>'
        + '<div id="pf-gallery" style="display:grid; grid-template-columns:repeat(2,1fr); gap:18px;" class="grid-2">'
        "</div>"
    )
    sidebar_html = shell.sidebar("portfolio", active="reports")
    return shell.document(
        "All Reports",
        sidebar_html=sidebar_html,
        main_html=main,
        data_json_script=_data_script(data),
        extra_scripts=_REPORTS_JS,
    )


# --- Compare ----------------------------------------------------------------


def render_compare(data: dict[str, Any]) -> str:
    main = (
        _page_header(
            "Report Portfolio",
            "Compare Reports",
            "Select up to 5 runs to compare side by side, across any platform.",
        )
        + '<div id="cmp-picker" style="margin-bottom:22px;"></div>'
        + '<div id="cmp-scorecards" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); '
        'gap:18px; margin-bottom:22px;"></div>'
        + '<div id="cmp-bars" style="display:grid; grid-template-columns:repeat(3,1fr); gap:18px; '
        'margin-bottom:22px;" class="grid-3"></div>'
        + '<div id="cmp-delta" style="margin-bottom:22px;"></div>'
        + '<div id="cmp-impact"></div>'
    )
    sidebar_html = shell.sidebar("portfolio", active="compare")
    return shell.document(
        "Compare Reports",
        sidebar_html=sidebar_html,
        main_html=main,
        data_json_script=_data_script(data),
        extra_scripts=_COMPARE_JS,
    )


# --- Shared client helpers --------------------------------------------------

_SHARED_JS = r"""
function pfData(){var n=document.getElementById('portfolio-data');return n?JSON.parse(n.textContent):{reports:[],summary:{}};}
function esc(v){var t=(v==null?'':String(v));return t.replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function fmtDur(ms){ms=Number(ms)||0;if(ms<1000)return Math.round(ms)+'ms';var s=ms/1000;if(s<60)return (Math.round(s*10)/10)+'s';var m=s/60;return (Math.round(m*10)/10)+'m';}
function pfColor(p){return {web:'var(--accent)',mobile:'var(--flaky)',api:'var(--broken)'}[p]||'var(--muted)';}
function matchReport(r,q,status,platform){
  if(status && (r.readiness||'')!==status)return false;
  if(platform && !(r.platforms&&r.platforms[platform]))return false;
  if(q){var hay=((r.run_id||'')+' '+(r.project_name||'')+' '+(r.framework||'')).toLowerCase();if(hay.indexOf(q.toLowerCase())<0)return false;}
  return true;
}
function areaPath(series,w,h){
  if(!series.length)return{line:'',area:''};
  var pad=12,innerW=w-pad*2,innerH=h-16;
  var xs=series.length===1?[w/2]:series.map(function(_,i){return pad+i/(series.length-1)*innerW;});
  var ys=series.map(function(v){return h-8-(Math.max(0,Math.min(100,v))/100)*innerH;});
  var pts=xs.map(function(x,i){return x.toFixed(1)+','+ys[i].toFixed(1);});
  var line=pts.join(' ');
  var area='M'+xs[0].toFixed(1)+','+(h-8).toFixed(1)+' L'+line.replace(/ /g,' L')+' L'+xs[xs.length-1].toFixed(1)+','+(h-8).toFixed(1)+' Z';
  return{line:line,area:area,xs:xs,ys:ys};
}
"""

_DASHBOARD_JS = (
    _SHARED_JS
    + r"""
var pfState={q:'',status:'',platform:''};
function pfFiltered(){var d=pfData();return (d.reports||[]).filter(function(r){return matchReport(r,pfState.q,pfState.status,pfState.platform);});}
function ring(score){
  var s=Math.max(0,Math.min(100,Math.round(score)));
  var col=s>=80?'var(--pass)':(s>=60?'var(--flaky)':'var(--fail)');
  return '<div style="width:118px;height:118px;border-radius:50%;flex-shrink:0;background:conic-gradient('+col+' 0 '+s+'%,var(--surfaceAlt) '+s+'% 100%);display:flex;align-items:center;justify-content:center;">'
    +'<div style="width:88px;height:88px;border-radius:50%;background:var(--surface);display:flex;flex-direction:column;align-items:center;justify-content:center;">'
    +'<strong style="font-family:\'IBM Plex Mono\',monospace;font-size:26px;font-weight:600;color:'+col+';line-height:1;">'+s+'</strong>'
    +'<span style="font-size:10px;font-weight:600;letter-spacing:0.08em;color:var(--faint);margin-top:3px;">HEALTH</span></div></div>';
}
function statTile(value,label,delta){
  var d='';
  if(delta){var pos=/^\+/.test(delta);d='<span style="display:inline-block;margin-top:6px;padding:2px 7px;border-radius:100px;font-size:10.5px;font-weight:700;font-family:\'IBM Plex Mono\',monospace;background:'+(pos?'var(--failSoft)':'var(--passSoft)')+';color:'+(pos?'var(--fail)':'var(--pass)')+';">'+esc(delta)+'</span>';}
  return '<div style="flex:1;min-width:130px;background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:18px;">'
    +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:25px;font-weight:600;color:var(--text);line-height:1;">'+esc(value)+'</div>'
    +'<div style="font-size:12.5px;color:var(--muted);margin-top:8px;">'+esc(label)+'</div>'+d+'</div>';
}
function renderDashboard(){
  var reports=pfFiltered();
  var total=reports.length;
  var ready=reports.filter(function(r){return r.readiness==='ready';}).length;
  var blocked=total-ready;
  var health=total?Math.round(reports.reduce(function(a,r){return a+(typeof r.quality_score==='number'?r.quality_score:r.pass_rate);},0)/total):0;
  var latest=reports[0]||{};
  var latestPass=Number(latest.pass_rate||0);
  var totalTests=reports.reduce(function(a,r){return a+(r.total||0);},0);
  var totalFlaky=reports.reduce(function(a,r){return a+(r.flaky||0);},0);
  var totalDur=reports.reduce(function(a,r){return a+(r.duration_ms||0);},0);
  // hero
  var gatePill,sentence;
  if(blocked){gatePill='<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:0.02em;background:var(--failSoft);color:var(--fail);"><span style="width:6px;height:6px;border-radius:50%;background:var(--fail);"></span>'+blocked+' RUN'+(blocked>1?'S':'')+' BLOCKED</span>';
    sentence=blocked+' of '+total+' run(s) are blocked and need attention before release.';}
  else{gatePill='<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:0.02em;background:var(--passSoft);color:var(--pass);"><span style="width:6px;height:6px;border-radius:50%;background:var(--pass);"></span>ALL RUNS READY</span>';
    sentence='All '+total+' retained run(s) are currently release-ready.';}
  var rw=total?(ready/total*100):0, bw=total?(blocked/total*100):0;
  var segBar='<div style="display:flex;height:12px;border-radius:100px;overflow:hidden;background:var(--surfaceAlt);margin-top:auto;">'
    +(ready?'<span style="width:'+rw.toFixed(2)+'%;background:var(--pass);"></span>':'')
    +(blocked?'<span style="width:'+bw.toFixed(2)+'%;background:var(--fail);"></span>':'')+'</div>'
    +'<div style="display:flex;gap:16px;margin-top:10px;font-size:12px;color:var(--muted);">'
    +'<span style="display:inline-flex;align-items:center;gap:6px;"><i style="width:9px;height:9px;border-radius:2px;background:var(--pass);display:inline-block;"></i>Ready '+ready+'</span>'
    +'<span style="display:inline-flex;align-items:center;gap:6px;"><i style="width:9px;height:9px;border-radius:2px;background:var(--fail);display:inline-block;"></i>Blocked '+blocked+'</span></div>';
  var passSeries=reports.slice().reverse().map(function(r){return Number(r.pass_rate||0);});
  var sp=areaPath(passSeries.length?passSeries:[latestPass],300,64);
  var spark='<svg viewBox="0 0 300 64" style="width:100%;height:64px;margin:8px 0;" preserveAspectRatio="none"><polyline points="'+sp.line+'" fill="none" stroke="var(--pass)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var hero='<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:20px;" class="grid-2">'
    +'<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--heroShadow);padding:22px;display:flex;flex-direction:column;">'
    +'<div style="display:flex;gap:20px;align-items:center;margin-bottom:18px;">'+ring(health)
    +'<div>'+gatePill+'<p style="font-size:14px;color:var(--muted);margin:12px 0 0;line-height:1.5;">'+esc(sentence)+'</p></div></div>'+segBar+'</div>'
    +'<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--heroShadow);padding:22px;">'
    +'<div style="font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);">Latest Pass Rate</div>'
    +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:46px;font-weight:600;color:var(--text);line-height:1.1;margin-top:4px;">'+Math.round(latestPass)+'%</div>'+spark
    +'<div style="display:flex;justify-content:space-between;border-top:1px solid var(--border);padding-top:12px;margin-top:4px;">'
    +'<span><strong style="font-family:\'IBM Plex Mono\',monospace;display:block;font-size:16px;">'+total+'</strong><span style="font-size:11.5px;color:var(--faint);">Runs</span></span>'
    +'<span><strong style="font-family:\'IBM Plex Mono\',monospace;display:block;font-size:16px;color:var(--fail);">'+blocked+'</strong><span style="font-size:11.5px;color:var(--faint);">Blocked</span></span>'
    +'<span style="text-align:right;"><strong style="font-family:\'IBM Plex Mono\',monospace;display:block;font-size:16px;color:var(--flaky);">'+totalFlaky+'</strong><span style="font-size:11.5px;color:var(--faint);">Flaky</span></span></div></div></div>';
  document.getElementById('pf-hero').innerHTML=hero;
  // insights
  var wins=[],focus=[];
  var pf=aggPlatforms(reports);
  var best=Object.keys(pf).sort(function(a,b){return pf[b].pass-pf[a].pass;})[0];
  if(best)wins.push(best.charAt(0).toUpperCase()+best.slice(1)+' is the strongest platform at '+Math.round(pf[best].pass)+'% pass rate.');
  if(ready)wins.push(ready+' of '+total+' run(s) are release-ready.');
  var healed=reports.reduce(function(a,r){return a+(r.healing_event_count||0);},0);
  if(healed)wins.push('Self-healing recovered '+healed+' failure(s) across retained runs.');
  if(!wins.length)wins.push('No positive release signal yet.');
  reports.filter(function(r){return r.readiness==='blocked';}).slice(0,3).forEach(function(r){
    focus.push(esc(r.run_id)+' is blocked — '+(r.failed_total||0)+' failed, '+Math.round(r.pass_rate)+'% pass.');});
  Object.keys(pf).forEach(function(p){if(pf[p].pass<50)focus.push(p.charAt(0).toUpperCase()+p.slice(1)+' lags at '+Math.round(pf[p].pass)+'% pass rate.');});
  if(!focus.length)focus.push('No retained runs currently need attention.');
  function insight(title,items,bg,color,icon){
    return '<div style="background:'+bg+';border-radius:16px;padding:20px 22px;">'
      +'<h2 style="font-family:\'Manrope\',sans-serif;font-size:16px;font-weight:700;margin:0 0 12px;color:'+color+';display:flex;align-items:center;gap:8px;">'+icon+esc(title)+'</h2>'
      +'<ul style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:9px;">'
      +items.map(function(i){return '<li style="font-size:13px;color:var(--text);line-height:1.45;padding-left:16px;position:relative;"><span style="position:absolute;left:0;color:'+color+';">•</span>'+i+'</li>';}).join('')+'</ul></div>';
  }
  document.getElementById('pf-insights').innerHTML=
    insight('Key Wins',wins,'var(--passSoft)','var(--pass)','<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>')
    +insight('Focus Areas',focus,'var(--failSoft)','var(--fail)','<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>');
  // kpis
  document.getElementById('pf-kpis').innerHTML=
    statTile(total,'Runs')+statTile(Math.round(latestPass)+'%','Latest Pass Rate')
    +statTile(blocked,'Blocked Runs')+statTile(totalFlaky,'Flaky Tests')
    +statTile(totalTests,'Total Tests')+statTile(fmtDur(totalDur),'Duration');
  // trend
  renderTrend(reports);
  // outcomes
  var maxOut=Math.max(ready,blocked,1);
  document.getElementById('pf-outcomes').innerHTML=
    outcomeRow('Ready',ready,maxOut,'var(--pass)')+outcomeRow('Blocked',blocked,maxOut,'var(--fail)');
  // coverage
  renderCoverage(pf);
  // attention
  var att=reports.filter(function(r){return r.readiness==='blocked';});
  document.getElementById('pf-attention').innerHTML=att.length?att.map(function(r){
    return '<div style="padding:12px 0;border-top:1px solid var(--border);"><a href="'+esc(r.entry_href)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:13.5px;font-weight:600;color:var(--link);text-decoration:none;">'+esc(r.run_id)+'</a>'
      +'<div style="font-size:12px;color:var(--muted);margin-top:4px;">'+esc(r.generated_display)+' · '+(r.failed_total||0)+' failed · '+(r.flaky||0)+' flaky · '+Math.round(r.pass_rate)+'% pass</div></div>';
  }).join(''):'<p style="font-size:13px;color:var(--faint);padding:8px 0;">Every retained run is release-ready.</p>';
}
function aggPlatforms(reports){
  var acc={};
  reports.forEach(function(r){var p=r.platforms||{};Object.keys(p).forEach(function(k){acc[k]=acc[k]||{total:0,passed:0};acc[k].total+=p[k].total||0;acc[k].passed+=p[k].passed||0;});});
  Object.keys(acc).forEach(function(k){acc[k].pass=acc[k].total?acc[k].passed/acc[k].total*100:0;});
  return acc;
}
function outcomeRow(label,val,max,color){
  return '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;"><span style="width:70px;font-size:13px;color:var(--muted);">'+esc(label)+'</span>'
    +'<div style="flex:1;height:12px;border-radius:100px;background:var(--surfaceAlt);overflow:hidden;"><span style="display:block;height:100%;width:'+(val/max*100).toFixed(1)+'%;background:'+color+';border-radius:100px;"></span></div>'
    +'<strong style="font-family:\'IBM Plex Mono\',monospace;font-size:14px;min-width:20px;text-align:right;">'+val+'</strong></div>';
}
function renderTrend(reports){
  var order=['web','mobile','api'];
  var chron=reports.slice().reverse();
  var html=order.map(function(p){
    var runs=chron.filter(function(r){return r.platforms&&r.platforms[p];});
    if(!runs.length)return '';
    var series=runs.map(function(r){return Number(r.platforms[p].pass_rate||0);});
    var tests=runs.reduce(function(a,r){return a+(r.platforms[p].total||0);},0);
    var last=series[series.length-1];
    var col=pfColor(p);
    var sp=areaPath(series,300,120);
    var pts=(sp.xs||[]).map(function(x,i){return '<circle cx="'+x.toFixed(1)+'" cy="'+sp.ys[i].toFixed(1)+'" r="3.5" fill="'+col+'"><title>'+esc(runs[i].run_id)+': '+Math.round(series[i])+'%</title></circle>';}).join('');
    return '<div style="background:var(--surfaceAlt);border-radius:12px;padding:16px;margin-bottom:14px;">'
      +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
      +'<span style="display:inline-flex;align-items:center;gap:8px;font-size:14px;font-weight:600;"><i style="width:9px;height:9px;border-radius:50%;background:'+col+';display:inline-block;"></i>'+p.charAt(0).toUpperCase()+p.slice(1)+'</span>'
      +'<strong style="font-family:\'IBM Plex Mono\',monospace;font-size:18px;color:'+col+';">'+Math.round(last)+'%</strong></div>'
      +'<svg viewBox="0 0 300 120" style="width:100%;height:96px;" preserveAspectRatio="none"><path d="'+sp.area+'" fill="'+col+'" opacity="0.10"/><polyline points="'+sp.line+'" fill="none" stroke="'+col+'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'+pts+'</svg>'
      +'<div style="font-size:11.5px;color:var(--faint);margin-top:8px;">'+runs.length+' run(s) with '+p.charAt(0).toUpperCase()+p.slice(1)+' tests.</div></div>';
  }).join('');
  document.getElementById('pf-trend').innerHTML=html||'<p style="font-size:13px;color:var(--faint);">No platform trend data yet.</p>';
}
function renderCoverage(pf){
  var order=['web','mobile','api'];var rows=order.filter(function(p){return pf[p];});
  document.getElementById('pf-coverage').innerHTML=rows.length?rows.map(function(p){
    var col=pfColor(p);var pct=Math.round(pf[p].pass);
    return '<div style="margin-bottom:16px;"><div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;"><strong>'+p.charAt(0).toUpperCase()+p.slice(1)+'</strong>'
      +'<span style="font-family:\'IBM Plex Mono\',monospace;color:var(--muted);">'+pct+'% · '+pf[p].total+' tests</span></div>'
      +'<div style="height:10px;border-radius:100px;background:var(--surfaceAlt);overflow:hidden;"><span style="display:block;height:100%;width:'+pct+'%;background:'+col+';border-radius:100px;"></span></div></div>';
  }).join(''):'<p style="font-size:13px;color:var(--faint);">No platform coverage yet.</p>';
}
function setupPage(){
  var s=document.getElementById('pf-search'),st=document.getElementById('pf-status'),pl=document.getElementById('pf-platform'),rs=document.getElementById('pf-reset');
  s.addEventListener('input',function(){pfState.q=s.value;renderDashboard();});
  st.addEventListener('change',function(){pfState.status=st.value;renderDashboard();});
  pl.addEventListener('change',function(){pfState.platform=pl.value;renderDashboard();});
  rs.addEventListener('click',function(){pfState={q:'',status:'',platform:''};s.value='';st.value='';pl.value='';renderDashboard();});
  renderDashboard();
}
"""
)

_REPORTS_JS = (
    _SHARED_JS
    + r"""
var pfState={q:'',status:'',platform:''};
function statusPill(r){
  var ready=r.readiness==='ready';
  return '<span style="display:inline-block;padding:3px 10px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:0.03em;background:'+(ready?'var(--passSoft)':'var(--failSoft)')+';color:'+(ready?'var(--pass)':'var(--fail)')+';">'+(ready?'READY':'BLOCKED')+'</span>';
}
function platChip(name){return '<span style="display:inline-block;padding:3px 10px;border-radius:100px;font-size:11.5px;background:var(--surfaceAlt);color:var(--muted);border:1px solid var(--border);">'+esc(name)+'</span>';}
function quickBtn(href,label){return '<a href="'+esc(href)+'" style="flex:1;text-align:center;padding:8px 0;border:1px solid var(--border);border-radius:8px;font-size:12.5px;font-weight:600;color:var(--text);text-decoration:none;background:var(--surface);">'+esc(label)+'</a>';}
function card(r){
  var chips=(r.platform_names||[]).map(platChip).join(' ');
  return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'+statusPill(r)
    +'<strong style="font-family:\'IBM Plex Mono\',monospace;font-size:18px;">'+Math.round(r.pass_rate)+'%</strong></div>'
    +'<a href="'+esc(r.entry_href)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:15px;font-weight:600;color:var(--link);text-decoration:none;overflow-wrap:anywhere;">'+esc(r.run_id)+'</a>'
    +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:var(--faint);margin:4px 0 12px;">'+esc(r.generated_display)+'</div>'
    +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;"><span>'+(r.total||0)+' tests</span><span>'+(r.failed_total||0)+' failed</span><span>'+(r.flaky||0)+' flaky</span><span>'+fmtDur(r.duration_ms)+'</span></div>'
    +(chips?'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">'+chips+'</div>':'')
    +'<div style="display:flex;gap:8px;margin-bottom:10px;">'+quickBtn(r.executive_href,'Executive')+quickBtn(r.entry_href,'Overview')+quickBtn(r.tests_href,'Tests')+'</div>'
    +'<button type="button" data-cmp="'+esc(r.run_dir)+'" style="width:100%;padding:10px 0;border:0;border-radius:8px;background:var(--surfaceAlt);color:var(--muted);font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">Add to Compare</button></div>';
}
function renderGallery(){
  var d=pfData();var reports=(d.reports||[]).filter(function(r){return matchReport(r,pfState.q,pfState.status,pfState.platform);});
  document.getElementById('pf-count').textContent=reports.length+' report'+(reports.length===1?'':'s');
  document.getElementById('pf-gallery').innerHTML=reports.length?reports.map(card).join(''):'<p style="font-size:14px;color:var(--faint);grid-column:1/-1;padding:40px;text-align:center;">No reports match your filters.</p>';
  document.querySelectorAll('[data-cmp]').forEach(function(b){b.addEventListener('click',function(){
    try{var sel=JSON.parse(localStorage.getItem('pf-compare')||'[]');if(sel.indexOf(b.dataset.cmp)<0&&sel.length<5)sel.push(b.dataset.cmp);localStorage.setItem('pf-compare',JSON.stringify(sel));b.textContent='Added to Compare';}catch(e){}
  });});
}
function setupPage(){
  var s=document.getElementById('pf-search'),st=document.getElementById('pf-status'),pl=document.getElementById('pf-platform'),rs=document.getElementById('pf-reset');
  s.addEventListener('input',function(){pfState.q=s.value;renderGallery();});
  st.addEventListener('change',function(){pfState.status=st.value;renderGallery();});
  pl.addEventListener('change',function(){pfState.platform=pl.value;renderGallery();});
  rs.addEventListener('click',function(){pfState={q:'',status:'',platform:''};s.value='';st.value='';pl.value='';renderGallery();});
  renderGallery();
}
"""
)

_COMPARE_JS = (
    _SHARED_JS
    + r"""
function selKey(){return 'pf-compare';}
function getSel(){try{return JSON.parse(localStorage.getItem(selKey())||'[]');}catch(e){return[];}}
function setSel(v){try{localStorage.setItem(selKey(),JSON.stringify(v.slice(0,5)));}catch(e){}}
function byDir(d,dir){return (d.reports||[]).filter(function(r){return r.run_dir===dir;})[0];}
function shortId(id){return String(id||'').replace(/^RUN-?/,'').replace(/Z$/,'');}
function renderCompare(){
  var d=pfData();var all=d.reports||[];var sel=getSel().filter(function(dir){return byDir(d,dir);});
  // picker
  var chips=sel.map(function(dir){var r=byDir(d,dir);return '<span style="display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:100px;background:var(--surfaceAlt);font-size:12.5px;font-family:\'IBM Plex Mono\',monospace;">'+esc(shortId(r.run_id))+'<button type="button" data-rm="'+esc(dir)+'" style="border:0;background:none;cursor:pointer;color:var(--faint);font-size:14px;line-height:1;">×</button></span>';}).join(' ');
  var avail=all.filter(function(r){return sel.indexOf(r.run_dir)<0;});
  var addList=avail.slice(0,6).map(function(r){return '<div style="display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-top:1px solid var(--border);"><div><strong style="font-family:\'IBM Plex Mono\',monospace;font-size:13.5px;">'+esc(r.run_id)+'</strong><div style="font-size:11.5px;color:var(--faint);font-family:\'IBM Plex Mono\',monospace;">'+esc(r.generated_display)+' · '+Math.round(r.pass_rate)+'% pass</div></div><button type="button" data-add="'+esc(r.run_dir)+'" style="border:0;background:none;color:var(--link);font-weight:600;font-size:13px;cursor:pointer;">+ Add</button></div>';}).join('');
  document.getElementById('cmp-picker').innerHTML='<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;">'
    +'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:'+(sel.length?'16px':'0')+';">'+(chips||'<span style="font-size:13px;color:var(--faint);">No runs selected yet.</span>')+'</div>'
    +(sel.length<5?'<div style="border-top:1px solid var(--border);padding-top:14px;"><div style="font-size:13px;font-weight:700;margin-bottom:6px;">Add a run ('+(5-sel.length)+' slot(s) left)</div>'+addList+'</div>':'')+'</div>';
  // scorecards
  var runs=sel.map(function(dir){return byDir(d,dir);});
  document.getElementById('cmp-scorecards').innerHTML=runs.map(function(r){
    var ready=r.readiness==='ready';var pc=r.pass_rate>=80?'var(--pass)':(r.pass_rate>=60?'var(--flaky)':'var(--fail)');
    return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;">'
      +'<a href="'+esc(r.entry_href)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:14px;font-weight:600;color:var(--link);text-decoration:none;">'+esc(r.run_id)+'</a>'
      +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:var(--faint);margin:4px 0 10px;">'+esc(r.generated_display)+'</div>'
      +'<span style="display:inline-block;padding:3px 10px;border-radius:100px;font-size:11px;font-weight:700;background:'+(ready?'var(--passSoft)':'var(--failSoft)')+';color:'+(ready?'var(--pass)':'var(--fail)')+';">'+(ready?'READY':'BLOCKED')+'</span>'
      +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:34px;font-weight:600;color:'+pc+';margin:12px 0 2px;">'+Math.round(r.pass_rate)+'%</div>'
      +'<div style="font-size:12px;color:var(--muted);">pass rate</div>'
      +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:var(--muted);margin-top:10px;line-height:1.7;">'+(r.total||0)+' tests · '+(r.failed_total||0)+' failed<br>'+(r.flaky||0)+' flaky · '+fmtDur(r.duration_ms)+'</div>'
      +'<button type="button" data-rm="'+esc(r.run_dir)+'" style="border:0;background:none;color:var(--fail);font-weight:600;font-size:13px;cursor:pointer;margin-top:12px;padding:0;">Remove</button></div>';
  }).join('')||'<p style="font-size:13px;color:var(--faint);">Add runs above to compare them.</p>';
  // bars
  function barCard(title,fmt,pick,color){
    var mx=Math.max.apply(null,runs.map(pick).concat([1]));
    return '<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;"><h2 style="font-family:\'Manrope\',sans-serif;font-size:15px;font-weight:700;margin:0 0 14px;">'+title+'</h2>'
      +runs.map(function(r){var v=pick(r);return '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><span style="width:78px;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+esc(shortId(r.run_id))+'</span><div style="flex:1;height:10px;border-radius:100px;background:var(--surfaceAlt);overflow:hidden;"><span style="display:block;height:100%;width:'+(v/mx*100).toFixed(1)+'%;background:'+(typeof color==='function'?color(r):color)+';border-radius:100px;"></span></div><strong style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;min-width:42px;text-align:right;">'+fmt(v)+'</strong></div>';}).join('')+'</div>';
  }
  document.getElementById('cmp-bars').innerHTML=runs.length?
    barCard('Pass Rate',function(v){return Math.round(v)+'%';},function(r){return Number(r.pass_rate||0);},function(r){return r.pass_rate>=80?'var(--pass)':(r.pass_rate>=60?'var(--flaky)':'var(--fail)');})
    +barCard('Duration',function(v){return fmtDur(v);},function(r){return Number(r.duration_ms||0);},'var(--accent)')
    +barCard('Failed',function(v){return String(v);},function(r){return Number(r.failed_total||0);},'var(--fail)'):'';
  // delta table
  if(runs.length>=2){
    var base=runs[0];var rows=runs.slice(1).map(function(r){
      function d(cur,prev,suffix,invert){var diff=cur-prev;var good=invert?diff<0:diff>0;var col=diff===0?'var(--muted)':(good?'var(--pass)':'var(--fail)');var sign=diff>0?'+':'';return '<td style="text-align:right;font-family:\'IBM Plex Mono\',monospace;color:'+col+';">'+sign+(suffix==='s'?(Math.round(diff/100)/10):Math.round(diff))+suffix+'</td>';}
      return '<tr><td style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;">'+esc(r.run_id)+'</td>'
        +d(r.pass_rate,base.pass_rate,'%',false)+d(r.failed_total,base.failed_total,'',true)+d(r.flaky,base.flaky,'',true)+d(r.duration_ms,base.duration_ms,'s',true)+'</tr>';
    }).join('');
    document.getElementById('cmp-delta').innerHTML='<div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:20px;overflow-x:auto;"><h2 style="font-family:\'Manrope\',sans-serif;font-size:16px;font-weight:700;margin:0 0 14px;">Delta vs Baseline · '+esc(base.run_id)+'</h2>'
      +'<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:var(--surfaceAlt);"><th style="text-align:left;padding:10px 12px;font-size:11px;letter-spacing:0.05em;color:var(--faint);text-transform:uppercase;">Run</th><th style="text-align:right;padding:10px 12px;font-size:11px;letter-spacing:0.05em;color:var(--faint);text-transform:uppercase;">Pass Rate</th><th style="text-align:right;padding:10px 12px;font-size:11px;letter-spacing:0.05em;color:var(--faint);text-transform:uppercase;">Failed</th><th style="text-align:right;padding:10px 12px;font-size:11px;letter-spacing:0.05em;color:var(--faint);text-transform:uppercase;">Flaky</th><th style="text-align:right;padding:10px 12px;font-size:11px;letter-spacing:0.05em;color:var(--faint);text-transform:uppercase;">Duration</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
  } else {document.getElementById('cmp-delta').innerHTML='';}
  document.getElementById('cmp-impact').innerHTML='';
  document.querySelectorAll('[data-add]').forEach(function(b){b.addEventListener('click',function(){var s=getSel();if(s.indexOf(b.dataset.add)<0)s.push(b.dataset.add);setSel(s);renderCompare();});});
  document.querySelectorAll('[data-rm]').forEach(function(b){b.addEventListener('click',function(){setSel(getSel().filter(function(x){return x!==b.dataset.rm;}));renderCompare();});});
}
function setupPage(){
  var d=pfData();
  if(!getSel().length){var pre=(d.reports||[]).slice(0,2).map(function(r){return r.run_dir;});setSel(pre);}
  renderCompare();
}
"""
)
