"""Write the graph as one HTML file. By default the 3d-force-graph library is
inlined so the file opens offline and makes no network request. Only note
names, folder paths and group names are embedded, unless excerpts are
explicitly requested."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from importlib import resources
from typing import Dict, List, Optional

from .graph import Graph, layered_positions
from .vault import Note

FORCE_GRAPH_VERSION = "1.80.1"
CDN_URL = f"https://cdn.jsdelivr.net/npm/3d-force-graph@{FORCE_GRAPH_VERSION}/dist/3d-force-graph.min.js"
EXCERPT_CHARS = 280


def vendored_js() -> str:
    return resources.files("amagi_vaultgraph").joinpath("vendor/3d-force-graph.min.js").read_text(encoding="utf-8")


def _sri(js: str) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(js.encode("utf-8")).digest()).decode("ascii")


def safe_json(data: object) -> str:
    """JSON that cannot close the <script> element it sits in."""
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def excerpt(note: Note, limit: int = EXCERPT_CHARS) -> str:
    text = " ".join(note.body.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def graph_data(graph: Graph, layered: bool = False, with_excerpts: bool = False) -> Dict[str, object]:
    ids = {n.id: i for i, n in enumerate(graph.notes)}
    pos = layered_positions(graph) if layered else {}
    nodes: List[Dict[str, object]] = []
    for n in graph.notes:
        node: Dict[str, object] = {
            "id": ids[n.id],
            "name": n.name,
            "path": n.id,
            "group": graph.groups[n.id],
            "deg": graph.degree(n.id),
            "val": 1 + graph.degree(n.id),
            "color": graph.colors[graph.groups[n.id]],
        }
        if n.id in pos:
            node["fx"], node["fy"], node["fz"] = pos[n.id]
        if with_excerpts:
            node["excerpt"] = excerpt(n)
        nodes.append(node)
    links = [{"source": ids[a], "target": ids[b]} for a, b in graph.undirected_edges]
    legend = [{"group": g, "color": graph.colors[g], "count": sum(1 for v in graph.groups.values() if v == g)}
              for g in graph.group_order]
    data: Dict[str, object] = {"nodes": nodes, "links": links, "legend": legend}
    if layered:
        cols: Dict[str, List[float]] = {}
        for n in graph.notes:
            x, y, _z = pos[n.id]
            cols.setdefault(graph.groups[n.id], [x, y])
            cols[graph.groups[n.id]][1] = max(cols[graph.groups[n.id]][1], y)
        data["columns"] = [{"group": g, "x": cols[g][0], "y": cols[g][1]} for g in graph.group_order if g in cols]
    return data


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="amagi-vaultgraph __VERSION__">
<title>__TITLE__</title>
<style>
html,body{margin:0;height:100%;background:#05060f;color:#c9cfe6;font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
#graph{position:absolute;inset:0}
.panel{position:absolute;z-index:2;background:rgba(10,12,28,.72);border:1px solid #1d2140;border-radius:8px;padding:8px 10px;backdrop-filter:blur(4px)}
#info{top:10px;left:10px;max-width:46ch}
#info h1{margin:0 0 2px;font-size:15px;color:#fff;font-weight:600}
#info .stats{color:#8f96b8}
#legend{bottom:10px;left:10px;max-height:45vh;overflow:auto}
#legend div{display:flex;align-items:center;gap:7px;cursor:pointer;padding:1px 0}
#legend div.off{opacity:.35}
#legend i{width:10px;height:10px;border-radius:50%;display:inline-block}
#legend b{font-weight:400;color:#8f96b8;margin-left:auto;padding-left:12px}
#find{top:10px;right:10px}
#find input{background:#0b0e22;border:1px solid #2a2f57;color:#fff;border-radius:6px;padding:5px 8px;width:200px;font:inherit}
#help{bottom:10px;right:10px;color:#8f96b8}
.tip{max-width:40ch}
.tip .p{color:#8f96b8;font-size:11px}
.tip .x{margin-top:4px;color:#c9cfe6;font-size:12px}
body.clean .panel,body.clean .col{display:none}
.col{position:absolute;z-index:1;transform:translate(-50%,-100%);font-size:12px;font-weight:600;letter-spacing:.04em;pointer-events:none;white-space:nowrap;text-shadow:0 0 6px #05060f}
</style>
__SCRIPT__
</head><body>
<div id="graph"></div>
<div id="info" class="panel"><h1>__TITLE__</h1><div class="stats">__STATS__</div></div>
<div id="find" class="panel"><input id="q" list="names" placeholder="Find a note..." autocomplete="off"><datalist id="names"></datalist></div>
<div id="legend" class="panel"></div>
<div id="help" class="panel">drag: rotate &middot; scroll: zoom &middot; click: focus &middot; space: spin &middot; h: hide panels</div>
<script>
const DATA=__DATA__;
const OPTS=__OPTS__;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const hidden=new Set();
const el=document.getElementById('graph');
const nodeVis=()=>n=>!hidden.has(n.group);
const linkVis=()=>l=>!hidden.has(l.source.group)&&!hidden.has(l.target.group);
const G=ForceGraph3D()(el)
  .backgroundColor('#05060f')
  .nodeId('id').nodeVal('val').nodeColor('color').nodeOpacity(0.92).nodeResolution(12)
  .nodeLabel(n=>'<div class="tip"><b>'+esc(n.name)+'</b><div class="p">'+esc(n.path)+' &middot; '+esc(n.group)+' &middot; '+n.deg+' link'+(n.deg===1?'':'s')+'</div>'+(n.excerpt?'<div class="x">'+esc(n.excerpt)+'</div>':'')+'</div>')
  .linkColor(()=> 'rgba(150,170,255,0.55)').linkOpacity(0.35).linkWidth(0)
  .linkDirectionalParticles(DATA.links.length<=3000?1:0).linkDirectionalParticleSpeed(0.004).linkDirectionalParticleWidth(1.2)
  .showNavInfo(false)
  .onNodeClick(focusNode);
if(OPTS.layered){G.cooldownTicks(1);}else{const ch=G.d3Force('charge');if(ch&&ch.distanceMax)ch.distanceMax(160);}
G.graphData({nodes:DATA.nodes,links:DATA.links});
let fitted=false;
function fit(){if(fitted)return;fitted=true;if(!OPTS.layered){G.zoomToFit(600,40);return;}
  let mx=1,my=1;DATA.nodes.forEach(n=>{mx=Math.max(mx,Math.abs(n.fx));my=Math.max(my,Math.abs(n.fy));});
  const t=Math.tan(Math.PI*G.camera().fov/360),asp=innerWidth/innerHeight;
  const d=Math.max(mx/(t*asp),my/t)*1.25+40;G.cameraPosition({x:0,y:0,z:d},{x:0,y:0,z:0},600);}
G.onEngineStop(fit);
setTimeout(fit,OPTS.layered?300:4000);
if(OPTS.layered&&DATA.columns){const labs=DATA.columns.map(c=>{const d=document.createElement('div');d.className='col';d.textContent=c.group;d.style.color=(DATA.legend.find(e=>e.group===c.group)||{}).color||'#fff';document.body.appendChild(d);return [c,d];});
  (function tick(){labs.forEach(([c,d])=>{const p=G.graph2ScreenCoords(c.x,c.y+12,0);d.style.left=p.x+'px';d.style.top=p.y+'px';d.style.display=hidden.has(c.group)?'none':'';});requestAnimationFrame(tick);})();}
function focusNode(n){const d=OPTS.layered?160:110;const r=1+d/Math.max(1,Math.hypot(n.x,n.y,n.z));G.cameraPosition({x:n.x*r,y:n.y*r,z:n.z*r||d},n,1200);}
const lg=document.getElementById('legend');
DATA.legend.forEach(e=>{const d=document.createElement('div');d.innerHTML='<i style="background:'+esc(e.color)+'"></i>'+esc(e.group)+'<b>'+e.count+'</b>';d.title='click to hide/show';d.onclick=()=>{hidden.has(e.group)?hidden.delete(e.group):hidden.add(e.group);d.classList.toggle('off');G.nodeVisibility(nodeVis()).linkVisibility(linkVis());};lg.appendChild(d);});
const dl=document.getElementById('names');
DATA.nodes.slice().sort((a,b)=>a.name.localeCompare(b.name)).forEach(n=>{const o=document.createElement('option');o.value=n.name;dl.appendChild(o);});
document.getElementById('q').addEventListener('change',e=>{const v=e.target.value.toLowerCase();const n=DATA.nodes.find(n=>n.name.toLowerCase()===v)||DATA.nodes.find(n=>n.name.toLowerCase().includes(v));if(n)focusNode(n);});
let spin=OPTS.spin,angle=0,timer=null;
function setSpin(on){spin=on;if(timer){clearInterval(timer);timer=null;}if(!on)return;const c=G.cameraPosition();const dist=Math.hypot(c.x,c.z)||400;angle=Math.atan2(c.x,c.z);timer=setInterval(()=>{angle+=0.004;G.cameraPosition({x:dist*Math.sin(angle),z:dist*Math.cos(angle)});},16);}
if(spin)setTimeout(()=>setSpin(true),OPTS.layered?900:4700);
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.code==='Space'){e.preventDefault();setSpin(!spin);}if(e.key==='h')document.body.classList.toggle('clean');});
window.addEventListener('resize',()=>G.width(innerWidth).height(innerHeight));
window.__vaultgraph={graph:G,data:DATA};
</script>
</body></html>
"""


def render_html(graph: Graph, title: str, version: str, layered: bool = False, offline: bool = True,
                spin: bool = False, with_excerpts: bool = False, stats_line: Optional[str] = None) -> str:
    data = graph_data(graph, layered=layered, with_excerpts=with_excerpts)
    js = vendored_js()
    if offline:
        script = "<script>\n" + js + "\n</script>"
    else:
        script = f'<script src="{CDN_URL}" integrity="{_sri(js)}" crossorigin="anonymous"></script>'
    if stats_line is None:
        stats_line = f"{len(data['nodes'])} notes &middot; {len(data['links'])} links &middot; coloured by {html.escape(graph.color_by)}"
    values = {
        "TITLE": html.escape(title),
        "VERSION": html.escape(version),
        "STATS": stats_line,
        "OPTS": safe_json({"layered": layered, "spin": spin}),
        "DATA": safe_json(data),
        "SCRIPT": script,
    }
    # one pass over the template: text that comes from notes is never re-scanned
    return re.sub(r"__([A-Z]+)__", lambda m: values.get(m.group(1), m.group(0)), _TEMPLATE)
