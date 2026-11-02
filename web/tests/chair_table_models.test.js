import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FurnitureModels, MODEL_REGISTRY } from '../src/furniture_models.js';
import { RoomScene } from '../src/room_scene.js';
import { preset, footprint, pointInside } from '../src/room_geometry.js';

const catalog=JSON.parse(await readFile(new URL('../../contracts/v2/catalog.json',import.meta.url),'utf8'));
// GLB files are not in git; see assets/kenney/furniture-kit/README.md to restore them.
const skip=key=>!existsSync(new URL(`../public${MODEL_REGISTRY[key].url}`,import.meta.url))&&`${key} GLB is not present`;
for(const key of ['chair','table','tv_unit'])test(`${key}: actual GLB fits, rotates, selects and switches to box`,{skip:skip(key)},async()=>{
  const definition=catalog.furniture.find(d=>d.key===key);
  const models=new FurnitureModels({load:async url=>{
    const bytes=await readFile(new URL(`../public${url}`,import.meta.url));
    return new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  }});
  const scene=Object.create(RoomScene.prototype);scene.group=new THREE.Group();scene.models=models;scene.useModels=true;
  try {
    models.request(key);await models.assets.values().next().value;await new Promise(resolve=>setImmediate(resolve));
    const room={vertices:preset('square',20),doors:[],windows:[],ceiling_height_m:2.5};
    for(const angle of [0,90,180,270,37]){
      const placement={key,x_m:2,y_m:2,rotation_deg:angle,placed:true};
      scene.update(room,[placement],[definition],key);scene.group.updateMatrixWorld(true);
      const root=scene.group.children.find(o=>o.userData.furnitureKey===key),model=root.getObjectByName('furniture-model');
      assert.ok(model,'the registered model must load without falling back');
      const localBounds=new THREE.Box3().setFromObject(model.clone(true)),size=localBounds.getSize(new THREE.Vector3());
      for(const [actual,expected] of [[size.x,definition.width_m],[size.y,definition.height_m],[size.z,definition.depth_m],[localBounds.min.y,0]])assert.ok(Math.abs(actual-expected)<1e-5);
      const polygon=footprint(definition,placement);let backVertices=0,screenVertices=0;
      model.traverse(mesh=>{
        if(!mesh.isMesh)return;
        const position=mesh.geometry.attributes.position;
        const index=mesh.geometry.index;
        for(let i=0;i<(index?index.count:position.count);i++){
          const world=mesh.localToWorld(new THREE.Vector3().fromBufferAttribute(position,index?index.getX(i):i));
          assert.ok(pointInside({x:world.x,y:-world.z},polygon),'actual vertices stay inside placement footprint');
          if(key==='tv_unit'&&mesh.material.name==='metal'){
            screenVertices++;const local=root.worldToLocal(world.clone());
            assert.ok(local.z<0,'TV screen is NORTH, aligned with the forward hazard and clearance');
          }
          if(key==='chair'){
            const local=root.worldToLocal(world.clone());
            if(local.y>definition.height_m*.8){
              backVertices++;assert.ok(local.z>definition.depth_m*.25,'backrest is SOUTH, opposite the NORTH/front clearance');
            }
          }
        }
      });
      if(key==='chair')assert.ok(backVertices>0);
      if(key==='tv_unit')assert.ok(screenVertices>0,'verify the actual screen geometry, not only the enclosing box');
      scene.ray=new THREE.Raycaster(new THREE.Vector3(2,3,-2),new THREE.Vector3(0,-1,0));
      assert.equal(scene.hitFurniture(),key);
      assert.ok(root.getObjectByName('furniture-outline'));
      scene.useModels=false;scene.update(...scene.lastUpdate);
      const boxRoot=scene.group.children.find(o=>o.userData.furnitureKey===key);
      assert.ok(boxRoot.getObjectByName('furniture-box'));assert.equal(boxRoot.getObjectByName('furniture-model'),undefined);
      scene.useModels=true;
    }
  } finally { scene.clear();models.dispose(); }
});
