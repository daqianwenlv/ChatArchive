'use strict';

const taskUI={draft:null,editId:null,groups:new Map(),searchEpoch:0,poll:null,run:null,rowPage:0};
const taskDimensions={group:'按群汇总',day:'按日统计',sender:'按发送者汇总',type:'按消息类型汇总',records:'整理资料清单'};
const taskStatuses={queued:['等待执行','info'],running:['执行中','info'],succeeded:['已完成','good'],failed:['失败','warn'],cancelled:['已取消','muted']};
const taskStatus=s=>s?badge(...(taskStatuses[s]||[s,'muted'])):badge('尚未运行');
const taskFormats={csv:'CSV 表格',markdown:'Markdown 报告',json:'JSON 数据'};
const taskKey=g=>JSON.stringify([g.source,g.id]);
const taskDefault=()=>({name:'',rule:{groups:[],keyword:'',message_type:'',days:7,window:'complete_days',dimension:'group',timezone:state.timezone},schedule:{frequency:'weekly',time:'09:00',weekday:0,monthday:1},output:'csv',enabled:true});
const taskOptions=(items,value)=>Object.entries(items).map(([k,v])=>`<option value="${esc(k)}" ${String(value)===k?'selected':''}>${esc(v)}</option>`).join('');
const taskSchedule=c=>c.schedule.frequency==='manual'?'仅手动运行':`${({daily:'每天',weekly:'每周'+['一','二','三','四','五','六','日'][c.schedule.weekday],monthly:'每月 '+c.schedule.monthday+' 日'})[c.schedule.frequency]} ${c.schedule.time} · ${c.rule.timezone}`;
function taskClear(){clearTimeout(taskUI.poll);taskUI.draft=null;taskUI.groups.clear();taskUI.run=null;taskUI.editId=null;taskUI.searchEpoch++;}
function taskSummary(c){const r=c.rule,time=({previous_week:'上一完整自然周',previous_month:'上一完整自然月',complete_days:`前 ${r.days} 个完整自然日`,rolling:`最近 ${r.days} 天`})[r.window];return `汇总 ${r.groups.length} 个群，${time}的${r.message_type?(types[r.message_type]||r.message_type):'全部'}消息${r.keyword?'，正文包含「'+r.keyword+'」':''}，${taskDimensions[r.dimension]}，生成 ${taskFormats[c.output]}。`;}

