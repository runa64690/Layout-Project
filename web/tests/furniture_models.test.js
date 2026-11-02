import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FurnitureModels, normalizeModel } from '../src/furniture_models.js';
import { RoomScene } from '../src/room_scene.js';
import { preset, footprint } from '../src/room_geometry.js';

// GLB files are not in git; see assets/kenney/furniture-kit/README.md to restore them.
const skip=!existsSync(new URL('../public/models/bookcase-open.glb',import.meta.url))&&'bookcase-open.glb is not present';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const def={key:'shelf',model_id:'shelf',width_m:1,depth_m:.5,height_m:1.75};
const placement={key:'shelf',x_m:2,y_m:2,rotation_deg:0,placed:true};
const room={vertices:preset('square',20),doors:[],windows:[],ceiling_height_m:2.5};
const readShelf=async()=>{
  const bytes=await readFile(new URL('../public/models/bookcase-open.glb',import.meta.url));
  return new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
};
const scene=models=>{const s=Object.create(RoomScene.prototype);s.group=new THREE.Group();s.models=models;s.useModels=true;return s;};
const furniture=s=>s.group.children.find(o=>o.userData.furnitureKey==='shelf');
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-5,`${a} != ${b}`);

test('bundled GLB preserves shelf geometry and wood color; unit template fits catalog bounds',{skip},async()=>{
  const {scene:source}=await readShelf();let vertices=0;
  source.traverse(o=>{if(o.isMesh){vertices+=o.geometry.attributes.position.count;assert.equal(o.material.color.getHexString(),'e59964');}});
  assert.equal(vertices,960);
  const normalized=normalizeModel(source,[0,90,0]);
  normalized.scale.set(def.width_m,def.height_m,def.depth_m);
  const box=new THREE.Box3().setFromObject(normalized),size=box.getSize(new THREE.Vector3());
  close(size.x,1);close(size.y,1.75);close(size.z,.5);close(box.min.y,0);close(box.getCenter(new THREE.Vector3()).x,0);close(box.getCenter(new THREE.Vector3()).z,0);
});

test('model and independent picking box match 2D footprints at arbitrary angles and ceiling height',{skip},async()=>{
  const models=new FurnitureModels({load:readShelf});models.request('shelf');await flush();await models.assets.values().next().value;await flush();
  const s=scene(models);
  for(const angle of [0,90,37]){
    const p={...placement,rotation_deg:angle};s.update(room,[p],[def],'shelf');s.group.updateMatrixWorld(true);
    const root=furniture(s),model=root.getObjectByName('furniture-model');assert.ok(model);
    const expected=footprint(def,p);
    for(const [x,z] of [[-.5,.25],[.5,.25],[.5,-.25],[-.5,-.25]]){
      const point=root.localToWorld(new THREE.Vector3(x,0,z));assert.ok(expected.some(p=>Math.hypot(p.x-point.x,p.y+point.z)<1e-6));
    }
    const localBox=new THREE.Box3().setFromObject(model.clone(true));close(localBox.min.y,0);close(localBox.max.y,1.75);
  }
  s.update(room,[placement],[def],null);
  // Hits the gap between shelves: only the catalog box participates in picking.
  s.ray=new THREE.Raycaster(new THREE.Vector3(2,.3,0),new THREE.Vector3(0,0,-1));assert.equal(s.hitFurniture(),'shelf');
  s.update(room,[placement],[{...def,ceiling_mounted:true}],null);
  s.group.updateMatrixWorld(true);
  close(new THREE.Box3().setFromObject(furniture(s).getObjectByName('furniture-model')).max.y,2.5);
  s.clear();models.dispose();
});

test('pending models use latest position and display mode; removed furniture never returns',{skip},async()=>{
  let resolve;const pending=new Promise(r=>resolve=r);let calls=0;let s;
  const models=new FurnitureModels({load:()=>{calls++;return pending;},onChange:()=>s.update(...s.lastUpdate)});s=scene(models);
  s.update(room,[placement],[def],null);assert.ok(furniture(s).getObjectByName('furniture-box'));
  s.update(room,[{...placement,x_m:3}],[def],null);s.useModels=false;
  resolve(await readShelf());await flush();
  assert.equal(calls,1);close(furniture(s).position.x,3);assert.ok(furniture(s).getObjectByName('furniture-box'));
  s.useModels=true;s.update(...s.lastUpdate);assert.ok(furniture(s).getObjectByName('furniture-model'));close(furniture(s).position.x,3);
  s.update(room,[],[def],null);assert.equal(furniture(s),undefined);s.clear();models.dispose();
  let finish;let removed;
  const delayed=new FurnitureModels({load:()=>new Promise(r=>finish=r),onChange:()=>removed.update(...removed.lastUpdate)});removed=scene(delayed);
  removed.update(room,[placement],[def],null);removed.update(room,[],[def],null);finish(await readShelf());await flush();assert.equal(furniture(removed),undefined);removed.clear();delayed.dispose();
});

test('unknown, failed and invalid models fall back without repeated requests or errors',async()=>{
  const errors=[];let calls=0;
  const models=new FurnitureModels({load:async()=>{calls++;throw new Error('offline');},onError:id=>errors.push(id)}),s=scene(models);
  s.update(room,[placement],[{...def,model_id:'unknown'}],null);assert.ok(furniture(s).getObjectByName('furniture-box'));assert.equal(calls,0);
  s.update(room,[placement],[def],null);await flush();s.update(...s.lastUpdate);await flush();
  assert.equal(calls,1);assert.deepEqual(errors,['shelf']);assert.ok(furniture(s).getObjectByName('furniture-box'));s.clear();models.dispose();
  const invalid=new FurnitureModels({load:async()=>({scene:new THREE.Group()}),onError:id=>errors.push(id)});invalid.request('shelf');await flush();assert.equal(invalid.create('shelf',def),null);assert.equal(errors.length,2);invalid.dispose();
});

test('shared resources survive redraws and release once, including late completion',{skip},async()=>{
  const asset=await readShelf();let geometry,material;asset.scene.traverse(o=>{if(o.isMesh){geometry=o.geometry;material=o.material;}});
  let disposed=0,materialDisposed=0;geometry.addEventListener('dispose',()=>disposed++);material.addEventListener('dispose',()=>materialDisposed++);
  const models=new FurnitureModels({load:async()=>asset});models.request('shelf');await flush();const s=scene(models);
  for(let i=0;i<10;i++)s.update(room,[placement],[def],'shelf');s.clear();assert.equal(disposed,0);assert.equal(materialDisposed,0);
  models.dispose();models.dispose();await flush();assert.equal(disposed,1);assert.equal(materialDisposed,1);
  let resolve;const lateAsset=await readShelf();let lateDisposed=0;lateAsset.scene.traverse(o=>o.geometry?.addEventListener('dispose',()=>lateDisposed++));
  const late=new FurnitureModels({load:()=>new Promise(r=>resolve=r),onChange:()=>assert.fail('disposed scene must not redraw')});late.request('shelf');late.dispose();resolve(lateAsset);await flush();assert.equal(lateDisposed,1);
});
