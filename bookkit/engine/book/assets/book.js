/* 책 엔진 런타임 — 쪽 나누기 · 두/한 페이지 보기 · 오른쪽 목록 · ↩ 연결고리와 돌아가기 · 예시 데이터 스위치 · 스티커 메모
   블록 원본은 #bksrc 에 차례로 있다. 800×1131 고정 판에 흘려 담고(기기 글꼴로 이 기기에서 잰다), 화면에는 --k 배로 줄여 보인다 */
(()=>{
'use strict';
const META=JSON.parse(document.getElementById('bkmeta').textContent);
const DOC=META.doc, KP='bk:'+DOC+':', W=800;
const store={get(k){try{return localStorage.getItem(KP+k)}catch(e){return null}},set(k,v){try{localStorage.setItem(KP+k,v)}catch(e){}}};
const $=id=>document.getElementById(id);
const book=$('book'), stage=$('stage'), rail=$('rail'), spMake=$('spMake'), layer=$('notes');
const bMode=$('bMode'), bRail=$('bRail'), bMemo=$('bMemo'), src=$('bksrc'), toastEl=$('toast'), chip=$('chip');
// 아래 질문 줄(두 페이지) — 예전 빌드 html 에는 자리가 없어 여기서 만든다(«예시 데이터 만든 과정» 위)
const spQa=$('spQa')||(()=>{const e=document.createElement('div');e.id='spQa';e.className='mk qa';e.hidden=true;spMake.before(e);return e;})();
const ICON={one:'<svg viewBox="0 0 24 24"><rect x="6" y="3" width="12" height="18" rx="1.5"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="9" y1="12" x2="15" y2="12"/></svg>',
            two:'<svg viewBox="0 0 24 24"><path d="M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2z"/><path d="M22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z"/></svg>'};
const qs=new URLSearchParams(location.search);
let mode=+(qs.get('mode')||store.get('mode')||(innerWidth<700?1:2)); if(mode!==1&&mode!==2)mode=2;
let pages=[], NS=0, cur=0, curPage=0, allBlocks=[];
const blockById=new Map(), anchorEl=new Map(), pageOf=new Map();
const report={ready:false,ms:0,pages:0,errors:[],chapters:[],blocks:0,ext_links:META.ext_links||0};
window.__book=report;
function toast(t){toastEl.textContent=t;toastEl.classList.add('on');clearTimeout(toast._t);toast._t=setTimeout(()=>toastEl.classList.remove('on'),1800);}

// ════════ 쪽 나누기 ════════
function mkPage(){
  const p=document.createElement('section');p.className='page';
  p.innerHTML='<div class="sheet"><div class="rh"><span class="rl"></span><span class="rr"></span></div><div class="body"><div class="pin"></div><div class="fn"></div></div><div class="pn"></div></div>';
  p._pin=p.querySelector('.pin');p._fn=p.querySelector('.fn');
  return p;
}
// 묶음 — 같은 data-g 는 한 묶음, data-kn(다음과 같은 쪽)은 다음 블록을 끌고 온다
function units(list){
  const us=[];let i=0;
  const takeGroup=(u)=>{const g=list[i].dataset.g;while(g!==undefined&&i+1<list.length&&list[i+1].dataset.g===g){i++;u.push(list[i]);}};
  while(i<list.length){
    const u=[list[i]];takeGroup(u);
    while(u[u.length-1].dataset.kn&&i+1<list.length&&!list[i+1].dataset.fp&&!list[i+1].dataset.np){i++;u.push(list[i]);takeGroup(u);}
    us.push(u);i++;
  }
  return us;
}
function place(page,u){
  const moved=[];
  for(const b of u){
    page._pin.appendChild(b);
    const s=b.querySelector(':scope>.fnsrc');
    if(s)for(const e of [...s.children]){moved.push([e,s]);page._fn.appendChild(e);}
  }
  return moved;
}
function unplace(u,moved,home){for(const [e,s] of moved)s.appendChild(e);for(const b of u)home.appendChild(b);}
function overflowY(page){const pin=page._pin,last=pin.lastElementChild;if(!last)return false;return last.offsetTop+last.offsetHeight>pin.clientHeight+0.5;}
function paginate(meas){
  const list=[...src.children];allBlocks=list;report.blocks=list.length;
  const out=[];let page=null;
  const open=()=>{page=mkPage();meas.appendChild(page);out.push(page);return page;};
  const err=(u,kind)=>{u.forEach(b=>b.classList.add('too-big'));report.errors.push({kind,block:u[0].dataset.id,page:out.length,blocks:u.map(b=>b.dataset.id)});};
  open();
  for(const u of units(list)){
    const f=u[0];
    if(f.dataset.fp){
      if(page._pin.childElementCount)open();
      page.classList.add('full');place(page,u);
      if(overflowY(page))err(u,'쪽보다 큰 블록');
      open();continue;
    }
    if(f.dataset.np&&page._pin.childElementCount)open();
    const wasEmpty=!page._pin.childElementCount;
    const moved=place(page,u);
    if(overflowY(page)){
      if(wasEmpty)err(u,'쪽보다 큰 블록');
      else{unplace(u,moved,src);open();place(page,u);if(overflowY(page))err(u,'쪽보다 큰 블록');}
    }
  }
  if(!page._pin.childElementCount&&out.length>1){out.pop();page.remove();}
  return out;
}
// 쪽 번호 · 머리글 · 각주 번호 · 차례 쪽 번호 · 넘침 검사
function finish(){
  let chl='';
  pages.forEach((p,i)=>{
    p.dataset.pi=i;p.dataset.side=i%2?'r':'l';
    const blks=[...p._pin.children];
    blks.forEach(b=>{pageOf.set(b.dataset.id,i);blockById.set(b.dataset.id,b);
      (b.dataset.a||'').split(' ').filter(Boolean).forEach(a=>anchorEl.set(a,b));});
    const first=blks[0];
    if(first&&first.dataset.chl)chl=first.dataset.chl;
    p.dataset.chl=chl;p.dataset.first=first?first.dataset.id:'';
    const rl=p.querySelector('.rl'),rr=p.querySelector('.rr'),rh=p.querySelector('.rh');
    if(i%2===0){rl.textContent=META.short;rr.textContent='';}else{rl.textContent='';rr.textContent=chl;}
    if(!first||['chapter','matter','cover','part'].includes(first.dataset.k))rh.classList.add('off');
    p.querySelector('.pn').textContent=i+1;
    // 각주 — 이 쪽의 표식 순서대로 1, 2, 3 …
    const order=[];let n=0;
    p._pin.querySelectorAll('sup.fm').forEach(s=>{
      n++;s.textContent=n;
      const e=p._fn.querySelector('.fne[data-f="'+s.dataset.f+'"]');
      if(e){e.querySelector('.fnn').textContent=n;order.push(e);}
      else report.errors.push({kind:'각주 없음',page:i+1,f:s.dataset.f});
    });
    order.forEach(e=>p._fn.appendChild(e));
    p._fn.querySelectorAll('.fne').forEach(e=>{if(!order.includes(e))report.errors.push({kind:'표식 없는 각주',page:i+1,f:e.dataset.f});});
    // 넘침(세로 · 가로) — 고정 판이라 여기서 잰 값이 모든 화면에 그대로다
    if(overflowY(p))report.errors.push({kind:'쪽 세로 넘침',page:i+1});
    blks.forEach(b=>{
      if(b.scrollWidth>b.clientWidth+1)report.errors.push({kind:'쪽 가로 넘침',page:i+1,block:b.dataset.id,over:b.scrollWidth-b.clientWidth});
    });
    if(p._fn.scrollWidth>p._fn.clientWidth+1)report.errors.push({kind:'각주 가로 넘침',page:i+1});
  });
  allBlocks.forEach(b=>{if(!pageOf.has(b.dataset.id)){pageOf.set(b.dataset.id,-1);}blockById.set(b.dataset.id,b);});
  // 차례 · 찾아보기 쪽 번호
  document.querySelectorAll('.measure .pg[data-to]').forEach(s=>{const t=target(s.dataset.to);s.textContent=t?pageOf.get(t.dataset.id)+1:'?';});
  // 연결고리 대상 검사
  document.querySelectorAll('.measure a[data-to]').forEach(a=>{if(a.dataset.ext)return;if(!target(a.dataset.to))report.errors.push({kind:'연결고리 대상 없음',to:a.dataset.to});});
  // 장별 쪽 범위
  const chs=[];
  pages.forEach((p,i)=>{[...p._pin.children].forEach(b=>{
    const k=b.dataset.ch;let c=chs.find(x=>x.key===k);
    if(!c){c={key:k,first:i+1,last:i+1};chs.push(c);}c.last=Math.max(c.last,i+1);});});
  report.chapters=chs.map(c=>{const m=META.chapters.find(x=>x.key===c.key)||{};return{...c,pages:c.last-c.first+1,label:m.label||'',title:m.title||c.key};});
  report.pages=pages.length;
}
function target(to){if(!to)return null;if(to.startsWith('b:'))return blockById.get(to.slice(2))||null;return anchorEl.get(to)||null;}
// 주소의 #앵커 → 블록. 앵커(c12 · c12-3 · c12-rule) · 블록 ID(c12-034) · 찾아보기 모양(b-c12-034) 모두 받는다 — 다른 책의 ↗ 연결고리가 이 주소로 연다
function hashTarget(){let h='';try{h=decodeURIComponent(location.hash.slice(1));}catch(e){h=location.hash.slice(1);}
  if(!h)return null;return target(h)||blockById.get(h)||(h.startsWith('b-')?blockById.get(h.slice(2)):null)||null;}

// ════════ 보기 ════════
const mkOf=p=>[...p.querySelectorAll('.pin template.mkt')].map(t=>{const c=t.dataset.cap;return '<h4>'+(+p.dataset.pi+1)+'쪽'+(c?' · '+esc(c):'')+'</h4><pre>'+t.innerHTML+'</pre>';});
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function makeBlock(el,parts){
  const was=el.classList.contains('open');
  el.className='mk'+(parts.length?'':' empty')+(el.classList.contains('mk1')?' mk1':'');
  el.innerHTML='<div class="mkh"><span class="sw"></span><span>예시 데이터 만든 과정'+(parts.length?'':' — 없음')+'</span></div><div class="mkb"></div>';
  el.querySelector('.mkb').innerHTML=parts.join('');
  if(parts.length&&(store.get('mk')==='1'||was))el.classList.add('open');
}
document.addEventListener('click',e=>{
  const h=e.target.closest('.mk .mkh');if(!h)return;
  const el=h.parentElement;if(el.classList.contains('empty'))return;
  el.classList.toggle('open');store.set(el.classList.contains('qa')?'qa':'mk',el.classList.contains('open')?'1':'0');
});
function fitScale(){
  const bw=book.clientWidth;if(!bw)return;
  const pw=mode===2?bw/2:Math.min(bw,880);
  book.style.setProperty('--k',(pw/W).toFixed(5));
}
function show(s){
  cur=Math.max(0,Math.min(NS-1,s));
  pages.forEach((p,i)=>p.classList.toggle('on',Math.floor(i/2)===cur));
  makeBlock(spMake,[pages[2*cur],pages[2*cur+1]].filter(Boolean).flatMap(mkOf));
  stage.scrollTop=0;savePos(2*cur);markRail();renderNotes();
}
function goPage(i,smooth){
  if(i<0||i>=pages.length)return;
  if(mode===2){show(Math.floor(i/2));}
  else{curPage=i;pages[i].scrollIntoView({block:'start',behavior:smooth?'smooth':'auto'});savePos(i);markRail();}
}
function goBlock(id,smooth){const i=pageOf.get(id);if(i!==undefined&&i>=0)goPage(i,smooth);}
function curIndex(){return mode===2?2*cur:curPage;}
function savePos(i){const p=pages[i];if(p&&p.dataset.first)store.set('pos',p.dataset.first);}
let io1=null;
function setMode(m){
  const from=pages.length?curIndex():0;
  mode=m;store.set('mode',m);
  book.classList.toggle('m2',m===2);book.classList.toggle('m1',m===1);
  spMake.hidden=m!==2;
  bMode.innerHTML=m===2?ICON.one:ICON.two;bMode.title=m===2?'한 페이지 보기':'두 페이지 보기';bMode.setAttribute('aria-label',bMode.title);
  fitScale();
  if(m===2){show(Math.floor(from/2));}
  else{pages.forEach(p=>p.classList.remove('on'));curPage=from;requestAnimationFrame(()=>{pages[from]&&pages[from].scrollIntoView({block:'start'});renderNotes();});}
  buildRail();
}
// 한 페이지: 화면 가운데에 있는 쪽 = 지금 쪽
function watchPages(){
  io1=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting&&mode===1){curPage=+e.target.dataset.pi;savePos(curPage);markRail();}});},{root:stage,rootMargin:'-45% 0px -45% 0px'});
  pages.forEach(p=>io1.observe(p));
}

