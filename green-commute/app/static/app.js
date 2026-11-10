'use strict';
const $=selector=>document.querySelector(selector);
const state={token:sessionStorage.getItem('gg_token'),user:null,page:null,session:0,controller:new AbortController(),aiHistory:[],aiDraft:'',aiRequest:null,selectedSupportId:null};
const icons={dashboard:'◫',journey:'↗',mall:'◇',wallet:'▤',orders:'▣',merchant:'▦',admin:'⚙',accounts:'◉'};
const names={dashboard:'我的概览',journey:'记录出行',mall:'积分商城',wallet:'积分账本',orders:'我的兑换',
  merchant:'商户工作台',admin:'运营管理',accounts:'账号管理'};
const rolePages={
  resident:['dashboard','journey','mall','wallet','orders','support','assistant'],
  merchant:['merchant','support','assistant'],
  admin:['admin','accounts','support','assistant']
};
const productIcons={train:'🚇',bike:'🚲',bag:'🛍️',plant:'🪴',coffee:'☕',leaf:'🌱',gift:'🎁'};
const fmt=n=>Number(n||0).toLocaleString('zh-CN');
const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=t=>t?new Date(t).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'-';

let toastTimer;
function toast(message){
  if(!message)return;
  const element=$('#toast');
  element.textContent=message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>element.classList.remove('show'),3300);
}

async function api(path,method='GET',body){
  const {session,token,controller}=state;
  const headers={Accept:'application/json'};
  if(body!==undefined)headers['Content-Type']='application/json';
  if(token)headers.Authorization='Bearer '+token;
  let response;
  try{
    response=await fetch('/api'+path,{method,headers,body:JSON.stringify(body),cache:'no-store',signal:controller.signal});
  }catch(error){
    if(state.session!==session)throw new DOMException('','AbortError');
    throw new Error('连接失败，请稍后重试');
  }
  const data=await response.json().catch(()=>null);
  if(state.session!==session)throw new DOMException('','AbortError');
  if(!response.ok){
    if(response.status===401 && token)logout();
    const detail=data?.detail;
    throw new Error(Array.isArray(detail)?detail.map(item=>item.msg).join('；'):detail||'请求失败，请稍后重试');
  }
  return data;
}

function logout(){
  sessionStorage.removeItem('gg_token');
  state.controller.abort();
  Object.assign(state,{token:null,user:null,page:null,session:state.session+1,controller:new AbortController(),
    pendingTrip:null,lastTrip:null,tripSubmitting:false,aiHistory:[],aiDraft:'',aiRequest:null,drawAssistant:null,selectedSupportId:null});
  document.querySelectorAll('.page').forEach(page=>{page.hidden=true;page.replaceChildren()});
  document.querySelectorAll('dialog').forEach(dialog=>{dialog.close();dialog.replaceChildren()});
  $('#nav').replaceChildren();
  $('#sidebar').classList.remove('open');
  $('#login-form').reset();
  $('#register-form').reset();
  setAuthTab(false);
  $('#login-page').hidden=false;
  $('#logout').hidden=true;
  $('#top-name').textContent='访客';
  $('#top-avatar').textContent='G';
  $('#crumb-title').textContent='登录';
  clearTimeout(toastTimer);
  $('#toast').textContent='';
  $('#toast').classList.remove('show');
}

function menu(){
  $('#nav').innerHTML=rolePages[state.user.role].map(page=>`<button class="nav-link ${state.page===page?'active':''}" data-page="${page}"><span aria-hidden="true">${icons[page]}</span> ${names[page]}</button>`).join('');
  $('#nav').querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>openPage(button.dataset.page));
}

function showUser(){
  const displayName=state.user.role==='resident'?state.user.username:state.user.display_name;
  $('#top-name').textContent=displayName;
  $('#top-avatar').textContent=displayName.charAt(0).toUpperCase();
  $('#logout').hidden=false;
}

async function refreshUser(){
  state.user=await api('/me');
  showUser();
}

async function openPage(page){
  if(!state.user || !rolePages[state.user.role].includes(page))return;
  state.page=page;
  menu();
  $('#sidebar').classList.remove('open');
  $('#login-page').hidden=true;
  document.querySelectorAll('.page').forEach(element=>{element.hidden=element.id!==page});
  $('#crumb-title').textContent=names[page];
  try{await render[page]()}catch(error){toast(error.message)}
}

function operationId(prefix){
  const random=Array.from(crypto.getRandomValues(new Uint8Array(12)),byte=>byte.toString(16).padStart(2,'0')).join('');
  return prefix+'-'+random;
}

