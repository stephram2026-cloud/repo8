import sys, time, json, os
sys.path.insert(0, "/tools")
from rd import *
import redis
r = redis.from_url(os.environ["REDASH_REDIS_URL"])
def dump(jid):
    h = r.hgetall("rq:job:" + jid)
    return {k.decode(): v.decode() for k, v in h.items() if k in (b"status", b"started_at", b"ended_at", b"timeout")}, "ttl", r.ttl("rq:job:" + jid)
which = sys.argv[1]
if which == "soft":
    print("== soft time limit (6s) on pg_sleep(40)")
    c = run("select pg_sleep(40), 3 as c"); jid = c[1]["job"]["id"]
    print(wait(jid, timeout=60, show=True)); print(dump(jid))
    print("lock:", r.keys("query_hash_job:*"))
if which == "start":
    c = run("select pg_sleep(%s), 4 as d" % sys.argv[2]); jid = c[1]["job"]["id"]
    print(wait(jid, statuses=(2,), timeout=20)); print("JOB", jid)
if which == "watch":
    jid = sys.argv[2]
    print(wait(jid, timeout=int(sys.argv[3]), show=True)); print(dump(jid))
    print("locks:", {k: r.get(k) for k in r.keys("query_hash_job:*")})
    print("rerun:", (c := run("select pg_sleep(%s), 4 as d" % sys.argv[4]))); 
    print("rq_status queues:", json.dumps(call("get", "/api/admin/queries/rq_status")[1]))
