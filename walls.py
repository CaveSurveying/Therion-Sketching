# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Turning sketch strokes into clean wall lines.

Strokes drawn twice are dropped, pieces whose ends meet are joined, and the
result is smoothed (Chaikin) and written as Bezier curves (Catmull-Rom).
"""
import math
from shapely.geometry import LineString, Point
def _dp(pp,tol):
    if len(pp)<3: return pp
    ls=LineString(pp).simplify(tol,preserve_topology=False)
    return list(ls.coords)
def _len(pp): return sum(math.dist(a,b) for a,b in zip(pp,pp[1:]))
def _sample(pp,step=0.1):
    ls=LineString(pp); n=max(2,int(ls.length/step))
    return [ls.interpolate(i/(n-1),normalized=True) for i in range(n)]
def drop_retraces(strokes, near=0.12, frac=0.75):
    """Remove strokes that mostly run along a longer stroke (pen gone over twice)."""
    order=sorted(range(len(strokes)),key=lambda i:-_len(strokes[i]))
    kept=[]
    for i in order:
        pp=strokes[i]
        if len(pp)<2: continue
        smp=_sample(pp)
        covered=0
        for k in kept:
            ls=LineString(strokes[k])
            covered=max(covered,sum(1 for p in smp if ls.distance(p)<near)/len(smp))
            if covered>=frac: break
        if covered<frac: kept.append(i)
    return [strokes[i] for i in kept]
def _dir(a,b): return math.atan2(b[1]-a[1],b[0]-a[0])
def join(strokes, gap=0.4, maxturn=70):
    """Chain strokes whose ends meet, where the line carries on without a sharp turn."""
    S=[list(s) for s in strokes]
    changed=True
    while changed:
        changed=False
        best=None
        for i in range(len(S)):
            for j in range(len(S)):
                if i==j: continue
                for ri in (False,True):
                    a=S[i][::-1] if ri else S[i]
                    for rj in (False,True):
                        b=S[j][::-1] if rj else S[j]
                        d=math.dist(a[-1],b[0])
                        if d>gap: continue
                        ta=_dir(a[-min(4,len(a))],a[-1]); tb=_dir(b[0],b[min(3,len(b)-1)])
                        turn=abs((math.degrees(tb-ta)+180)%360-180)
                        if turn>maxturn: continue
                        if best is None or d<best[0]: best=(d,i,j,ri,rj)
        if best:
            _,i,j,ri,rj=best
            a=S[i][::-1] if ri else S[i]; b=S[j][::-1] if rj else S[j]
            S[i]=a+b; del S[j]; changed=True
    return S
def chaikin(pp, n=2):
    closed=math.dist(pp[0],pp[-1])<1e-6
    for _ in range(n):
        q=[pp[0]] if not closed else []
        for a,b in zip(pp,pp[1:]):
            q+=[(0.75*a[0]+0.25*b[0],0.75*a[1]+0.25*b[1]),(0.25*a[0]+0.75*b[0],0.25*a[1]+0.75*b[1])]
        q+= [pp[-1]] if not closed else [q[0]]
        pp=q
    return pp
def clean(strokes, min_len=0.25):
    s=[_dp(pp,0.02) for pp in strokes if len(pp)>1]
    s=drop_retraces(s)
    s=join(s)
    out=[]
    for pp in s:
        if _len(pp)<min_len: continue
        pp=_dp(pp,0.05)
        if len(pp)>=3: pp=_dp(chaikin(pp,2),0.025)
        out.append(pp)
    return out
def bezier_lines(pp, px):
    """th2 Bezier text for a smooth curve through the points (Catmull-Rom)."""
    P=[px(p) for p in pp]
    o=["  %.2f %.2f"%P[0]]
    for i in range(len(P)-1):
        p0=P[i-1] if i>0 else P[i]; p1=P[i]; p2=P[i+1]; p3=P[i+2] if i+2<len(P) else P[i+1]
        c1=(p1[0]+(p2[0]-p0[0])/6, p1[1]+(p2[1]-p0[1])/6)
        c2=(p2[0]-(p3[0]-p1[0])/6, p2[1]-(p3[1]-p1[1])/6)
        o.append("  %.2f %.2f %.2f %.2f %.2f %.2f"%(*c1,*c2,*p2))
    return o

def on_edge(pp, ring, near=0.3, frac=0.6):
    """True if most of the line follows the passage outline (a real wall),
    False for lines inside the passage (ledges, channel and upper-level edges)."""
    edge=LineString(ring)
    smp=_sample(pp)
    return sum(1 for p in smp if edge.distance(p)<near)/len(smp)>=frac

def split_by_edge(pp, ring, near=0.3, min_run=0.4):
    """Split a line into (is_wall, points) runs: along the passage outline or inside it."""
    edge=LineString(ring)
    flags=[edge.distance(Point(p))<near for p in pp]
    runs=[];cur=[pp[0]];f=flags[0]
    for p,fl in zip(pp[1:],flags[1:]):
        cur.append(p)
        if fl!=f:
            runs.append([f,cur]); cur=[p]; f=fl
    runs.append([f,cur])
    # fold runs that are too short into their neighbour
    merged=[]
    for f,r in runs:
        if merged and (_len(r)<min_run or merged[-1][0]==f):
            merged[-1][1]+=r[1:]
        else: merged.append([f,r])
    if len(merged)>1 and _len(merged[0][1])<min_run:
        merged[1][1]=merged[0][1]+merged[1][1][1:]; merged.pop(0)
    return [(f,r) for f,r in merged if len(r)>1]


def bezier_closed(pp, px):
    """th2 Bezier text for a smooth closed curve through the points
    (Catmull-Rom, wrapping round), ending back at the start."""
    P = [px(p) for p in pp]
    if len(P) > 1 and math.dist(P[0], P[-1]) < 1e-6:
        P = P[:-1]
    n = len(P)
    o = ["  %.2f %.2f" % P[0]]
    for i in range(n):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        o.append("  %.2f %.2f %.2f %.2f %.2f %.2f" % (*c1, *c2, *p2))
    return o
