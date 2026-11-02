import { SHAPES,SIZES,TATAMI_M2,clone,preset,area,bounds,distance,signedArea,validateRoom,moveEdge,
  footprint,pointInside,project,openingSegment,openingValid,doorFront,placementIssue,reconcileRoom,snapToWall } from './room_geometry.js';
import { RoomScene } from './room_scene.js';

const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={shelf:'本棚',bed:'ベッド',table:'テーブル',tv_unit:'テレビ台',chair:'椅子',ceiling_light:'天井照明'};
const poseChanged=(a,b)=>!a||a.placed!==b.placed||Math.abs(a.x_m-b.x_m)>1e-8||Math.abs(a.y_m-b.y_m)>1e-8||Math.abs(a.rotation_deg-b.rotation_deg)>1e-8;

export function startRoomApp({createScene=(...args)=>new RoomScene(...args)}={}){
  const initial=preset();
  const state={shape:'square',size:6,step:'room',mode:'2d',room:{vertices:initial,ceiling_height_m:2.5,doors:[],windows:[]},draft:null,
    baseline:clone(initial),history:[],placements:[],defs:[],selected:null,openingTool:null,revision:0,evaluation:null,candidates:[],candidateRevision:null,
    fixed:new Set(),snap:true,drag:null,view:null,job:null,polling:false,scenario:'',busy:false,catalogError:false,useModels:true};
  state.draft=clone(state.room);
  document.querySelector('#app').innerHTML=`
    <header class="topbar"><a class="brand" href="./" aria-label="madori ホーム"><span class="brand-mark">⌂</span>madori<span class="brand-sub">間取りから、暮らしを整える。</span></a><span class="local-badge"><i></i>ROOM PLANNER</span></header>
    <main class="workspace"><aside class="sidebar"><nav class="steps" aria-label="作業の流れ"><span id="step-room">01 部屋をつくる</span><span id="step-furniture">02 家具を置く</span></nav><div id="panel"></div></aside>
    <section class="editor" aria-label="間取り編集エリア"><div class="editor-top"><div><p class="eyebrow">YOUR SPACE</p><h1 id="editor-title">わたしの部屋</h1></div><div class="view-switch"><button id="view-2d" class="active">2D 間取り</button><button id="view-3d">3D 確認</button></div></div>
      <div class="viewport" id="viewport"><svg id="plan" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="部屋の間取り。辺や角をドラッグして編集できます。"></svg><div id="three-root" hidden></div>
      <div class="area-card"><span>現在の広さ</span><strong id="area-value">6.00<small>帖</small></strong><span id="area-m2">9.72 ㎡</span></div>
      <div id="model-switch" class="view-switch model-switch" role="group" aria-label="家具の表示" hidden><button id="show-models" class="active" aria-pressed="true">家具モデル</button><button id="show-boxes" aria-pressed="false">箱表示</button></div>
      <div class="viewport-tools"><button id="fit" title="部屋全体を表示">全体を表示</button><button id="zoom-in" aria-label="拡大">＋</button><button id="zoom-out" aria-label="縮小">−</button></div><div id="view-hint" class="view-hint"></div></div>
      <div class="editor-bottom"><div id="geometry-message" role="status"></div><div id="actions"></div></div>
    </section></main><div id="notice" class="notice" role="status" aria-live="polite"></div>
    <dialog id="confirm-room"><h2>部屋の変更を確定</h2><p id="confirm-text"></p><div class="dialog-actions"><button id="confirm-cancel">編集に戻る</button><button id="confirm-apply" class="primary">変更を確定</button></div></dialog>`;
  const $=id=>document.getElementById(id),svg=$('plan'),viewport=$('viewport');
  let scene=null,noticeTimer=null,epoch=0;
  const activeRoom=()=>state.step==='room'?state.draft:state.room;
  function notice(message){$('notice').textContent=message;$('notice').classList.add('visible');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').classList.remove('visible'),6500);}
  function touched(){state.revision++;}
  function pushHistory(){state.history.push(clone({room:state.draft,shape:state.shape,size:state.size,baseline:state.baseline}));if(state.history.length>100)state.history.shift();}
  function undo(){if(!state.history.length)return;const before=state.history.pop();state.draft=before.room;state.shape=before.shape;state.size=before.size;state.baseline=before.baseline;render();}
  function fit(){const b=bounds(activeRoom().vertices),w=Math.max(.5,b.maxX-b.minX),h=Math.max(.5,b.maxY-b.minY);state.view={cx:(b.minX+b.maxX)/2,cy:(b.minY+b.maxY)/2,span:Math.max(w,h)*1.55};scene?.fit(activeRoom().vertices);draw();}
  function metrics(){const w=viewport.clientWidth||700,h=viewport.clientHeight||600,span=state.view?.span||6;const unit=span/Math.min(w,h);return {w,h,unit,x:state.view.cx-w*unit/2,y:-state.view.cy-h*unit/2,width:w*unit,height:h*unit};}
  function screenPoint(event){const m=metrics(),r=svg.getBoundingClientRect();return {x:m.x+(event.clientX-r.left)/r.width*m.width,y:-(m.y+(event.clientY-r.top)/r.height*m.height)};}
  const pointsAttr=v=>v.map(p=>`${p.x},${-p.y}`).join(' ');
  function thumbnail(shape){const v=preset(shape),b=bounds(v),pad=.3;return `<svg viewBox="${b.minX-pad} ${-b.maxY-pad} ${b.maxX-b.minX+pad*2} ${b.maxY-b.minY+pad*2}" aria-hidden="true"><polygon points="${pointsAttr(v)}"/></svg>`;}
  function selectionPanel(){
    return `<div class="section-heading"><p class="eyebrow">MAKE IT YOURS</p><h2>どんなお部屋ですか？</h2><p>近い形を選んで、あなたの部屋に<br>合わせて調整しましょう。</p></div><section><h3>部屋の形 <span>8 TYPES</span></h3><div class="shape-grid">${SHAPES.map(([id,label])=>`<button class="shape-card ${state.shape===id?'selected':''}" data-shape="${id}" aria-pressed="${state.shape===id}">${thumbnail(id)}<span>${label}</span></button>`).join('')}</div></section>
      <section><h3>部屋の広さ <span>帖</span></h3><div class="size-grid">${SIZES.map(s=>`<button data-size="${s}" class="${state.size===s?'selected':''}" aria-pressed="${state.size===s}">${s}<small>帖</small></button>`).join('')}</div><p class="fine">1帖 = 1.62㎡で換算しています。<br>編集すると、実際の面積に合わせて帖数が変わります。</p></section>
      <section class="tips"><span class="tip-icon">↔</span><div><strong>つかんで、部屋に合わせる</strong><p>辺を動かすと壁の位置が変わります。<br>丸い角を動かすと斜めの壁も作れます。</p></div></section>
      <div class="edit-tools"><button id="undo" ${state.history.length?'':'disabled'}>↶ 元に戻す</button><button id="reset-room">選択時の形に戻す</button></div>
      <details class="dimensions"><summary>すべての辺の長さ</summary><div id="dimension-list"></div></details>`;
  }
  function furniturePanel(){
    const selected=state.placements.find(p=>p.key===state.selected),definition=state.defs.find(d=>d.key===state.selected);
    return `<div class="section-heading"><p class="eyebrow">FIND YOUR LAYOUT</p><h2>暮らしを置いてみよう。</h2><p>家具を選んで、部屋をクリック。<br>置いた家具はドラッグで動かせます。</p></div>
      <button id="edit-room" class="back-button">← 部屋の形を編集</button>
      ${state.catalogError?'<p class="error">家具データに接続できません。</p><button id="retry-catalog">再接続</button>':''}
      <section><h3>家具 <span>CATALOG</span></h3><div class="furniture-grid">${state.defs.map(d=>{const p=state.placements.find(p=>p.key===d.key);return `<button data-furniture="${d.key}" class="${state.selected===d.key?'selected':''}"><strong>${esc(d.label)}</strong><small>${d.width_m.toFixed(2)} × ${d.depth_m.toFixed(2)} m</small><span>${p?.placed?'配置済み':p?'配置待ち':'＋ 選ぶ'}</span></button>`;}).join('')}</div></section>
      ${selected&&definition?`<section class="selected-panel"><h3>${esc(definition.label)}</h3><label for="rotation">回転 <output id="rotation-value">${selected.rotation_deg.toFixed(0)}°</output></label><input id="rotation" type="range" min="0" max="359" step="1" value="${selected.rotation_deg}"><div class="row"><button id="turn-left">−1°</button><button id="turn-right">＋1°</button><button id="unplace">配置を外す</button></div><label class="check"><input type="checkbox" id="fixed" ${state.fixed.has(selected.key)?'checked':''} ${selected.placed?'':'disabled'}>候補生成で動かさない</label><button id="remove-furniture" class="text-button">この家具を選択から外す</button></section>`:''}
      <label class="check"><input type="checkbox" id="snap" ${state.snap?'checked':''}>壁への吸着</label>
      <section><h3>ドア・窓 <span>OPENINGS</span></h3><div class="row"><button id="add-door" class="${state.openingTool?.kind==='doors'?'selected':''}">＋ ドア</button><button id="add-window" class="${state.openingTool?.kind==='windows'?'selected':''}">＋ 窓</button></div><label class="opening-width">開口幅 <input id="opening-width" type="number" min="0.1" max="10" step="0.1" value="${state.openingTool?.width||.8}"> m</label><div class="opening-list">${['doors','windows'].flatMap(kind=>state.room[kind].map(o=>`<div><span>${kind==='doors'?'ドア':'窓'} ${o.width_m.toFixed(2)}m ${o.placed?'':'・再配置が必要'}</span><button data-move-opening="${o.key}" data-kind="${kind}">移動</button><button data-delete-opening="${o.key}" data-kind="${kind}" aria-label="${esc(o.key)}を削除">×</button></div>`)).join('')}</div><p class="fine">ドア前の50cmは家具を置けません。<br>出入口を置くと避難経路も評価できます。</p></section>
      <section class="evaluation"><h3>配置を確かめる</h3><div class="row"><button id="evaluate" class="primary" ${state.busy?'disabled':''}>危険度を評価</button><button id="optimize" ${state.job?'disabled':''}>候補を3案生成</button></div>${state.job?`<p class="fine">配置候補を計算中…</p><button id="resume-job">結果取得を再開</button><button id="stop-poll">結果待ちを終了</button>`:''}<div id="results">${resultsHTML()}</div></section>`;
  }
  function resultsHTML(){
    const e=state.evaluation;let html='';
    if(e){const stale=e.revision!==state.revision;html+=`<div class="result-card ${stale?'stale':''}"><strong>${stale?'変更前の配置':e.safety.status==='met'?'設定した安全条件を達成':e.safety.status==='unmet'?'配置の見直しが必要です':'未評価の項目があります'}</strong><p>検出事項 ${e.safety.violation_count}件 ・ 重複面積 ${e.safety.overlap_area_m2.toFixed(2)}㎡</p><ul>${e.safety.issues.map(i=>`<li>${esc(labels[i.source_key]||'平常時')} → ${esc(labels[i.target_key]||i.target_key)}：${i.kind==='exposure'?'転倒・落下範囲が重なります':'出入口への経路が塞がっています'}</li>`).join('')}${e.safety.unassessed.map(u=>`<li>${u.includes('exit')?'有効な出入口がなく、避難経路を評価できません。':'ベッド・椅子がなく、人体への影響を評価できません。'}</li>`).join('')}</ul>${!stale?`<label>表示する危険範囲<select id="scenario"><option value="">表示しない</option>${[...new Set(e.regions.filter(r=>r.scenario_id).map(r=>r.scenario_id))].map(id=>`<option value="${esc(id)}" ${state.scenario===id?'selected':''}>${esc(labels[id.split(':')[0]]||id)} / ${esc(id.split(':')[1])}</option>`).join('')}</select></label>`:''}<p class="fine">${esc(e.limitations[0])}</p></div>`;}
    if(state.candidates.length){html+=`<p class="fine">${state.candidateRevision===state.revision?'配置候補':'変更前の条件で生成した候補です。適用時に再検証します。'}</p>`+state.candidates.map((c,i)=>`<button class="candidate" data-candidate="${i}"><span>案 ${i+1}</span><span>${c.safety.status==='met'?'条件達成':'参考改善案'} · 検出 ${c.safety.violation_count}件</span><b>適用 →</b></button>`).join('');}
    return html;
  }
  function render(){
    $('step-room').classList.toggle('active',state.step==='room');$('step-furniture').classList.toggle('active',state.step==='furniture');
    $('panel').innerHTML=state.step==='room'?selectionPanel():furniturePanel();
    $('editor-title').textContent=state.step==='room'?'わたしの部屋':'家具のレイアウト';
    $('actions').innerHTML=state.step==='room'?'<button id="continue" class="primary">この部屋で家具を置く <span>→</span></button>':'<span class="fine">選択した家具を配置してから評価できます。</span>';
    const bind=(id,fn)=>$(id)?.addEventListener('click',fn);
    document.querySelectorAll('[data-shape]').forEach(b=>b.onclick=()=>choose(b.dataset.shape,state.size));
    document.querySelectorAll('[data-size]').forEach(b=>b.onclick=()=>choose(state.shape,Number(b.dataset.size)));
    bind('undo',undo);
    bind('reset-room',()=>{pushHistory();state.draft.vertices=clone(state.baseline);render();fit();burst();});bind('continue',commitRoom);
    bind('edit-room',()=>{state.step='room';state.draft=clone(state.room);state.history=[];state.openingTool=null;setMode('2d');render();fit();});
    document.querySelectorAll('[data-furniture]').forEach(b=>b.onclick=()=>{const key=b.dataset.furniture;state.selected=key;state.openingTool=null;if(!state.placements.some(p=>p.key===key)){state.placements.push({key,x_m:0,y_m:0,rotation_deg:0,placed:false,restraint:'unknown',installation_confirmed:false});touched();}render();});
    bind('retry-catalog',loadCatalog);bind('turn-left',()=>rotate(-1));bind('turn-right',()=>rotate(1));
    $('rotation')?.addEventListener('input',e=>setRotation(Number(e.target.value)));
    $('fixed')?.addEventListener('change',e=>{if(e.target.checked)state.fixed.add(state.selected);else state.fixed.delete(state.selected);});
    $('snap')?.addEventListener('change',e=>state.snap=e.target.checked);
    bind('unplace',()=>{const p=state.placements.find(p=>p.key===state.selected);p.placed=false;p.installation_confirmed=false;state.fixed.delete(p.key);touched();render();});
    bind('remove-furniture',()=>{state.placements=state.placements.filter(p=>p.key!==state.selected);state.fixed.delete(state.selected);state.selected=null;touched();render();});
    const openingTool=kind=>{state.selected=null;state.openingTool={kind,width:Number($('opening-width')?.value)||.8};render();notice('配置する壁をクリックしてください。');};
    bind('add-door',()=>openingTool('doors'));bind('add-window',()=>openingTool('windows'));
    $('opening-width')?.addEventListener('change',e=>{if(state.openingTool)state.openingTool.width=Math.max(.1,Math.min(10,Number(e.target.value)||.8));});
    document.querySelectorAll('[data-move-opening]').forEach(b=>b.onclick=()=>{const o=state.room[b.dataset.kind].find(o=>o.key===b.dataset.moveOpening);state.openingTool={kind:b.dataset.kind,key:o.key,width:o.width_m};state.selected=null;render();});
    document.querySelectorAll('[data-delete-opening]').forEach(b=>b.onclick=()=>{state.room[b.dataset.kind]=state.room[b.dataset.kind].filter(o=>o.key!==b.dataset.deleteOpening);touched();render();});
    bind('evaluate',evaluate);bind('optimize',optimize);bind('resume-job',pollJob);bind('stop-poll',()=>{epoch++;state.job=null;state.polling=false;render();});
    $('scenario')?.addEventListener('change',e=>{state.scenario=e.target.value;draw();});
    document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>applyCandidate(Number(b.dataset.candidate)));
    draw();
  }
  function choose(shape,size){pushHistory();const changedShape=shape!==state.shape;state.shape=shape;state.size=size;state.draft.vertices=preset(shape,size);if(changedShape)for(const opening of [...state.draft.doors,...state.draft.windows])opening.placed=false;state.baseline=clone(state.draft.vertices);render();fit();burst();}
  function burst(){if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;const target=state.mode==='2d'?svg:$('three-root');target.classList.remove('pop');void target.offsetWidth;target.classList.add('pop');viewport.classList.remove('burst');void viewport.offsetWidth;viewport.classList.add('burst');}
  function commitRoom(){
    if(!validateRoom(state.draft.vertices).valid)return;
    const changes=reconcileRoom(state.draft,state.placements,state.defs);
    const apply=()=>{state.room=changes.room;state.placements=changes.placements;for(const key of changes.furniture)state.fixed.delete(key);state.step='furniture';state.history=[];touched();$('confirm-room').close();render();fit();};
    const openingCount=[...changes.room.doors,...changes.room.windows].filter(o=>!o.placed&&[...state.room.doors,...state.room.windows].some(old=>old.key===o.key&&old.placed)).length;
    if(changes.furniture.length||openingCount){$('confirm-text').textContent=`${changes.furniture.length?`${changes.furniture.map(k=>labels[k]).join('、')}を未配置に戻します。`:''}${openingCount?`ドア・窓 ${openingCount}件は再配置が必要です。`:''}`;$('confirm-apply').onclick=apply;$('confirm-room').showModal();}else apply();
  }
  $('confirm-cancel').onclick=()=>$('confirm-room').close();
  function selectedRegions(){return state.evaluation?.revision===state.revision?state.evaluation.regions.filter(r=>r.scenario_id&&r.scenario_id===state.scenario):[];}
  function draw(){
    if(!state.view)return;
    const room=activeRoom(),v=room.vertices,valid=validateRoom(v),m=metrics(),u=m.unit;
    $('area-value').innerHTML=valid.valid?`${(area(v)/TATAMI_M2).toFixed(2)}<small>帖</small>`:'—';$('area-m2').textContent=valid.valid?`${area(v).toFixed(2)} ㎡`:'計算できません';
    $('geometry-message').textContent=!valid.valid?valid.reasons.join(' '):valid.narrow?'50cm未満の狭い部分があります。通行や家具の寸法を確認してください。':state.step==='room'?'辺と角をドラッグして、お部屋の形を調整できます。':'家具を選択して移動・回転できます。';
    $('geometry-message').className=!valid.valid?'error':valid.narrow?'warning':'';
    if($('continue'))$('continue').disabled=!valid.valid;
    $('view-hint').textContent=state.mode==='3d'?'ドラッグで視点を回転 · ホイールで拡大 / 縮小':state.step==='room'?'● 角を動かす　 ━ 辺を動かす':'クリックで家具を配置 · ドラッグで移動';
    if($('dimension-list'))$('dimension-list').innerHTML=v.map((a,i)=>`<div>辺 ${i+1}<strong>${distance(a,v[(i+1)%v.length]).toFixed(2)} m</strong></div>`).join('');
    svg.setAttribute('viewBox',`${m.x} ${m.y} ${m.width} ${m.height}`);
    let html=`<defs><pattern id="grid" width=".25" height=".25" patternUnits="userSpaceOnUse"><circle cx="0" cy="0" r="${u*.75}" fill="#bdc8bc"/></pattern></defs><rect x="${m.x}" y="${m.y}" width="${m.width}" height="${m.height}" fill="url(#grid)"/>`;
    html+=`<polygon points="${pointsAttr(v)}" fill="${valid.valid?'#eee5d2':'none'}" class="floor"/>`;
    if(valid.valid)for(const door of room.doors)for(const part of doorFront(room,door))html+=`<polygon points="${part[0].map(([x,y])=>`${x},${-y}`).join(' ')}" fill="#b7d9da" opacity=".65"/>`;
    if(state.step==='furniture')for(const r of selectedRegions())html+=`<polygon points="${pointsAttr(r.points)}" fill="#e99d84" opacity=".6"/>`;
    const sign=Math.sign(signedArea(v))||1,labelRects=[];
    v.forEach((a,i)=>{
      const b=v[(i+1)%v.length],len=distance(a,b),bad=valid.bad.has(i);
      html+=`<line x1="${a.x}" y1="${-a.y}" x2="${b.x}" y2="${-b.y}" stroke="${bad?'#c94f49':'#315d4c'}" stroke-width="${u*4}" stroke-linecap="round"/><line data-edge="${i}" x1="${a.x}" y1="${-a.y}" x2="${b.x}" y2="${-b.y}" stroke="transparent" stroke-width="${u*20}" class="edge-hit"/>`;
      let x=(a.x+b.x)/2+(b.y-a.y)/Math.max(len,1e-6)*u*24*sign,y=-(a.y+b.y)/2+(b.x-a.x)/Math.max(len,1e-6)*u*24*sign;
      const labelW=u*69,labelH=u*22;
      for(let attempt=0;attempt<12&&labelRects.some(r=>Math.abs(x-r.x)<labelW&&Math.abs(y-r.y)<labelH);attempt++)y-=labelH;
      labelRects.push({x,y});
      html+=`<g pointer-events="none"><rect x="${x-labelW/2}" y="${y-labelH/2}" width="${labelW}" height="${labelH}" rx="${u*5}" fill="#f8faf6" opacity=".95"/><text x="${x}" y="${y}" font-size="${u*12}" text-anchor="middle" dominant-baseline="central" fill="${bad?'#c94f49':'#355c4d'}">${len.toFixed(2)} m</text></g>`;
    });
    for(const kind of ['doors','windows'])for(const o of room[kind]){const seg=openingSegment(room,o);if(o.placed&&seg)html+=`<line x1="${seg.a.x}" y1="${-seg.a.y}" x2="${seg.b.x}" y2="${-seg.b.y}" stroke="${kind==='doors'?'#d6984d':'#659cba'}" stroke-width="${u*8}" stroke-linecap="round"/>`;}
    const shown=state.drag?.preview?state.placements.map(p=>p.key===state.drag.preview.key?state.drag.preview:p):state.placements;
    if(state.step==='furniture')for(const p of shown){if(!p.placed)continue;const d=state.defs.find(d=>d.key===p.key);if(!d)continue;const bad=!!placementIssue(room,shown,state.defs,p),poly=footprint(d,p);html+=`<g data-furniture-shape="${p.key}" class="furniture-shape"><polygon points="${pointsAttr(poly)}" fill="${bad?'#e6a29a':p.key===state.selected?'#d8b47e':'#96b3a1'}" fill-opacity="${d.ceiling_mounted?.55:.95}" stroke="${bad?'#c94f49':p.key===state.selected?'#926835':'#577c68'}" stroke-width="${u*2}" ${d.ceiling_mounted?`stroke-dasharray="${u*5} ${u*3}"`:''}/><text x="${p.x_m}" y="${-p.y_m}" font-size="${u*11}" text-anchor="middle" dominant-baseline="central" pointer-events="none">${esc(d.label)}</text></g>`;}
    if(state.step==='room')v.forEach((a,i)=>{html+=`<circle data-vertex="${i}" cx="${a.x}" cy="${-a.y}" r="${u*12}" fill="transparent" class="vertex-hit"/><circle cx="${a.x}" cy="${-a.y}" r="${u*5}" fill="#fff" stroke="${valid.bad.has(i)?'#c94f49':'#315d4c'}" stroke-width="${u*2}" pointer-events="none"/>`;});
    svg.innerHTML=html;
    if(state.mode==='3d'&&scene){scene.useModels=state.useModels;scene.update(room,state.step==='furniture'?shown:[],state.defs,state.selected,state.step==='furniture'?selectedRegions():[]);}
  }
  function setMode(mode){
    if(mode==='3d'&&!validateRoom(activeRoom().vertices).valid){notice('部屋の形を修正すると3Dで確認できます。');return;}
    if(mode==='3d'&&!scene){try{scene=createScene($('three-root'),onScenePointer,{onInvalidate:draw,onModelError:id=>notice(`${state.defs.find(d=>d.model_id===id)?.label||'家具'}のモデルを読み込めなかったため、箱で表示します。`)});scene.fit(activeRoom().vertices);}catch(error){notice('3D表示を開始できません。WebGLを利用できるブラウザーで開いてください。');return;}}
    state.mode=mode;svg.hidden=mode!=='2d';svg.style.display=mode==='2d'?'block':'none';$('three-root').hidden=mode!=='3d';
    $('model-switch').hidden=mode!=='3d';
    $('view-2d').classList.toggle('active',mode==='2d');$('view-3d').classList.toggle('active',mode==='3d');scene?.resize();draw();
  }
  $('view-2d').onclick=()=>setMode('2d');$('view-3d').onclick=()=>setMode('3d');$('fit').onclick=fit;
  function setModelDisplay(useModels){state.useModels=useModels;for(const [id,active] of [['show-models',useModels],['show-boxes',!useModels]]){$(id).classList.toggle('active',active);$(id).setAttribute('aria-pressed',String(active));}draw();}
  $('show-models').onclick=()=>setModelDisplay(true);$('show-boxes').onclick=()=>setModelDisplay(false);
  function zoom(factor){if(state.mode==='3d')scene?.zoom(factor);else state.view.span=Math.max(1,Math.min(40,state.view.span*factor));draw();}
  $('zoom-in').onclick=()=>zoom(.8);$('zoom-out').onclick=()=>zoom(1.25);
  svg.addEventListener('wheel',e=>{e.preventDefault();state.view.span=Math.max(1,Math.min(40,state.view.span*Math.exp(e.deltaY*.001)));draw();},{passive:false});
  function startFurnitureDrag(event,point,hitKey=null){
    if(state.openingTool){placeOpening(point);return;}
    let p=state.placements.find(p=>p.key===state.selected&&!p.placed);
    if(!p&&hitKey)p=state.placements.find(p=>p.key===hitKey);
    if(!p)p=[...state.placements].reverse().find(p=>p.placed&&pointInside(point,footprint(state.defs.find(d=>d.key===p.key),p)));
    if(!p)return;
    state.selected=p.key;state.drag={kind:'furniture',pointer:event.pointerId,original:clone(p),offset:p.placed?{x:point.x-p.x_m,y:point.y-p.y_m}:{x:0,y:0},preview:{...p,placed:true}};
    updateFurnitureDrag(point);render();
    // Capture to the stable viewport in 2D; keep Three.js canvas events in 3D.
    (state.mode==='2d'?viewport:event.currentTarget).setPointerCapture?.(event.pointerId);
    if(scene)scene.controls.enabled=false;
  }
  function updateFurnitureDrag(point){const drag=state.drag,p={...drag.original,x_m:point.x-drag.offset.x,y_m:point.y-drag.offset.y,placed:true};const def=state.defs.find(d=>d.key===p.key);drag.preview=state.snap?snapToWall(state.room,def,p):p;draw();}
  function finishDrag(cancel=false){
    const drag=state.drag;if(!drag)return;
    if(drag.kind==='furniture'&&!cancel){const issue=placementIssue(state.room,state.placements,state.defs,drag.preview);if(issue)notice(issue);else{const p=state.placements.find(p=>p.key===drag.preview.key);Object.assign(p,drag.preview);if(poseChanged(drag.original,p)){p.installation_confirmed=false;touched();}}}
    if(cancel&&drag.kind==='room'){state.draft.vertices=drag.original;state.history.pop();}
    state.drag=null;if(scene)scene.controls.enabled=true;render();
  }
  svg.addEventListener('pointerdown',event=>{
    if(event.button!==0||state.drag)return;const point=screenPoint(event);
    if(state.step==='furniture'){startFurnitureDrag(event,point);return;}
    const vertex=event.target.dataset.vertex,edge=event.target.dataset.edge;if(vertex===undefined&&edge===undefined)return;
    pushHistory();state.drag={kind:'room',pointer:event.pointerId,original:clone(state.draft.vertices),point,vertex:vertex===undefined?null:Number(vertex),edge:edge===undefined?null:Number(edge)};viewport.setPointerCapture(event.pointerId);event.preventDefault();
  });
  viewport.addEventListener('pointermove',event=>{
    const drag=state.drag;if(!drag||drag.pointer!==event.pointerId||state.mode!=='2d')return;
    const p=screenPoint(event);if(drag.kind==='furniture'){updateFurnitureDrag(p);return;}
    const dx=p.x-drag.point.x,dy=p.y-drag.point.y;
    if(drag.vertex!==null){const v=clone(drag.original);v[drag.vertex].x+=dx;v[drag.vertex].y+=dy;state.draft.vertices=v;}else state.draft.vertices=moveEdge(drag.original,drag.edge,dx,dy);
    draw();
  });
  viewport.addEventListener('pointerup',event=>{if(state.drag?.pointer===event.pointerId)finishDrag();});
  viewport.addEventListener('pointercancel',()=>finishDrag(true));window.addEventListener('blur',()=>finishDrag(true));
  window.addEventListener('keydown',e=>{if(e.key==='Escape'){finishDrag(true);state.openingTool=null;render();}if((e.ctrlKey||e.metaKey)&&e.key==='z'&&state.step==='room'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();if(state.drag)finishDrag(true);else undo();}});
  function onScenePointer(type,event,point,hitKey){if(state.step!=='furniture')return;if(type==='pointerdown'&&event.button===0&&!state.drag)startFurnitureDrag(event,point,hitKey);if(type==='pointermove'&&state.drag?.kind==='furniture'&&state.drag.pointer===event.pointerId)updateFurnitureDrag(point);if(type==='pointerup'&&state.drag?.pointer===event.pointerId)finishDrag();if(type==='pointercancel'&&state.drag?.pointer===event.pointerId)finishDrag(true);}
  function placeOpening(point){
    const tool=state.openingTool;let nearest=null;
    state.room.vertices.forEach((a,i)=>{const b=state.room.vertices[(i+1)%state.room.vertices.length],q=project(point,a,b),d=distance(point,q),len=distance(a,b);if(!nearest||d<nearest.d)nearest={a,q,d,len};});
    if(nearest.d>.4){notice('壁の近くを選んでください。');return;}
    if(nearest.len<tool.width){notice('この壁には開口部が収まりません。');return;}
    const previous=state.room[tool.kind].find(o=>o.key===tool.key);
    const opening={...(previous||{}),key:tool.key||`${tool.kind==='doors'?'door':'window'}_${Date.now()}`,label:tool.kind==='doors'?'ドア':'窓',edge_id:nearest.a.id,offset_m:Math.max(0,Math.min(nearest.len-tool.width,nearest.q.t*nearest.len-tool.width/2)),width_m:tool.width,placed:true};
    if(!openingValid(state.room,opening)){notice('ほかのドア・窓と重なります。');return;}
    const next=clone(state.room);next[tool.kind]=[...next[tool.kind].filter(o=>o.key!==opening.key),opening];
    if(state.placements.some(p=>p.placed&&placementIssue(next,state.placements,state.defs,p))){notice('ドア前に家具があります。家具を移動してから配置してください。');return;}
    state.room=next;state.openingTool=null;touched();render();
  }
  function rotate(delta){const p=state.placements.find(p=>p.key===state.selected);if(p)setRotation((p.rotation_deg+delta+360)%360);}
  function setRotation(angle){const p=state.placements.find(p=>p.key===state.selected);if(!p)return;const candidate={...p,rotation_deg:angle};const issue=placementIssue(state.room,state.placements,state.defs,candidate);if(issue){notice(issue);$('rotation').value=p.rotation_deg;return;}p.rotation_deg=angle;p.installation_confirmed=false;touched();$('rotation').value=angle;$('rotation-value').textContent=`${angle.toFixed(0)}°`;draw();refreshResults();}
  function refreshResults(){if($('results')){$('results').innerHTML=resultsHTML();$('scenario')?.addEventListener('change',e=>{state.scenario=e.target.value;draw();});document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>applyCandidate(Number(b.dataset.candidate)));}}
  function payload(){return {schema_version:2,revision:state.revision,room:clone(state.room),placements:clone(state.placements)};}
  async function api(path,body){const response=await fetch(`/api/v2/${path}`,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(30000)});if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:`APIに接続できません (${response.status})`);}return response.json();}
  async function loadCatalog(){try{const data=await api('catalog');state.defs=data.furniture;state.catalogError=false;render();}catch(error){state.catalogError=true;render();notice('評価APIに接続できません。部屋の編集は続けられます。家具配置にはAPIを起動してください。');}}
  async function evaluate(){if(state.busy)return;if(!state.placements.length||state.placements.some(p=>!p.placed)){notice('選択した家具をすべて配置してください。');return;}state.busy=true;render();try{state.evaluation=await api('evaluate',payload());state.scenario='';}catch(error){notice(`評価できませんでした。編集内容は保持しています。${error.message}`);}finally{state.busy=false;render();}}
  async function optimize(){if(!state.placements.length){notice('候補に含める家具を選んでください。');return;}if(state.job)return;state.job={id:null};render();try{const result=await api('optimization-jobs',{layout:payload(),fixed_keys:[...state.fixed],candidate_count:3,sample_count:900,burn_in:250,sample_stride:15,rng_seed:42});state.job=result;pollJob();}catch(error){state.job=null;notice(`候補を生成できませんでした。${error.message}`);}render();}
  async function pollJob(){if(state.polling||!state.job?.id)return;state.polling=true;const current=++epoch,id=state.job.id;try{while(current===epoch&&state.job){const result=await api(`optimization-jobs/${id}`);if(current!==epoch)break;if(result.status==='succeeded'){state.candidates=result.candidates;state.candidateRevision=result.revision;state.job=null;notice(result.candidates.length?'配置候補ができました。':'条件を満たす候補が見つかりませんでした。家具を減らすか部屋を調整してください。');break;}if(result.status==='failed'){state.job=null;throw new Error('計算に失敗しました。条件を調整して再生成してください。');}await new Promise(resolve=>setTimeout(resolve,1000));}}catch(error){notice(`結果を取得できませんでした。${state.job?'「結果取得を再開」で再試行できます。':''}${error.message}`);}finally{if(current===epoch)state.polling=false;render();}}
  async function applyCandidate(index){
    const c=state.candidates[index];if(!c)return;
    const keys=state.placements.map(p=>p.key).sort().join(',');if(c.placements.map(p=>p.key).sort().join(',')!==keys){notice('家具の選択が変わっています。候補を再生成してください。');return;}
    const next=c.placements.map(p=>{const existing=state.placements.find(e=>e.key===p.key);return {...existing,x_m:p.x_m,y_m:p.y_m,rotation_deg:p.rotation_deg,placed:p.placed,installation_confirmed:existing.installation_confirmed&&!poseChanged(existing,p)};});
    if(next.some(p=>state.fixed.has(p.key)&&poseChanged(state.placements.find(e=>e.key===p.key),p))){notice('固定中の家具が動く候補は適用できません。');return;}
    if(next.some(p=>placementIssue(state.room,next,state.defs,p))){notice('現在の部屋・開口部に収まらない候補です。再生成してください。');return;}
    state.placements=next;touched();render();await evaluate();
  }
  new ResizeObserver(()=>draw()).observe(viewport);
  fit();render();burst();loadCatalog();
  window.addEventListener('pagehide',()=>{epoch++;scene?.dispose();},{once:true});
}
