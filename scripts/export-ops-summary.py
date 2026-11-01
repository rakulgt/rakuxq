#!/usr/bin/env python3
"""Server-only aggregate export for RakuInsight, version 1.
Input: read-only public metrics SQLite. Output: whitelisted counts/timing, never event rows.
Source: original Raku implementation, MIT; production adapter, no model/engine changes.
"""
import argparse,datetime,json,os,pathlib,sqlite3,tempfile
def summary(database,now=None):
    now=now or datetime.datetime.now(datetime.timezone.utc)
    current=now.isoformat(timespec='milliseconds').replace('+00:00','Z')
    with sqlite3.connect(pathlib.Path(database).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        connection.row_factory=sqlite3.Row
        totals=connection.execute('SELECT successful,accepted,review_required,first_seen_at,last_seen_at FROM public_totals WHERE singleton=1').fetchone()
        windows={}
        for days in [1,7,30]:
            cutoff=(now-datetime.timedelta(days=days)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            row=connection.execute("SELECT count(*) AS recorded,sum(status='accepted') AS accepted,sum(status='review_required') AS review_required,avg(duration_ms) AS average_duration_ms FROM public_events WHERE occurred_at>=? AND occurred_at<=?",(cutoff,current)).fetchone()
            windows[str(days)]={k:round(float(row[k] or 0),1) if k=='average_duration_ms' else int(row[k] or 0) for k in row.keys()}
        cutoff=(now-datetime.timedelta(days=30)).isoformat(timespec='milliseconds').replace('+00:00','Z')
        daily=connection.execute("SELECT substr(datetime(occurred_at,'+8 hours'),1,10) AS day,count(*) AS recorded FROM public_events WHERE occurred_at>=? AND occurred_at<=? GROUP BY day ORDER BY day",(cutoff,current)).fetchall()
    return {'schemaVersion':1,'source':'rakuxq-public-metrics-aggregate','generatedAt':current,'timezone':'Asia/Shanghai','windowMode':'rolling-last-n-days','sourceRetentionHours':720,'sourceMaxRows':100000,'lifetime':dict(totals) if totals else {},'windows':windows,'daily':[dict(r) for r in daily],'quality':{'scope':'A production recorded FEN-producing interactions only; B experiment excluded by original source','testTrafficSeparated':False,'rejectedAndNetworkFailuresIncluded':False,'statement':'accepted 是技术接受状态，不是识别准确率；分母仅含原统计已记录的交互，不能计算全请求成功率。测试及内部流量尚未独立分离。'},'rawEventsExported':False}
def write_summary(database,output):
    value=summary(database);target=pathlib.Path(output);fd,tmp=tempfile.mkstemp(prefix='.ops-summary-',dir=target.parent)
    try:
        os.fchmod(fd,0o640)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,target)
    finally:pathlib.Path(tmp).unlink(missing_ok=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    try:write_summary(args.database,args.output);print('RakuXQ aggregate export complete; no event rows or identifiers exported.')
    except Exception as error:print('RakuXQ aggregate export failed: '+type(error).__name__);raise SystemExit(1)