const head=(tag,title,sub,right='')=>`<div class="page-head"><div><div class="eyebrow">${tag}</div><h1>${title}</h1><p>${sub}</p></div>${right}</div>`;
const stat=(label,val,caption,icon)=>`<div class="stat-card"><div class="stat-top"><span class="stat-title">${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${val}</div><div class="stat-caption">${caption}</div></div>`;
const modeZh={bus:'公交车',metro:'地铁',bike:'骑行',walk:'步行'};
const render={
 async dashboard(){await refreshUser();const [trips,data]=await Promise.all([api('/trips'),api('/wallet')]);const total=trips.reduce((s,t)=>s+t.saved_kg,0);const dist=trips.reduce((s,t)=>s+t.distance_km,0);const days=[];for(let i=6;i>=0;i--){let d=new Date;d.setDate(d.getDate()-i);days.push({key:d.toISOString().slice(0,10),label:['日','一','二','三','四','五','六'][d.getDay()],val:0})}for(const t of trips){let d=days.find(x=>x.key===t.created_at.slice(0,10));if(d)d.val+=t.points}const max=Math.max(...days.map(d=>d.val),1);$('#dashboard').innerHTML=head('YOUR IMPACT','早上好，'+safe(state.user.display_name)+' 👋','今天也为低碳城市贡献一份力量吧。','<span class="pill">✳ 绿色行动者</span>')+`<div class="hero"><div><div class="eyebrow" style="color:#b6dc9b">A GREENER CITY STARTS WITH YOU</div><h2>绿色出行，不止于抵达。<br>让环保成为日常习惯。</h2><p>记录公交、地铁、骑行或步行，累计您的减碳成果。</p><button class="button-light" id="hero-go">＋ 记录一段绿色出行 ↗</button></div><div class="hero-right"><div class="big-leaf">❧</div></div></div><div class="cards">${stat('当前可用积分',fmt(data.balance),'每次绿色出行均可累积','✳')}${stat('近期行程减碳',total.toFixed(2)+' <small style="font-size:13px">kg</small>','CO₂e 估算值','☘')}${stat('绿色行程',fmt(trips.length),'最近最多 100 条','↗')}${stat('近期绿色里程',dist.toFixed(1)+' <small style="font-size:13px">km</small>','已完成绿色出行里程','◇')}</div><div class="split"><div class="surface"><div class="surface-title"><h3>近 7 天积分趋势</h3><button class="link" id="chart-detail">查看记录 ↗</button></div><p class="sub">日常低碳行动，积少成多</p><div class="chart-wrap">${days.map(d=>`<div class="chart-col"><div class="bar" title="${d.val} 积分" style="height:${Math.max(3,d.val/max*115)}px"></div><div class="chart-label">周${d.label}</div></div>`).join('')}</div></div><div class="surface"><div class="surface-title"><h3>低碳小贴士</h3><span class="tag">ECO TIP</span></div><div class="tips"><strong>公交与骑行，让每公里更有意义。</strong><p>减排量根据行程记录和当时生效的排放规则估算。积分和减排量可在行程记录中核对。</p></div><p class="hint" style="margin-top:20px">已累计获得积分 <strong>${fmt(data.total_earned)}</strong>，累计支出积分 <strong>${fmt(data.total_spent)}</strong>。</p></div></div>`;$('#hero-go').onclick=()=>openPage('journey');$('#chart-detail').onclick=()=>openPage('wallet')},
 async orders(){const rows=await api('/redemptions');$('#orders').innerHTML=head('REDEMPTION HISTORY','我的兑换','查询已兑换的商品与当前商户履约状态。')+`<div class="surface"><h3>兑换订单</h3><p class="sub">兑换、履约和退款都会同步记录积分账本</p><div class="table-scroll"><table class="table"><thead><tr><th>订单编号</th><th>商品</th><th>兑换时间</th><th>消耗积分</th><th>状态</th></tr></thead><tbody>${rows.map(r=>`<tr><td>#${r.id}</td><td>${safe(r.product_name)}</td><td>${time(r.created_at)}</td><td class="minus">-${r.points}</td><td><span class="status ${r.status==='TO_FULFILL'?'pending':''}">${r.status==='FULFILLED'?'已核销':r.status==='TO_FULFILL'?'待商户核销':r.status==='REFUNDED'?'已退款':'处理中'}</span>${r.status==='TO_FULFILL'?` <button class="small-action" data-refund="${r.id}">申请退款</button>`:''}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无兑换订单</td></tr>'}</tbody></table></div></div>`;$('#orders').querySelectorAll('[data-refund]').forEach(b=>b.onclick=async()=>{if(!confirm('确认退回这笔兑换并返还积分吗？'))return;b.disabled=true;try{const x=await api(`/redemptions/${b.dataset.refund}/refund`,'POST');toast(`退款成功，当前余额 ${x.balance} 积分`);await openPage('orders')}catch(e){toast(e.message);b.disabled=false}})},
async admin(){const [st,settlements,merchants]=await Promise.all([api('/admin/stats'),api('/admin/settlements'),api('/admin/merchants')]);$('#admin').innerHTML=head('OPERATIONS CENTER','运营管理中心','查看全站低碳成果，追踪事件处理与商户积分清算。',`<button class="outline" id="replay">↻ 重试待处理事件 (${st.pending_events})</button>`)+`<div class="cards">${stat('注册居民',fmt(st.users),'城市低碳参与者','◉')}${stat('已完成行程',fmt(st.trips),'已发放积分的行程','↗')}${stat('减碳总量',fmt(st.saved_kg)+' kg','平台累计 CO₂e','☘')}${stat('平台发放积分',fmt(st.issued_points),'历史发放总量','✳')}</div><div class="surface"><div class="surface-title"><h3>商户结算管理</h3><span class="pill">兑换订单 ${st.redemptions} 笔</span></div><p class="sub">商户完成核销后，可标记该订单已结算积分</p><div class="table-scroll"><table class="table"><thead><tr><th>订单</th><th>商户用户ID</th><th>积分额</th><th>清算状态</th><th>操作</th></tr></thead><tbody>${settlements.map(s=>`<tr><td>#${s.redemption_id}</td><td>${s.merchant_id}</td><td>${s.points}</td><td><span class="status ${s.status==='PENDING'?'pending':''}">${s.status==='SETTLED'?'已清算':s.status==='CANCELLED'?'已取消':'待清算'}</span></td><td>${s.status==='PENDING'?`<button class="small-action" data-settle="${s.redemption_id}">完成清算</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无清算记录</td></tr>'}</tbody></table></div></div>`;$('#replay').onclick=async()=>{try{const d=await api('/admin/events/process','POST');toast('已处理 '+d.processed+' 个事件');openPage('admin')}catch(e){toast(e.message)}};$('#admin').querySelectorAll('[data-settle]').forEach(b=>b.onclick=async()=>{try{await api(`/admin/settlements/${b.dataset.settle}/settle`,'POST');toast('清算标记成功');openPage('admin')}catch(e){toast(e.message)}});renderAdminMerchants(merchants)}
};
function tripTable(rows){return `<div class="table-scroll"><table class="table"><thead><tr><th>行程编号</th><th>行程时间</th><th>方式</th><th>距离</th><th>减碳量</th><th>奖励积分</th><th>来源/规则</th><th>状态</th></tr></thead><tbody>${rows.map(t=>`<tr><td>${safe(t.client_trip_id)}</td><td>${time(t.created_at)}</td><td>${modeZh[t.mode]}</td><td>${t.distance_km.toFixed(2)} km</td><td>${t.saved_kg.toFixed(3)} kg</td><td class="plus">+${t.points}</td><td>${t.source==='legacy'?'历史记录':t.source==='simulated'?'估算记录':t.source==='imported'?'导入':t.source==='partner'?'合作方':'手动'} · ${safe(t.rule_version||'-')}</td><td><span class="status ${t.status==='PENDING'?'pending':''}">${t.status==='AWARDED'?'已发放':'待处理'}</span></td></tr>`).join('')||'<tr><td colspan="8" class="empty">暂时还没有行程，开始记录第一段低碳出行吧！</td></tr>'}</tbody></table></div>`}

render.mall=async function(){const [products,wallet,merchants]=await Promise.all([api('/products'),api('/wallet'),api('/merchants')]);$('#mall').innerHTML=head('REWARDS MARKETPLACE','积分兑换商城','查看全部商品，或选择指定商户和品类。',`<span class="pill">当前积分 ${fmt(wallet.balance)}</span>`)+`<div class="filters"><button class="filter active" data-merchant="全部">全部商户</button>${merchants.map(m=>`<button class="filter" data-merchant="${m.id}">${safe(m.display_name)}（${m.product_count}）</button>`).join('')}</div><div class="filters"><button class="filter active" data-filter="全部">全部品类</button>${[...new Set(products.map(p=>p.category))].map(c=>`<button class="filter" data-filter="${safe(c)}">${safe(c)}</button>`).join('')}</div><div id="product-grid" class="product-grid"></div>`;let mf='全部',cf='全部';const draw=()=>{$('#product-grid').innerHTML=products.filter(p=>(mf==='全部'||String(p.merchant_id)===mf)&&(cf==='全部'||p.category===cf)).map(p=>`<div class="product-card"><div class="product-art">${productIcons[p.icon]||'🎁'}</div><div class="product-body"><span class="tag">${safe(p.merchant_name||'商户')} · ${safe(p.category)}</span><div class="product-name">${safe(p.name)}</div><div class="product-desc">${safe(p.description)}</div><div class="product-meta"><span>库存 ${p.stock}</span><span>${fmt(p.cost)} 积分</span></div><div class="product-bottom"><button class="primary" data-buy="${p.id}" ${p.stock?'':'disabled'}>${p.stock?'立即兑换':'已售罄'}</button></div></div></div>`).join('')||'<p class="empty">暂时没有商品</p>';$('#product-grid').querySelectorAll('[data-buy]').forEach(b=>b.onclick=async()=>{try{const r=await api('/redemptions','POST',{product_id:Number(b.dataset.buy)});toast(`兑换成功，剩余 ${r.balance} 积分`);openPage('mall')}catch(e){toast(e.message)}})};$('#mall').querySelectorAll('[data-merchant]').forEach(b=>b.onclick=()=>{mf=b.dataset.merchant;$('#mall').querySelectorAll('[data-merchant]').forEach(x=>x.classList.toggle('active',x===b));draw()});$('#mall').querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{cf=b.dataset.filter;$('#mall').querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));draw()});draw()};

