import datetime as dt,json,sqlite3
from pathlib import Path
import pytest
from chatarchive.database import SCHEMA,finalize
from chatarchive.importer import insert
from chatarchive.security import Principal

@pytest.fixture
def archive(tmp_path):
    c=sqlite3.connect(tmp_path/'archive.sqlite3');c.executescript(SCHEMA)
    for source,name in [('feishu','飞书'),('wecom','企业微信'),('wechat','微信'),('dingtalk','钉钉')]:
        c.execute('INSERT INTO sources VALUES(?,?,?,?,?,?)',(source,name,'continuous','2026-10-11T00:00:00Z','ok','{}'))
    for source,gid,name in [('feishu','g1','产品讨论'),('feishu','g2','受限群'),('wecom','wr001',''),('feishu','g3','未归档群')]:
        insert(c,{'kind':'group','source':source,'id':gid,'name':name,'connection':'Y1'})
    base=int(dt.datetime(2026,10,10,15,59,tzinfo=dt.timezone.utc).timestamp()*1000)
    for index,(source,gid,text,sid) in enumerate([('feishu','g1','发布版本，完成测试','u1'),('feishu','g1','发布计划 100% 完成','u2'),('feishu','g2','私密数据不应越权','u3'),('wecom','wr001','企微消息','wm001')]):
        insert(c,{'kind':'message','source':source,'id':'m'+str(index),'group_id':gid,'ts':base+index*60000,'sender_id':sid,'sender_name':'同名成员','type':'text','text':text})
    insert(c,{'kind':'message','source':'wecom','id':'undated','group_id':'wr001','ts':None,'text':'缺少时间','type':'unknown'})
    c.execute('INSERT INTO metadata VALUES(?,?)',('indexed_at','2026-10-11T00:00:00Z'));finalize(c);c.close();return tmp_path

@pytest.fixture
def owner():return Principal('owner',admin=True)

@pytest.fixture
def restricted():return Principal('reader',sources=('feishu',),groups=('feishu:g1',))