// ════════ 오른쪽 목록 — 장 이름 머리 + 쪽(펼침) 축소판. 축소판은 보일 때만 그린다 ════════
let railIO=null;
function chapterStarts(){
  const m=new Map();
  pages.forEach((p,i)=>{[...p._pin.children].forEach(b=>{if(['chapter','matter','part','cover'].includes(b.dataset.k)){
    const c=META.chapters.find(x=>x.key===b.dataset.ch);const lab=c?c.label:'';const t=c?c.title:(b.dataset.k==='cover'?'표지':b.dataset.ch);
    if(!m.has(i))m.set(i,[]);m.get(i).push({lab,t,id:b.dataset.id});}});});
  return m;
}
function thumbOf(i){const p=pages[i];const c=document.createElement('div');c.className='page';c.dataset.side=p.dataset.side;
  const s=p.querySelector('.sheet').cloneNode(true);s.querySelectorAll('template').forEach(t=>t.remove());c.appendChild(s);c.setAttribute('inert','');return c;}
function buildRail(){
  if(!pages.length)return;
  rail.innerHTML='';if(railIO)railIO.disconnect();
  railIO=new IntersectionObserver(es=>{es.forEach(e=>{if(!e.isIntersecting)return;const b=e.target;if(b.dataset.done)return;b.dataset.done='1';
    if(b.dataset.s!==undefined){const s=+b.dataset.s;b.querySelectorAll('.tsp>div').forEach((cell,j)=>{if(pages[2*s+j])cell.appendChild(thumbOf(2*s+j));});}
    else{b.querySelector('.tpg').appendChild(thumbOf(+b.dataset.i));}
    railIO.unobserve(b);});},{root:rail,rootMargin:'600px 0px'});
  const starts=chapterStarts();
  const head=(c)=>{const h=document.createElement('button');h.type='button';h.className='rch';h.innerHTML=(c.lab?'<small>'+esc(c.lab)+'</small>':'')+esc(c.t);
    h.addEventListener('click',()=>goBlock(c.id));rail.appendChild(h);};
  if(mode===2){
    for(let s=0;s<NS;s++){
      [2*s,2*s+1].forEach(i=>(starts.get(i)||[]).forEach(head));
      const b=document.createElement('button');b.type='button';b.className='th';b.dataset.s=s;
      b.innerHTML='<div class="tsp"><div></div><div></div></div><span class="tl">'+(2*s+1)+(pages[2*s+1]?'–'+(2*s+2):'')+'쪽</span>';
      b.addEventListener('click',()=>show(s));rail.appendChild(b);railIO.observe(b);
    }
  }else{
    pages.forEach((p,i)=>{
      (starts.get(i)||[]).forEach(head);
      const b=document.createElement('button');b.type='button';b.className='th';b.dataset.i=i;
      b.innerHTML='<div class="tpg"></div><span class="tl">'+(i+1)+'쪽</span>';
      b.addEventListener('click',()=>goPage(i,true));rail.appendChild(b);railIO.observe(b);
    });
  }
  markRail();
}
function markRail(){
  const k=mode===2?cur:curPage;
  rail.querySelectorAll('.th').forEach(b=>{const on=(mode===2?+b.dataset.s:+b.dataset.i)===k;b.setAttribute('aria-current',String(on));
    if(on&&!document.body.classList.contains('norail')){const r=b.getBoundingClientRect(),rr=rail.getBoundingClientRect();if(r.top<rr.top||r.bottom>rr.bottom)b.scrollIntoView({block:'nearest'});}});
}