render.journey=async function(){
  const trips=await api('/trips');
  $('#journey').innerHTML=head('GREEN JOURNEY','记录绿色出行','根据出行方式、里程和当前排放规则计算积分。')+`
    <div class="grid-two">
      <div class="surface"><h3>新增一段绿色行程</h3>
        <form id="trip-form">
          <div class="form-grid">
            <label class="field">出行方式<select name="mode">${Object.entries(modeZh).map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select></label>
            <label class="field">行程距离（公里）<input name="distance" type="number" value="10" min="0.01" max="100" step="0.01" required></label>
          </div>
          <p class="hint" id="trip-number">${state.lastTrip?'已保存行程编号：'+safe(state.lastTrip):'行程保存后显示系统生成的编号。'}</p>
          <button class="primary block" type="submit" ${state.tripSubmitting?'disabled':''}>提交行程 · 获取积分</button>
        </form>
      </div>
      <div class="surface"><h3>预计碳减排</h3><div class="sample"><small>预计减少 CO₂e</small>
        <div class="sample-value" id="preview-carbon">—</div><span>预计获得 <strong id="preview-points">—</strong> 积分</span>
        <hr class="line"><small id="preview-rule">计算结果以服务端当前规则为准。</small></div>
      </div>
    </div>
    <div class="surface" style="margin-top:22px"><h3>我的绿色行程</h3>${tripTable(trips)}</div>`;
  const form=$('#trip-form');
  const mode=form.elements.mode;
  const distance=form.elements.distance;
  let previewRequest=0;
  async function updatePreview(){
    const request=++previewRequest;
    const previewCarbon=$('#preview-carbon');
    const previewPoints=$('#preview-points');
    const previewRule=$('#preview-rule');
    if(!distance.value || !distance.validity.valid){
      previewCarbon.textContent='—';
      previewPoints.textContent='—';
      previewRule.textContent='请输入有效的行程距离。';
      return;
    }
    try{
      const params=new URLSearchParams({mode:mode.value,distance_km:distance.value});
      const result=await api('/carbon/calculate?'+params);
      if(request!==previewRequest || !form.isConnected)return;
      previewCarbon.textContent=result.saved_kg.toFixed(3)+' kg';
      previewPoints.textContent=fmt(result.points);
      previewRule.textContent=`规则 ${result.rule_version} · 汽车基准 ${result.baseline_g_per_km} g/km · 当前方式 ${result.mode_g_per_km} g/km`;
    }catch(error){
      if(request===previewRequest && form.isConnected){
        previewCarbon.textContent='—';
        previewPoints.textContent='—';
        previewRule.textContent=error.message;
      }
    }
  }
  mode.onchange=distance.oninput=updatePreview;
  updatePreview();
  form.onsubmit=async event=>{
    event.preventDefault();
    if(state.tripSubmitting)return;
    const session=state.session;
    const payload={mode:mode.value,distance_km:distance.value,source:'simulated'};
    const signature=JSON.stringify(payload);
    if(state.pendingTrip?.signature!==signature){
      state.pendingTrip={signature,id:operationId('TRIP')};
    }
    state.tripSubmitting=true;
    event.submitter.disabled=true;
    try{
      const result=await api('/trips','POST',{...payload,client_trip_id:state.pendingTrip.id});
      state.pendingTrip=null;
      state.lastTrip=result.trip.client_trip_id;
      toast(`行程已保存，获得 ${result.trip.points} 积分，当前余额 ${result.balance}`);
      if(state.page==='journey')await render.journey();
    }catch(error){toast(error.message)}
    finally{
      if(state.session===session){
        state.tripSubmitting=false;
        const button=$('#trip-form button[type="submit"]');
        if(button)button.disabled=false;
      }
    }
  };
};

