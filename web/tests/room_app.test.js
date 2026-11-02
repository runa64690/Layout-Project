// DOM interaction tests, not a replacement for a real rendering/touch check.
import { test,beforeEach,afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { startRoomApp } from '../src/room_app.js';

const defs=[{key:'bed',label:'ベッド',width_m:1.5,depth_m:1,height_m:.75,ceiling_mounted:false},
  {key:'chair',label:'椅子',width_m:.25,depth_m:.25,height_m:.5,ceiling_mounted:false}];
let dom,errors,requests,failFetch,reduce,timers,jobResponse;
const originalTimeout=globalThis.setTimeout;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const q=selector=>document.querySelector(selector);
const click=selector=>{assert.ok(q(selector),selector);q(selector).click();};
const event=(target,type,x,y,extra={})=>{const e=new dom.window.MouseEvent(type,{bubbles:true,clientX:x,clientY:y,button:0,...extra});Object.defineProperty(e,'pointerId',{value:1});target.dispatchEvent(e);};
function world(x,y){const [vx,vy,w,h]=q('#plan').getAttribute('viewBox').split(' ').map(Number);return [(x-vx)/w*900,(-y-vy)/h*600];}
function dragVertex(index,x,y,cancel=false){
  const circle=q(`[data-vertex="${index}"]`),start=world(Number(circle.getAttribute('cx')),-Number(circle.getAttribute('cy'))),end=world(x,y);
  event(circle,'pointerdown',...start);event(q('#viewport'),'pointermove',...end);event(q('#viewport'),cancel?'pointercancel':'pointerup',...end);
}
function place(x,y){event(q('#plan'),'pointerdown',...world(x,y));event(q('#viewport'),'pointerup',...world(x,y));}

beforeEach(()=>{
  dom=new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>',{url:'http://localhost/'});
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,ResizeObserver:class{observe(){}disconnect(){}},matchMedia:()=>({matches:reduce})});
  Object.defineProperties(dom.window.HTMLElement.prototype,{clientWidth:{get(){return 900;}},clientHeight:{get(){return 600;}}});
  dom.window.SVGElement.prototype.getBoundingClientRect=()=>({left:0,top:0,width:900,height:600});
  dom.window.HTMLElement.prototype.setPointerCapture=()=>{};
  dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  errors=[];requests=[];failFetch=false;reduce=false;timers=[];jobResponse=null;
  dom.window.addEventListener('error',e=>errors.push(e.error));
  globalThis.setTimeout=(fn,ms)=>{const id=originalTimeout(fn,ms);timers.push(id);return id;};
  globalThis.fetch=async(path,options)=>{
    if(failFetch)throw new Error('offline');
    if(path.endsWith('/catalog'))return {ok:true,json:async()=>({furniture:defs})};
    if(path.endsWith('/optimization-jobs/job1'))return {ok:true,json:async()=>jobResponse};
    const data=JSON.parse(options.body);requests.push({path,data});
    if(path.endsWith('/optimization-jobs')){
      jobResponse={id:'job1',status:'succeeded',revision:data.layout.revision,candidates:[{
        placements:data.layout.placements.map(p=>({...p,x_m:p.x_m+.3})),
        safety:{status:'met',violation_count:0},valid:true,cost:0,
      }]};
      return {ok:true,json:async()=>({id:'job1',status:'queued',revision:data.layout.revision})};
    }
    return {ok:true,json:async()=>({schema_version:2,revision:data.revision,regions:[],limitations:['25cm格子による近似'],safety:{status:'not_evaluated',violation_count:0,overlap_area_m2:0,issues:[],unassessed:['No exit']}})};
  };
});
afterEach(()=>{for(const id of timers)clearTimeout(id);globalThis.setTimeout=originalTimeout;dom.window.close();assert.deepEqual(errors,[]);});