// ════════ 넘김 · 연결고리 · 답 가림 ════════
book.addEventListener('click',e=>{
  if(memoMode)return;
  const a=e.target.closest('a[data-to]');
  if(a){e.preventDefault();
    if(a.dataset.ext){toast('이 판에 들어 있지 않은 장');return;}
    jump(a.dataset.to,a.classList.contains('back')||a.classList.contains('ix'));return;}
  const ans=e.target.closest('.ans');
  if(ans){ans.classList.toggle('open');return;}
  if(mode!==2||liveDown||e.target.closest('button,a,input,textarea,label,.note,.live'))return;  // 조작 블록(.live) 안 클릭 · 끌기는 넘김이 아니다
  const r=book.getBoundingClientRect(),fx=(e.clientX-r.left)/r.width;
  if(fx<0.2)show(cur-1);else if(fx>0.8)show(cur+1);
});
book.addEventListener('mousemove',e=>{
  if(mode!==2)return;const r=book.getBoundingClientRect(),fx=(e.clientX-r.left)/r.width;
  const inLive=!!e.target.closest('.live');  // 조작 블록 위에서는 넘김 표시를 켜지 않는다
  book.classList.toggle('hz-l',fx<0.2&&cur>0&&!memoMode&&!inLive);book.classList.toggle('hz-r',fx>0.8&&cur<NS-1&&!memoMode&&!inLive);
});
book.addEventListener('mouseleave',()=>book.classList.remove('hz-l','hz-r'));
addEventListener('keydown',e=>{
  if(e.target.closest('input,textarea,select,.live')||e.altKey||e.ctrlKey||e.metaKey)return;  // 조작 블록에 포커스가 있으면 ← → 는 블록 몫
  if(mode!==2)return;
  if(e.key==='ArrowRight'||e.key==='PageDown'){show(cur+1);e.preventDefault();}
  if(e.key==='ArrowLeft'||e.key==='PageUp'){show(cur-1);e.preventDefault();}
});
let backFrom=null;
function jump(to,withChip){
  const t=target(to);if(!t){toast('대상 없음');return;}
  const from=pages[curIndex()];
  goBlock(t.dataset.id,true);
  t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');
  if(withChip&&from){backFrom=from.dataset.first;chip.querySelector('.go span').textContent='· '+(+from.dataset.pi+1)+'쪽';chip.hidden=false;}
}
$('chipGo').addEventListener('click',()=>{if(backFrom)goBlock(backFrom,true);chip.hidden=true;backFrom=null;});
$('chipX').addEventListener('click',()=>{chip.hidden=true;backFrom=null;});

// ════════ 버튼 ════════
function setRail(on){document.body.classList.toggle('norail',!on);bRail.setAttribute('aria-pressed',String(on));store.set('rail',on?'1':'0');
  requestAnimationFrame(()=>{fitScale();renderNotes();markRail();});}
bRail.addEventListener('click',()=>setRail(document.body.classList.contains('norail')));
// «노트 목록» 단추 — devview Book 탭 iframe 안이면 왼쪽 책 목록 보이기 · 숨기기(부모에 {book:'toggle-list'}) · 밖(새 탭)이면 원래 링크 그대로
(()=>{const h=$('bHome');if(!h||window.parent===window)return;
  h.title='책 목록 보이기 · 숨기기';h.setAttribute('aria-label','책 목록 보이기 · 숨기기');
  h.addEventListener('click',e=>{e.preventDefault();window.parent.postMessage({book:'toggle-list'},'*');});})();
