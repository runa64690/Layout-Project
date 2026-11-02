import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { bounds, validateRoom, placementIssue } from './room_geometry.js';
import { FurnitureModels } from './furniture_models.js';

export class RoomScene {
  constructor(root,onPointer,{onInvalidate,onModelError}={}) {
    this.root=root;
    this.useModels=true;
    this.models=new FurnitureModels({onChange:()=>{if(!this.disposed&&!root.hidden){if(onInvalidate)onInvalidate();else if(this.lastUpdate)this.update(...this.lastUpdate);}},onError:onModelError});
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.shadowMap.enabled=true;
    this.renderer.setClearColor('#eef2ec');
    root.append(this.renderer.domElement);
    this.labelLayer=document.createElement('div');this.labelLayer.className='scene-labels';root.append(this.labelLayer);
    this.labels=[];
    this.scene=new THREE.Scene();
    this.scene.add(new THREE.HemisphereLight('#ffffff','#b5b7a7',3));
    const sun=new THREE.DirectionalLight('#fff6df',3);sun.position.set(3,10,5);sun.castShadow=true;this.scene.add(sun);
    this.camera=new THREE.PerspectiveCamera(42,1,.01,200);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.maxPolarAngle=Math.PI/2.05;this.controls.enableDamping=true;
    this.group=new THREE.Group();this.scene.add(this.group);
    this.ray=new THREE.Raycaster();this.plane=new THREE.Plane(new THREE.Vector3(0,1,0),0);
    this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(root);
    for(const type of ['pointerdown','pointermove','pointerup','pointercancel'])this.renderer.domElement.addEventListener(type,event=>{
      const rect=this.renderer.domElement.getBoundingClientRect();
      this.ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1),this.camera);
      const p=this.ray.ray.intersectPlane(this.plane,new THREE.Vector3());
      if(p)onPointer(type,event,{x:p.x,y:-p.z},type==='pointerdown'?this.hitFurniture():null);
    },{capture:true});
    this.renderer.setAnimationLoop(()=>{if(!root.hidden){this.controls.update();this.renderer.render(this.scene,this.camera);this.positionLabels();}});
  }
  hitFurniture(){this.group.updateMatrixWorld(true);const targets=[];this.group.traverse(o=>{if(o.userData.furnitureHit)targets.push(o);});const hits=this.ray.intersectObjects(targets,false);return hits[0]?.object.userData.furnitureKey||null;}
  positionLabels(){for(const {element,position} of this.labels){const p=position.clone().project(this.camera);element.hidden=p.z>1||p.z<-1;element.style.left=`${(p.x+1)/2*this.root.clientWidth}px`;element.style.top=`${(1-p.y)/2*this.root.clientHeight}px`;}}
  resize(){const w=this.root.clientWidth,h=this.root.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  zoom(factor){const offset=this.camera.position.clone().sub(this.controls.target);offset.multiplyScalar(factor);offset.clampLength(1,80);this.camera.position.copy(this.controls.target).add(offset);this.controls.update();}
  clear(){for(const child of [...this.group.children]){child.traverse(o=>{if(o.userData.sharedModelAsset)return;o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});this.group.remove(child);}this.labels=[];this.labelLayer?.replaceChildren();}
  fit(vertices){const b=bounds(vertices),cx=(b.minX+b.maxX)/2,cy=(b.minY+b.maxY)/2,size=Math.max(b.maxX-b.minX,b.maxY-b.minY,2);this.camera.position.set(cx+size*.9,size*1.5,-cy+size*1.3);this.controls.target.set(cx,0,-cy);this.controls.update();this.resize();}
  meshPolygon(points,color,y=.02,opacity=1){const shape=new THREE.Shape(points.map(p=>new THREE.Vector2(p.x,p.y)));const geometry=new THREE.ShapeGeometry(shape);geometry.rotateX(-Math.PI/2);const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,transparent:opacity<1,opacity}));mesh.position.y=y;mesh.receiveShadow=true;return mesh;}
  box(w,h,d,color,x,y,z,rotation=0,opacity=1){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshStandardMaterial({color,transparent:opacity<1,opacity}));m.position.set(x,y,z);m.rotation.y=rotation;m.castShadow=true;m.receiveShadow=true;return m;}
  update(room,placements,defs,selected,regions=[]){
    if(this.disposed)return;
    this.lastUpdate=[room,placements,defs,selected,regions];
    this.clear();if(!validateRoom(room.vertices).valid)return;
    this.group.add(this.meshPolygon(room.vertices,'#e1d4ba',0));
    room.vertices.forEach((a,i)=>{
      const b=room.vertices[(i+1)%room.vertices.length],len=Math.hypot(b.x-a.x,b.y-a.y),t={x:(b.x-a.x)/len,y:(b.y-a.y)/len};
      if(this.labelLayer){const element=document.createElement('span');element.textContent=`${len.toFixed(2)} m`;this.labelLayer.append(element);this.labels.push({element,position:new THREE.Vector3((a.x+b.x)/2,.08,-(a.y+b.y)/2)});}
      const openings=[...room.doors.map(o=>({...o,kind:'door'})),...room.windows.map(o=>({...o,kind:'window'}))].filter(o=>o.placed&&o.edge_id===a.id).sort((a,b)=>a.offset_m-b.offset_m);
      const addWall=(start,end,height,base=0,color='#e6e9df')=>{if(end<=start)return;const mid=(start+end)/2;this.group.add(this.box(end-start,height,.07,color,a.x+t.x*mid,base+height/2,-a.y-t.y*mid,Math.atan2(t.y,t.x),.38));};
      let start=0;
      for(const o of openings){addWall(start,o.offset_m,room.ceiling_height_m);if(o.kind==='window'){addWall(o.offset_m,o.offset_m+o.width_m,.85);addWall(o.offset_m,o.offset_m+o.width_m,1.15,.85,'#90c9d6');}addWall(o.offset_m,o.offset_m+o.width_m,room.ceiling_height_m-2,2);start=o.offset_m+o.width_m;}
      addWall(start,len,room.ceiling_height_m);
    });
    for(const p of placements){if(!p.placed)continue;const d=defs.find(d=>d.key===p.key);if(!d)continue;const y=d.ceiling_mounted?room.ceiling_height_m-d.height_m:0;
      const bad=placementIssue(room,placements,defs,p);
      const root=new THREE.Group();root.userData.furnitureKey=p.key;root.position.set(p.x_m,y,-p.y_m);root.rotation.y=-p.rotation_deg*Math.PI/180;this.group.add(root);
      const model=this.useModels!==false?this.models?.create(d.model_id,d):null;
      if(model){model.name='furniture-model';root.add(model);}
      else {
        const mesh=this.box(d.width_m,d.height_m,d.depth_m,bad?'#cc655c':selected===p.key?'#c58a44':'#6e8c7b',0,d.height_m/2,0,0,d.ceiling_mounted?.55:1);mesh.name='furniture-box';root.add(mesh);
        if(p.key==='bed'){const pillow=this.box(d.width_m*.2,.08,d.depth_m*.8,'#f7f1e6',-d.width_m*.35,d.height_m/2+.04,0);mesh.add(pillow);}
      }
      const hit=new THREE.Mesh(new THREE.BoxGeometry(d.width_m,d.height_m,d.depth_m),new THREE.MeshBasicMaterial({visible:false}));hit.position.y=d.height_m/2;hit.userData.furnitureHit=true;hit.userData.furnitureKey=p.key;root.add(hit);
      if(bad||selected===p.key){const geometry=new THREE.BoxGeometry(d.width_m+.006,d.height_m+.006,d.depth_m+.006);const outline=new THREE.LineSegments(new THREE.EdgesGeometry(geometry),new THREE.LineBasicMaterial({color:bad?'#cc655c':'#c58a44'}));geometry.dispose();outline.name='furniture-outline';outline.position.y=d.height_m/2;root.add(outline);}
    }
    for(const r of regions)this.group.add(this.meshPolygon(r.points,r.kind==='door_front'?'#71a5b3':'#dc8062',.035,.5));
  }
  dispose(){this.disposed=true;this.lastUpdate=null;this.observer.disconnect();this.renderer.setAnimationLoop(null);this.clear();this.models.dispose();this.controls.dispose();this.renderer.dispose();}
}