test('initial UI selects square and six tatami; all shape and size controls work',async()=>{
  startRoomApp();await flush();
  assert.match(q('#area-value').textContent,/6.00/);assert.equal(q('#area-m2').textContent,'9.72 ㎡');
  assert.equal(q('[data-shape="square"]').getAttribute('aria-pressed'),'true');
  for(const shape of ['l','reverse_l','convex','concave','s','reverse_s','rectangle','square']){
    click(`[data-shape="${shape}"]`);assert.equal(q('#continue').disabled,false);assert.equal(q('#area-m2').textContent,'9.72 ㎡');
  }
  click('[data-size="20"]');assert.equal(q('#area-m2').textContent,'32.40 ㎡');
  click('#undo');assert.equal(q('[data-size="6"]').getAttribute('aria-pressed'),'true');assert.equal(q('#area-m2').textContent,'9.72 ㎡');
});

test('vertex drag creates diagonal, undo restores coordinates, cancel rolls back',async()=>{
  startRoomApp();await flush();const before=q('.floor').getAttribute('points');
  dragVertex(2,2.5,3.1);assert.notEqual(q('.floor').getAttribute('points'),before);assert.equal(q('#continue').disabled,false);
  assert.ok([...q('#plan').querySelectorAll('text')].every(e=>/^\d+\.\d{2} m$/.test(e.textContent)));
  click('#undo');assert.equal(q('.floor').getAttribute('points'),before);
  dragVertex(2,2,2,true);assert.equal(q('.floor').getAttribute('points'),before);
});

test('edge drag preserves connectivity and updates area',async()=>{
  startRoomApp();await flush();const edge=q('[data-edge="0"]'),start=world(1.5,0),end=world(1.5,-.5);
  event(edge,'pointerdown',...start);event(q('#viewport'),'pointermove',...end);event(q('#viewport'),'pointerup',...end);
  assert.equal(q('[data-edge="0"]').getAttribute('y1'),'0.5');assert.equal(q('[data-edge="0"]').getAttribute('y2'),'0.5');
  assert.equal(q('[data-edge="1"]').getAttribute('y1'),'0.5');assert.notEqual(q('#area-m2').textContent,'9.72 ㎡');
});

test('invalid draft stays visible in red and blocks continue until repaired',async()=>{
  startRoomApp();await flush();dragVertex(1,-1,1);
  assert.equal(q('#continue').disabled,true);assert.equal(q('#area-m2').textContent,'計算できません');assert.ok(q('line[stroke="#c94f49"]'));
  click('#undo');assert.equal(q('#continue').disabled,false);assert.equal(q('#area-m2').textContent,'9.72 ㎡');
});

test('reduced motion suppresses burst on initial display and preset changes',async()=>{
  reduce=true;startRoomApp();await flush();assert.equal(q('#plan').classList.contains('pop'),false);click('[data-shape="s"]');assert.equal(q('#viewport').classList.contains('burst'),false);
});

test('furniture placement, arbitrary rotation and evaluation use meter API; changes mark results stale',async()=>{
  startRoomApp();await flush();click('#continue');click('[data-furniture="chair"]');place(1,1);
  assert.ok(q('[data-furniture-shape="chair"]'));
  q('#rotation').value='37';q('#rotation').dispatchEvent(new dom.window.Event('input',{bubbles:true}));
  click('#evaluate');await flush();
  assert.equal(requests.length,1);assert.equal(requests[0].data.placements[0].rotation_deg,37);
  assert.ok(Math.abs(requests[0].data.placements[0].x_m-1)<1e-9);assert.match(q('#results').textContent,/未評価/);
  click('#turn-right');assert.match(q('#results').textContent,/変更前の配置/);
});

test('failed evaluation preserves furniture and reconnect can retry',async()=>{
  startRoomApp();await flush();click('#continue');click('[data-furniture="chair"]');place(1,1);
  const before=q('[data-furniture-shape="chair"] polygon').getAttribute('points');failFetch=true;click('#evaluate');await flush();
  assert.equal(q('[data-furniture-shape="chair"] polygon').getAttribute('points'),before);assert.match(q('#notice').textContent,/編集内容は保持/);
  failFetch=false;click('#evaluate');await flush();assert.equal(requests.length,1);
});