// devview Book 탭 안 — 다른 출처라 iframe 안 키가 부모로 안 올라간다. Alt+Q · W · B 를 부모에 넘기고, 부모의 {book:'wand'} 로 고른 메모의 🪄 를 누른다
(()=>{if(window.parent===window)return;
  const own=el=>{const t=el&&el.closest&&el.closest('.note,.qr');return t&&(t._n||t.classList.contains('qr'))?t:null;};
  const idOf=t=>t._n?t._n.id:t.dataset.id;
  let pick=null;  // 마지막으로 누른 메모 · 질문 줄의 id
  addEventListener('pointerdown',e=>{const t=own(e.target);if(t){pick=idOf(t);window.parent.postMessage({book:'pick',id:pick},'*');}},true);
  // devview 단축키 — 마법봉 Alt+Q · W · 지시 붙은 마법봉 Alt+E · R(고른 메모는 {book:'pick'} 으로 미리 알림) · Book Alt+B · 그래프 화면 Alt+` · 0~8 은 devview 로 넘김 / 기호 Alt+Z · X · C · V 는 이 책의 입력 칸에 넣음
  const HOT=['KeyQ','KeyW','KeyE','KeyR','BracketLeft','BracketRight','Semicolon','Quote','KeyB','Backquote','Digit0','Digit1','Digit2','Digit3','Digit4','Digit5','Digit6','Digit7','Digit8'];
  const SYM={KeyZ:'❇️',KeyX:'🔎',KeyC:'💭',KeyV:'📌'};
  addEventListener('keydown',e=>{
    if(!e.altKey||e.ctrlKey||e.metaKey||e.shiftKey||e.isComposing)return;
    const t=document.activeElement;
    if(SYM[e.code]&&t&&(t.tagName==='TEXTAREA'||t.tagName==='INPUT')){e.preventDefault();e.stopPropagation();t.setRangeText(SYM[e.code],t.selectionStart,t.selectionEnd,'end');t.dispatchEvent(new Event('input',{bubbles:true}));return;}
    if(!HOT.includes(e.code))return;
    e.preventDefault();e.stopPropagation();window.parent.postMessage({book:'key',code:e.code},'*');
  },true);
  addEventListener('message',e=>{
    if(e.source!==window.parent||!e.data||e.data.book!=='wand')return;
    const a=own(document.activeElement),id=a?idOf(a):pick;
    const t=a||[...document.querySelectorAll('.note,.qr')].find(x=>own(x)&&idOf(x)===id&&!x.hidden);
    if(!t||(!a&&!id)){toast('메모를 고르지 않음');return;}
    const w=t.querySelector('.nw');
    if(!w||w.hidden){toast('접수 뒤 보낼 수 있음');return;}
    w.click();
  });})();
bMode.addEventListener('click',()=>setMode(mode===2?1:2));
$('bTop').addEventListener('click',()=>goPage(0,true));
new ResizeObserver(()=>{fitScale();clearTimeout(fitScale._t);fitScale._t=setTimeout(renderNotes,120);}).observe(stage);

