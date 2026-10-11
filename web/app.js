'use strict';
function logo(id){
 const art={feishu:'<path fill="currentColor" d="M3 6.5 12 11l8-7-5 10-11 6 5-8L3 6.5Z"/><path fill="#a6bbff" d="m12 11 8-7-1 8-4 2Z"/>',wecom:'<path fill="currentColor" d="M3 5h18v11H11l-5 4v-4H3z"/><path stroke="white" stroke-width="1.5" d="M7 9h10M7 12h7"/>',wechat:'<path fill="currentColor" d="M10 3c-5 0-8 3-8 6 0 2 1 4 3 5l-1 3 4-2h2c-1-1-1-3-1-4 0-4 4-6 8-5-1-2-4-3-7-3Z"/><path fill="currentColor" opacity=".65" d="M16 7c4 0 7 2 7 5 0 2-1 3-2 4l1 3-4-2h-2c-3 0-6-2-6-5s3-5 6-5Z"/>',dingtalk:'<path fill="currentColor" d="m5 3 15 5-5 2 3 2-5 2 1 3-6 5 2-8-5-3 6-1-6-7Z"/>'};
 return `<span class="source-logo ${id}" aria-hidden="true"><svg viewBox="0 0 24 24">${art[id]}</svg></span>`;
}
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=value=>new Intl.NumberFormat('zh-CN').format(value??0);
const icon=name=>`<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const names={feishu:'飞书',wecom:'企业微信',wechat:'微信',dingtalk:'钉钉'};
const types={text:'文字',post:'富文本',image:'图片',file:'文件',video:'视频',media:'视频',voice:'语音',audio:'语音',interactive:'卡片',system:'系统',revoke:'撤回提示',mixed:'混合消息',unknown:'其他',emotion:'表情',chatrecord:'聊天记录',link:'链接',card:'名片',weapp:'小程序'};
const state={timezone:'Asia/Shanghai',me:null,sources:[],indexed:null,epoch:0,groupFilter:{source:'',q:'',status:'all',kind:'group',offset:0},recordFilter:{q:'',start:'',end:'',msg_type:'',offset:0},range:30,selectedGroups:new Set(),keys:[],revoke:null};
const date=(v,full=false)=>v?new Intl.DateTimeFormat('zh-CN',{timeZone:state.timezone,year:'numeric',month:'2-digit',day:'2-digit',...(full?{hour:'2-digit',minute:'2-digit',hour12:false}:{})}).format(new Date(v.includes('T')?v:v.replace(' ','T')+'+08:00')).replaceAll('/','-'):'—';
const stamp=seconds=>seconds?date(new Date(seconds*1000).toISOString(),true):'—';
const enc=encodeURIComponent;
const groupURL=(source,id,records=false)=>`#group/${source}/${enc(id)}${records?'/records':''}`;
const route=()=>{let parts=location.hash.slice(1).split('/');return {page:parts[0]||'overview',source:parts[1]||'',id:decodeURIComponent(parts[2]||''),tab:parts[3]||''};};
function badge(label,kind='muted'){return `<span class="badge ${kind}"><i class="badge-dot"></i>${esc(label)}</span>`;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>$('toast').hidden=true,3000);}
function params(values){const q=new URLSearchParams();Object.entries(values).forEach(([k,v])=>{if(v!==null&&v!==undefined&&v!=='')q.set(k,v);});return q.toString();}
async function api(path,values={},options={}){
 const r=await fetch('api/'+path+(Object.keys(values).length?'?'+params(values):''),{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
 let data;try{data=await r.json();}catch{if(r.status===401||r.redirected){showLogin();throw Error('请登录后继续');}throw Error('服务暂时不可用，请稍后重试');}
 if(r.status===401){if(path!=='session'||options.method!=='POST')showLogin(data.login_url);throw Error(data.error||'需要登录后查看聊天数据');}
 if(data.code==='password_change_required'){state.me=null;showPassword(true);}
 if(!r.ok)throw Error(data.error||data.detail||'请求未完成');return data;
}
function showLogin(url){
 state.epoch++;state.me=null;state.sources=[];state.visibleMessages=[];state.currentGroup=null;state.keys=[];state.selectedGroups.clear();
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('account-menu').open=false;
 $('page-content').replaceChildren();$('message-body').replaceChildren();$('new-token').value='';
 document.body.classList.add('locked');$('auth-screen').hidden=false;document.title='登录 · ChatArchive';
 if(url){$('feishu-login').href=url;$('feishu-login').hidden=false;}
}
function showPassword(required=false){
 state.passwordRequired=required;$('password-form').reset();$('password-error').textContent='';
 $('password-title').textContent=required?'设置你的登录密码':'修改密码';
 $('password-description').textContent=required?'首次登录，请更换管理员提供的初始密码。':'修改后，其他设备需要重新登录。';
 $('password-close').hidden=required;
 if(required){document.body.classList.add('locked');$('auth-screen').hidden=true;}
 if(!$('password-dialog').open)$('password-dialog').showModal();
}
async function logout(){
 try{await api('session',{}, {method:'DELETE'});}catch(e){if(state.me){toast(e.message);return;}}
 $('login-form').reset();$('login-error').textContent='';showLogin();location.hash='overview';
}

function header(title,subtitle,crumbs=[]){$('page-title').textContent=title;$('page-subtitle').textContent=subtitle;document.title=title+' · ChatArchive';$('breadcrumbs').innerHTML='<a href="#overview">工作空间</a>'+crumbs.map(c=>`<span class="crumb-divider">/</span>${c[1]?`<a href="${c[1]}">${esc(c[0])}</a>`:`<strong>${esc(c[0])}</strong>`}`).join('');}
function metric(label,value,foot,symbol){return `<article class="kpi"><div class="kpi-top"><span>${label}</span>${icon(symbol)}</div><strong class="kpi-value">${value}</strong><div class="kpi-foot">${foot}</div></article>`;}
function empty(title,text=''){return `<div class="empty-state">${icon('search')}<strong>${esc(title)}</strong>${text?`<p>${esc(text)}</p>`:''}</div>`;}
function sourceStatus(s){return s.mode==='unconfigured'?badge('未连接'):s.mode==='import'?badge('历史导入','info'):badge('已接入','good');}
function groupStatus(g){return !g.message_count?badge('未归档','warn'):g.source==='wechat'?badge('历史导入','info'):g.in_chat===0?badge('保留历史','muted'):g.enabled===0?badge('已停用','muted'):badge('有归档','good');}
function rangeParams(){if(!state.range)return{};const end=new Date();const start=new Date(Date.now()-(state.range-1)*86400000);const key=d=>new Intl.DateTimeFormat('en-CA',{timeZone:state.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(d);return {start:key(start),end:key(end)};}
function rangeSelect(){return `<select id="analysis-range" aria-label="分析时间范围">${[[7,'近 7 天'],[30,'近 30 天'],[90,'近 90 天'],[0,'全部记录']].map(([v,t])=>`<option value="${v}" ${state.range===v?'selected':''}>${t}</option>`).join('')}</select>`;}
function pager(data,kind){return `<div class="pager"><span>共 ${n(data.total)} ${kind==='groups'?'个会话':'条记录'}${data.total?` · ${n(data.offset+1)}–${n(data.offset+data.items.length)}`:''}</span><div><button class="button small" data-page-kind="${kind}" data-offset="${Math.max(0,data.offset-data.limit)}" ${data.offset===0?'disabled':''}>上一页</button><button class="button small" data-page-kind="${kind}" data-offset="${data.offset+data.limit}" ${!data.has_more?'disabled':''}>下一页</button></div></div>`;}
async function groupTable(source=''){
 const f=state.groupFilter,data=await api('groups',{...f,source:source||f.source,limit:25});
 const filters=`<form class="group-toolbar" id="group-search-form"><label class="search-field">${icon('search')}<input name="q" type="search" value="${esc(f.q)}" placeholder="搜索群名或编号" aria-label="搜索群名或编号"></label>${!source?`<select name="source" aria-label="来源筛选"><option value="">全部来源</option>${state.sources.filter(s=>s.mode!=='unconfigured').map(s=>`<option value="${s.source}" ${f.source===s.source?'selected':''}>${s.name}</option>`).join('')}</select>`:''}<select name="kind" aria-label="会话类型"><option value="group" ${f.kind==='group'?'selected':''}>群聊</option><option value="private" ${f.kind==='private'?'selected':''}>私聊</option><option value="all" ${f.kind==='all'?'selected':''}>全部会话</option></select><select name="status" aria-label="归档状态"><option value="all">全部状态</option><option value="archived" ${f.status==='archived'?'selected':''}>已有消息</option><option value="uncovered" ${f.status==='uncovered'?'selected':''}>尚未归档</option></select><button class="button" type="submit">筛选</button></form>`;
 return `<section class="panel group-panel"><div class="panel-heading"><h2>群管理 <span class="count-inline">${n(data.total)}</span></h2><span class="panel-caption">按最近消息排序</span></div>${filters}${data.items.length?`<div class="table-scroll"><table class="data-table group-table"><thead><tr><th>群名 / 编号</th><th>来源</th><th class="numeric">消息数</th><th class="numeric">参与人数</th><th>最近消息</th><th>归档状态</th><th></th></tr></thead><tbody>${data.items.map(g=>`<tr><td><a class="group-name" href="${groupURL(g.source,g.id)}"><strong>${esc(g.display_name)}</strong>${g.name?`<small title="${esc(g.id)}">${esc(g.id)}</small>`:'<small>平台暂未提供群名</small>'}</a></td><td><span class="source-chip">${logo(g.source)}${names[g.source]}</span>${g.connection&&g.source==='feishu'?`<small class="connection-label">${esc(g.connection)}</small>`:''}</td><td class="numeric">${n(g.message_count)}</td><td class="numeric">${n(g.participant_count)}</td><td class="cell-date">${date(g.last_message_at,true)}</td><td>${groupStatus(g)}</td><td><a class="row-action" href="${groupURL(g.source,g.id)}" aria-label="查看${esc(g.display_name)}">${icon('chevron')}</a></td></tr>`).join('')}</tbody></table></div>`:empty('没有符合条件的会话','调整名称、来源或归档状态后重试。')}${pager(data,'groups')}</section>`;
}
async function overview(){
 header('概览','群管理与采集覆盖',[['概览']]);const src=state.sources.filter(s=>s.mode!=='unconfigured');
 const total=key=>src.reduce((v,s)=>v+(s[key]||0),0),uncovered=total('groups')-total('archived_groups');
 const cards=`<div class="kpi-grid">${metric('归档消息',n(total('messages')),'全部已保存消息','archive')}${metric('群目录',n(total('groups')),`${n(total('archived_groups'))} 个群已有消息`,'file')}${metric('已接入数据源',`${src.length}<span class="unit">/ 4</span>`,src.map(s=>s.name).join(' · '),'connect')}${metric('尚未归档的群',n(uncovered),'已发现，暂无保存记录','alert')}</div>`;
 return cards+await groupTable();
}
async function sourcesPage(){
 header('数据源','从连接进入群分析与记录查询',[['数据源']]);
 return `<div class="connector-grid">${state.sources.map(s=>`<article class="connector-card ${s.mode==='unconfigured'?'unconnected':''}"><header>${logo(s.source)}<div><h2>${s.name}</h2><small>${s.mode==='import'?'历史记录导入':s.source==='wecom'?'会话内容存档':s.source==='feishu'?'应用与群消息':'尚未配置连接'}</small></div>${sourceStatus(s)}</header><dl class="connector-info"><div><dt>消息</dt><dd>${s.mode==='unconfigured'?'—':n(s.messages)}</dd></div><div><dt>群目录</dt><dd>${s.mode==='unconfigured'?'—':n(s.groups)}</dd></div><div><dt>最近消息</dt><dd>${date(s.last_message_at)}</dd></div></dl><div class="connector-bottom"><p>${s.source==='feishu'?Object.entries(s.details.connections||{}).map(([k,v])=>`${esc(k)} · ${v.visible_groups} 个群`).join('　'):s.source==='wecom'?'以群编号识别会话':s.source==='wechat'?`${n(s.private_conversations)} 个私聊`:'连接后可查询群与记录'}</p>${s.mode!=='unconfigured'?`<a class="button" href="#source/${s.source}">查看数据 ${icon('arrow')}</a>`:badge('未接入')}</div></article>`).join('')}</div>`;
}
function subnav(source,active,group){const base=group?groupURL(source,group.id):`#source/${source}`;return `<div class="section-tabs"><a class="${active==='analysis'?'active':''}" href="${base}">群分析</a><a class="${active==='records'?'active':''}" href="${base}/records">记录分析</a>${!group?`<a class="${active==='connection'?'active':''}" href="${base}/connection">连接状态</a>`:''}</div>`;}
function trend(data,start,end){
 if(data.length){const counts=new Map(data.map(x=>[x.day,x.count]));const first=new Date((start||data[0].day)+'T00:00:00Z'),last=new Date((end||data.at(-1).day)+'T00:00:00Z');const rows=[];for(let ms=first.getTime();ms<=last.getTime();ms+=86400000){const key=new Date(ms).toISOString().slice(0,10);rows.push({day:key,count:counts.get(key)||0});}data=rows;}
 if(!data.length)return empty('此时间段没有带日期的消息');
 const values=data.map(d=>d.count),max=Math.max(...values,1),W=700,H=190,L=40,R=15,T=12,B=28,step=(W-L-R)/Math.max(1,data.length-1),y=v=>H-B-v/max*(H-B-T);
 const points=data.map((d,i)=>`${L+i*step},${y(d.count)}`).join(' ');
 return `<div class="analysis-trend"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(data[0].day)} 至 ${esc(data.at(-1).day)} 的每日消息量">${[0,.5,1].map(v=>`<line x1="${L}" x2="${W-R}" y1="${y(max*v)}" y2="${y(max*v)}" class="chart-grid"/><text x="${L-8}" y="${y(max*v)+3}" text-anchor="end" class="chart-label">${n(Math.round(max*v))}</text>`).join('')}<polyline class="chart-line" stroke="#5677ed" points="${points}"/>${data.map((d,i)=>`<circle cx="${L+i*step}" cy="${y(d.count)}" r="${data.length<40?3:1.5}" fill="#5677ed"><title>${d.day} · ${n(d.count)} 条</title></circle>`).join('')}<text x="${L}" y="${H-3}" class="chart-label">${data[0].day}</text><text x="${W-R}" y="${H-3}" text-anchor="end" class="chart-label">${data.at(-1).day}</text></svg></div>`;
}
function bars(items,label){const max=Math.max(1,...items.map(v=>v.count));return `<div class="bar-list">${items.map(x=>`<div class="bar-item"><span title="${esc(label(x))}">${esc(label(x))}</span><div class="bar-track"><i style="width:${x.count/max*100}%"></i></div><b>${n(x.count)}</b></div>`).join('')}</div>`;}
function analysisPanels(a){
 const t=a.totals;
 return `<div class="analysis-toolbar"><span>消息日期 ${a.range.start?`${a.range.start} — ${a.range.end}`:'全部时间'}</span>${rangeSelect()}</div><div class="kpi-grid">${metric('区间消息',n(t.messages),'按发送时间统计','archive')}${metric('发言人数',n(t.participants),'按平台账号分别统计','file')}${metric('有消息的天数',n(t.active_days),'当前时间范围内','clock')}${metric('保留的撤回记录',n(t.revoked),t.undated?`${n(t.undated)} 条记录缺少时间`:'原始归档标记','info')}</div><div class="analysis-charts"><section class="panel"><div class="panel-heading"><h2>每日消息量</h2><span class="panel-caption">鼠标指向节点查看数量</span></div>${trend(a.days,a.range.start,a.range.end)}</section><section class="panel"><div class="panel-heading"><h2>消息类型</h2></div>${a.types.length?bars(a.types.slice(0,7),x=>types[x.type]||x.type):empty('暂无数据')}</section></div><div class="analysis-charts lower"><section class="panel"><div class="panel-heading"><h2>参与情况</h2><span class="panel-caption">发言较多的 15 个账号</span></div>${a.participants.length?bars(a.participants,x=>x.name):empty('暂无发言账号')}</section><section class="panel"><div class="panel-heading"><h2>高频词</h2><span class="panel-caption">${n(a.keyword_sample)} 条文本</span></div><div class="keyword-list">${a.keywords.map(w=>`<button class="keyword" data-word="${esc(w.word)}">${esc(w.word)}<span>${n(w.messages)}</span></button>`).join('')||'<span class="muted-copy">此范围内暂无可分析文本</span>'}</div><div class="panel-note">按包含词语的消息数统计，点击查看对应记录。</div><div class="panel-heading"><h2>发送时段</h2><span class="panel-caption">${esc(state.timezone)}</span></div><div class="hour-chart">${Array.from({length:24},(_,i)=>{const count=a.hours.find(h=>h.hour===i)?.count||0,max=Math.max(1,...a.hours.map(h=>h.count));return `<i style="height:${Math.max(2,count/max*65)}px" title="${i}:00 · ${n(count)} 条"></i>`;}).join('')}</div><div class="hour-labels"><span>00:00</span><span>12:00</span><span>23:00</span></div></section></div>`;
}
async function sourceDetail(r){
 const source=state.sources.find(s=>s.source===r.source);if(!source)throw Error('未找到数据源');
 header(source.name,'群分析与记录查询',[['数据源','#sources'],[source.name]]);
 const tab=r.id||'analysis';let html=subnav(r.source,tab);
 if(tab==='records')return html+await records(r.source);
 if(tab==='connection')return html+`<section class="panel connection-detail"><div class="panel-heading"><h2>连接信息</h2>${sourceStatus(source)}</div><dl class="detail-facts">${[['接入方式',source.mode==='import'?'历史导入':source.source==='wecom'?'企业微信会话内容存档':'飞书应用'],['归档消息',n(source.messages)],['已有记录的群',n(source.archived_groups)],['已发现的群',n(source.groups)],['最新消息',date(source.last_message_at,true)],['查询索引更新',date(state.indexed,true)]].map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>${source.source==='feishu'?`<h3>应用连接</h3><div class="connections">${Object.entries(source.details.connections||{}).map(([key,x])=>`<div><strong>${esc(key)}</strong>${badge('已连接','good')}<span>可见 ${n(x.visible_groups)} 个群</span></div>`).join('')}</div>`:''}${source.source==='wecom'?'<p class="panel-note">群名缺失时以平台群编号显示。附件消息可检索，原件未下载。</p>':''}<a class="button" href="#source/${r.source}">查看群目录 ${icon('arrow')}</a></section>`;
 const a=await api('analysis',{source:r.source,...rangeParams()});return html+analysisPanels(a)+await groupTable(r.source);
}
async function groupDetail(r){
 const g=await api('group',{source:r.source,group_id:r.id});state.currentGroup=g;
 header(g.display_name,`${names[g.source]} · ${n(g.message_count)} 条消息 · ${n(g.participant_count)} 个发言账号`,[['数据源','#sources'],[names[g.source],`#source/${g.source}`],['群详情']]);
 $('back-link').hidden=false;$('back-link').href=`#source/${g.source}`;
 let html=`<div class="group-identity">${logo(g.source)}<span class="mono">${esc(g.id)}</span>${groupStatus(g)}${g.connection?`<span class="connection-tag">${esc(g.connection)}</span>`:''}<span class="identity-dates">${date(g.first_message_at)} — ${date(g.last_message_at)}</span></div>`+subnav(r.source,r.tab==='records'?'records':'analysis',g);
 if(!g.message_count)return html+empty('此群尚无保存的消息',g.connection.includes('Y2')?'Y2 应用可见此群，当前归档任务尚未覆盖。':'此群已进入目录，但现有档案中没有消息。');
 if(r.tab==='records')return html+await records(r.source,r.id);
 const a=await api('analysis',{source:r.source,group_id:r.id,...rangeParams()});
 return html+analysisPanels(a)+`<div class="analysis-end"><span>分析基于当前时间范围内已归档的记录。</span><a class="button primary" href="${groupURL(r.source,r.id,true)}">查看群消息 ${icon('arrow')}</a></div>`;
}
async function records(source,group_id){
 const f=state.recordFilter,data=await api('messages',{source,group_id,...f,limit:40});state.visibleMessages=data.items;
 return `<section class="panel records-panel"><form id="records-form" class="record-filters"><label class="search-field wide">${icon('search')}<input name="q" value="${esc(f.q)}" type="search" aria-label="搜索消息正文" placeholder="搜索消息正文"></label><label class="date-field"><span>开始日期</span><input type="date" name="start" value="${f.start}"></label><label class="date-field"><span>结束日期</span><input type="date" name="end" value="${f.end}"></label><select name="msg_type" aria-label="消息类型"><option value="">全部类型</option>${Object.entries(types).filter(([k])=>!['media','audio'].includes(k)).map(([k,v])=>`<option value="${k}" ${f.msg_type===k?'selected':''}>${v}</option>`).join('')}</select><button class="button primary" type="submit">查询</button><button class="text-button" type="button" id="clear-records">重置</button></form><div class="results-header"><strong>${n(data.total)} 条记录</strong><span>按消息时间从近到远 · ${f.q?`关键词「${esc(f.q)}」`:'全部正文'}</span></div>${data.items.length?`<div class="message-list">${data.items.map((m,i)=>`<article class="message-row"><div class="sender-avatar">${esc((m.sender||'?').slice(0,1))}</div><div class="message-main"><div class="message-meta"><strong title="${esc(m.sender_id)}">${esc(m.sender)}</strong><span>${types[m.type]||esc(m.type)}</span>${m.deleted?badge('已撤回','warn'):''}<time>${date(m.sent_at,true)}</time></div>${!group_id?`<a class="message-group" href="${groupURL(m.source,m.group_id)}">${esc(m.display_name)} ${icon('chevron')}</a>`:''}<p class="message-text">${esc(m.text.slice(0,900))}${m.text.length>900?'…':''}</p><button class="text-button message-detail" data-message="${i}">查看原文与引用 ${icon('arrow')}</button></div></article>`).join('')}</div>`:empty('没有找到记录','调整关键词、日期或消息类型后重试。')}${pager(data,'records')}</section>`;
}
async function mcpPage(){
 header('MCP 接口','为接入平台分配查询范围与访问密钥',[['MCP 接口']]);
 const config=await api('integration');state.endpoint=config.endpoint;
 let html=`<section class="panel integration-header"><div><div class="eyebrow">连接地址</div><div class="endpoint"><code>${esc(config.endpoint)}</code><button class="button small" id="copy-endpoint">复制</button></div><div class="integration-meta">${badge('服务可用','good')}<span>Streamable HTTP</span><span>Bearer 密钥</span></div></div><button class="button" id="copy-config">复制接入配置</button></section>`;
 if(state.me.admin){const [keys,audit]=await Promise.all([api('keys'),api('audit')]);state.keys=keys.items;
 html+=`<section class="panel keys-panel"><div class="panel-heading"><h2>访问密钥</h2><button class="button primary" id="create-key">${icon('connect')} 创建密钥</button></div>${keys.items.length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>名称</th><th>数据范围</th><th>权限</th><th>有效期至</th><th>最近使用</th><th>状态</th><th></th></tr></thead><tbody>${keys.items.map(k=>{const active=!k.revoked_at&&k.expires_at>Date.now()/1000;return `<tr><td><strong>${esc(k.name)}</strong><small class="key-prefix">${esc(k.prefix)}…</small></td><td>${k.sources.map(s=>names[s]).join('、')}<small class="key-prefix">${k.groups?`${k.groups.length} 个指定会话`:'全部会话'}</small></td><td>${k.permissions.map(p=>({'groups:read':'群目录','messages:read':'原文','analysis:read':'分析'}[p])).join(' · ')}</td><td class="cell-date">${stamp(k.expires_at)}</td><td class="cell-date">${stamp(k.last_used)}</td><td>${k.revoked_at?badge('已撤销'):active?badge('有效','good'):badge('已过期','warn')}</td><td>${active?`<button class="text-button danger-text" data-revoke="${k.id}">撤销</button>`:''}</td></tr>`;}).join('')}</tbody></table></div>`:empty('尚未创建访问密钥','按来源或指定群授权后，将密钥交给需要接入的平台。')}</section>`;
 html+=`<section class="panel tools-panel"><div class="panel-heading"><h2>查询工具</h2><span class="panel-caption">所有调用受密钥范围约束</span></div><div class="tool-grid">${config.tools.map(t=>`<div class="tool-item">${icon(t.name==='analyze_group'?'bars':t.name==='search_messages'?'search':'file')}<div><code>${t.name}</code><p>${({list_sources:'查看来源与采集覆盖',list_groups:'查询群名、编号与消息数',search_messages:'筛选日期、关键词和消息类型',get_message:'读取消息原文与引用',analyze_group:'查询趋势、参与情况与高频词'})[t.name]}</p></div></div>`).join('')}</div></section>`;
 const logs=audit.items.filter(x=>x.action.startsWith('mcp.')).slice(0,12);
 html+=`<section class="panel audit-panel"><div class="panel-heading"><h2>最近调用</h2><span class="panel-caption">只记录调用元信息</span></div>${logs.length?`<div class="audit-list">${logs.map(x=>`<div><code>${esc(x.action.replace('mcp.',''))}</code><span>${esc(state.keys.find(k=>k.id===x.actor)?.name||'访问密钥')}</span><span>${x.result==='ok'?badge('成功','good'):badge('拒绝','warn')}</span><time>${stamp(x.at)}</time></div>`).join('')}</div>`:empty('暂无接口调用')}</section>`;
 }else html+=empty('访问密钥由管理员管理','当前密钥可用于其授权范围内的查询。');
 return html;
}
async function load(){const epoch=++state.epoch;if(state.renderedRoute!==location.hash){$('page-content').innerHTML='<div class="loading">正在读取数据…</div>';state.renderedRoute=location.hash;}$('notice').hidden=true;$('back-link').hidden=true;$('page-content').setAttribute('aria-busy','true');$('refresh').disabled=true;
 try{if(!state.me){const me=await api('me');if(epoch!==state.epoch)return;state.me=me;}
 if(state.me.must_change_password){showPassword(true);return;}
 $('auth-label').textContent=state.me.admin?'管理员':'只读访问';$('account-name').textContent=state.me.username;$('account-avatar').textContent=state.me.username.slice(0,1).toUpperCase();$('account-role').textContent=state.me.authentication==='feishu'?'飞书管理员':'空间管理员';$('change-password').hidden=state.me.authentication!=='password';
 $('auth-screen').hidden=true;document.body.classList.remove('locked');
 const src=await api('sources');if(epoch!==state.epoch)return;state.sources=src.sources;state.timezone=src.timezone;document.querySelector('.timezone').textContent=src.timezone;state.indexed=src.indexed_at;$('updated-at').textContent='索引更新 '+date(src.indexed_at,true);$('system-status').textContent='查询服务已连接';
 const r=route(),nav=['source','group'].includes(r.page)?'sources':r.page;document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('selected',a.dataset.nav===nav));
 const page=r.page==='overview'?await overview():r.page==='sources'?await sourcesPage():r.page==='source'?await sourceDetail(r):r.page==='group'?await groupDetail(r):r.page==='mcp'?await mcpPage():empty('页面不存在');
 if(epoch!==state.epoch)return;$('page-content').innerHTML=page;$('footer-status').textContent=(src.sources.some(s=>s.mode==='continuous')?'采集索引':'已导入记录')+' · 时区 '+src.timezone;
 if(src.sources.some(s=>s.mode==='continuous')&&src.indexed_at&&Date.now()-Date.parse(src.indexed_at)>20*60000){$('notice').textContent='查询索引更新延迟，当前显示最近一次完整数据。';$('notice').hidden=false;}
 }catch(e){if(epoch===state.epoch){$('notice').textContent=e.message;$('notice').hidden=false;$('page-content').innerHTML=empty('暂时无法读取数据','请检查登录状态，或点击右上角刷新。');$('system-status').textContent='连接需检查';}}
 finally{if(epoch===state.epoch){$('page-content').removeAttribute('aria-busy');$('refresh').disabled=false;}}
}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制');}catch{toast('复制失败，请选择文字手动复制');}}
function messageDetails(index){const m=state.visibleMessages[index];if(!m)return;$('message-body').innerHTML=`<div class="message-source">${badge(names[m.source],'info')}${badge(types[m.type]||m.type)}${m.deleted?badge('已撤回','warn'):''}</div><dl class="detail-facts">${[['群',m.display_name],['群编号',m.group_id],['发送者',m.sender],['发送者编号',m.sender_id||'未知'],['时间',date(m.sent_at,true)],['消息 ID',m.id]].map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><h3 class="message-body-title">原文</h3><pre class="full-message">${esc(m.text)}</pre>${m.media_state?`<p class="panel-note">附件：${({removed:'原件已由历史策略移除',error:'处理异常',stored:'原系统保留原件，本接口不提供下载',not_downloaded:'尚未下载原件'})[m.media_state]||esc(m.media_state)}</p>`:''}<button class="button" id="copy-citation">复制消息引用</button>`;$('copy-citation').onclick=()=>copy(`${names[m.source]} · ${m.display_name} · ${date(m.sent_at,true)}\n消息 ID: ${m.id}\n${m.text}`);$('message-dialog').showModal();}
async function populateKeyGroups(){const chosen=[...$('key-sources').querySelectorAll('input:checked')].map(e=>e.value);const search=$('key-group-search').value;const rows=await Promise.all(chosen.map(source=>api('groups',{source,q:search,kind:'all',limit:100})));$('key-groups').innerHTML=rows.flatMap(r=>r.items).map(g=>{const key=g.source+':'+g.id;return `<label><input type="checkbox" aria-label="${esc(g.display_name)} ${names[g.source]}" value="${esc(key)}" ${state.selectedGroups.has(key)?'checked':''}><span>${esc(g.display_name)}<small>${names[g.source]} · ${n(g.message_count)} 条</small></span></label>`;}).join('')||'<p class="muted-copy">没有符合条件的群</p>';if(rows.some(r=>r.has_more))$('key-groups').insertAdjacentHTML('beforeend','<p class="panel-note">每个来源显示前 100 个会话，请搜索定位其他群。</p>');}
function openKey(){state.selectedGroups.clear();$('key-form').reset();$('key-form').hidden=false;$('key-created').hidden=true;$('new-token').value='';$('key-error').textContent='';$('key-group-picker').hidden=true;$('key-sources').innerHTML=state.sources.filter(s=>s.mode!=='unconfigured').map(s=>`<label><input type="checkbox" name="key-source" value="${s.source}" ${s.source==='feishu'?'checked':''}>${s.name}</label>`).join('');$('key-dialog').showModal();}
$('page-content').addEventListener('submit',e=>{e.preventDefault();const form=e.target,values=Object.fromEntries(new FormData(form));if(form.id==='group-search-form')Object.assign(state.groupFilter,values,{offset:0});if(form.id==='records-form')Object.assign(state.recordFilter,values,{offset:0});load();});
$('page-content').addEventListener('change',e=>{if(e.target.id==='analysis-range'){state.range=Number(e.target.value);load();}});
$('page-content').addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;
 if(t.dataset.pageKind){state[t.dataset.pageKind==='groups'?'groupFilter':'recordFilter'].offset=Number(t.dataset.offset);load();}
 if(t.dataset.message!==undefined)messageDetails(Number(t.dataset.message));
 if(t.dataset.word){state.recordFilter={q:t.dataset.word,start:'',end:'',...rangeParams(),msg_type:'',offset:0};const r=route();location.hash=r.page==='group'?groupURL(r.source,r.id,true):`#source/${r.source}/records`;}
 if(t.id==='clear-records'){state.recordFilter={q:'',start:'',end:'',msg_type:'',offset:0};load();}
 if(t.id==='copy-endpoint')copy(state.endpoint);
 if(t.id==='copy-config')copy(JSON.stringify({mcpServers:{ChatArchive:{type:'http',url:state.endpoint,headers:{Authorization:'Bearer <YOUR_ACCESS_KEY>'}}}},null,2));
 if(t.id==='create-key')openKey();
 if(t.dataset.revoke){state.revoke=t.dataset.revoke;$('revoke-description').textContent='撤销「'+(state.keys.find(k=>k.id===state.revoke)?.name||'')+'」后，使用此密钥的客户端将立即失去查询权限。';$('revoke-dialog').showModal();}
});
document.addEventListener('click',e=>{const b=e.target.closest('[data-close]');if(b)$(b.dataset.close).close();});
$('key-dialog').addEventListener('close',()=>{$('new-token').value='';state.selectedGroups.clear();});
$('key-scope').addEventListener('change',()=>{$('key-group-picker').hidden=$('key-scope').value!=='selected';if(!$('key-group-picker').hidden)populateKeyGroups().catch(e=>$('key-error').textContent=e.message);});
$('key-sources').addEventListener('change',()=>{const allowed=[...$('key-sources').querySelectorAll('input:checked')].map(x=>x.value);state.selectedGroups=new Set([...state.selectedGroups].filter(k=>allowed.includes(k.split(':')[0])));if(!$('key-group-picker').hidden)populateKeyGroups().catch(e=>$('key-error').textContent=e.message);});
$('key-group-search').addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>populateKeyGroups().catch(e=>$('key-error').textContent=e.message),300);});
$('key-groups').addEventListener('change',e=>{if(e.target.matches('input')){e.target.checked?state.selectedGroups.add(e.target.value):state.selectedGroups.delete(e.target.value);$('selected-count').textContent='已选择 '+state.selectedGroups.size+' 个会话';}});
$('key-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.target.querySelector('[type=submit]');b.disabled=true;try{const data=await api('keys',{}, {method:'POST',body:JSON.stringify({name:$('key-name').value,sources:[...$('key-sources').querySelectorAll('input:checked')].map(x=>x.value),groups:$('key-scope').value==='all'?null:[...state.selectedGroups],permissions:[...e.target.querySelectorAll('[name=permission]:checked')].map(x=>x.value),days:Number($('key-days').value)})});$('key-form').hidden=true;$('key-created').hidden=false;$('new-token').value=data.token;load();}catch(e){$('key-error').textContent=e.message;}finally{b.disabled=false;}});
$('copy-token').onclick=()=>copy($('new-token').value);
$('confirm-revoke').onclick=async()=>{try{await api('keys/'+state.revoke,{}, {method:'DELETE'});$('revoke-dialog').close();toast('密钥已撤销');load();}catch(e){toast(e.message);}};
$('login-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('[type=submit]');b.disabled=true;$('login-error').textContent='';try{await api('session',{}, {method:'POST',body:JSON.stringify({username:$('login-username').value.trim(),password:$('login-password').value})});$('login-password').value='';state.me=null;await load();}catch(e){$('login-error').textContent=e.message;}finally{b.disabled=false;}};
$('logout').onclick=logout;$('password-logout').onclick=logout;
$('change-password').onclick=()=>{$('account-menu').open=false;showPassword();};
$('password-dialog').addEventListener('cancel',e=>{if(state.passwordRequired)e.preventDefault();});
$('password-dialog').addEventListener('close',()=>{$('password-form').reset();});
$('password-form').onsubmit=async e=>{e.preventDefault();$('password-error').textContent='';if($('new-password').value!==$('confirm-password').value){$('password-error').textContent='两次输入的新密码不一致';return;}const b=e.target.querySelector('[type=submit]');b.disabled=true;try{await api('password',{}, {method:'POST',body:JSON.stringify({current_password:$('current-password').value,new_password:$('new-password').value})});state.passwordRequired=false;$('password-dialog').close();state.me=null;toast('密码已更新');await load();}catch(e){$('password-error').textContent=e.message;}finally{b.disabled=false;}};
window.addEventListener('pageshow',e=>{if(e.persisted){state.me=null;load();}});

$('refresh').onclick=()=>load();
window.addEventListener('hashchange',()=>{state.groupFilter.offset=0;state.currentGroup=null;load();window.scrollTo({top:0,behavior:'instant'});});
load();