render.wallet=async function(){
  const zone=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
  const walletTime=new Intl.DateTimeFormat('zh-CN',{timeZone:zone,dateStyle:'short',timeStyle:'short'});
  const panel=$('#wallet');
  panel.innerHTML=head('POINTS LEDGER','积分账本','查看出行奖励、兑换支出和退款。')+`
    <div id="wallet-summary" class="cards"></div>
    <section class="surface">
      <div class="surface-title"><h3>流水明细</h3><span class="account-note" id="wallet-total"></span></div>
      <form id="wallet-filter" class="filter-form">
        <label class="field">开始日期<input type="date" name="start_date"></label>
        <label class="field">结束日期<input type="date" name="end_date"></label>
        <label class="field">收支<select name="direction"><option value="all">全部</option><option value="income">收入</option><option value="expense">支出</option></select></label>
        <button class="outline" type="button" id="wallet-reset">重置</button>
      </form>
      <p class="hint">日期按 ${safe(zone)} 时区显示，包含所选结束日期。</p>
      <p id="wallet-error" class="form-error" role="alert" hidden></p>
      <div class="table-scroll"><table class="table"><thead><tr><th>流水编号</th><th>摘要</th><th>时间</th><th>关联业务</th><th>积分变动</th><th>变动后余额</th></tr></thead>
        <tbody id="wallet-rows"></tbody></table></div>
      <div class="page-controls"><button class="outline" type="button" id="wallet-prev" disabled>上一页</button><span id="wallet-page">第 1 页</span><button class="outline" type="button" id="wallet-next" disabled>下一页</button></div>
    </section>`;
  const form=$('#wallet-filter');
  const errorLine=$('#wallet-error');
  const previous=$('#wallet-prev');
  const next=$('#wallet-next');
  let cursors=[null];
  let nextCursor=null;
  let requestNumber=0;
  async function loadPage(requestedCursors){
    const request=++requestNumber;
    const params=new URLSearchParams({limit:'20',timezone:zone});
    for(const [name,value] of new FormData(form)){
      if(value)params.set(name,value);
    }
    const cursor=requestedCursors.at(-1);
    if(cursor!==null)params.set('before_id',cursor);
    errorLine.hidden=true;
    previous.disabled=next.disabled=true;
    try{
      const wallet=await api('/wallet?'+params);
      if(!form.isConnected || request!==requestNumber)return;
      cursors=requestedCursors;
      nextCursor=wallet.next_before_id;
      $('#wallet-summary').innerHTML=stat('可用余额',fmt(wallet.balance),'当前可用积分','✳')+
        stat('累计收入',fmt(wallet.total_earned),'全量账本统计','↗')+stat('累计支出',fmt(wallet.total_spent),'全量账本统计','◇');
      $('#wallet-total').textContent=`${wallet.consistent?'账本一致':'需要核验'} · 全部共 ${fmt(wallet.transaction_count)} 笔`;
      $('#wallet-rows').innerHTML=wallet.transactions.map(item=>`<tr><td>#${item.id}</td><td>${safe(item.description)}</td>
        <td>${walletTime.format(new Date(item.created_at))}</td><td>${({TRIP:'出行',REDEEM:'兑换',REFUND:'退款'})[item.kind]||'业务'} #${item.reference_id}</td>
        <td class="${item.delta>0?'plus':'minus'}">${item.delta>0?'+':''}${item.delta}</td><td>${fmt(item.balance_after)}</td></tr>`).join('')||
        '<tr><td colspan="6" class="empty">当前筛选条件下没有积分流水</td></tr>';
      $('#wallet-page').textContent=`第 ${cursors.length} 页`;
      previous.disabled=cursors.length<=1;
      next.disabled=nextCursor===null;
    }catch(error){
      if(form.isConnected && request===requestNumber){
        errorLine.textContent=error.message;
        errorLine.hidden=false;
      }
    }
  }
  form.onchange=()=>loadPage([null]);
  form.onsubmit=event=>{event.preventDefault();loadPage([null])};
  $('#wallet-reset').onclick=()=>{form.reset();loadPage([null])};
  previous.onclick=()=>loadPage(cursors.slice(0,-1));
  next.onclick=()=>loadPage([...cursors,nextCursor]);
  await loadPage([null]);
};

