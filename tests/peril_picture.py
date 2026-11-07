"""
tests/peril_picture.py - the Peril heat map of a saved battle turn as one web page (2026-11-07, Daniel's peril heat map
design; INTEGRATION__peril).

    python tests/peril_picture.py pg 1 11                    # setup, battle, turn: the state at the END of that turn
    python tests/peril_picture.py pg 1 11 --out peril.html   # where to write (default stats/peril_pg_b1_t11.html)

The state is the one tests/turn_inspector.py keeps (make_state: played once, then reused). The page shows, for the
unit you pick from the list (the TARGET: the damage is figured against it), what the other side could do to it
standing on each hex of the board, from every spot each of them could reach this coming turn:

    All enemies / one enemy   the sum of their fields, or one attacker's field
    Peak / Mean               the most it could take there from any one reachable spot (worst case), or the average
                              over all the attacker's spots
    The grey hexes            no line of sight from anywhere that attacker could reach
Hexes carry their terrain faintly (woods green, rough brown, higher ground lighter). Unit markers: blue / red discs.
"""
import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "pathfinder"))
os.chdir(REPO)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__forces as forces  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__peril as peril  # noqa: E402
import INTEGRATION__saved_state as saved_state  # noqa: E402
import INTEGRATION__vision as vision  # noqa: E402
import hex_geometry  # noqa: E402
import turn_inspector as ti  # noqa: E402

SQRT3_2 = 0.8660254