async function consolePage(r){
 header('指令台','选择资料范围，执行统计或保存为定期任务',[['指令台']]);
 if(!state.me.admin)return empty('需要管理员权限','请使用管理员账号创建和运行统计任务。');
 const id=r.source||null;
 if(!taskUI.draft||taskUI.editId!==id){
  const c=id?await api('tasks/'+enc(id)):taskDefault();
  taskUI.draft={name:c.name,rule:c.rule,schedule:c.schedule,output:c.output,enabled:c.enabled};taskUI.editId=id;
  const refs=await Promise.all(c.rule.groups.map(g=>api('group',{source:g.source,group_id:g.id}).catch(()=>({...g,display_name:g.id,message_count:0}))));
  refs.forEach(g=>taskUI.groups.set(taskKey(g),g));
 }
 const c=taskUI.draft;
 return `<form id="task-compose" class="command-layout">
 <div class="command-main"><section class="panel command-panel"><div class="command-section-title"><span class="step-number">1</span><h2>选择群</h2><span id="task-selected-count" class="panel-caption"></span></div><div id="task-selected" class="task-selected"></div><div class="group-search-row"><label class="search-field wide">${icon('search')}<input id="task-group-search" type="search" maxlength="160" placeholder="搜索群名或编号" aria-label="搜索任务群"></label><select id="task-source" aria-label="按来源筛选群"><option value="">全部来源</option>${taskOptions(names,'')}</select></div><div id="task-group-results" class="task-group-results" aria-live="polite"><p class="muted-copy">正在读取群…</p></div><div id="task-group-pages" class="task-group-pages"></div></section>
 <section class="panel command-panel"><div class="command-section-title"><span class="step-number">2</span><h2>资料与统计方式</h2></div><div class="task-presets"><span>常用规则</span><button type="button" class="button small" data-task-preset="weekly">跨群周报</button><button type="button" class="button small" data-task-preset="files">资料清单</button><button type="button" class="button small" data-task-preset="daily">每日趋势</button></div><div class="task-field-grid"><label>统计范围<div class="task-window"><select name="window" aria-label="统计时间范围">${taskOptions({complete_days:'前 N 个完整自然日',rolling:'截至执行时最近 N 天'},c.rule.window)}</select><input name="days" type="number" min="1" max="366" value="${c.rule.days}" required aria-label="统计天数"><span>天</span></div></label><label>消息类型<select name="message_type">${taskOptions({'':'全部类型',...Object.fromEntries(Object.entries(types).filter(([k])=>!['media','audio'].includes(k)))},c.rule.message_type)}</select></label><label class="task-field-full">正文包含<input name="keyword" maxlength="160" value="${esc(c.rule.keyword)}" placeholder="例如：合同，或一个项目名称（按完整关键词匹配）"><small>留空则统计全部；文件按消息类型筛选，附件内容不参与正文搜索。</small></label><label>统计方式<select name="dimension">${taskOptions(taskDimensions,c.rule.dimension)}</select></label><label>导出格式<select name="output">${taskOptions(taskFormats,c.output)}</select></label></div></section>
 <section class="panel command-panel"><div class="command-section-title"><span class="step-number">3</span><h2>保存任务</h2><span class="panel-caption">需要重复执行时设置</span></div><div class="task-field-grid"><label class="task-field-full">任务名称<input name="name" maxlength="80" value="${esc(c.name)}" placeholder="例如：产品群与交付群每周资料汇总"></label><label>执行周期<select name="frequency">${taskOptions({manual:'仅手动运行',daily:'每天',weekly:'每周',monthly:'每月'},c.schedule.frequency)}</select></label><label id="task-time-field">执行时间<input name="time" type="time" required value="${c.schedule.time}"></label><label id="task-week-field">每周<select name="weekday">${taskOptions({0:'周一',1:'周二',2:'周三',3:'周四',4:'周五',5:'周六',6:'周日'},c.schedule.weekday)}</select></label><label id="task-month-field">每月<input name="monthday" type="number" min="1" max="28" value="${c.schedule.monthday}" required><small>可选择 1–28 日，每个月都能执行。</small></label><label>时区<input name="timezone" required maxlength="64" value="${esc(c.rule.timezone)}" list="task-timezones"><datalist id="task-timezones"><option value="Asia/Shanghai"><option value="Asia/Singapore"><option value="UTC"></datalist></label></div></section></div>
 <aside class="command-aside"><section class="panel task-preview"><div class="eyebrow">统计指令</div><h2>${id?'编辑任务':'准备执行'}</h2><p id="task-command-preview"></p><dl><div><dt>结果</dt><dd>表格与原文依据</dd></div><div><dt>保留位置</dt><dd>任务 → 运行记录</dd></div><div><dt>定期执行</dt><dd id="task-schedule-preview"></dd></div></dl><p id="task-compose-error" class="form-error" role="alert"></p><button class="button primary" type="submit" value="run">${icon('bars')} 立即统计</button><button class="button" type="submit" value="save">${icon('clock')} ${id?'保存修改':'保存为任务'}</button>${id?`<a class="text-link" href="#tasks/${enc(id)}">返回任务详情</a>`:''}<small>统计已归档的数据，运行结果保存在当前工作空间。</small></section></aside></form>`;
}

