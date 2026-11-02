import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { SHAPES,SIZES,preset,area,validateRoom,moveEdge,clone,bounds,distance,footprint,
  pointInside,placementIssue,reconcileRoom,openingSegment,doorFront,multiArea,snapToWall } from '../src/room_geometry.js';

const room=(vertices)=>({vertices,doors:[],windows:[],ceiling_height_m:2.5});
const points=(values)=>values.map(([x,y],i)=>({id:`v${i}`,x,y}));
const defs=[{key:'bed',width_m:1.5,depth_m:1,height_m:.75,ceiling_mounted:false},{key:'chair',width_m:.25,depth_m:.25,height_m:.5,ceiling_mounted:false},{key:'shelf',width_m:1,depth_m:.5,height_m:1.75,ceiling_mounted:false}];
const placement=(key,x,y)=>({key,x_m:x,y_m:y,rotation_deg:0,placed:true});
for(const [shape] of SHAPES)for(const size of SIZES)test(`${shape} ${size}帖: valid exact floor area`,()=>{
  const v=preset(shape,size);assert.equal(validateRoom(v).valid,true);assert.ok(Math.abs(area(v)-size*1.62)<1e-10);assert.equal(new Set(v.map(p=>p.id)).size,v.length);
});
test('shared server fixtures match current presets',()=>{
  const fixtures=JSON.parse(readFileSync(new URL('../../contracts/room-presets.json',import.meta.url),'utf8'));
  for(const f of fixtures)assert.deepEqual(f.vertices,preset(f.shape,f.tatami));
});
test('missing room size is six tatami',()=>assert.equal(area(preset()).toFixed(2),'9.72'));
test('reverse presets are geometric mirrors',()=>{
  for(const shape of ['l','s']){const a=preset(shape),b=preset(`reverse_${shape}`),max=bounds(a).maxX;for(const p of a)assert.ok(b.some(q=>Math.abs(q.x-(max-p.x))<1e-8&&Math.abs(q.y-p.y)<1e-8));}
});
test('edge translation preserves connection, edge length and unrelated vertices',()=>{
  const a=preset(),b=moveEdge(a,0,9,-.5);assert.equal(b[0].y,-.5);assert.equal(b[1].y,-.5);assert.equal(distance(a[0],a[1]),distance(b[0],b[1]));assert.deepEqual(b.slice(2),a.slice(2));assert.equal(validateRoom(b).valid,true);assert.ok(area(b)>area(a));
});
test('diagonal wall and narrow room remain valid',()=>{
  const v=preset();v[2].x-=.7;assert.equal(validateRoom(v).valid,true);
  const narrow=validateRoom(points([[0,0],[.3,0],[.3,4],[0,4]]));assert.equal(narrow.valid,true);assert.equal(narrow.narrow,true);
});
for(const values of [ [[0,0],[2,2],[0,2],[2,0]],[[0,0],[2,0],[2,0],[0,2]],[[0,0],[2,0],[1,0],[1,2],[0,2]],[[0,0],[2,0],[2,2],[1,0],[0,2]],[[0,0],[1,0],[2,0]] ])test('invalid ring is rejected and recoverable',()=>{const before=preset();assert.equal(validateRoom(points(values)).valid,false);assert.equal(validateRoom(clone(before)).valid,true);});
test('furniture cannot span a notch even with all four corners inside',()=>{
  const r=room(points([[0,0],[3,0],[3,3],[1.6,3],[1.6,1.5],[1.4,1.5],[1.4,3],[0,3]])),p=placement('bed',1.5,1.5);
  assert.ok(footprint(defs[0],p).every(v=>pointInside(v,r.vertices)));assert.match(placementIssue(r,[p],defs,p),/部屋の外/);
});
test('diagonal opening and its clearance use the actual wall',()=>{
  const r=room(points([[0,0],[4,0],[3,3],[0,3]]));const o={key:'d',edge_id:'v1',offset_m:.5,width_m:.8,placed:true};r.doors=[o];
  const segment=openingSegment(r,o);assert.ok(Math.abs(distance(segment.a,segment.b)-.8)<1e-10);assert.ok(Math.abs(multiArea(doorFront(r,o))-.4)<1e-10);
});
test('room editing only unplaces affected furniture and openings',()=>{
  const r=room(points([[0,0],[2,0],[2,2],[0,2]]));r.windows=[{key:'w',edge_id:'v1',offset_m:1.5,width_m:1,placed:true}];
  const placements=[placement('chair',.5,.5),placement('bed',3,3)];const result=reconcileRoom(r,placements,defs);
  assert.deepEqual(result.furniture,['bed']);assert.deepEqual(result.openings,['w']);assert.equal(result.placements[0].placed,true);assert.equal(placements[1].placed,true);
});
test('wall snap leaves two centimetres and avoids openings',()=>{
  const r=room(points([[0,0],[4,0],[4,4],[0,4]])),p=placement('shelf',2,.3);
  const snapped=snapToWall(r,defs[2],p);assert.ok(Math.abs(snapped.y_m-.27)<1e-8);
  r.doors=[{key:'d',edge_id:'v0',offset_m:1.4,width_m:1.2,placed:true}];assert.deepEqual(snapToWall(r,defs[2],p),p);
});