function openFormDialog({title,fields,submitLabel='保存',save,complete,dialog=$('#form-dialog')}){
  dialog.innerHTML=`<div class="dialog-title"><h2>${title}</h2><button type="button" class="text-button" aria-label="关闭" data-close>×</button></div>
    <form class="form-grid">
      ${fields}
      <p class="form-error field full" role="alert" hidden></p>
      <div class="dialog-actions field full">
        <button class="outline" type="button" data-close>取消</button>
        <button class="primary" type="submit">${submitLabel}</button>
      </div>
    </form>`;
  dialog.setAttribute('aria-label',title);
  const form=dialog.querySelector('form');
  const errorLine=form.querySelector('.form-error');
  const closeButtons=dialog.querySelectorAll('[data-close]');
  let saving=false;
  dialog.oncancel=event=>{if(saving)event.preventDefault()};
  closeButtons.forEach(button=>button.onclick=()=>dialog.close());
  dialog.addEventListener('close',()=>{
    if(!dialog.open && dialog.contains(form))dialog.replaceChildren();
  },{once:true});
  form.onsubmit=async event=>{
    event.preventDefault();
    if(saving)return;
    saving=true;
    const button=event.submitter;
    button.disabled=true;
    closeButtons.forEach(close=>close.disabled=true);
    errorLine.hidden=true;
    try{
      const result=await save(new FormData(form));
      if(!dialog.open || !form.isConnected)return;
      dialog.close();
      if(complete)await complete(result);
    }catch(error){
      if(dialog.open && form.isConnected && error.name!=='AbortError'){
        errorLine.textContent=error.message;
        errorLine.hidden=false;
      }else{
        toast(error.message);
      }
    }finally{
      saving=false;
      button.disabled=false;
      closeButtons.forEach(close=>close.disabled=false);
    }
  };
  dialog.showModal();
  return form;
}