def gather(setup, battle, turn):
    ti.configure(setup, [])
    with redirect_stdout(io.StringIO()):
        terrain = orchestrator._load_map()
        roster = config.load_roster()
    path = ti.make_state(setup, battle, turn, terrain, roster)
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        b = saved_state.load(path)
    tm = b.terrain_map
    vt = vision.table(tm)
    live = forces.standing(b.units)
    hexes = []
    for (x, y) in vt.hexes:
        info = tm["hexes"].get(hex_geometry.hex_label(x, y), {})
        feats = info.get("features", {})
        hexes.append({"x": x, "y": y, "lv": info.get("level", 0),
                      "t": "w" if "woods" in feats else ("r" if "rough" in feats else "")})
    units = []
    for u in live:
        units.append({"name": u.side_name, "team": u.team, "hex": u.hex,
                      "xy": list(hex_geometry.parse_hex_label(u.hex)) if u.hex else None})
    fields = {}                                                   # target name -> {attacker name or "all": [peak, mean]}
    for target in live:
        per = {}
        foes = forces.enemies_of(target, b.units)
        for foe in foes:
            f = peril.unit_field(foe, target, tm, vt=vt)
            per[foe.side_name] = [[round(float(v), 1) for v in f.peak], [round(float(v), 1) for v in f.mean]]
        total_peak = [round(sum(per[f.side_name][0][i] for f in foes), 1) for i in range(len(hexes))]
        total_mean = [round(sum(per[f.side_name][1][i] for f in foes), 1) for i in range(len(hexes))]
        per["All enemies"] = [total_peak, total_mean]
        fields[target.side_name] = per
    return {"title": f"{ti.bb.SETUPS[setup][2]}, battle {battle}, end of turn {turn}", "hexes": hexes, "units": units,
            "fields": fields}


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Peril Heat Map</title>
<style>
:root{--bg:#f6f4ef;--fg:#1f1d1a;--muted:#6b665e;--panel:#fff;--line:#d9d4c9;--blue:#2a6fdb;--red:#d2402f}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17181a;--fg:#ecebe8;--muted:#9a978f;--panel:#202226;--line:#35383d}}
:root[data-theme="dark"]{--bg:#17181a;--fg:#ecebe8;--muted:#9a978f;--panel:#202226;--line:#35383d}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 12px;font-size:14px}
.bar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px}
label{font-size:13px;color:var(--muted);display:flex;flex-direction:column;gap:3px}
select{font:inherit;padding:5px 8px;border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px}
.wrap{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px;overflow:auto}
svg{display:block;max-width:100%;height:auto}
.legend{display:flex;align-items:center;gap:8px;margin:10px 0;font-size:13px;color:var(--muted)}
.ramp{height:12px;width:220px;border-radius:3px}
#info{font-size:13px;color:var(--muted);min-height:20px;margin-top:6px}
</style></head><body><main>
<h1>Peril heat map</h1><p class="sub" id="title"></p>
<div class="bar">
<label>Damage figured against<select id="target"></select></label>
<label>From<select id="from"></select></label>
<label>Show<select id="kind"><option value="0">Peak (worst case, any reachable spot)</option><option value="1">Mean (over every reachable spot)</option></select></label>
</div>
<div class="wrap"><svg id="map"></svg></div>
<div class="legend"><span>0</span><div class="ramp" id="ramp"></div><span id="maxv"></span><span>&nbsp;expected damage a turn (movement-score points); grey = no line of sight</span></div>
<div id="info">Hover a hex.</div>
<script>
const D=__DATA__;
document.getElementById("title").textContent=D.title;
const S=14,W=Math.sqrt(3)/2*S;
const xs=D.hexes.map(h=>h.x*1.5*S/2*2/2*1),ys=D.hexes.map(h=>-h.y*W);
const px=h=>h.x*1.5*S*1, py=h=>-h.y*W;
let minx=1e9,maxx=-1e9,miny=1e9,maxy=-1e9;
D.hexes.forEach(h=>{minx=Math.min(minx,px(h));maxx=Math.max(maxx,px(h));miny=Math.min(miny,py(h));maxy=Math.max(maxy,py(h));});
const pad=S*1.6, svg=document.getElementById("map");
svg.setAttribute("viewBox",`${minx-pad} ${miny-pad} ${maxx-minx+2*pad} ${maxy-miny+2*pad}`);
const pts=[0,1,2,3,4,5].map(i=>[Math.cos(i*Math.PI/3)*S*.97,Math.sin(i*Math.PI/3)*S*.97].join(",")).join(" ");
const ns="http://www.w3.org/2000/svg";
const cells=D.hexes.map((h,i)=>{const p=document.createElementNS(ns,"polygon");p.setAttribute("points",pts);
 p.setAttribute("transform",`translate(${px(h)},${py(h)})`);svg.appendChild(p);
 p.addEventListener("mousemove",()=>show(i));p.addEventListener("click",()=>show(i));return p;});
const marks=D.units.filter(u=>u.xy).map(u=>{const g=document.createElementNS(ns,"circle");g.setAttribute("r",S*.55);
 g.setAttribute("cx",px({x:u.xy[0]}));g.setAttribute("cy",py({y:u.xy[1]}));
 g.setAttribute("fill",u.team==="Blue"?"#2a6fdb":"#d2402f");g.setAttribute("stroke","#fff");g.setAttribute("stroke-width",1.5);
 g.style.pointerEvents="none";svg.appendChild(g);return {u,g};});
const T=document.getElementById("target"),F=document.getElementById("from"),K=document.getElementById("kind");
D.units.forEach(u=>{const o=document.createElement("option");o.value=u.name;o.textContent=u.name+" ("+(u.hex||"off board")+")";T.appendChild(o);});
function terrainTint(h){let r=235,g=232,b=222;if(h.t==="w"){r=196;g=216;b=184}else if(h.t==="r"){r=216;g=198;b=170}
 const l=h.lv*10;return `rgb(${Math.min(255,r+l)},${Math.min(255,g+l)},${Math.min(255,b+l)})`;}
function ramp(v,m){const t=m?Math.min(1,v/m):0;const a=[255,246,200],b=[240,150,40],c=[170,20,30];
 const mix=(p,q,u)=>p.map((x,i)=>Math.round(x+(q[i]-x)*u));const col=t<.5?mix(a,b,t*2):mix(b,c,(t-.5)*2);return `rgb(${col})`;}
document.getElementById("ramp").style.background="linear-gradient(90deg,"+[0,.25,.5,.75,1].map(t=>ramp(t,1)).join(",")+")";
function cur(){return D.fields[T.value][F.value][+K.value];}
function refill(){const target=T.value;F.innerHTML="";Object.keys(D.fields[target]).sort((a,b)=>a==="All enemies"?-1:b==="All enemies"?1:a.localeCompare(b))
 .forEach(n=>{const o=document.createElement("option");o.value=n;o.textContent=n;F.appendChild(o);});draw();}
function draw(){const f=cur();const m=Math.max(...f,1);document.getElementById("maxv").textContent=m.toFixed(0);
 cells.forEach((p,i)=>{const h=D.hexes[i];const v=f[i];
  p.setAttribute("fill",v>0?ramp(v,m):"#b9b6ae");p.setAttribute("fill-opacity",v>0?.95:.55);p.setAttribute("stroke",terrainTint(h));p.setAttribute("stroke-width",1.2);});
 marks.forEach(({u,g})=>{g.setAttribute("stroke-width",u.name===T.value?3.5:1.2);g.setAttribute("stroke",u.name===T.value?"#111":"#fff");});}
function show(i){const h=D.hexes[i],f=cur();let lab="";try{lab=" (hex "+String(h.x+1).padStart(2,"0")+String(1-Math.floor((h.y-(h.x%2?-1:0))/2)).padStart(2,"0")+")"}catch(e){}
 document.getElementById("info").textContent=`Hex ${h.x},${h.y}${lab}: ${f[i]>0?f[i].toFixed(1)+" expected damage":"no damage from this selection"} - level ${h.lv}${h.t==="w"?", woods":h.t==="r"?", rough":""}`;}
T.addEventListener("change",refill);F.addEventListener("change",draw);K.addEventListener("change",draw);
refill();
</script></main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("setup", choices=sorted(ti.bb.SETUPS))
    ap.add_argument("battle", type=int)
    ap.add_argument("turn", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()
    data = gather(a.setup, a.battle, a.turn)
    out = a.out or os.path.join(REPO, "stats", f"peril_{a.setup}_b{a.battle}_t{a.turn}.html")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
