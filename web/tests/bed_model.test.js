import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FurnitureModels } from '../src/furniture_models.js';
import { RoomScene } from '../src/room_scene.js';
import { pointInside, footprint } from '../src/room_geometry.js';

// GLB files are not in git; see assets/kenney/furniture-kit/README.md to restore them.
const skip=!existsSync(new URL('../public/models/bed-single.glb',import.meta.url))&&'bed-single.glb is not present';

test('real bed pillow lies in the API head region at 0, 90, 180, 270 and 37 degrees',{skip},async()=>{
  const fixture=JSON.parse(await readFile(new URL('../../contracts/v2/bed-head.json',import.meta.url),'utf8'));
  const bytes=await readFile(new URL('../public/models/bed-single.glb',import.meta.url));
  const models=new FurnitureModels({load:()=>new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'')});
  try {
    assert.equal(fixture.definition.pillow_side,'WEST');
    models.request('bed');await models.assets.values().next().value;await new Promise(resolve=>setImmediate(resolve));
    const s=Object.create(RoomScene.prototype);s.group=new THREE.Group();s.models=models;s.useModels=true;
    for(const {placement,head} of fixture.cases){
      s.update(fixture.room,[placement],[fixture.definition],'bed');s.group.updateMatrixWorld(true);
      const root=s.group.children.find(o=>o.userData.furnitureKey==='bed'),visual=root.getObjectByName('furniture-model');
      assert.ok(visual,'bed GLB must load instead of falling back to a box');
      const pillow=visual.getObjectByName('pillow');assert.ok(pillow?.isMesh,'check the actual named pillow mesh');
      const positions=pillow.geometry.attributes.position;
      for(let i=0;i<positions.count;i++){
        const vertex=pillow.localToWorld(new THREE.Vector3().fromBufferAttribute(positions,i));
        assert.ok(pointInside({x:vertex.x,y:-vertex.z},head),`pillow vertex ${i} is outside API head at ${placement.rotation_deg} degrees`);
      }
      const occupied=footprint(fixture.definition,placement);
      const box=new THREE.Box3().setFromObject(visual);
      assert.ok(Math.abs(box.min.y)<1e-6);assert.ok(Math.abs(box.max.y-fixture.definition.height_m)<1e-6);
      const size=new THREE.Box3().setFromObject(visual.clone(true)).getSize(new THREE.Vector3());
      assert.ok(Math.abs(size.x-fixture.definition.width_m)<1e-5);
      assert.ok(Math.abs(size.z-fixture.definition.depth_m)<1e-5);
      // The shaped model need not fill every corner of its rectangular bounds.
      // Check containment of actual vertices, not equality of rotated AABBs.
      visual.traverse(mesh=>{
        if(!mesh.isMesh)return;
        const points=mesh.geometry.attributes.position;
        for(let i=0;i<points.count;i++){
          const vertex=mesh.localToWorld(new THREE.Vector3().fromBufferAttribute(points,i));
          assert.ok(pointInside({x:vertex.x,y:-vertex.z},occupied),`bed vertex outside footprint at ${placement.rotation_deg} degrees`);
        }
      });
      s.useModels=false;s.update(...s.lastUpdate);s.group.updateMatrixWorld(true);
      const fallback=s.group.children.find(o=>o.userData.furnitureKey==='bed').getObjectByName('furniture-box');
      assert.ok(fallback);const marker=fallback.children[0];assert.ok(marker);
      const center=marker.getWorldPosition(new THREE.Vector3());assert.ok(pointInside({x:center.x,y:-center.z},head),'box pillow agrees with the model');
      s.useModels=true;s.clear();
    }
  } finally { models.dispose(); }
});