test('room edit is a draft, confirms affected furniture and unplaces only affected item',async()=>{
  startRoomApp();await flush();click('#continue');click('[data-furniture="bed"]');place(2.2,1.5);click('[data-furniture="chair"]');place(.5,.5);
  click('#edit-room');click('[data-shape="l"]');click('#continue');
  assert.equal(q('#confirm-room').open,true);assert.match(q('#confirm-text').textContent,/ベッド/);
  click('#confirm-cancel');assert.ok(q('#continue'));
  click('#continue');click('#confirm-apply');assert.ok(q('[data-furniture-shape="chair"]'));assert.equal(q('[data-furniture-shape="bed"]'),null);
});

test('stale candidate is revalidated and triggers evaluation with current room',async()=>{
  startRoomApp();await flush();click('#continue');click('[data-furniture="chair"]');place(1,1);
  click('#optimize');await flush();await flush();assert.ok(q('[data-candidate="0"]'));
  click('#turn-right');assert.match(q('#results').textContent,/変更前の条件/);
  click('[data-candidate="0"]');await flush();
  assert.equal(requests.at(-1).path,'/api/v2/evaluate');assert.ok(requests.at(-1).data.revision>jobResponse.revision);
  assert.ok(Math.abs(requests.at(-1).data.placements[0].x_m-1.3)<1e-8);
});

test('candidate that moves a currently fixed item is rejected',async()=>{
  startRoomApp();await flush();click('#continue');click('[data-furniture="chair"]');place(1,1);
  click('#optimize');await flush();await flush();click('#fixed');
  const before=q('[data-furniture-shape="chair"] polygon').getAttribute('points');click('[data-candidate="0"]');await flush();
  assert.equal(q('[data-furniture-shape="chair"] polygon').getAttribute('points'),before);assert.match(q('#notice').textContent,/固定中/);
});

test('door and window positioning on a wall enforces opening overlap',async()=>{
  startRoomApp();await flush();click('#continue');click('#add-door');place(1,0);
  assert.match(q('.opening-list').textContent,/ドア 0.80m/);
  click('#add-window');place(1,0);assert.match(q('#notice').textContent,/重なり/);
  assert.equal(q('.opening-list').children.length,1);
  place(2.5,0);assert.equal(q('.opening-list').children.length,2);
});

test('model display toggle persists across 2D, preserves evaluation and redraws latest data after loading',async()=>{
  let callbacks,lastDraw,drawCount=0;
  const fake={fit(){},resize(){},controls:{},dispose(){},update(...args){lastDraw=structuredClone(args);drawCount++;}};
  startRoomApp({createScene:(root,pointer,options)=>{callbacks=options;return fake;}});await flush();
  click('#continue');click('[data-furniture="chair"]');place(1,1);click('#evaluate');await flush();
  const evaluation=requests[0].data,result=q('#results').innerHTML;
  assert.equal(q('#model-switch').hidden,true);click('#view-3d');assert.equal(fake.useModels,true);assert.equal(q('#model-switch').hidden,false);
  click('#show-boxes');assert.equal(fake.useModels,false);assert.equal(q('#show-boxes').getAttribute('aria-pressed'),'true');
  click('#view-2d');const count=drawCount;callbacks.onInvalidate();assert.equal(drawCount,count);
  click('#view-3d');assert.equal(fake.useModels,false);click('#show-models');assert.equal(fake.useModels,true);
  assert.equal(q('#results').innerHTML,result);assert.equal(requests.length,1);
  click('#evaluate');await flush();assert.deepEqual(requests[1].data,evaluation);
  click('#unplace');callbacks.onInvalidate();assert.equal(lastDraw[1][0].placed,false);
  callbacks.onModelError('chair');assert.match(q('#notice').textContent,/箱で表示/);
});
