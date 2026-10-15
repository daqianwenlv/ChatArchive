from __future__ import annotations
import collections, datetime as dt, json, logging, os, re
from zoneinfo import ZoneInfo
from pathlib import Path
from .database import read_db
from .media import media_path

TZ=ZoneInfo(os.environ.get('CHATARCHIVE_TIMEZONE','Asia/Shanghai'))
NAMES={'feishu':'飞书','wecom':'企业微信','wechat':'微信','dingtalk':'钉钉'}
STOP=set('我们 你们 他们 这个 那个 这些 那些 一个 一下 一些 已经 可以 需要 没有 还是 就是 什么 怎么 现在 今天 明天 昨天 收到 好的 谢谢 大家 然后 还有 这里 这样 时候 进行 因为 所以 如果 但是 不好意思 相关 图片 文件 视频 消息 撤回 系统 语音 链接 分享 文字 空内容 类型 内容 机器人'.split())

def iso(value):return dt.datetime.fromtimestamp(value/1000,TZ).isoformat(timespec='seconds') if value else None

def day_ms(value,end=False):
    if not value:return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('日期格式应为 YYYY-MM-DD')
    d=dt.date.fromisoformat(value)+(dt.timedelta(days=1) if end else dt.timedelta())
    return int(dt.datetime.combine(d,dt.time.min,TZ).timestamp()*1000)

def like(value):return '%'+value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'

