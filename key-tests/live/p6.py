import sys, time, json, os, threading
sys.path.insert(0, "/tools")
from rd import *
dss = call("get", "/api/data_sources")[1]
sink = [d for d in dss if d["name"] == "sink"]
if sink:
    ds_id = sink[0]["id"]
else:
    code, ds = call("post", "/api/data_sources", json={"name": "sink", "type": "pg", "options": {"host": "sink", "dbname": "x", "user": "u"}})
    ds_id = ds["id"]
print("DS", ds_id)
t0 = time.time()
print("test sink ds (no interference):" if len(sys.argv) < 2 else "test sink ds:", call("post", "/api/data_sources/%d/test" % ds_id), "%.1fs" % (time.time() - t0))