function taskReadForm(){
 const f=$('task-compose');if(!f)return taskUI.draft;
 const v=Object.fromEntries(new FormData(f)),c=taskUI.draft;
 c.name=v.name;c.rule={...c.rule,keyword:v.keyword,message_type:v.message_type,days:Number(v.days),window:v.window,dimension:v.dimension,timezone:v.timezone};
 c.schedule={frequency:v.frequency,time:v.time,weekday:Number(v.weekday),monthday:Number(v.monthday)};c.output=v.output;return c;
}
function taskPreview(){
 const c=taskReadForm();if(!$('task-compose'))return;
 $('task-command-preview').textContent=taskSummary(c);$('task-schedule-preview').textContent=taskSchedule(c);
 $('task-week-field').hidden=c.schedule.frequency!=='weekly';$('task-month-field').hidden=c.schedule.frequency!=='monthly';$('task-time-field').hidden=c.schedule.frequency==='manual';
 $('task-selected-count').textContent=`已选 ${c.rule.groups.length} / 50`;
 $('task-selected').innerHTML=c.rule.groups.map(g=>`<button type="button" class="task-chip" data-task-remove="${esc(taskKey(g))}" aria-label="移除 ${esc(taskUI.groups.get(taskKey(g))?.display_name||g.id)}">${esc(taskUI.groups.get(taskKey(g))?.display_name||g.id)} ${icon('close')}</button>`).join('')||'<span class="muted-copy">从下方选择一个或多个群，可跨数据源统计。</span>';
}
async function taskSearchGroups(offset=0){
 if(!$('task-group-search'))return;const epoch=++taskUI.searchEpoch,q=$('task-group-search').value,source=$('task-source').value;
 const data=await api('groups',{q,source,limit:20,offset});if(epoch!==taskUI.searchEpoch||!$('task-group-results'))return;
 data.items.forEach(g=>taskUI.groups.set(taskKey(g),g));
 $('task-group-results').innerHTML=data.items.map(g=>`<label class="task-group-option"><input type="checkbox" data-task-group="${esc(taskKey(g))}" ${taskUI.draft.rule.groups.some(x=>taskKey(x)===taskKey(g))?'checked':''}>${logo(g.source)}<span><strong>${esc(g.display_name)}</strong><small>${names[g.source]} · ${esc(g.id)}</small></span><em>${n(g.message_count)} 条</em></label>`).join('')||'<p class="muted-copy">没有符合条件的群。</p>';
 $('task-group-pages').innerHTML=`<span>${n(data.total)} 个群 · ${data.total?offset+1:0}–${offset+data.items.length}</span><div><button class="button small" type="button" data-task-group-page="${offset-20}" ${offset===0?'disabled':''}>上一页</button><button class="button small" type="button" data-task-group-page="${offset+20}" ${data.has_more?'':'disabled'}>下一页</button></div>`;
}

