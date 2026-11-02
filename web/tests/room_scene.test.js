import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { RoomScene } from '../src/room_scene.js';
import { SHAPES,preset,area,footprint } from '../src/room_geometry.js';

// Exercise the real Three.js mesh math without claiming a WebGL render test.
const scene=()=>{const s=Object.create(RoomScene.prototype);s.group=new THREE.Group();return s;};
for(const [shape] of SHAPES)test(`${shape}: Three.js triangulation preserves floor area`,()=>{
  const s=scene(),vertices=preset(shape,6);
  s.update({vertices,doors:[],windows:[],ceiling_height_m:2.5},[],[],null);
  const floor=s.group.children[0],positions=floor.geometry.attributes.position,index=floor.geometry.index;
  let total=0;
  for(let i=0;i<index.count;i+=3){const pts=[0,1,2].map(j=>({x:positions.getX(index.getX(i+j)),y:-positions.getZ(index.getX(i+j))}));total+=area(pts);}
  assert.ok(Math.abs(total-9.72)<1e-5);s.clear();assert.equal(s.group.children.length,0);
});
test('3D furniture rotation and dimensions match the 2D footprint',()=>{
  const s=scene(),r={vertices:preset('square',20),doors:[],windows:[],ceiling_height_m:2.5};
  const def={key:'table',width_m:1.5,depth_m:.8,height_m:.7},p={key:'table',x_m:2,y_m:2,rotation_deg:37,placed:true};
  s.update(r,[p],[def],null);s.group.updateMatrixWorld(true);
  const mesh=s.group.children.find(o=>o.userData.furnitureKey==='table'),expected=footprint(def,p);
  for(const [x,z] of [[-.75,.4],[.75,.4],[.75,-.4],[-.75,-.4]]){const w=mesh.localToWorld(new THREE.Vector3(x,0,z));assert.ok(expected.some(p=>Math.hypot(p.x-w.x,p.y+w.z)<1e-6));}
});
test('invalid room never generates a misleading floor mesh',()=>{
  const s=scene();s.update({vertices:[{x:0,y:0},{x:2,y:2},{x:0,y:2},{x:2,y:0}],doors:[],windows:[]},[],[],null);assert.equal(s.group.children.length,0);
});

test('3D picking selects a tall furniture surface above the floor',()=>{
  const s=scene(),r={vertices:preset('square',20),doors:[],windows:[],ceiling_height_m:2.5};
  const def={key:'shelf',width_m:1,depth_m:.5,height_m:1.75,ceiling_mounted:false},p={key:'shelf',x_m:2,y_m:2,rotation_deg:0,placed:true};
  s.update(r,[p],[def],null);s.ray=new THREE.Raycaster(new THREE.Vector3(2,3,0),new THREE.Vector3(0,-1.25,-2).normalize());
  assert.equal(s.hitFurniture(),'shelf');
});