// ════════ 스티커 메모 — 메모 버튼 → 붙일 곳을 누르면 포스트잇 → 접수하면 서버(/api/notes)에 저장
// 위치는 «가장 가까운 블록» 기준(쪽 나누기가 기기마다 달라도 같은 자리에 붙는다): x = 쪽 폭 대비, y = 블록 위 끝에서 쪽 폭 대비 거리
const API='api/notes';
let notes=[],memoMode=false;
async function api(method,path,body){
  const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,credentials:'same-origin'});
  if(r.status===401){location.href='/login?next='+encodeURIComponent(location.pathname+location.search+location.hash);throw new Error('login');}
  if(!r.ok)throw new Error('http '+r.status);
  return r.json();
}
function setMemo(on){memoMode=on;bMemo.setAttribute('aria-pressed',String(on));document.body.classList.toggle('memo-mode',on);if(on)book.classList.remove('hz-l','hz-r');}
bMemo.addEventListener('click',e=>{e.stopPropagation();setMemo(!memoMode);});
function nearestBlock(page,y){const bs=[...page._pin.children];let best=bs[0];for(const b of bs){if(b.getBoundingClientRect().top<=y)best=b;}return best;}
function sectionOf(blk){const i=allBlocks.indexOf(blk);for(let j=i;j>=0;j--){const b=allBlocks[j];if(b.dataset.k==='section')return b.textContent.trim().replace(/^(\d+\.\d+)/,'$1 ').slice(0,40);if(['chapter','matter','part'].includes(b.dataset.k))break;}return '';}
function ctxOf(page,blk){
  const parts=['p'+(+page.dataset.pi+1),page.dataset.chl||''];
  const s=sectionOf(blk);if(s)parts.push(s);
  const t=(blk.innerText||blk.textContent).replace(/\s+/g,' ').trim().slice(0,50);if(t)parts.push('«'+t+'»');
  parts.push('b='+blk.dataset.id);
  return parts.filter(Boolean).join(' | ').slice(0,300);
}
const blockOfNote=n=>{const m=/b=([^\s|]+)/.exec(n.ctx||'');return m?blockById.get(m[1]):null;};
book.addEventListener('click',ev=>{
  if(!memoMode||ev.target.closest('.note'))return;
  const page=ev.target.closest('.page');if(!page||!page._pin)return;
  ev.preventDefault();ev.stopPropagation();setMemo(false);
  const blk=nearestBlock(page,ev.clientY);if(!blk)return;
  const pr=page.getBoundingClientRect(),br=blk.getBoundingClientRect();
  draw({id:null,slide:+page.dataset.pi+1,x:Math.min(Math.max((ev.clientX-pr.left)/pr.width,0),0.98),y:(ev.clientY-br.top)/pr.width,ctx:ctxOf(page,blk),text:''},true);
},true);
function visible(page){return mode===1||page.classList.contains('on');}
function place2(el,n){
  const blk=blockOfNote(n);const lr=layer.getBoundingClientRect();
  let page=blk?pages[pageOf.get(blk.dataset.id)]:pages[(n.slide||1)-1];
  if(!page||!visible(page)){el.hidden=true;return false;}
  el.hidden=false;
  const pr=page.getBoundingClientRect();const top0=blk?blk.getBoundingClientRect().top:pr.top;
  const nw=el.offsetWidth||474;
  el.style.left=Math.min(Math.max(pr.left-lr.left+n.x*pr.width,0),Math.max(lr.width-nw,0))+'px';
  el.style.top=Math.max(top0-lr.top+n.y*pr.width,0)+'px';
  return true;
}
function draw(n,draft){
  const el=document.createElement('div');el.className='note';el._n=n;
  const head=document.createElement('div');head.className='nh';
  const t=document.createElement('span');t.className='nt';t.textContent=draft?'새 메모':('접수 · '+(n.ts||'').slice(5,16));
  const x=document.createElement('button');x.type='button';x.setAttribute('aria-label','메모 지우기');x.textContent='×';
  head.append(t,x);el.appendChild(head);
  const msg=document.createElement('p');msg.className='ne';msg.hidden=true;
  const b=document.createElement('div');b.className='nb';b.textContent=n.text||'';
  const ta=document.createElement('textarea');ta.placeholder='질문 · 지시';ta.maxLength=2000;
  const f=document.createElement('div');f.className='nf';
  const send=document.createElement('button');send.type='button';f.appendChild(send);
  // 마법봉 — 접수된 메모만 · 페이지 서버가 이 메모 글 · 자리로 2ND 에 보냄(devview 허브)
  const wand=document.createElement('button');wand.type='button';wand.className='nw';wand.textContent='🪄';wand.title='마법봉 — 2ND 에 이 메모 질문';wand.setAttribute('aria-label','마법봉');wand.hidden=draft;f.insertBefore(wand,send);
  function editing(on){
    if(on){ta.value=n.text||'';b.replaceWith(ta);send.textContent='접수';setTimeout(()=>ta.focus(),0);}
    else{b.textContent=n.text;ta.replaceWith(b);send.textContent='수정';}
    wand.hidden=on;
  }
  wand.addEventListener('click',async()=>{
    wand.disabled=true;msg.hidden=false;msg.classList.add('ok');msg.textContent='보내는 중';
    try{
      const r=await fetch(API+'/'+n.id+'/magic',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',credentials:'same-origin'});
      const d=await r.json().catch(()=>({}));
      if(r.ok){n.magic_rid=d.rid;msg.textContent='보냄 · 2ND 답 대기';startPoll();}
      else{msg.classList.remove('ok');msg.textContent=/미연결|thread 없음/.test(d.error||'')?'2ND 미연결':r.status===409?'이미 보냄 · 답 대기':'보내기 실패';}
    }catch(e){msg.classList.remove('ok');msg.textContent='보내기 실패';}
    finally{wand.disabled=false;}
  });
  el.append(draft?ta:b,msg);
  // 답이 달린 스티커는 여기 그리지 않는다(아래 질문 줄 행) — 보낸 뒤 답 대기만 표시
  if(!draft&&n.magic_rid){msg.hidden=false;msg.classList.add('ok');msg.textContent='보냄 · 2ND 답 대기';}
  el.appendChild(f);send.textContent=draft?'접수':'수정';
  if(draft)setTimeout(()=>ta.focus(),0);
  send.addEventListener('click',async()=>{
    if(!ta.isConnected){editing(true);return;}
    const text=ta.value.trim();if(!text)return;
    send.disabled=true;msg.hidden=true;msg.classList.remove('ok');
    try{
      if(!n.id){const saved=await api('POST',API,{doc:DOC,slide:n.slide,x:n.x,y:n.y,w:el.offsetWidth,h:el.offsetHeight,ctx:n.ctx,text});
        notes.push(saved);el.remove();draw(saved,false);return;}
      Object.assign(n,await api('PATCH',API+'/'+n.id,{text}));editing(false);
    }catch(e){msg.hidden=false;msg.textContent='접수 실패';}
    finally{send.disabled=false;}
  });
  x.addEventListener('click',async()=>{
    if(n.id){try{await api('DELETE',API+'/'+n.id);notes=notes.filter(m=>m.id!==n.id);}catch(e){msg.hidden=false;msg.classList.remove('ok');msg.textContent='지우기 실패';return;}}
    el.remove();
  });
  head.addEventListener('pointerdown',ev=>{
    if(ev.target.closest('button'))return;
    head.setPointerCapture(ev.pointerId);
    const sx=ev.clientX,sy=ev.clientY,ox=el.offsetLeft,oy=el.offsetTop;
    const mv=e=>{el.style.left=Math.max(0,ox+e.clientX-sx)+'px';el.style.top=Math.max(0,oy+e.clientY-sy)+'px';};
    const up=async()=>{head.removeEventListener('pointermove',mv);head.removeEventListener('pointerup',up);head.removeEventListener('pointercancel',up);
      const blk=blockOfNote(n);const page=blk?pages[pageOf.get(blk.dataset.id)]:null;if(!page)return;
      const lr=layer.getBoundingClientRect(),pr=page.getBoundingClientRect(),br=blk.getBoundingClientRect();
      n.x=(el.offsetLeft-(pr.left-lr.left))/pr.width;n.y=(el.offsetTop-(br.top-lr.top))/pr.width;
      if(n.id){try{await api('PATCH',API+'/'+n.id,{x:n.x,y:n.y});}catch(e){}}};
    head.addEventListener('pointermove',mv);head.addEventListener('pointerup',up);head.addEventListener('pointercancel',up);
  });
  if(n.w>0)el.style.width=n.w+'px';
  if(n.h>0)el.style.height=n.h+'px';
  layer.appendChild(el);place2(el,n);
  let rt=null;
  new ResizeObserver(()=>{if(!n.id)return;clearTimeout(rt);rt=setTimeout(()=>{
    if(!el.isConnected||!el.offsetWidth||el.hidden)return;
    const w=el.offsetWidth,h=el.offsetHeight;if(Math.abs(w-(n.w||0))<2&&Math.abs(h-(n.h||0))<2)return;
    n.w=w;n.h=h;api('PATCH',API+'/'+n.id,{w,h}).catch(()=>{});},500);}).observe(el);
}
function renderNotes(){
  if(!pages.length)return;
  layer.querySelectorAll('.note').forEach(el=>{if(el.querySelector('textarea')&&!el._n.id){place2(el,el._n);return;}el.remove();});
  notes.forEach(n=>{if(!n.answer)draw(n,false);});  // 답 달린 것은 아래 질문 줄로
  renderQa();
}

// ════════ 아래 질문 줄 — 답 달린 스티커를 지금 펼친 쪽(한 페이지 = 그 쪽) 것만 행으로. 행 안에서 꼬리 질문 + 🪄 ════════
const openRows=new Set(), qDraft=new Map(), qMsg=new Map();
let qaDirty=false;
const pageOfNote=n=>{const b=blockOfNote(n);return b?pageOf.get(b.dataset.id):(n.slide||1)-1;};
const titleOf=n=>{const t=String(n.title||'').trim();if(t)return t;const q=String(n.text||'').replace(/\s+/g,' ').trim();return q.length>30?q.slice(0,30)+'…':q;};
function qItem(cls,head,text){const d=document.createElement('div');d.className='qx '+cls;const b=document.createElement('b');b.textContent=head;d.append(b,document.createTextNode(text||''));return d;}
function qaRow(n,k){
  const r=document.createElement('div');r.className='qr'+(openRows.has(n.id)?' open':'');r.dataset.id=n.id;
  const h=document.createElement('button');h.type='button';h.className='qrh';h.textContent='Q'+k+'. '+titleOf(n);h.title=n.text||'';
  h.addEventListener('click',()=>{r.classList.toggle('open');if(r.classList.contains('open'))openRows.add(n.id);else openRows.delete(n.id);});
  const b=document.createElement('div');b.className='qrb';
  b.append(qItem('qaq','질문 · '+(n.ts||'').slice(5,16),n.text),qItem('qan','답'+(n.answer_ts?' · '+n.answer_ts.slice(5,16):''),n.answer));
  (n.thread||[]).forEach(t=>{if(!t||typeof t!=='object')return;
    const d=document.createElement('div');d.className='qt';d.dataset.t=t.id;
    d.appendChild(qItem('qaq','꼬리 질문 · '+(t.ts||'').slice(5,16),t.q));
    if(t.a)d.appendChild(qItem('qan','답'+(t.a_ts?' · '+t.a_ts.slice(5,16):''),t.a));
    else{const w=document.createElement('p');w.className='qwait';w.textContent=t.magic_rid?'2ND 답 대기':'미전송';d.appendChild(w);}
    b.appendChild(d);});
  const f=document.createElement('div');f.className='qf';
  const ta=document.createElement('textarea');ta.placeholder='꼬리 질문';ta.maxLength=2000;ta.value=qDraft.get(n.id)||'';
  ta.addEventListener('input',()=>qDraft.set(n.id,ta.value));
  const w=document.createElement('button');w.type='button';w.className='nw';w.textContent='🪄';w.title='마법봉 — 2ND 에 꼬리 질문';w.setAttribute('aria-label','마법봉');
  f.append(ta,w);
  const msg=document.createElement('p');msg.className='qe';const m0=qMsg.get(n.id);msg.hidden=!m0;if(m0){msg.textContent=m0.t;msg.classList.toggle('ok',!!m0.ok);}
  w.addEventListener('click',()=>askThread(n,ta,w));
  // 지우기 — 스티커의 × 와 같은 DELETE(질문 · 답 · 꼬리 모두)
  const x=document.createElement('button');x.type='button';x.className='qdel';x.textContent='지우기';x.title='이 질문 지우기';f.appendChild(x);
  x.addEventListener('click',async()=>{try{await api('DELETE',API+'/'+n.id);notes=notes.filter(m=>m.id!==n.id);openRows.delete(n.id);renderQa();}
    catch(e){qMsg.set(n.id,{t:'지우기 실패',ok:false});renderQa();}});
  b.append(f,msg);r.append(h,b);
  return r;
}
async function askThread(n,ta,w){
  const say=(t,ok)=>{qMsg.set(n.id,{t,ok});renderQa();};
  const q=ta.value.trim();let t=null;
  w.disabled=true;
  try{
    if(q){Object.assign(n,await api('POST',API+'/'+n.id+'/thread',{q}));t=n.thread[n.thread.length-1];qDraft.delete(n.id);}
    else t=(n.thread||[]).filter(x=>x&&!x.a&&!x.magic_rid).pop()||null;  // 빈 칸 + 미전송 꼬리 = 다시 보내기
    if(!t){w.disabled=false;ta.focus();return;}
  }catch(e){w.disabled=false;say('접수 실패',false);return;}
  try{
    const r=await fetch(API+'/'+n.id+'/thread/'+t.id+'/magic',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',credentials:'same-origin'});
    const d=await r.json().catch(()=>({}));
    if(r.ok){t.magic_rid=d.rid;say('보냄 · 2ND 답 대기',true);startPoll();}
    else say(/미연결|thread 없음/.test(d.error||'')?'2ND 미연결':r.status===409?'이미 보냄 · 답 대기':'보내기 실패',false);
  }catch(e){say('보내기 실패',false);}
}
function fillQa(el,list){
  if(!list.length){el.hidden=true;el.innerHTML='';return;}
  el.hidden=false;el.classList.toggle('open',store.get('qa')!=='0');
  el.innerHTML='<div class="mkh"><span class="sw"></span><span></span></div><div class="mkb"></div>';
  el.querySelector('.mkh span:last-child').textContent='질문 '+list.length;
  const body=el.querySelector('.mkb');list.forEach((n,i)=>body.appendChild(qaRow(n,i+1)));
}
function renderQa(){
  if(!pages.length)return;
  const done=notes.filter(n=>n.answer).sort((a,b)=>String(a.ts||'').localeCompare(String(b.ts||'')));
  if(mode===2){fillQa(spQa,done.filter(n=>Math.floor(pageOfNote(n)/2)===cur));pages.forEach(p=>{if(p._qa){p._qa.hidden=true;p._qa.innerHTML='';}});}
  else{spQa.hidden=true;spQa.innerHTML='';pages.forEach((p,i)=>{if(p._qa)fillQa(p._qa,done.filter(n=>pageOfNote(n)===i));});}
}
// 답 대기(원 질문 · 꼬리)가 있으면 4초마다 다시 읽는다 — 답이 달리면 스티커가 질문 줄로 옮겨진다
let pollT=null;
const pendingNotes=()=>notes.some(n=>(n.magic_rid&&!n.answer)||(n.thread||[]).some(t=>t&&t.magic_rid&&!t.a));
// 쓰는 중(꼬리 질문 칸 포커스 · 고치는 중인 스티커) — 그동안은 다시 그리지 않고 다음 차례로 미룬다
const editingNow=()=>{const a=document.activeElement;return !!(a&&a.matches&&a.matches('.qf textarea'))||[...layer.querySelectorAll('.note textarea')].some(x=>x.closest('.note')._n.id);};
function startPoll(){if(!pollT&&pendingNotes())pollT=setInterval(poll,4000);}
async function poll(){
  if(qaDirty&&!editingNow()){qaDirty=false;renderNotes();}
  if(document.visibilityState==='visible'){
    let fresh=null;try{fresh=await api('GET',API+'?doc='+encodeURIComponent(DOC));}catch(e){}
    if(fresh&&JSON.stringify(fresh)!==JSON.stringify(notes)){
      // 같은 id 는 같은 객체에 덮어쓴다(그려 둔 스티커가 들고 있는 객체 그대로)
      const byId=new Map(notes.map(x=>[x.id,x]));
      notes=fresh.map(f=>{const e=byId.get(f.id);if(!e)return f;Object.keys(e).forEach(k=>{if(!(k in f))delete e[k];});return Object.assign(e,f);});
      report.notes=notes.length;if(editingNow())qaDirty=true;else renderNotes();
    }
  }
  if(!pendingNotes()&&!qaDirty){clearInterval(pollT);pollT=null;}
}
// 주소 #note=<스티커 id>[&t=<꼬리 id>] — 그 쪽으로 넘기고 질문 줄에서 그 행을 펼친다(답 전이면 스티커를 보인다)
function noteHash(){let h=location.hash.slice(1);try{h=decodeURIComponent(h);}catch(e){}if(!h.startsWith('note='))return null;const u=new URLSearchParams(h);return {id:u.get('note')||'',t:u.get('t')||''};}
function openNoteHash(){
  const q=noteHash();if(!q)return false;
  const n=notes.find(x=>x.id===q.id);if(!n){toast('스티커 없음');return true;}
  const pi=pageOfNote(n);
  if(n.answer){openRows.add(n.id);store.set('qa','1');}
  if(pi>=0&&pi<pages.length)goPage(pi,false);
  renderNotes();
  requestAnimationFrame(()=>{
    let el=null;
    if(n.answer){const panel=mode===2?spQa:(pages[pi]&&pages[pi]._qa);const row=panel&&panel.querySelector('.qr[data-id="'+CSS.escape(n.id)+'"]');
      el=row&&((q.t&&row.querySelector('.qt[data-t="'+CSS.escape(q.t)+'"]'))||row);}
    else el=[...layer.querySelectorAll('.note')].find(e=>e._n&&e._n.id===n.id)||null;
    if(!el)return;
    el.scrollIntoView({block:'center'});
    if(n.answer){el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
  });
  report.noteHash=q;
  return true;
}
async function loadNotes(){try{notes=await api('GET',API+'?doc='+encodeURIComponent(DOC));renderNotes();report.notes=notes.length;openNoteHash();startPoll();}catch(e){report.notes_error=String(e.message||e);}}

// ════════ 조작 블록 — 단계 재생기 · 조건 슬라이더 · 크게 열기 ════════
// 첫 화면은 빌드가 HTML 로 이미 그려 뒀다. 여기서는 블록 안 script.lvdata(미리 계산한 그림 · 지표)를 읽어 골라 보이기만 한다 — 새로 계산하지 않는다
let liveDown=false;  // 마지막 눌림이 조작 블록 안에서 시작했나(끌다가 블록 밖에서 놓아도 넘김이 아니다)
document.addEventListener('pointerdown',e=>{liveDown=!!(e.target.closest&&e.target.closest('.live'));},true);
const lvUse=el=>{const b=el.closest('.blk');if(b)logUse(b.dataset.id);};
function initStepper(el,d){
  const fig=el.querySelector('.lvfig'),txt=[...el.querySelectorAll('.lvs')],pos=el.querySelector('.lvpos'),play=el.querySelector('[data-a=play]');
  const rows=[...el.querySelectorAll('.lvtab tbody tr[data-r]')],n=d.steps.length;
  let cur=d.start,timer=null;
  function paint(){
    fig.innerHTML=d.steps[cur].svg;
    txt.forEach((p,i)=>p.classList.toggle('on',i===cur));
    pos.textContent=(cur+1)+' / '+n;
    const r=d.steps[cur].row;
    rows.forEach(tr=>{const k=+tr.dataset.r,f=d.first[k];
      tr.classList.toggle('lv-cur',k===r);tr.classList.toggle('lv-todo',k!==r&&f!==undefined&&f>cur);});
    el.dataset.step=cur;
  }
  function go(k){k=Math.max(0,Math.min(n-1,k));if(k===cur)return;cur=k;paint();lvUse(el);}
  function stop(){clearInterval(timer);timer=null;play.setAttribute('aria-pressed','false');}
  function run(){
    if(cur>=n-1){cur=0;paint();}
    play.setAttribute('aria-pressed','true');
    timer=setInterval(()=>{if(cur>=n-1){stop();return;}cur++;paint();if(cur>=n-1)stop();},d.auto);
  }
  el.addEventListener('click',e=>{
    const b=e.target.closest('button[data-a]');if(!b)return;
    const a=b.dataset.a;
    if(a==='play'){if(timer)stop();else{run();lvUse(el);}return;}
    stop();
    if(a==='first')go(0);else if(a==='prev')go(cur-1);else if(a==='next')go(cur+1);
  });
  el.addEventListener('keydown',e=>{
    if(e.target.closest('input,textarea,select')||e.altKey||e.ctrlKey||e.metaKey)return;
    if(e.key==='ArrowRight'){stop();go(cur+1);e.preventDefault();}
    else if(e.key==='ArrowLeft'){stop();go(cur-1);e.preventDefault();}
  });
  paint();
}
function initSlider(el,d){
  const fig=el.querySelector('.lvfig'),miss=el.querySelector('.lvmiss'),rs=[...el.querySelectorAll('input.lvr')],outs=[...el.querySelectorAll('output.lvpv')];
  const tiles=[...el.querySelectorAll('.lvm')],notes=[...el.querySelectorAll('.lvn')];
  const idx=d.params.map(p=>p.default);
  const keyOf=()=>idx.map((i,j)=>d.params[j].keys[i]).join('|');
  const num=(x,prec)=>prec!==null&&prec!==undefined?x.toFixed(prec):String(+x.toPrecision(6));
  function paint(){
    const k=keyOf(),f=d.frames[k];
    el.dataset.key=k;
    const old=fig.querySelector('svg');if(old)old.remove();
    if(f)fig.insertAdjacentHTML('afterbegin',f.svg);
    miss.hidden=!!f;
    tiles.forEach(t=>{const m=f&&f.m[t.dataset.m],v=t.querySelector('.lvmv');
      v.textContent=m?m.t:'–';v.classList.toggle('bad',!!(m&&m.bad));
      t.querySelector('.lvmd').textContent=m&&m.d?m.d:' ';});
    notes.forEach(p=>p.classList.toggle('on',p.dataset.k===k));
    outs.forEach(o=>{const j=+o.dataset.p;o.textContent=d.params[j].texts[idx[j]];rs[j].setAttribute('aria-valuetext',o.textContent);});
  }
  rs.forEach(r=>r.addEventListener('input',()=>{const j=+r.dataset.p,v=+r.value;if(idx[j]===v)return;idx[j]=v;paint();lvUse(el);}));
  const pd=d.predict;
  if(pd){
    const inp=el.querySelector('.lvpin'),res=el.querySelector('.lvpr');
    const check=()=>{
      const x=parseFloat(inp.value);
      if(!isFinite(x)){res.textContent='숫자를 입력';inp.focus();return;}
      Object.entries(pd.at).forEach(([pk,i])=>{const j=d.params.findIndex(p=>p.key===pk);idx[j]=i;rs[j].value=i;});
      paint();
      const f=d.frames[keyOf()],m=f&&f.m[pd.metric];
      if(!m||m.v===null){res.textContent='계산 안 함';delete res.dataset.actual;return;}
      const diff=x-m.v,tol=pd.prec!==null&&pd.prec!==undefined?0.5*Math.pow(10,-pd.prec):1e-9;
      res.textContent='실제 '+m.t+' · 입력 '+num(x,pd.prec)+' · 차이 '+(Math.abs(diff)<tol?'0':(diff>0?'+':'-')+num(Math.abs(diff),pd.prec));
      res.dataset.actual=String(m.v);res.dataset.diff=String(diff);
      lvUse(el);
    };
    el.querySelector('[data-a=check]').addEventListener('click',check);
    inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();check();}});
  }
  paint();
}
function initLive(){
  book.querySelectorAll('.live').forEach(el=>{
    try{
      const s=el.querySelector(':scope>script.lvdata');
      if(s){const d=JSON.parse(s.textContent);if(d.kind==='stepper')initStepper(el,d);else if(d.kind==='slider')initSlider(el,d);}
      else if(el.classList.contains('lv-open'))el.addEventListener('click',e=>{if(e.target.closest('a.lvgo'))lvUse(el);});
    }catch(err){const b=el.closest('.blk');report.errors.push({kind:'조작 블록 초기화 실패',block:b?b.dataset.id:'',msg:String(err&&err.message||err)});}
  });
}