function taskRunsTable(data,taskId=''){
 return `${data.items.length?`<div class="table-scroll"><table class="data-table"><thead><tr><th>统计任务</th><th>发起方式</th><th>开始时间</th><th>状态</th><th></th></tr></thead><tbody>${data.items.map(r=>`<tr><td><a class="task-name" href="#runs/${r.id}">${esc(r.name)}</a></td><td>${({console:'指令台',manual:'手动执行',scheduled:'定时执行'})[r.trigger]}</td><td>${stamp(r.started_at||r.created_at)}</td><td>${taskStatus(r.status)}</td><td><a class="text-link" href="#runs/${r.id}">查看结果 ${icon('arrow')}</a></td></tr>`).join('')}</tbody></table></div>`:empty('暂无运行记录','在指令台执行统计，或运行一个已保存的任务。')}<div class="task-group-pages"><span>共 ${n(data.total)} 次运行</span><div><a class="button small ${data.offset===0?'disabled':''}" href="${taskId?'#tasks/'+taskId:'#tasks/history'}/${Math.max(0,data.offset-30)}">上一页</a><a class="button small ${!data.has_more?'disabled':''}" href="${taskId?'#tasks/'+taskId:'#tasks/history'}/${data.offset+30}">下一页</a></div></div>`;
}
async function tasksPage(r){
 header('任务','管理统计规则、执行周期与运行结果',[['任务']]);
 if(!state.me.admin)return empty('需要管理员权限');
 if(r.source&&r.source!=='history'){
  const c=await api('tasks/'+enc(r.source)),runs=await api('task-runs',{task_id:c.id,offset:Number(r.id)||0});
  const selected=await Promise.all(c.rule.groups.map(g=>api('group',{source:g.source,group_id:g.id}).catch(()=>({...g,display_name:g.id}))));
  header(c.name,taskSchedule(c),[['任务','#tasks'],[c.name]]);
  return `<section class="panel task-detail-summary"><div>${badge(c.enabled?(c.schedule.frequency==='manual'?'仅手动':'已启用'):'已暂停',c.enabled?'good':'muted')}<h2>${esc(taskSummary(c))}</h2><div class="task-selected">${selected.map(g=>`<a class="task-chip" href="${groupURL(g.source,g.id)}" title="${esc(g.id)}">${names[g.source]} · ${esc(g.display_name)}</a>`).join('')}</div><p>下次执行：${stamp(c.next_run)} · 运行结果独立保留，修改规则不改变历史结果。</p></div><div class="task-actions"><button class="button primary" data-task-run="${c.id}">立即运行</button><a class="button" href="#console/${c.id}">编辑规则</a><button class="button" data-task-toggle="${c.id}" data-enabled="${c.enabled}">${c.enabled?'暂停任务':'启用任务'}</button></div></section><section class="panel task-history"><div class="panel-heading"><h2>运行记录</h2></div>${taskRunsTable(runs,c.id)}</section>`;
 }
 const tasks=await api('tasks'),history=r.source==='history';
 const toolbar=`<div class="view-toolbar"><div class="tabs"><a class="tab ${!history?'selected':''}" href="#tasks">统计任务 <span>${tasks.items.length}</span></a><a class="tab ${history?'selected':''}" href="#tasks/history">运行记录</a></div><a class="button primary" href="#console">${icon('clock')} 新建任务</a></div>`;
 if(history){const runs=await api('task-runs',{offset:Number(r.id)||0});return toolbar+`<section class="panel">${taskRunsTable(runs)}</section>`;}
 const active=tasks.items.filter(c=>c.enabled&&c.schedule.frequency!=='manual').length;
 const failed=tasks.items.filter(c=>c.last_status==='failed').length;
 return `<div class="kpi-grid task-kpis"><div class="kpi"><div class="kpi-top">统计任务 ${icon('file')}</div><strong class="kpi-value">${n(tasks.items.length)}</strong><div class="kpi-foot">保存的群范围与统计规则</div></div><div class="kpi"><div class="kpi-top">定时执行 ${icon('clock')}</div><strong class="kpi-value">${n(active)}</strong><div class="kpi-foot">由服务器按计划执行</div></div><div class="kpi"><div class="kpi-top">最近运行失败 ${icon('alert')}</div><strong class="kpi-value">${n(failed)}</strong><div class="kpi-foot">可查看原因并重新运行</div></div></div>${toolbar}${tasks.items.length?`<section class="panel"><div class="table-scroll"><table class="data-table task-table"><thead><tr><th>任务 / 资料范围</th><th>执行周期</th><th>下次执行</th><th>最近结果</th><th>操作</th></tr></thead><tbody>${tasks.items.map(c=>`<tr><td><a class="task-name" href="#tasks/${c.id}">${esc(c.name)}</a><small>${c.rule.groups.length} 个群 · ${taskDimensions[c.rule.dimension]} · ${taskFormats[c.output]}</small></td><td>${c.enabled?'':badge('已暂停')}<span>${esc(taskSchedule(c))}</span></td><td>${stamp(c.next_run)}</td><td>${c.last_run_id?`<a href="#runs/${c.last_run_id}">${taskStatus(c.last_status)}</a>`:taskStatus(null)}</td><td><div class="task-actions"><button class="text-button" data-task-run="${c.id}">运行</button><a class="text-link" href="#console/${c.id}">编辑</a><button class="text-button" data-task-toggle="${c.id}" data-enabled="${c.enabled}">${c.enabled?'暂停':'启用'}</button></div></td></tr>`).join('')}</tbody></table></div></section>`:`<section class="panel task-empty">${icon('clock')}<h2>把重复的统计交给任务</h2><p>选择群和资料范围，设置每天、每周或每月执行。<br>每次结果都会留在运行记录中。</p><a class="button primary" href="#console">创建第一个任务</a></section>`}`;
}