function usernameField(value=''){
  return `<label class="field">用户名<input name="username" value="${safe(value)}" required minlength="3" maxlength="48" pattern="[a-zA-Z0-9_]+" autocomplete="off"></label>`;
}
function storeNameField(value=''){
  return `<label class="field">商户名称<input name="display_name" value="${safe(value)}" required maxlength="80"></label>`;
}
function passwordField(label){
  return `<label class="field full">${label}<input type="password" name="password" required minlength="8" maxlength="128" autocomplete="new-password"></label>`;
}

function renderAdminMerchants(merchants){
  const panel=document.createElement('section');
  panel.className='surface section-gap';
  panel.innerHTML=`<div class="surface-title"><h3>商户账号</h3><button id="new-merchant" type="button" class="primary">新增商户</button></div>
    <div id="admin-merchants">${merchants.map(merchant=>`<div class="admin-row"><div><strong>${safe(merchant.display_name)}</strong>
      <small>账号 #${merchant.id} · ${merchant.product_count} 件在售商品</small></div></div>`).join('')||
      '<p class="empty">暂无商户</p>'}</div>`;
  $('#admin').prepend(panel);
  panel.querySelector('#new-merchant').onclick=()=>openFormDialog({
    title:'新增商户',fields:usernameField()+storeNameField()+passwordField('初始密码'),submitLabel:'创建商户',
    save:fields=>api('/admin/merchants','POST',Object.fromEntries(fields)),
    complete:async()=>{
      toast('商户账号创建成功');
      if(state.page==='admin')await render.admin();
    }
  });
}

render.accounts=async function(){
  const panel=$('#accounts');
  panel.innerHTML=head('ACCOUNT MANAGEMENT','账号管理','管理居民和商户的资料、密码与启用状态。')+`
    <section class="surface">
      <form id="account-filters" class="filter-form">
        <label class="field">角色<select name="role"><option value="">全部</option><option value="resident">居民</option><option value="merchant">商户</option></select></label>
        <label class="field">用户名<input name="username" maxlength="48" placeholder="按用户名搜索"></label>
        <label class="field">启用状态<select name="enabled"><option value="">全部</option><option value="true">启用</option><option value="false">停用</option></select></label>
        <button type="submit" class="primary">查找</button><button type="button" class="outline" id="account-reset">重置</button>
      </form>
      <div class="table-scroll"><table class="table"><thead><tr><th>用户名</th><th>角色</th><th>商户名称</th><th>状态</th><th>操作</th></tr></thead>
      <tbody id="account-rows"></tbody></table></div>
    </section>`;
  const filters=$('#account-filters');
  const rows=$('#account-rows');
  let latestRequest=0;
  async function loadAccounts(){
    const request=++latestRequest;
    try{
      const params=new URLSearchParams();
      for(const [key,value] of new FormData(filters))if(value.trim())params.set(key,value.trim());
      const accounts=await api('/admin/accounts?'+params);
      if(!rows.isConnected || request!==latestRequest)return;
      rows.innerHTML=accounts.map(account=>`<tr><td>${safe(account.username)}</td>
        <td>${account.role==='merchant'?'商户':'居民'}</td><td>${account.role==='merchant'?safe(account.display_name):'—'}</td>
        <td><span class="status ${account.enabled?'':'pending'}">${account.enabled?'启用':'停用'}</span></td>
        <td><div class="row-actions">
          <button class="outline" type="button" data-edit-account="${account.id}">编辑</button>
          <button class="outline" type="button" data-reset-account="${account.id}">重置密码</button>
          <button class="outline" type="button" data-toggle-account="${account.id}">${account.enabled?'停用':'恢复'}</button>
        </div></td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无符合条件的账号</td></tr>';
      for(const account of accounts){
        const endpoint=`/admin/accounts/${account.id}`;
        rows.querySelector(`[data-edit-account="${account.id}"]`).onclick=()=>openFormDialog({
          title:'编辑账号',
          fields:usernameField(account.username)+(account.role==='merchant'?storeNameField(account.display_name):''),
          save:fields=>api(endpoint,'PATCH',Object.fromEntries(fields)),
          complete:async()=>{toast('账号资料已更新');await loadAccounts()}
        });
        rows.querySelector(`[data-reset-account="${account.id}"]`).onclick=()=>openFormDialog({
          title:'重置密码',fields:passwordField('新密码'),
          save:fields=>api(endpoint+'/reset-password','POST',Object.fromEntries(fields)),
          complete:()=>toast('密码已重置，该账号需要重新登录')
        });
        const toggle=rows.querySelector(`[data-toggle-account="${account.id}"]`);
        toggle.onclick=async()=>{
          toggle.disabled=true;
          try{
            const updated=await api(endpoint,'PATCH',{enabled:!account.enabled});
            toast(updated.enabled?'账号已恢复':'账号已停用');
            await loadAccounts();
          }catch(error){toast(error.message);toggle.disabled=false}
        };
      }
    }catch(error){toast(error.message)}
  }
  filters.onsubmit=event=>{event.preventDefault();loadAccounts()};
  $('#account-reset').onclick=()=>{filters.reset();loadAccounts()};
  await loadAccounts();
};

