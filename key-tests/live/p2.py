import sys, time, json, os
sys.path.insert(0, "/tools")
from rd import *
import redis
r = redis.from_url(os.environ["REDASH_REDIS_URL"])
def dump(jid):
    h = r.hgetall("rq:job:" + jid)
    return {k.decode(): (v.decode() if k in (b"status", b"started_at", b"ended_at", b"worker_name") else "...") for k, v in h.items() if k in (b"status", b"started_at", b"ended_at")}, "ttl", r.ttl("rq:job:" + jid)

print("== A: cancel a running query")
c = run("select pg_sleep(30), 1 as a"); jid = c[1]["job"]["id"]; print(c)
print(wait(jid, statuses=(2,), timeout=20))
t0 = time.time()
print("cancel:", cancel(jid), dump(jid))
print("after cancel:", job(jid))
print("cancel again:", cancel(jid))
print("rerun same query right away:", (c2 := run("select pg_sleep(30), 1 as a")))
time.sleep(8)
print("8s later:", job(jid), dump(jid))
print("rq_status:", json.dumps(call("get", "/api/admin/queries/rq_status")[1]["queues"]))
jid2 = c2[1]["job"]["id"]
print("job2 == job1?", jid2 == jid, job(jid2))
print("cancel job2:", cancel(jid2)); time.sleep(7); print(job(jid2), dump(jid2))
print("pg activity:", run("select count(*) from pg_stat_activity where query like '%pg_sleep(30)%' and state='active' and query not like '%pg_stat_activity%'", max_age=0)[1])

print("== B: cancel a finished query")
c = run("select 2 as b"); jid = c[1]["job"]["id"]; print(wait(jid))
print("cancel finished:", cancel(jid)); print(job(jid), dump(jid))
print("rerun:", (c := run("select 2 as b"))); print(wait(c[1]["job"]["id"]))