class Queries:
    def __init__(self,path):self.path=path
    def filters(self,p,source=None,group_id=None,start=None,end=None,q=None,msg_type=None,alias='m'):
        where,args=p.sql_scope(alias)
        if source:
            if source not in NAMES:raise ValueError('无效数据源')
            where+=f' AND {alias}.source=?';args.append(source)
        if group_id:
            if not source:raise ValueError('指定群时必须指定数据源')
            where+=f' AND {alias}.group_id=?';args.append(group_id)
        if start:where+=f' AND {alias}.ts>=?';args.append(day_ms(start))
        if end:where+=f' AND {alias}.ts<?';args.append(day_ms(end,True))
        if start and end and start>end:raise ValueError('开始日期不能晚于结束日期')
        if q:
            if len(q)>160:raise ValueError('搜索词最多 160 字')
            where+=f" AND {alias}.text LIKE ? ESCAPE '\\'";args.append(like(q))
        if msg_type:where+=f' AND {alias}.type=?';args.append(msg_type)
        return where,args
    def source_list(self,p):
        p.require('groups:read')
        where,args=p.sql_scope('g')
        with read_db(self.path) as c:
            records={r['source']:dict(r) for r in c.execute(f'''SELECT source,SUM(message_count) messages,COUNT(CASE WHEN kind='group' THEN 1 END) groups,COUNT(CASE WHEN kind='private' THEN 1 END) private_conversations,COUNT(CASE WHEN message_count>0 AND kind='group' THEN 1 END) archived_groups,MAX(last_ts) last_ts FROM (SELECT *,id group_id FROM groups) g WHERE {where} GROUP BY source''',args)}
            src=[]
            for r in c.execute('SELECT * FROM sources'):
                if r['source'] not in p.sources:continue
                item=dict(r);item['details']=json.loads(item['details']) if p.groups is None else {}
                item.update(records.get(r['source'],{'messages':0,'groups':0,'private_conversations':0,'archived_groups':0,'last_ts':None}));item['last_message_at']=iso(item.pop('last_ts'));src.append(item)
            meta=dict(c.execute('SELECT key,value FROM metadata'))
        return {'sources':src,'indexed_at':meta.get('indexed_at'),'timezone':str(TZ)}
    def catalog(self):
        path=Path(self.path).parent/'catalog.sqlite3'
        return path if path.is_file() else None
    def labelled(self,where):
        """Group rows joined with their number, primary category and tags when a catalogue exists."""
        if self.catalog():
            return f'''(SELECT g0.*,g0.id group_id,l.seq,l.category_id,c.name category,l.tags,l.origin label_origin,l.locked label_locked FROM groups g0
                LEFT JOIN cat.group_labels l ON l.source=g0.source AND l.group_id=g0.id LEFT JOIN cat.categories c ON c.id=l.category_id) g WHERE {where}'''
        return f"(SELECT *,id group_id,NULL seq,NULL category_id,NULL category,'[]' tags,'' label_origin,0 label_locked FROM groups) g WHERE {where}"
    def groups(self,p,source=None,q='',kind='group',status='all',limit=30,offset=0,category=''):
        p.require('groups:read'); limit=max(1,min(int(limit),100));offset=max(0,min(int(offset),100000))
        where,args=p.sql_scope('g')
        if source:
            if source not in NAMES:raise ValueError('无效数据源')
            where+=' AND g.source=?';args.append(source)
        if kind not in ('group','private','all'):raise ValueError('无效会话类型')
        if kind!='all':where+=' AND g.kind=?';args.append(kind)
        if q:
            if len(q)>160:raise ValueError('搜索词过长')
            number=q.lstrip('#＃')
            where+=" AND (g.name LIKE ? ESCAPE '\\' OR g.id LIKE ? ESCAPE '\\' OR g.category LIKE ? ESCAPE '\\' OR g.tags LIKE ? ESCAPE '\\'"+(" OR g.seq=?" if number.isdigit() else '')+')'
            args.extend([like(q)]*4+([int(number)] if number.isdigit() else []))
        if category=='none':where+=' AND g.category_id IS NULL'
        elif category:
            if not category.isdigit():raise ValueError('无效分类')
            where+=' AND g.category_id=?';args.append(int(category))
        if status=='archived':where+=' AND g.message_count>0'
        elif status=='uncovered':where+=' AND g.message_count=0'
        elif status!='all':raise ValueError('无效归档状态')
        base=self.labelled(where);catalog=self.catalog()
        with read_db(self.path,{'cat':catalog} if catalog else None) as c:
            total=c.execute('SELECT COUNT(*) FROM '+base,args).fetchone()[0]
            rows=c.execute('SELECT * FROM '+base+' ORDER BY (last_ts IS NULL),last_ts DESC,source,id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
            categories=[dict(r) for r in c.execute('SELECT id,name FROM cat.categories ORDER BY position,id')] if catalog else []
        return {'items':[self.group_row(r) for r in rows],'total':total,'offset':offset,'limit':limit,'has_more':offset+len(rows)<total,'categories':categories}
    @staticmethod
    def group_row(r):
        d=dict(r);d.pop('group_id',None);d['tags']=json.loads(d.get('tags') or '[]');d['label_locked']=bool(d.get('label_locked'));d['display_name']=d['name'] or d['id'];d['first_message_at']=iso(d.pop('first_ts'));d['last_message_at']=iso(d.pop('last_ts'));return d
    def group(self,p,source,group_id):
        p.require('groups:read');where,args=self.filters(p,source,group_id,alias='g')
        catalog=self.catalog()
        with read_db(self.path,{'cat':catalog} if catalog else None) as c:r=c.execute('SELECT * FROM '+self.labelled(where),args).fetchone()
        if r is None:raise LookupError('群不存在或不在授权范围内')
        return self.group_row(r)
    @staticmethod
    def message_row(r):
        d=dict(r);d.pop('raw',None);d['sent_at']=iso(d.pop('ts'));d['media_available']=bool(d.get('media_sha256'));d['display_name']=d['group_name'] or d['group_id'];d['sender']=d['sender_name'] or d['sender_id'] or '未知发送者';d['deleted']=bool(d['deleted']);return d
    def messages(self,p,source=None,group_id=None,q='',msg_type=None,start=None,end=None,limit=50,offset=0):
        p.require('messages:read');limit=max(1,min(int(limit),100));offset=max(0,min(int(offset),1000000))
        where,args=self.filters(p,source,group_id,start,end,q,msg_type)
        with read_db(self.path) as c:
            total=c.execute(f'SELECT COUNT(*) FROM messages m WHERE {where}',args).fetchone()[0]
            rows=c.execute(f'''SELECT m.*,g.name group_name FROM messages m JOIN groups g ON g.source=m.source AND g.id=m.group_id WHERE {where} ORDER BY (m.ts IS NULL),m.ts DESC,m.source,m.id DESC LIMIT ? OFFSET ?''',args+[limit,offset]).fetchall()
        return {'items':[self.message_row(r) for r in rows],'total':total,'offset':offset,'limit':limit,'has_more':offset+len(rows)<total}
    def message(self,p,source,message_id):
        p.require('messages:read');where,args=self.filters(p,source)
        with read_db(self.path) as c:
            r=c.execute(f'''SELECT m.*,g.name group_name FROM messages m JOIN groups g ON g.source=m.source AND g.id=m.group_id WHERE {where} AND m.id=?''',args+[message_id]).fetchone()
            if r is None:raise LookupError('记录不存在或不在授权范围内')
            item=self.message_row(r)
            try:item['raw']=json.loads(r['raw']) if 'raw' in r.keys() else {}
            except ValueError:item['raw']={}
            # The quoted message, when it is also archived and within the same scope.
            parent=c.execute(f'''SELECT m.id,m.ts,m.sender_id,m.sender_name,m.type,m.text,m.deleted FROM messages m WHERE {where} AND m.id=?''',args+[r['parent_id']]).fetchone() if r['parent_id'] else None
        item['parent']={'id':parent['id'],'sent_at':iso(parent['ts']),'sender':parent['sender_name'] or parent['sender_id'] or '未知发送者','type':parent['type'],'text':parent['text'][:2000],'deleted':bool(parent['deleted'])} if parent else None
        return item
    def media(self,p,source,message_id):
        item=self.message(p,source,message_id)
        if not item.get('media_sha256'):raise LookupError('该消息没有已归档的附件')
        path=media_path(Path(self.path).parent/'media',item['media_sha256'])
        if not path.is_file():raise LookupError('附件文件缺失，请运行 doctor 检查')
        return path,item['media_name'] or item['media_sha256'],item['media_mime']
    def analysis(self,p,source=None,group_id=None,start=None,end=None):
        p.require('analysis:read');where,args=self.filters(p,source,group_id,start,end)
        with read_db(self.path) as c:
            c.create_function('local_day',1,lambda ts:dt.datetime.fromtimestamp(ts/1000,TZ).date().isoformat() if ts else None)
            c.create_function('local_hour',1,lambda ts:dt.datetime.fromtimestamp(ts/1000,TZ).hour if ts else None)
            totals=dict(c.execute(f'''SELECT COUNT(*) messages,COUNT(DISTINCT source||':'||group_id) conversations,COUNT(DISTINCT CASE WHEN sender_id!='' THEN source||':'||sender_id END) participants,COUNT(DISTINCT local_day(ts)) active_days,MIN(ts) first_ts,MAX(ts) last_ts,SUM(CASE WHEN ts IS NULL THEN 1 ELSE 0 END) undated,SUM(deleted) revoked FROM messages m WHERE {where}''',args).fetchone())
            days=[dict(r) for r in c.execute(f'SELECT local_day(ts) day,COUNT(*) count FROM messages m WHERE {where} AND ts IS NOT NULL GROUP BY day ORDER BY day',args)]
            types=[dict(r) for r in c.execute(f'SELECT type,COUNT(*) count FROM messages m WHERE {where} GROUP BY type ORDER BY count DESC',args)]
            hours=[dict(r) for r in c.execute(f'SELECT local_hour(ts) hour,COUNT(*) count FROM messages m WHERE {where} AND ts IS NOT NULL GROUP BY hour ORDER BY hour',args)]
            # A sender ID is the identity; names are presentation only and never used to merge people.
            people=[dict(r) for r in c.execute(f'''SELECT source,sender_id,MAX(sender_name) name,COUNT(*) count,MAX(ts) last_ts FROM messages m WHERE {where} AND sender_id!='' GROUP BY source,sender_id ORDER BY count DESC LIMIT 15''',args)]
            sample=[dict(r) for r in c.execute(f'''SELECT id,source,text,ts FROM messages m WHERE {where} AND type IN ('text','post','mixed') AND text!='' ORDER BY ts DESC,id DESC LIMIT 3000''',args)] if 'messages:read' in p.permissions or p.admin else []
        totals['first_message_at']=iso(totals.pop('first_ts'));totals['last_message_at']=iso(totals.pop('last_ts'));totals['undated']=totals['undated'] or 0;totals['revoked']=totals['revoked'] or 0
        for person in people:person['last_message_at']=iso(person.pop('last_ts'));person['name']=person['name'] or person['sender_id']
        words=collections.Counter(); evidence={}
        if sample:
            import jieba
            jieba.setLogLevel(logging.ERROR)
            for row in sample:
                text=re.sub(r'https?://\S+|\b(?:ou_|oc_|wm|wr)\w+|@[^\s]+',' ',row['text'][:5000])
                terms=set(w for w in jieba.cut(text) if 2<=len(w)<=12 and w not in STOP and not w.isdigit() and re.fullmatch(r'[\u4e00-\u9fffA-Za-z]+',w))
                words.update(terms)
                for w in terms:
                    if w not in evidence:evidence[w]={'source':row['source'],'message_id':row['id']}
        return {'totals':totals,'days':days,'hours':hours,'types':types,'participants':people,'keywords':[{'word':w,'messages':v,'evidence':evidence[w]} for w,v in words.most_common(16)],'keyword_sample':len(sample),'keyword_method':'最近 3000 条以内文本，按包含词语的消息数统计','timezone':str(TZ),'range':{'start':start,'end':end},'analysis_kind':'descriptive_statistics'}
