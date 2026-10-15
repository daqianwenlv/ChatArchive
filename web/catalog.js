'use strict';
// Group catalogue: numbers, one primary category plus tags, AI proposals and classification jobs.
const catalogUI={data:null,draft:null,timer:null,job:null,label:null};
const originNames={rule:'群名规则',ai:'AI 判断',manual:'手工设置'};
const words=value=>[...new Set(String(value||'').split(/[,，、\s]+/).map(x=>x.trim()).filter(Boolean))];
function catalogCell(g){
 if(g.seq==null)return '<span class="muted-copy">—</span>';
 return `${g.category?`<span class="category-chip">${esc(g.category)}</span>`:'<span class="category-chip none">未分类</span>'}${g.label_locked?'<span class="lock-mark" title="手工锁定，自动归类不会修改">锁</span>':''}${g.tags.length?`<small class="tag-list">${g.tags.map(t=>`<span>${esc(t)}</span>`).join('')}</small>`:''}`;
}
function categoryFilter(data,f){
 if(!data.categories?.length)return '';
 return `<select name="category" aria-label="分类筛选"><option value="">全部分类</option>${data.categories.map(c=>`<option value="${c.id}" ${String(f.category)===String(c.id)?'selected':''}>${esc(c.name)}</option>`).join('')}<option value="none" ${f.category==='none'?'selected':''}>未分类</option></select>`;
}
async function groupLabelBlock(g){
 if(g.seq==null)return '';
 let label=null;try{label=await api('catalog/group',{source:g.source,group_id:g.id});}catch{return '';}
 state.labelEvidence=label.evidence;
 const confidence=label.confidence!=null?` · 把握 ${Math.round(label.confidence*100)}%`:'';
 return `<section class="panel group-label"><div class="label-main"><span class="seq-number">#${label.seq}</span>${label.category?`<span class="category-chip">${esc(label.category)}</span>`:'<span class="category-chip none">未分类</span>'}${label.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}${state.me?.admin?`<button class="button" data-edit-label>调整分类</button>`:''}</div>${label.origin?`<p class="label-reason">${originNames[label.origin]||esc(label.origin)}${confidence}${label.locked?' · 已锁定':''}${label.reason?' · '+esc(label.reason):''}</p>`:'<p class="label-reason">尚未归类</p>'}${label.evidence.length?`<div class="label-evidence">依据消息 ${label.evidence.map((id,i)=>`<button class="text-button" data-label-evidence="${i}">${i+1}</button>`).join('')}</div>`:''}</section>`;
}
async function openCatalog(){
 $('catalog-error').textContent='';
 catalogUI.data=await api('catalog');
 catalogUI.draft=catalogUI.data.categories.map(c=>({id:c.id,name:c.name,description:c.description,keywords:c.keywords,groups:c.groups}));
 catalogUI.fromProposal=false;renderCatalog();$('catalog-dialog').showModal();
 if(catalogUI.data.job?.status==='running')watchJob(catalogUI.data.job.id);
}
function renderCatalog(){
 const d=catalogUI.data,s=d.stats,job=catalogUI.job||d.job,running=job?.status==='running';
 $('catalog-stats').innerHTML=`<span>已编号 <b>${n(s.numbered)}</b></span><span>已归类 <b>${n(s.classified)}</b></span><span>手工锁定 <b>${n(s.locked)}</b></span><span>待归类 <b>${n(s.pending)}</b></span><span class="${d.ai.ready?'':'warn-text'}">${d.ai.ready?'AI：'+esc(d.ai.model):'尚未配置 AI'}</span>`;
 $('catalog-job').innerHTML=!job?'':running?`<div class="job-line">${job.kind==='propose'?'正在分析群聊、生成分类建议':'正在归类'}… ${job.total?`${n(job.done)} / ${n(job.total)}`:''}<i class="job-bar"><i style="width:${job.total?Math.round(job.done/job.total*100):5}%"></i></i></div>`:job.status==='failed'?`<p class="form-error">上次${job.kind==='propose'?'生成建议':'归类'}未完成：${esc(job.error)}</p>`:job.kind==='classify'&&job.result?`<p class="panel-note flush">上次归类处理 ${n(job.result.processed)} 个群${job.result.notes?.length?'；'+job.result.notes.map(esc).join('；'):''}</p>`:'';
 const rows=catalogUI.draft;
 $('catalog-list').innerHTML=rows.length?rows.map((c,i)=>`<div class="category-row" data-row="${i}"><div class="category-fields"><input class="text-input" data-field="name" value="${esc(c.name)}" maxlength="20" placeholder="分类名称" aria-label="分类名称"><input class="text-input" data-field="keywords" value="${esc(c.keywords.join('、'))}" placeholder="识别词，用顿号分隔" aria-label="识别词"><input class="text-input wide" data-field="description" value="${esc(c.description)}" maxlength="200" placeholder="说明" aria-label="说明"></div><div class="category-meta">${c.groups!=null?`<span>${n(c.groups)} 个群</span>`:''}${c.examples?.length?`<small>例：${c.examples.map(g=>`${g.seq?'#'+g.seq+' ':''}${esc(g.name)}`).join('，')}</small>`:''}<button class="text-button danger-text" data-remove="${i}">删除</button></div></div>`).join(''):`<div class="empty-state">${icon('file')}<strong>还没有分类</strong><p>${d.ai.ready?'点击「生成分类建议」，AI 会阅读群名和消息摘录，提出一套大类供你修改确认。':'配置 AI 后可生成建议，也可以手动添加分类。'}</p></div>`;
 $('catalog-propose').disabled=running||!d.ai.ready;
 $('catalog-save').disabled=running;$('catalog-save').textContent=catalogUI.fromProposal?'确认分类并开始归类':'保存分类';
 $('catalog-classify-new').disabled=$('catalog-classify-all').disabled=running||!d.categories.length||catalogUI.fromProposal;
}
function readDraft(){
 document.querySelectorAll('#catalog-list .category-row').forEach(row=>{const c=catalogUI.draft[Number(row.dataset.row)];row.querySelectorAll('[data-field]').forEach(input=>{c[input.dataset.field]=input.dataset.field==='keywords'?words(input.value):input.value.trim();});});
}
async function watchJob(id){
 clearTimeout(catalogUI.timer);
 try{catalogUI.job=await api('catalog/jobs/'+id);}catch(e){$('catalog-error').textContent=e.message;return;}
 const job=catalogUI.job;
 if(job.status==='running'){renderCatalog();if($('catalog-dialog').open)catalogUI.timer=setTimeout(()=>watchJob(id),2000);return;}
 catalogUI.data=await api('catalog');
 if(job.status==='succeeded'&&job.kind==='propose'){
  const existing=Object.fromEntries(catalogUI.data.categories.map(c=>[c.name,c.id]));
  catalogUI.draft=job.result.categories.map(c=>({id:existing[c.name]??null,name:c.name,description:c.description,keywords:c.keywords,groups:c.group_count,examples:c.examples}));
  catalogUI.fromProposal=true;toast('已生成 '+catalogUI.draft.length+' 个分类建议，请检查后确认');
 }
 if(job.status==='succeeded'&&job.kind==='classify'){toast('归类完成');load();}
 renderCatalog();
}
async function startJob(path,body){
 $('catalog-error').textContent='';
 try{const job=await api(path,{}, {method:'POST',body:JSON.stringify(body||{})});catalogUI.job=job;renderCatalog();watchJob(job.id);}catch(e){$('catalog-error').textContent=e.message;}
}
async function saveCatalog(){
 readDraft();$('catalog-error').textContent='';
 const categories=catalogUI.draft.filter(c=>c.name).map(c=>({id:c.id,name:c.name,description:c.description,keywords:c.keywords}));
 if(!categories.length){$('catalog-error').textContent='至少保留一个分类';return;}
 const removed=catalogUI.data.categories.filter(c=>!categories.some(x=>x.id===c.id)&&c.groups);
 if(removed.length&&!confirm(`删除的分类中有 ${removed.reduce((v,c)=>v+c.groups,0)} 个群，这些群会变为未分类（包括手工设置的）。继续？`))return;
 try{
  const fromProposal=catalogUI.fromProposal;await api('catalog/categories',{}, {method:'PUT',body:JSON.stringify({categories})});
  catalogUI.data=await api('catalog');catalogUI.draft=catalogUI.data.categories.map(c=>({id:c.id,name:c.name,description:c.description,keywords:c.keywords,groups:c.groups}));catalogUI.fromProposal=false;
  toast('分类已保存');renderCatalog();load();
  if(fromProposal)startJob('catalog/classify',{mode:'all'});
 }catch(e){$('catalog-error').textContent=e.message;}
}
async function openLabel(){
 const g=state.currentGroup;if(!g)return;$('label-error').textContent='';
 try{
  const [cat,label]=await Promise.all([api('catalog'),api('catalog/group',{source:g.source,group_id:g.id})]);
  $('label-title').textContent=`调整分类 · #${label.seq} ${g.display_name}`;
  $('label-category').innerHTML=`<option value="">未分类</option>${cat.categories.map(c=>`<option value="${c.id}" ${c.id===label.category_id?'selected':''}>${esc(c.name)}</option>`).join('')}`;
  $('label-tags').value=label.tags.join('、');$('label-locked').checked=true;$('label-dialog').showModal();
 }catch(e){toast(e.message);}
}
$('page-content').addEventListener('click',async e=>{const t=e.target.closest('button');if(!t)return;
 if(t.id==='open-catalog')openCatalog().catch(err=>toast(err.message));
 if(t.dataset.editLabel!==undefined)openLabel();
 if(t.dataset.labelEvidence!==undefined){const g=state.currentGroup;try{state.visibleMessages=[await api('message',{source:g.source,message_id:state.labelEvidence[Number(t.dataset.labelEvidence)]})];messageDetails(0);}catch(err){toast(err.message);}}
});
$('catalog-propose').onclick=()=>{if(catalogUI.data.categories.length&&!confirm('生成的新建议会替换下方列表（保存前不会生效）。继续？'))return;startJob('catalog/proposals');};
$('catalog-add').onclick=()=>{readDraft();catalogUI.draft.push({id:null,name:'',description:'',keywords:[]});renderCatalog();$('catalog-list').querySelector('.category-row:last-child input')?.focus();};
$('catalog-list').addEventListener('click',e=>{const b=e.target.closest('[data-remove]');if(!b)return;readDraft();catalogUI.draft.splice(Number(b.dataset.remove),1);renderCatalog();});
$('catalog-save').onclick=saveCatalog;
$('catalog-classify-new').onclick=()=>startJob('catalog/classify',{mode:'new'});
$('catalog-classify-all').onclick=()=>{if(confirm('重新判断所有未锁定的群？手工锁定的群保持不变。'))startJob('catalog/classify',{mode:'all'});};
$('catalog-dialog').addEventListener('close',()=>clearTimeout(catalogUI.timer));
$('label-form').addEventListener('submit',async e=>{e.preventDefault();const g=state.currentGroup;$('label-error').textContent='';
 try{const value=$('label-category').value;await api('catalog/group',{}, {method:'PUT',body:JSON.stringify({source:g.source,group_id:g.id,category_id:value?Number(value):null,tags:words($('label-tags').value),locked:$('label-locked').checked})});$('label-dialog').close();toast('分类已更新');load();}
 catch(err){$('label-error').textContent=err.message;}
});