const iconLabels={train:'地铁',bike:'自行车',bag:'环保袋',plant:'植物',coffee:'咖啡',leaf:'绿叶',gift:'礼品'};
render.merchant=async function(){
  const [products,orders,categories]=await Promise.all([
    api('/merchant/products'),api('/merchant/orders'),api('/merchant/categories')
  ]);
  const panel=$('#merchant');
  panel.innerHTML=head('MERCHANT CONSOLE','商户工作台','管理本店商品、库存和兑换订单。',
    '<button class="primary" type="button" id="new-product">新增商品</button>')+
    '<div class="cards">'+stat('在售商品',fmt(products.filter(product=>product.active).length),'当前在售商品','◇')+
    stat('兑换订单',fmt(orders.length),'收到的兑换请求','▣')+
    stat('待履约',fmt(orders.filter(order=>order.redemption.status==='TO_FULFILL').length),'等待商户核销','◫')+'</div>'+`
    <section class="surface"><h3>商品管理</h3><div class="table-scroll"><table class="table"><thead>
      <tr><th>商品</th><th>品类</th><th>积分价格</th><th>库存</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${products.map(product=>`<tr><td>${safe(product.name)}</td><td>${safe(product.category)}</td><td>${fmt(product.cost)}</td>
        <td>${fmt(product.stock)}</td><td>${product.active?'在售':'已下架'}</td>
        <td><div class="row-actions"><button class="outline" type="button" data-edit-product="${product.id}">编辑</button>
        <button class="outline" type="button" data-stock-product="${product.id}">调整库存</button>
        <button class="outline" type="button" data-toggle-product="${product.id}">${product.active?'下架':'上架'}</button></div></td></tr>`).join('')||
        '<tr><td colspan="6" class="empty">暂无商品</td></tr>'}</tbody></table></div>
    </section>
    <section class="surface section-gap"><h3>兑换订单</h3>
      ${orders.map(({redemption:order,settlement_status})=>`<div class="admin-row"><div>
        <strong>#${order.id} · ${safe(order.product_name)}</strong>
        <small>${fmt(order.points)} 积分 · ${time(order.created_at)} · ${({PENDING:'待结算',SETTLED:'已结算',CANCELLED:'已取消'})[settlement_status]||'处理中'}</small></div>
        ${order.status==='TO_FULFILL'?`<button class="small-action" type="button" data-fulfill="${order.id}">确认核销</button>`:
          `<span class="status">${({FULFILLED:'已核销',REFUNDED:'已退款'})[order.status]||'处理中'}</span>`}
      </div>`).join('')||'<p class="empty">尚无兑换订单</p>'}
    </section>`;

  async function refreshMerchant(){
    if(state.page==='merchant')await render.merchant();
  }

  function showProductForm(product){
    const fields=`
      <label class="field full">商品名称<input name="name" required minlength="2" maxlength="90" value="${safe(product?.name)}"></label>
      <label class="field">积分价格<input name="cost" type="number" required min="1" max="100000" value="${product?.cost??20}"></label>
      ${product?'':'<label class="field">初始库存<input name="stock" type="number" required min="0" max="100000" value="10"></label>'}
      <div class="field"><label for="product-category">品类</label><div class="inline-field">
        <select name="category" id="product-category" required><option value="">请选择</option>${categories.map(category=>
          `<option value="${safe(category.name)}" ${category.name===product?.category?'selected':''}>${safe(category.name)}</option>`).join('')}</select>
        <button type="button" class="outline" data-new-category>新增品类</button>
      </div></div>
      <label class="field">图标<select name="icon">${Object.entries(iconLabels).map(([icon,label])=>
        `<option value="${icon}" ${icon===(product?.icon||'gift')?'selected':''}>${label}</option>`).join('')}</select></label>
      <label class="field full">商品说明<textarea name="description" maxlength="300" rows="3">${safe(product?.description)}</textarea></label>`;
    const form=openFormDialog({
      title:product?'编辑商品':'新增商品',fields,submitLabel:product?'保存商品':'上架商品',
      save:formData=>{
        const payload=Object.fromEntries(formData);
        payload.cost=Number(payload.cost);
        if(!product)payload.stock=Number(payload.stock);
        return api(product?`/merchant/products/${product.id}`:'/merchant/products',product?'PATCH':'POST',payload);
      },
      complete:async()=>{toast(product?'商品已更新':'商品已上架');await refreshMerchant()}
    });
    form.querySelector('[data-new-category]').onclick=()=>openFormDialog({
      title:'新增品类',dialog:$('#category-dialog'),
      fields:'<label class="field full">品类名称<input name="name" required maxlength="40"></label>',
      save:formData=>api('/merchant/categories','POST',{name:formData.get('name')}),
      complete:category=>{
        categories.push(category);
        const select=form.elements.category;
        select.add(new Option(category.name,category.name,true,true));
        toast('品类已创建');
      }
    });
  }

  panel.querySelector('#new-product').onclick=()=>showProductForm();
  for(const product of products){
    const endpoint=`/merchant/products/${product.id}`;
    panel.querySelector(`[data-edit-product="${product.id}"]`).onclick=()=>showProductForm(product);
    panel.querySelector(`[data-stock-product="${product.id}"]`).onclick=()=>{
      let previousOperation;
      openFormDialog({
        title:'调整库存',
        fields:`<p class="hint field full">${safe(product.name)} · 当前库存 ${fmt(product.stock)} 件</p>
          <label class="field">变动数量<input type="number" name="quantity" min="-100000" max="100000" step="1" required placeholder="补货填正数，扣减填负数"></label>
          <label class="field">备注<input name="note" required minlength="2" maxlength="200"></label>`,
        save:fields=>{
          const quantity=Number(fields.get('quantity'));
          const note=fields.get('note');
          if(quantity===0)throw new Error('库存变动必须为非零整数');
          const signature=JSON.stringify([quantity,note]);
          if(previousOperation?.signature!==signature)previousOperation={signature,id:operationId('stock')};
          return api(endpoint+'/inventory','POST',{quantity,note,operation_id:previousOperation.id});
        },
        complete:async()=>{toast('库存已更新');await refreshMerchant()}
      });
    };
    const toggle=panel.querySelector(`[data-toggle-product="${product.id}"]`);
    toggle.onclick=async()=>{
      toggle.disabled=true;
      try{
        await api(endpoint,'PATCH',{active:!product.active});
        toast(product.active?'商品已下架':'商品已上架');
        await refreshMerchant();
      }catch(error){toast(error.message);toggle.disabled=false}
    };
  }
  panel.querySelectorAll('[data-fulfill]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    try{
      await api(`/merchant/orders/${button.dataset.fulfill}/fulfill`,'POST');
      toast('订单核销成功');
      await refreshMerchant();
    }catch(error){toast(error.message);button.disabled=false}
  });
};

