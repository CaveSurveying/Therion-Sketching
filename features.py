# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Water, water flow and formations from the blue and green sketch lines.

Blue: groups of short straight strokes are hatching (a pool, drawn as
water), a closed blue outline is a pool too, and other squiggles are water
flow. Green: concentric rings are a stalagmite boss, a small "Y" of straight
strokes a stalactite, anything else flowstone.
"""
import math
from shapely.geometry import Polygon, Point, LineString
def plen(pp): return sum(math.dist(a,b) for a,b in zip(pp,pp[1:]))
def span(pp):
    s=pp[::max(1,len(pp)//20)]+[pp[-1]]
    return max(math.dist(a,b) for a in s for b in s)
def straightness(pp):
    (x1,y1),(x2,y2)=max(((p,q) for p in pp[::2] for q in pp[::2]),key=lambda pq:math.dist(*pq))
    L=math.dist((x1,y1),(x2,y2)) or 1
    return max(abs((x2-x1)*(y1-y)-(x1-x)*(y2-y1))/L for x,y in pp)
def centroid(pp): return (sum(p[0] for p in pp)/len(pp), sum(p[1] for p in pp)/len(pp))
def classify(polys, passage=None):
    """passage: optional shapely polygon to trim pools to."""
    from shapely.ops import unary_union
    from .settings import SETTINGS
    blue=[pp for c,pp in polys if c=='BLUE' and len(pp)>1 and plen(pp)>0.05]
    closed_pools=set()
    if SETTINGS['pools_first']:      # a closed blue outline is a pool, never a flow arrow
        for k,pp in enumerate(blue):
            if math.dist(pp[0],pp[-1])<max(0.15,0.2*plen(pp)) and len(pp)>2:
                g=Polygon(pp).buffer(0)
                if g.area>=SETTINGS['pool_min_area']: closed_pools.add(k)
    lines=[LineString(pp) for pp in blue]
    hatch=[i for i,pp in enumerate(blue) if straightness(pp)<0.08 and 0.15<plen(pp)<3.5]
    # group hatch strokes that lie within 0.6 m of each other
    groups=[]
    for i in hatch:
        hit=[g for g in groups if any(lines[i].distance(lines[k])<0.6 for k in g)]
        merged={i}
        for g in hit: merged|=g; groups.remove(g)
        groups.append(merged)
    groups=[g for g in groups if len(g)>=3 and not (g & closed_pools)]
    used=set(); pools=[]
    for g in groups:
        core=unary_union([lines[k] for k in g])
        members=set(g)|{k for k in range(len(blue)) if k not in g and lines[k].distance(core)<0.15 and plen(blue[k])<12}
        geom=unary_union([lines[k] for k in members]).convex_hull.buffer(0.05)
        if passage is not None: geom=geom.intersection(passage)
        if geom.geom_type=='MultiPolygon': geom=max(geom.geoms,key=lambda p:p.area)
        if geom.is_empty or geom.area<0.2: continue
        used|=members; pools.append((None,geom.simplify(0.03)))
    flows=[]
    for k,pp in enumerate(blue):
        if k in used or k in closed_pools: continue
        if any(g.buffer(0.2).contains(Point(centroid(pp))) for _,g in pools): continue
        if plen(pp)<0.3: continue
        if straightness(pp)<0.06: continue            # stray straight stroke, not a squiggle
        flows.append(pp)
    for k,pp in enumerate(blue):   # a closed blue outline with no hatching is a pool too
        if k in closed_pools:
            g=Polygon(pp).buffer(0)
            if passage is not None: g=g.intersection(passage.buffer(0.3))
            if g.geom_type=='MultiPolygon': g=max(g.geoms,key=lambda q:q.area)
            if not g.is_empty: pools.append((pp,g))
            continue
        if plen(pp)>1.0 and math.dist(pp[0],pp[-1])<0.35 and not any(g.intersects(LineString(pp)) for _,g in pools):
            g=Polygon(pp).buffer(0)
            if g.area>0.25: pools.append((pp,g))
    # green: cluster strokes
    green=[pp for c,pp in polys if c=='GREEN' and len(pp)>1]
    cl=[]
    for pp in green:
        m=centroid(pp)
        for c in cl:
            if any(math.dist(m,q)<0.6 for q in c['m']): c['p'].append(pp); c['m'].append(m); break
        else: cl.append({'p':[pp],'m':[m]})
    forms=[]
    for c in cl:
        pts=[p for pp in c['p'] for p in pp]; ctr=centroid(pts)
        closed=sum(1 for pp in c['p'] if math.dist(pp[0],pp[-1])<0.1 and plen(pp)>0.3)
        allstraight=all(straightness(pp)<0.05 for pp in c['p'])
        if closed>=2: kind='stalagmite'          # concentric rings: a boss
        elif allstraight and span(pts)<1.0 and len(c['p'])>=2: kind='stalactite'   # the "Y" mark
        else: kind='flowstone'
        forms.append((kind,ctr))
    return pools,flows,forms