function taskResultRows(){
 const result=taskUI.run?.result;if(!result||!$('task-result-table'))return;
 const start=taskUI.rowPage*50,rows=result.rows.slice(start,start+50);
 $('task-result-table').innerHTML=`<div class="table-scroll"><table class="data-table task-report-table"><thead><tr>${result.columns.map(c=>`<th>${esc(c.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${result.columns.map(c=>`<td>${esc(c.key==='source'?(names[row[c.key]]||row[c.key]):c.key==='type'?(types[row[c.key]]||row[c.key]):row[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${!rows.length?empty('这个时间范围内没有匹配的记录','本次结果已保存，可调整规则后重新统计。'):''}<div class="task-group-pages"><span>表格共 ${n(result.rows.length)} 行${result.truncated?'（达到 2000 行上限）':''}</span><div><button class="button small" data-task-result-page="${taskUI.rowPage-1}" ${start===0?'disabled':''}>上一页</button><span>${taskUI.rowPage+1} / ${Math.max(1,Math.ceil(result.rows.length/50))}</span><button class="button small" data-task-result-page="${taskUI.rowPage+1}" ${start+50>=result.rows.length?'disabled':''}>下一页</button></div></div>`;
}
async function taskRunPage(r){
 const run=await api('task-runs/'+enc(r.source));taskUI.run=run;taskUI.rowPage=0;
 header(run.name,'每次执行独立留存，可查看规则、统计结果与原文依据',[['任务','#tasks'],['运行记录','#tasks/history'],['结果']]);
 const detail=`<section class="panel task-run-heading"><div>${taskStatus(run.status)}<span>${stamp(run.created_at)} · ${({console:'指令台',manual:'手动执行',scheduled:'定时执行'})[run.trigger]}</span></div><p>${esc(taskSummary(run.config))}</p><div class="task-actions">${run.task_id?`<a class="text-link" href="#tasks/${run.task_id}">查看任务 ${icon('arrow')}</a>`:''}<button class="text-button" id="task-reuse">使用此规则</button></div></section>`;
 if(!run.result)return detail+(run.status==='failed'?empty('统计未完成',run.error):run.status==='cancelled'?empty('本次运行已取消'):empty(run.status==='running'?'正在统计':'已加入执行队列','可以离开此页面，结果将保留在运行记录中。'));
 const result=run.result;
 return detail+`<div class="kpi-grid task-kpis"><div class="kpi"><div class="kpi-top">匹配消息</div><strong class="kpi-value">${n(result.totals.messages)}</strong><div class="kpi-foot">全量匹配统计</div></div><div class="kpi"><div class="kpi-top">有消息的群</div><strong class="kpi-value">${n(result.totals.active_groups)}<span class="unit">/ ${result.groups.length}</span></strong><div class="kpi-foot">本次选定群范围</div></div><div class="kpi"><div class="kpi-top">参与者</div><strong class="kpi-value">${n(result.totals.participants)}</strong><div class="kpi-foot">按来源与账号编号去重</div></div></div><section class="panel task-result"><div class="panel-heading"><h2>${taskDimensions[run.config.rule.dimension]}</h2><div class="task-actions">${Object.entries(taskFormats).map(([f,label])=>`<a class="button small" href="api/task-runs/${run.id}/export?format=${f}" download>${icon('download')}${label}</a>`).join('')}</div></div><div class="task-result-meta"><span>${esc(result.range.start)} ≤ 消息时间 &lt; ${esc(result.range.end_exclusive)}</span><span>索引更新 ${esc(result.indexed_at||'未知')}</span></div><div id="task-result-table"></div><p class="panel-note">${esc(result.notes)}${result.undated_excluded?` 所选范围另有 ${n(result.undated_excluded)} 条缺少时间的记录未参与统计。`:''}</p></section><section class="panel task-evidence"><details><summary>原文依据 <span>最近 ${result.evidence.length} 条匹配消息</span></summary><div>${result.evidence.map((m,i)=>`<article><div><strong>${esc(m.group_name)}</strong><span>${esc(m.sender)} · ${esc(m.sent_at)}</span></div><p>${esc(m.text.slice(0,250))}${m.text.length>250?'…':''}</p><button class="text-button" data-task-evidence="${i}">查看完整原文与引用 ${icon('arrow')}</button></article>`).join('')}</div></details></section>`;
}

function taskMount(r){
 clearTimeout(taskUI.poll);
 if(r.page==='console'){taskPreview();taskSearchGroups().catch(e=>toast(e.message));}
 if(r.page==='runs'){
  taskResultRows();if(['queued','running'].includes(taskUI.run?.status)){const hash=location.hash;taskUI.poll=setTimeout(()=>{if(location.hash===hash&&state.me)load();},2500);}
 }
}
function taskBind(){
 $('page-content').addEventListener('submit',async e=>{
  if(e.target.id!=='task-compose')return;e.preventDefault();const c=taskReadForm(),action=e.submitter?.value;
  $('task-compose-error').textContent='';
  if(!c.rule.groups.length){$('task-compose-error').textContent='请至少选择一个群。';return;}
  if(action==='save'&&!c.name.trim()){$('task-compose-error').textContent='为任务填写一个名称。';e.target.elements.name.focus();return;}
  const buttons=[...e.target.querySelectorAll('[type=submit]')];buttons.forEach(b=>b.disabled=true);
  try{
   if(action==='save'){const t=await api('tasks'+(taskUI.editId?'/'+enc(taskUI.editId):''),{},{method:taskUI.editId?'PUT':'POST',body:JSON.stringify(c)});taskUI.draft=null;location.hash='tasks/'+t.id;toast('任务已保存');}
   else{const run=await api('commands',{},{method:'POST',body:JSON.stringify({name:c.name.trim()||'即时统计',rule:c.rule,output:c.output})});location.hash='runs/'+run.id;}
  }catch(err){if($('task-compose-error'))$('task-compose-error').textContent=err.message;else toast(err.message);}finally{buttons.forEach(b=>b.disabled=false);}
 });
 $('page-content').addEventListener('input',e=>{
  if(e.target.closest('#task-compose'))taskPreview();
  if(e.target.id==='task-group-search'){clearTimeout(taskUI.searchTimer);taskUI.searchTimer=setTimeout(()=>taskSearchGroups().catch(e=>toast(e.message)),250);}
 });
 $('page-content').addEventListener('change',e=>{
  if(e.target.id==='task-source')taskSearchGroups().catch(e=>toast(e.message));
  if(e.target.dataset.taskGroup){
   const [source,id]=JSON.parse(e.target.dataset.taskGroup),c=taskUI.draft;
   if(e.target.checked){if(c.rule.groups.length>=50){e.target.checked=false;toast('一次最多选择 50 个群');return;}c.rule.groups.push({source,id});}
   else c.rule.groups=c.rule.groups.filter(g=>taskKey(g)!==e.target.dataset.taskGroup);
  }
  if(e.target.closest('#task-compose'))taskPreview();
 });
 $('page-content').addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  try{
   if(b.dataset.taskGroupPage!==undefined)await taskSearchGroups(Number(b.dataset.taskGroupPage));
   if(b.dataset.taskRemove){taskUI.draft.rule.groups=taskUI.draft.rule.groups.filter(g=>taskKey(g)!==b.dataset.taskRemove);taskPreview();document.querySelectorAll('[data-task-group]').forEach(x=>{if(x.dataset.taskGroup===b.dataset.taskRemove)x.checked=false;});}
   if(b.dataset.taskPreset){const f=$('task-compose'),preset=b.dataset.taskPreset;f.elements.dimension.value=preset==='files'?'records':preset==='daily'?'day':'group';f.elements.message_type.value=preset==='files'?'file':'';f.elements.days.value=preset==='daily'?1:7;f.elements.window.value='complete_days';f.elements.frequency.value=preset==='daily'?'daily':'weekly';taskPreview();}
   if(b.dataset.taskRun){b.disabled=true;const run=await api('tasks/'+b.dataset.taskRun+'/run',{},{method:'POST'});location.hash='runs/'+run.id;}
   if(b.dataset.taskToggle){b.disabled=true;await api('tasks/'+b.dataset.taskToggle+(b.dataset.enabled==='true'?'/pause':'/resume'),{},{method:'POST'});toast(b.dataset.enabled==='true'?'任务已暂停；已开始的统计会正常完成':'任务已启用');await load();}
   if(b.dataset.taskResultPage!==undefined){taskUI.rowPage=Number(b.dataset.taskResultPage);taskResultRows();}
   if(b.dataset.taskEvidence!==undefined){const m=taskUI.run.result.evidence[Number(b.dataset.taskEvidence)],raw=await api('message',{source:m.source,message_id:m.id});state.visibleMessages=[raw];messageDetails(0);}
   if(b.id==='task-reuse'){const c=taskUI.run.config;taskUI.draft={...taskDefault(),name:c.name||'',rule:structuredClone(c.rule),output:c.output};taskUI.editId=null;for(const g of taskUI.run.result?.groups||[])taskUI.groups.set(taskKey(g),{...g,display_name:g.name});location.hash='console';}
  }catch(err){toast(err.message);}finally{b.disabled=false;}
 });
 window.addEventListener('hashchange',()=>{clearTimeout(taskUI.poll);taskUI.searchEpoch++;});
}
