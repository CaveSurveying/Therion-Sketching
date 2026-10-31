# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see LICENSE.
"""Slope arrows and boulders drawn as small closed shapes in the sketch."""
import math
from shapely.geometry import LineString, Polygon, Point
from .geom import closed, length
def shape_of(pp):
    """'arrow' (thin closed triangle: slope arrow), 'boulder' (small blobby loop) or None."""
    if len(pp)<3: return None,None
    ls=LineString(pp); b=ls.bounds; size=max(b[2]-b[0],b[3]-b[1])
    L=length(pp)
    if size>2.5 or size<0.2 or L<0.4: return None,None
    gap=math.dist(pp[0],pp[-1])
    if gap>max(0.5,0.4*size): return None,None
    poly=Polygon(pp).buffer(0)
    if poly.geom_type!='Polygon': poly=max(poly.geoms,key=lambda g:g.area) if hasattr(poly,'geoms') and poly.geoms else ls.convex_hull
    hull=ls.convex_hull
    if hull.geom_type!='Polygon' or hull.area<0.01: return None,None
    ratio=hull.area/size**2
    taper=_taper(pp)
    if ratio<0.45 and taper is not None and size>=0.6:
        return 'arrow',taper
    if ratio>=0.33:
        return 'boulder',poly if poly.area>0.3*hull.area else hull
    return None,None
def _taper(pp):
    """For a long thin shape, (middle, bearing from wide end to narrow end) if one end
    is at least twice as wide as the other, else None."""
    r=LineString(pp).convex_hull.minimum_rotated_rectangle
    c=list(r.exterior.coords)[:4]
    e1=math.dist(c[0],c[1]); e2=math.dist(c[1],c[2])
    a,b=(c[0],c[1]) if e1>=e2 else (c[1],c[2])
    L=max(e1,e2); W=min(e1,e2)
    if L<1.8*W: return None
    ux,uy=(b[0]-a[0])/L,(b[1]-a[1])/L
    proj=[((p[0]-a[0])*ux+(p[1]-a[1])*uy, (p[0]-a[0])*-uy+(p[1]-a[1])*ux) for p in pp]
    t0=min(t for t,_ in proj); t1=max(t for t,_ in proj)
    def width(lo,hi):
        v=[w for t,w in proj if lo<=(t-t0)/(t1-t0+1e-9)<=hi]
        return (max(v)-min(v)) if len(v)>1 else 0
    w0=width(0.05,0.3); w1=width(0.7,0.95)
    if max(w0,w1)<1.7*max(min(w0,w1),0.02): return None
    mid=(sum(p[0] for p in pp)/len(pp),sum(p[1] for p in pp)/len(pp))
    sgn=1 if w0>w1 else -1     # point from the wide end to the narrow end
    return mid, math.degrees(math.atan2(sgn*ux,sgn*uy))%360
def arrow_bearing(corners):
    """Apex is opposite the shortest side; the arrow runs from the base to the apex."""
    sides=[(math.dist(corners[i],corners[(i+1)%3]),i) for i in range(3)]
    _,i=min(sides); a,b=corners[i],corners[(i+1)%3]; apex=corners[(i+2)%3]
    base=((a[0]+b[0])/2,(a[1]+b[1])/2)
    mid=((base[0]+apex[0])/2,(base[1]+apex[1])/2)
    return mid, math.degrees(math.atan2(apex[0]-base[0],apex[1]-base[1]))%360

def split_symbols(strokes):
    """Pull the slope arrows and boulders out of a list of black strokes.
    Returns (other strokes, boulders as polygons, arrows as (middle, bearing))."""
    rest=[];boulders=[];arrows=[]
    for pp in strokes:
        kind,g=shape_of(pp)
        if kind=='arrow': arrows.append(g)
        elif kind=='boulder': boulders.append(g)
        elif closed(pp, 0.15, points=3) and length(pp)<3: boulders.append(Polygon(pp).buffer(0))
        else: rest.append(pp)
    return rest,[b for b in boulders if b.geom_type=='Polygon' and b.area>0.005],arrows
def symbols_th2(boulders, arrows, px):
    from .walls import chaikin, bezier_lines
    o=[]
    for b in boulders:
        ring=list(b.simplify(0.03).exterior.coords)
        if len(ring)>=4: ring=chaikin(ring,2)
        o+=["line rock-border -close on"]+bezier_lines(ring[:-1],px)+["endline",""]
    for m,brg in arrows:
        o+=["point %.2f %.2f gradient -orientation %.1f"%(*px(m),brg),""]
    return o