// ════════ 읽기 기록 — META.reading_log 인 책만. 쪽마다 «화면에 보인 시간»(탭이 숨겨졌거나 60초 입력 없으면 안 센다) · 조작 블록 사용 횟수. 로컬 저장만 ════════
const logOn=!!META.reading_log,IDLE=60000;
let LOG={v:1,total:0,pages:{},uses:{}},lastInput=Date.now(),lastTick=Date.now(),logSort='page',resetArm=null;
if(logOn){try{const s=JSON.parse(store.get('log')||'null');if(s&&s.v===1)LOG=s;}catch(e){}}
function logSave(){store.set('log',JSON.stringify(LOG));}
function logUse(id){if(!logOn||!id)return;LOG.uses[id]=(LOG.uses[id]||0)+1;logSave();}
const shownPages=()=>mode===2?[pages[2*cur],pages[2*cur+1]].filter(Boolean):[pages[curPage]].filter(Boolean);
function logTick(){
  const now=Date.now(),dt=Math.min(now-lastTick,1500);lastTick=now;
  if(document.visibilityState!=='visible'||now-lastInput>=IDLE||dt<=0)return;
  shownPages().forEach(p=>{const k=p.dataset.first;if(k)LOG.pages[k]=(LOG.pages[k]||0)+dt;});
  LOG.total+=dt;logSave();
}
function logData(){
  const pg=[];pages.forEach((p,i)=>{const ms=LOG.pages[p.dataset.first]||0;if(ms>0)pg.push({page:i+1,chapter:p.dataset.chl||'',sec:Math.round(ms/1000),ms});});
  const us=Object.entries(LOG.uses).map(([id,n])=>{const b=blockById.get(id),pi=pageOf.get(id);
    return {block:id,page:pi>=0&&pi!==undefined?pi+1:null,chapter:b?(b.dataset.chl||''):'',kind:b?b.dataset.k:'',count:n};}).sort((a,b)=>(a.page||0)-(b.page||0));
  return {doc:DOC,total_sec:Math.round(LOG.total/1000),pages:pg,uses:us};
}
function logRender(){
  const d=logData(),body=document.getElementById('logBody');
  const rows=d.pages.slice();if(logSort==='time')rows.sort((a,b)=>b.ms-a.ms);
  let h='<table class="lgt"><thead><tr><th>장</th><th>쪽</th><th>초</th></tr></thead><tbody>'
    +(rows.length?rows.map(r=>'<tr><td>'+esc(r.chapter)+'</td><td>'+r.page+'</td><td>'+r.sec+'</td></tr>').join(''):'<tr><td colspan="3" class="lgn">기록 없음</td></tr>')+'</tbody></table>';
  h+='<p class="lgh">조작 블록 사용</p><table class="lgt"><thead><tr><th>블록</th><th>쪽</th><th>횟수</th></tr></thead><tbody>'
    +(d.uses.length?d.uses.map(u=>'<tr><td>'+esc(u.block)+'</td><td>'+(u.page||'')+'</td><td>'+u.count+'</td></tr>').join(''):'<tr><td colspan="3" class="lgn">기록 없음</td></tr>')+'</tbody></table>';
  body.innerHTML=h;
  document.getElementById('logTotal').textContent='합계 '+d.total_sec+'초';
  document.getElementById('logSort').textContent=logSort==='time'?'쪽 순서로':'긴 순으로';
}
function initLog(){
  if(!logOn)return;
  const fab=document.querySelector('.fab'),top=$('bTop');
  const btn=document.createElement('button');btn.type='button';btn.className='fbtn';btn.id='bLog';btn.title='읽기 기록';btn.setAttribute('aria-label','읽기 기록');
  btn.innerHTML='<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>';
  fab.insertBefore(btn,top);
  const pn=document.createElement('div');pn.id='logPanel';pn.className='lgp';pn.hidden=true;
  pn.innerHTML='<div class="lgb"><div class="lgtop"><b>읽기 기록</b><span id="logTotal"></span><button type="button" class="lgx" id="logClose" aria-label="닫기">×</button></div>'
    +'<div class="lgbar"><button type="button" id="logSort"></button><button type="button" id="logCopy">복사</button><button type="button" id="logReset">초기화</button></div>'
    +'<div class="lgbody" id="logBody"></div></div>';
  document.body.appendChild(pn);
  const open=on=>{pn.hidden=!on;btn.setAttribute('aria-pressed',String(on));if(on)logRender();};
  btn.addEventListener('click',e=>{e.stopPropagation();open(pn.hidden);});
  $('logClose').addEventListener('click',()=>open(false));
  $('logSort').addEventListener('click',()=>{logSort=logSort==='time'?'page':'time';logRender();});
  $('logCopy').addEventListener('click',async()=>{
    const t=JSON.stringify(logData(),null,2);
    try{await navigator.clipboard.writeText(t);}catch(e){const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e2){}ta.remove();}
    report.copied=t;toast('복사함');
  });
  $('logReset').addEventListener('click',()=>{  // 두 번 눌러야 지운다(확인창은 쓰지 않는다)
    const b=$('logReset');
    if(!resetArm){b.textContent='한 번 더 누르면 지움';resetArm=setTimeout(()=>{resetArm=null;b.textContent='초기화';},3000);return;}
    clearTimeout(resetArm);resetArm=null;b.textContent='초기화';
    LOG={v:1,total:0,pages:{},uses:{}};logSave();logRender();
  });
  ['pointerdown','pointermove','keydown','wheel','scroll','touchstart'].forEach(t=>addEventListener(t,()=>{lastInput=Date.now();},{capture:true,passive:true}));
  lastTick=Date.now();setInterval(logTick,1000);
  addEventListener('pagehide',logSave);
  report.log=()=>JSON.parse(JSON.stringify(LOG));
}

