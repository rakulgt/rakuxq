"""RakuInsight export contract tests. Original Raku code, MIT; synthetic SQLite only."""
import datetime,importlib.util,json,pathlib,sqlite3
spec=importlib.util.spec_from_file_location('ops_export',pathlib.Path(__file__).resolve().parents[3]/'scripts/export-ops-summary.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def test_summary_omits_every_raw_and_customer_field_and_counts_window(tmp_path):
    db=tmp_path/'metrics.sqlite3';now=datetime.datetime(2026,11,1,10,tzinfo=datetime.timezone.utc)
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE public_totals(singleton INTEGER,successful INTEGER,accepted INTEGER,review_required INTEGER,first_seen_at TEXT,last_seen_at TEXT)')
        c.execute("INSERT INTO public_totals VALUES(1,2,1,1,'2026-10-31T00:00:00Z','2026-11-01T09:00:00Z')")
        c.execute('CREATE TABLE public_events(occurred_at TEXT,status TEXT,duration_ms INTEGER,fen TEXT,source_id TEXT)')
        c.execute("INSERT INTO public_events VALUES('2026-11-01T09:00:00.000Z','accepted',300,'private-board','private-customer')")
        c.execute("INSERT INTO public_events VALUES('2026-10-31T01:00:00.000Z','review_required',500,'private-board','private-customer')")
    before=db.read_bytes();value=module.summary(db,now);text=json.dumps(value)
    assert value['windows']['1']['recorded']==1 and value['windows']['7']['recorded']==2
    assert value['windows']['7']['average_duration_ms']==400
    assert 'private-board' not in text and 'private-customer' not in text
    assert 'events' not in value and 'fen' not in value and 'source_id' not in value
    assert value['quality']['testTrafficSeparated'] is False
    assert value['sourceRetentionHours']==720 and db.read_bytes()==before
