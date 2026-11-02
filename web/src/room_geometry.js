import clipping from 'polygon-clipping';

export const TATAMI_M2 = 1.62;
export const SIZES = [4.5, 6, 7, 8, 10, 12, 15, 20];
export const SHAPES = [
  ['square', '正方形'], ['rectangle', '長方形'], ['l', 'L字型'], ['reverse_l', '逆L字型'],
  ['convex', '凸型'], ['concave', '凹型'], ['s', 'S字型'], ['reverse_s', '逆S字型'],
];
export const EPS = 1e-6;
const grids = { l: ['10','10','11'], convex: ['010','111','111'], concave: ['101','101','111'], s: ['011','010','110'] };
export const clone = (value) => structuredClone(value);
export const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);
export const signedArea = (v) => v.reduce((sum,a,i) => {const b=v[(i+1)%v.length];return sum+a.x*b.y-b.x*a.y;},0)/2;
export const area = (v) => Math.abs(signedArea(v));
export const ring = (v) => [...v.map(p=>[p.x,p.y]), [v[0].x,v[0].y]];
export const polygon = (v) => [ring(v)];
export function multiArea(multi) {return multi.reduce((sum,poly)=>sum+poly.reduce((s,r,i)=>s+(i?-1:1)*area(r.map(([x,y])=>({x,y}))),0),0);}
export function bounds(v) {return {minX:Math.min(...v.map(p=>p.x)),minY:Math.min(...v.map(p=>p.y)),maxX:Math.max(...v.map(p=>p.x)),maxY:Math.max(...v.map(p=>p.y))};}
const cross = (a,b,c) => (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
export function project(p,a,b) {
  const dx=b.x-a.x,dy=b.y-a.y,d=dx*dx+dy*dy;
  const t=d?Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/d)):0;
  return {x:a.x+t*dx,y:a.y+t*dy,t};
}
const onSegment = (p,a,b) => distance(p,project(p,a,b))<=EPS;
function intersects(a,b,c,d) {
  const c1=cross(a,b,c),c2=cross(a,b,d),c3=cross(c,d,a),c4=cross(c,d,b);
  return (c1*c2<0 && c3*c4<0) || onSegment(a,c,d)||onSegment(b,c,d)||onSegment(c,a,b)||onSegment(d,a,b);
}
export function pointInside(p,v) {
  let inside=false;
  for(let i=0,j=v.length-1;i<v.length;j=i++) {
    const a=v[i],b=v[j];
    if(onSegment(p,a,b))return true;
    if((a.y>p.y)!==(b.y>p.y) && p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x)inside=!inside;
  }
  return inside;
}
export function preset(shape='square',tatami=6) {
  if(!SIZES.includes(tatami))tatami=6;
  let points;
  if(shape==='square'||shape==='rectangle') {
    const w=shape==='square'?1:4,h=shape==='square'?1:3;
    points=[{x:0,y:0},{x:w,y:0},{x:w,y:h},{x:0,y:h}];
  } else {
    const reverse=shape.startsWith('reverse_');
    const rows=grids[reverse?shape.slice(8):shape]||grids.l;
    const squares=[];
    rows.forEach((row,i)=>[...row].forEach((cell,j)=>{
      if(cell==='1') {const x=reverse?row.length-1-j:j,y=rows.length-1-i;squares.push([[[x,y],[x+1,y],[x+1,y+1],[x,y+1],[x,y]]]);}
    }));
    points=clipping.union(...squares)[0][0].slice(0,-1).map(([x,y])=>({x,y}));
  }
  if(signedArea(points)<0)points.reverse();
  const scale=Math.sqrt(tatami*TATAMI_M2/area(points));
  return points.map((p,i)=>({id:`v${i}`,x:p.x*scale,y:p.y*scale}));
}
export function validateRoom(v) {
  const bad=new Set(), reasons=[];
  if(v.length<3||v.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))return {valid:false,bad:new Set(v.map((_,i)=>i)),reasons:['部屋の座標が不正です。'],narrow:false};
  const n=v.length;
  for(let i=0;i<n;i++) {
    const a=v[i],b=v[(i+1)%n],c=v[(i+2)%n];
    if(distance(a,b)<=EPS){bad.add(i);reasons.push('長さがゼロの辺があります。');}
    if(Math.abs(cross(a,b,c))<=EPS && (a.x-b.x)*(c.x-b.x)+(a.y-b.y)*(c.y-b.y)>EPS) {bad.add(i);bad.add((i+1)%n);reasons.push('辺が折り返して重なっています。');}
    for(let j=i+1;j<n;j++) {
      if(j===(i+1)%n||i===(j+1)%n)continue;
      if(intersects(a,b,v[j],v[(j+1)%n])){bad.add(i);bad.add(j);reasons.push('辺が交差、または接触しています。');}
    }
  }
  if(area(v)<=1e-8){v.forEach((_,i)=>bad.add(i));reasons.push('面積がゼロになっています。');}
  const b=bounds(v);
  if(b.maxX-b.minX>16||b.maxY-b.minY>16||v.some(p=>Math.abs(p.x)>100||Math.abs(p.y)>100)){
    v.forEach((_,i)=>bad.add(i));reasons.push('編集範囲は幅・奥行きそれぞれ16m以内です。');
  }
  let narrow=false;
  if(!bad.size)for(let i=0;i<n;i++)for(let j=i+1;j<n;j++) {
    if(j===i+1||(i===0&&j===n-1))continue;
    const a=v[i],b=v[(i+1)%n],c=v[j],d=v[(j+1)%n];
    for(const [p,q] of [[a,project(a,c,d)],[b,project(b,c,d)],[c,project(c,a,b)],[d,project(d,a,b)]]) {
      if(distance(p,q)<.5-EPS&&pointInside({x:(p.x+q.x)/2,y:(p.y+q.y)/2},v))narrow=true;
    }
  }
  return {valid:bad.size===0,bad,reasons:[...new Set(reasons)],narrow};
}
export function moveEdge(v,index,dx,dy) {
  const next=clone(v),a=v[index],b=v[(index+1)%v.length],len=distance(a,b);
  if(len<=EPS)return next;
  const nx=-(b.y-a.y)/len,ny=(b.x-a.x)/len,d=dx*nx+dy*ny;
  for(const i of [index,(index+1)%v.length]){next[i].x+=nx*d;next[i].y+=ny*d;}
  return next;
}
export function footprint(def,p) {
  const c=Math.cos(p.rotation_deg*Math.PI/180),s=Math.sin(p.rotation_deg*Math.PI/180),w=def.width_m/2,h=def.depth_m/2;
  return [[-w,-h],[w,-h],[w,h],[-w,h]].map(([x,y])=>({x:p.x_m+c*x+s*y,y:p.y_m-s*x+c*y}));
}
export function openingSegment(room,o) {
  const i=room.vertices.findIndex(v=>v.id===o.edge_id);
  if(i<0)return null;
  const a=room.vertices[i],b=room.vertices[(i+1)%room.vertices.length],len=distance(a,b);
  if(len<=EPS||o.offset_m<0||o.width_m<=0||o.offset_m+o.width_m>len+EPS)return null;
  const t={x:(b.x-a.x)/len,y:(b.y-a.y)/len};
  return {a:{x:a.x+t.x*o.offset_m,y:a.y+t.y*o.offset_m},b:{x:a.x+t.x*(o.offset_m+o.width_m),y:a.y+t.y*(o.offset_m+o.width_m)},t};
}
export function doorFront(room,o) {
  const seg=openingSegment(room,o);
  if(!o.placed||!seg)return [];
  const {a,b,t}=seg,sign=Math.sign(signedArea(room.vertices)),nx=-t.y*.5*sign,ny=t.x*.5*sign;
  return clipping.intersection(polygon([a,b,{x:b.x+nx,y:b.y+ny},{x:a.x+nx,y:a.y+ny}]),polygon(room.vertices));
}
export function openingValid(room,o) {
  if(!openingSegment(room,o))return false;
  return ![...room.doors,...room.windows].some(other=>other.key!==o.key&&other.placed&&other.edge_id===o.edge_id&&Math.max(other.offset_m,o.offset_m)<Math.min(other.offset_m+other.width_m,o.offset_m+o.width_m)-EPS);
}
export function placementIssue(room,placements,defs,p) {
  if(!p.placed)return '';
  const def=defs.find(d=>d.key===p.key);
  if(!def||!validateRoom(room.vertices).valid)return '部屋または家具の形状が不正です。';
  const poly=polygon(footprint(def,p));
  if(multiArea(clipping.difference(poly,polygon(room.vertices)))>1e-8)return '家具が部屋の外に出ています。';
  for(const other of placements) {
    const od=defs.find(d=>d.key===other.key);
    if(other.key!==p.key&&other.placed&&od&&od.ceiling_mounted===def.ceiling_mounted&&multiArea(clipping.intersection(poly,polygon(footprint(od,other))))>1e-8)return '家具が重なっています。';
  }
  if(!def.ceiling_mounted)for(const door of room.doors) {
    const front=doorFront(room,door);
    if(front.length&&multiArea(clipping.intersection(poly,front))>1e-8)return 'ドア前の50cmを空けてください。';
  }
  return '';
}
export function reconcileRoom(room,placements,defs) {
  const nextRoom=clone(room),next=clone(placements),openings=[],furniture=[];
  for(const o of [...nextRoom.doors,...nextRoom.windows])if(o.placed&&!openingValid(nextRoom,o)){o.placed=false;openings.push(o.key);}
  for(const p of next)if(p.placed&&placementIssue(nextRoom,next,defs,p)){p.placed=false;p.installation_confirmed=false;furniture.push(p.key);}
  return {room:nextRoom,placements:next,openings,furniture};
}
export function snapToWall(room,def,p) {
  let faces=[];
  if(['shelf','tv_unit'].includes(p.key))faces=[{x:0,y:-1}];
  if(p.key==='bed')faces=[{x:-1,y:0},{x:0,y:1},{x:0,y:-1}];
  let best=p,bestDistance=.15;
  const winding=Math.sign(signedArea(room.vertices));
  room.vertices.forEach((a,i)=>{
    const b=room.vertices[(i+1)%room.vertices.length],length=distance(a,b),t={x:(b.x-a.x)/length,y:(b.y-a.y)/length},out={x:t.y*winding,y:-t.x*winding};
    const intervals=[...room.doors,...room.windows].filter(o=>o.placed&&o.edge_id===a.id).map(o=>[o.offset_m,o.offset_m+o.width_m]).sort((a,b)=>a[0]-b[0]);
    const segments=[];let start=0;
    for(const [lo,hi] of [...intervals,[length,length]]){if(lo>start)segments.push([start,lo]);start=Math.max(start,hi);}
    for(const face of faces){
      const angle=((Math.atan2(face.y,face.x)-Math.atan2(out.y,out.x))*180/Math.PI+360)%360;
      if(Math.abs(((angle-p.rotation_deg+540)%360)-180)>10)continue;
      const candidate={...p,rotation_deg:angle};
      const half=face.x?def.width_m/2:def.depth_m/2;
      const center={x:p.x_m+out.x*half,y:p.y_m+out.y*half};
      const along=(center.x-a.x)*t.x+(center.y-a.y)*t.y;
      const span=face.x?def.depth_m:def.width_m;
      if(!segments.some(([lo,hi])=>along-span/2>=lo-EPS&&along+span/2<=hi+EPS))continue;
      const gap=(center.x-a.x)*out.x+(center.y-a.y)*out.y+.02;
      if(Math.abs(gap)<bestDistance){candidate.x_m-=out.x*gap;candidate.y_m-=out.y*gap;best=candidate;bestDistance=Math.abs(gap);}
    }
  });
  return best;
}
