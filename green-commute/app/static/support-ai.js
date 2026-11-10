/* GreenGo: customer-service tickets and an opt-in, real LLM assistant. */
'use strict';
icons.support='◉'; icons.assistant='✦';
names.support='客服中心'; names.assistant='AI 出行助手';
const ticketLabels={OPEN:'待处理',IN_PROGRESS:'处理中',RESOLVED:'已解决'};
const categories=['积分问题','行程问题','兑换订单','账号帮助','其他'];

render.support=async function(){
  const tickets=await api('/support/tickets');
  const isAgent=state.user.role==='admin';
  if(!tickets.some(x=>x.id===state.selectedSupportId))state.selectedSupportId=tickets.length?tickets[0].id:null;
  const list=tickets.map(x=>`<button type="button" class="ticket-item ${state.selectedSupportId===x.id?'selected':''}" data-ticket-id="${x.id}">
    <span class="ticket-line"><strong>#${x.id} ${safe(x.subject)}</strong><span class="status ${x.status==='RESOLVED'?'':'pending'}">${ticketLabels[x.status]||'未知'}</span></span>
    <span class="ticket-meta">${safe(x.category)}${isAgent?' · '+safe(x.customer_name):''} · ${time(x.updated_at)}</span></button>`).join('');
  $('#support').innerHTML=head('CUSTOMER SUPPORT',isAgent?'客服工单工作台':'客服中心',isAgent?'查看用户咨询、回复工单、更新处理状态。':'有积分、行程或兑换问题？可创建工单联系平台人工客服。',!isAgent?'<button class="primary" id="create-ticket-toggle">＋ 新建咨询</button>':'<span class="pill">人工工单处理</span>')+
   `<div id="new-ticket" class="surface" hidden><h3>提交客服工单</h3><form id="new-ticket-form" class="form-grid">
     <div class="field"><label>问题分类</label><select id="ticket-category">${categories.map(c=>`<option>${c}</option>`).join('')}</select></div>
     <div class="field"><label>问题标题</label><input id="ticket-subject" minlength="4" maxlength="100" required placeholder="例如：积分尚未到账"></div>
     <div class="field full"><label>详细描述</label><textarea id="ticket-message" minlength="5" maxlength="2000" rows="4" required placeholder="请填写发生了什么，不要上传密码或敏感信息"></textarea></div>
     <div class="field full"><button type="submit" class="primary">提交咨询</button></div>
   </form></div>
   <div class="support-layout"><div class="surface ticket-list"><div class="surface-title"><h3>${isAgent?'全部工单':'我的工单'}</h3><span class="account-note">最近100条 · ${tickets.length} 条</span></div><div class="ticket-scroll">${list||'<p class="empty">尚无客服工单</p>'}</div></div>
   <div id="ticket-detail" class="surface ticket-detail"><p class="empty">${tickets.length?'正在加载咨询详情…':'请创建工单开始咨询'}</p></div></div>`;
  if(!isAgent){
    $('#create-ticket-toggle').onclick=()=>{$('#new-ticket').hidden=!$('#new-ticket').hidden;if(!$('#new-ticket').hidden)$('#ticket-subject').focus()};
    $('#new-ticket-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const t=await api('/support/tickets','POST',{category:$('#ticket-category').value,subject:$('#ticket-subject').value,content:$('#ticket-message').value});state.selectedSupportId=t.id;toast('咨询工单已创建');await render.support()}catch(err){toast(err.message)}finally{b.disabled=false}};
  }
  $('#support').querySelectorAll('[data-ticket-id]').forEach(b=>b.onclick=async()=>{state.selectedSupportId=Number(b.dataset.ticketId);await openPage('support')});
  if(state.selectedSupportId)await displayTicket(state.selectedSupportId);
};
async function displayTicket(id){
  const data=await api(`/support/tickets/${id}`);
  if(state.page!=='support'||id!==state.selectedSupportId)return;
  const {ticket,messages}=data,admin=state.user.role==='admin';
  $('#ticket-detail').innerHTML=`<div class="ticket-heading"><div><div class="eyebrow">TICKET #${ticket.id}</div><h3>${safe(ticket.subject)}</h3><p class="hint">${safe(ticket.category)} · ${safe(ticket.customer_name)} · ${time(ticket.created_at)}</p></div><span class="status ${ticket.status==='RESOLVED'?'':'pending'}">${ticketLabels[ticket.status]||'未知'}</span></div>
    <div class="support-messages" aria-label="客服对话历史">${messages.map(message=>{
      const mine=message.sender_id===state.user.id;
      return `<div class="message-bubble ${mine?'mine-message':'other-message'}"><div class="msg-meta">${mine?'我':safe(message.sender_name)} · ${time(message.created_at)}</div><div class="msg-text">${safe(message.content)}</div></div>`;
    }).join('')}</div>
    ${admin?`<form id="status-form" class="support-status"><label>工单状态</label><select id="ticket-status"><option value="OPEN" ${ticket.status==='OPEN'?'selected':''}>待处理</option><option value="IN_PROGRESS" ${ticket.status==='IN_PROGRESS'?'selected':''}>处理中</option><option value="RESOLVED" ${ticket.status==='RESOLVED'?'selected':''}>已解决</option></select><button type="submit" class="outline">更新状态</button></form>`:''}
    <form id="reply-form" class="support-reply"><label>${admin?'人工客服回复':'补充说明或继续咨询'}</label><textarea id="reply-text" maxlength="2000" rows="3" required placeholder="输入消息，发送后将保存至客服工单…"></textarea><button class="primary" type="submit">发送回复 ↗</button></form>`;
  const thread=$('#ticket-detail .support-messages');thread.scrollTop=thread.scrollHeight;
  $('#reply-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await api(`/support/tickets/${ticket.id}/messages`,'POST',{content:$('#reply-text').value});toast('回复已发送');await render.support()}catch(err){toast(err.message)}finally{b.disabled=false}};
  if(admin)$('#status-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await api(`/support/tickets/${ticket.id}/status`,'PATCH',{status:$('#ticket-status').value});toast('工单状态已更新');await render.support()}catch(err){toast(err.message)}finally{b.disabled=false}};
}

const FAQ=[
  {q:'出行积分如何计算？',a:'系统用行程距离和当时生效的排放因子估算减排量，再按生效规则换算积分并向下取整。请在「记录出行」查看本次行程的规则和预估结果。'},
  {q:'为什么我的积分没有增加？',a:'请在「记录出行」查看行程编号、距离和状态。极短行程可能得到0积分；重复行程不会重复发放。如需核查，请创建客服工单。'},
  {q:'兑换后能取消吗？',a:'待商户核销的订单可以在「我的兑换」申请退款。退款返还积分并回补库存。已核销订单的问题可提交客服工单。'}
];
render.assistant=async function(){
  const config=await api('/assistant/config');
  const connected=config.configured;
  $('#assistant').innerHTML=head('AI GREEN MOBILITY', 'AI 绿色出行助手','咨询绿色出行、积分计算、商城规则。真正的大模型服务仅在配置 API 后启用。',`<span class="pill">${connected?'真实大模型 · '+safe(config.model):'未配置大模型'}</span>`)+
   `<div class="ai-layout"><div class="surface"><div class="surface-title"><h3>对话助手</h3><button type="button" class="outline" id="clear-ai">清空对话</button></div>
     <p class="hint ai-notice">${safe(config.notice)} ${connected?'模型内容仅供参考，不代表官方碳核证或账户数据。':'当前不调用任何模型，右侧常见问题为本地固定知识库（非 AI）。'}</p>
     <div id="ai-thread" class="ai-thread" aria-live="polite"></div>
     <form id="ai-form" class="ai-form"><textarea id="ai-text" rows="3" maxlength="1500" placeholder="例如：骑行15公里能得到多少积分？" ${connected?'':'disabled'} required></textarea><button type="submit" class="primary" id="ai-send" ${connected?'':'disabled'}>发送给大模型 ↗</button></form>
   </div><div class="surface ai-knowledge"><h3>绿色知识问答</h3><p class="sub">本地规则说明 · 不调用AI</p>
     ${FAQ.map((f,i)=>`<details class="faq-item"><summary>${safe(f.q)}</summary><p>${safe(f.a)}</p></details>`).join('')}
     <hr class="line"><p class="hint">如需人工查询账户、投诉或处理兑换订单，请使用客服中心。</p><button type="button" class="outline" id="to-support">前往客服中心 ↗</button>
   </div></div>`;
  const form=$('#ai-form');
  const textarea=$('#ai-text');
  const send=$('#ai-send');
  const thread=$('#ai-thread');
  const clear=$('#clear-ai');
  let composing=false;

  function draw(){
    if(!form.isConnected)return;
    const request=state.aiRequest;
    const messages=request?[...state.aiHistory,{role:'user',content:request.content},{role:'assistant',content:'模型正在生成回复…'}]:state.aiHistory;
    thread.innerHTML=messages.length?messages.map(message=>`<div class="ai-bubble ${message.role==='user'?'mine':'bot'}">
      <span class="msg-meta">${message.role==='user'?'我的问题':'AI 助手'}</span><div class="msg-text">${safe(message.content)}</div></div>`).join(''):
      '<div class="ai-welcome"><div class="ai-star">✦</div><strong>欢迎使用 GreenGo AI 助手</strong><p>输入绿色出行相关问题，获取来自已配置模型的回答。</p></div>';
    thread.scrollTop=thread.scrollHeight;
    textarea.readOnly=Boolean(request);
    if(textarea.value!==state.aiDraft)textarea.value=state.aiDraft;
    send.disabled=!connected || Boolean(request);
    send.textContent=request?'生成中…':'发送给大模型 ↗';
    clear.disabled=Boolean(request);
  }

  state.drawAssistant=draw;
  draw();
  clear.onclick=()=>{
    state.aiHistory=[];
    state.aiDraft='';
    draw();
    toast('已清空本次会话');
  };
  $('#to-support').onclick=()=>openPage('support');
  textarea.oninput=()=>{state.aiDraft=textarea.value};
  textarea.addEventListener('compositionstart',()=>{composing=true});
  textarea.addEventListener('compositionend',()=>{composing=false});
  textarea.addEventListener('keydown',event=>{
    if(event.key!=='Enter' || event.shiftKey || event.isComposing || composing || event.keyCode===229)return;
    event.preventDefault();
    if(connected && !state.aiRequest && textarea.value.trim())form.requestSubmit(send);
  });

  form.onsubmit=async event=>{
    event.preventDefault();
    if(!connected || state.aiRequest || composing)return;
    const content=textarea.value.trim();
    if(!content)return;
    const request={content};
    state.aiDraft=textarea.value;
    state.aiRequest=request;
    draw();
    try{
      const result=await api('/assistant/chat','POST',{message:content,history:state.aiHistory.slice(-8)});
      if(state.aiRequest!==request)return;
      state.aiHistory=[...state.aiHistory,{role:'user',content},{role:'assistant',content:result.answer}].slice(-16);
      state.aiDraft='';
    }catch(error){
      toast(error.message);
    }finally{
      if(state.aiRequest===request){
        state.aiRequest=null;
        state.drawAssistant?.();
      }
    }
  };
};
