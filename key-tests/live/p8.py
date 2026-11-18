"""Proof: a running query whose worker died cannot be cancelled for about a minute (DELETE /api/jobs/<id> -> 500)."""
import sys, time, json, os
sys.path.insert(0, "/tools")
from rd import *
import redis
r = redis.from_url(os.environ["REDASH_REDIS_URL"])
step = sys.argv[1]
if step == "start":
    c = run("select pg_sleep(301), %d as dead_worker" % time.time()); jid = c[1]["job"]["id"]
    print("started:", wait(jid, statuses=(2,), timeout=30)[1]["job"]["status"] == 2); print("JOB", jid)
else:
    jid = sys.argv[2]
    ex = [x.decode() for x in r.zrange("rq:executions:" + jid, 0, -1)]
    print("  job status in redis:", r.hget("rq:job:" + jid, "status"), "| rq:executions:<job> =", ex,
          "| execution hashes present:", [bool(r.exists("rq:execution:%s:%s" % (jid, e))) for e in ex])
    print("  GET    /api/jobs/<id> ->", job(jid))
    print("  DELETE /api/jobs/<id> ->", cancel(jid))
    print("  GET    /api/jobs/<id> ->", job(jid))