// ════════ 시작 ════════
async function init(){
  try{if(document.fonts&&document.fonts.ready)await document.fonts.ready;}catch(e){}
  const t0=performance.now();
  const meas=document.createElement('div');meas.className='measure';document.body.appendChild(meas);
  pages=paginate(meas);
  finish();
  pages.forEach(p=>{book.insertBefore(p,layer);const m=document.createElement('div');m.className='mk mk1';makeBlock(m,mkOf(p));book.insertBefore(m,layer);
    const q=document.createElement('div');q.className='mk qa qa1';q.hidden=true;p._qa=q;book.insertBefore(q,m);});  // 한 페이지 — 그 쪽 질문 줄
  meas.remove();
  NS=Math.ceil(pages.length/2);
  const ld=$('loading');if(ld)ld.remove();
  watchPages();
  const r0=store.get('rail');setRail(r0===null?innerWidth>=1100:r0==='1');
  // 처음 쪽: 주소 #앵커 → 저장된 위치(블록) → 맨 앞
  let start=0;const ht=hashTarget();
  if(ht&&pageOf.get(ht.dataset.id)>=0)start=pageOf.get(ht.dataset.id);
  else{const pos=store.get('pos');if(pos&&pageOf.has(pos)&&pageOf.get(pos)>=0)start=pageOf.get(pos);}
  curPage=start;cur=Math.floor(start/2);
  setMode(mode);
  if(mode===1)requestAnimationFrame(()=>goPage(start));
  if(ht){ht.classList.add('flash');report.hash=ht.dataset.id;}
  addEventListener('hashchange',()=>{if(openNoteHash())return;const t=hashTarget();if(!t)return;goBlock(t.dataset.id,false);t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');});
  report.ms=Math.round(performance.now()-t0);report.ready=true;
  report.go=(i)=>goPage(i);report.mode=()=>mode;report.cur=()=>curIndex();report.setMode=(m)=>setMode(m);
  document.body.dataset.paged='1';
  initLive();initLog();
  loadNotes();
}
init();
})();
