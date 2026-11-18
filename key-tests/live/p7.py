import sys, time, json, os
sys.path.insert(0, "/tools")
from rd import *
import redis
r = redis.from_url(os.environ["REDASH_REDIS_URL"])
def dump(jid):
    h = r.hgetall("rq:job:" + jid)
    return {k.decode(): v.decode() for k, v in h.items() if k in (b"status", b"started_at", b"ended_at")}, "ttl", r.ttl("rq:job:" + jid)
def regs():
    out = {}
    for k in sorted(r.keys("rq:*")):
        k = k.decode()
        if any(k.startswith(p) for p in ("rq:wip:", "rq:canceled:", "rq:failed:", "rq:queue:queries", "rq:finished:queries")):
            t = r.type(k).decode()
            out[k] = r.zcard(k) if t == "zset" else r.llen(k)
    return out
tag = int(time.time())
print("== cancel while queued behind a long query")
a = run("select pg_sleep(12), %d as blocker" % tag)[1]["job"]["id"]
print(wait(a, statuses=(2,), timeout=20)[1]["job"]["status"])
b = run("select %d as queued_one" % tag)[1]["job"]["id"]
print("b:", job(b)[1]["job"])
print("cancel b:", cancel(b), dump(b))
print("b after cancel:", job(b)[1]["job"])
print("rerun b ->", (b2 := run("select %d as queued_one" % tag)[1]["job"]["id"]), "same id" if b2 == b else "new job")
print("rerun b again ->", (b3 := run("select %d as queued_one" % tag)[1]["job"]["id"]), "shares b2" if b3 == b2 else "DUPLICATE of b2")
print("wait a:", wait(a, timeout=30)[1]["job"]["status"])
time.sleep(3)
print("b final:", job(b)[1]["job"], dump(b))
print("b2 final:", job(b2)[1]["job"]); print("b3 final:", job(b3)[1]["job"])
print(regs())