function setAuthTab(register){
  $('.auth-tabs').querySelectorAll('[data-auth]').forEach(tab=>tab.classList.toggle('active',(tab.dataset.auth==='register')===register));
  $('#login-form').hidden=register;
  $('#register-form').hidden=!register;
  $('#auth-title').textContent=register?'创建居民账户':'登录青行';
  $('#auth-eyebrow').textContent=register?'JOIN GREENGO':'WELCOME BACK';
  $('#auth-subtitle').textContent=register?'注册后可记录出行并兑换积分':'请输入用户名和密码';
}

function startSession(result){
  logout();
  state.token=result.access_token;
  sessionStorage.setItem('gg_token',state.token);
  state.user=result.user;
  showUser();
}

for(const [id,path] of [['login-form','/auth/login'],['register-form','/auth/register']]){
  const form=document.getElementById(id);
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=event.submitter;
    button.disabled=true;
    try{
      const result=await api(path,'POST',Object.fromEntries(new FormData(form)));
      startSession(result);
      toast(path==='/auth/register'?'注册成功':'欢迎回来，'+state.user.display_name);
      await openPage(rolePages[state.user.role][0]);
    }catch(error){toast(error.message)}
    finally{button.disabled=false}
  };
}
$('.auth-tabs').querySelectorAll('[data-auth]').forEach(tab=>tab.onclick=()=>setAuthTab(tab.dataset.auth==='register'));
$('#logout').onclick=logout;
$('#mobile-menu').onclick=()=>$('#sidebar').classList.toggle('open');
$('#today').textContent=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric'}).format(new Date());
if(state.token){
  const session=state.session;
  refreshUser().then(()=>openPage(rolePages[state.user.role][0])).catch(()=>{
    if(state.session===session)logout();
  });
}else{
  logout();
}
