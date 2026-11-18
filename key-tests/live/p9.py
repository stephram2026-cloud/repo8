"""Proof: "Test Connection" answers success for a data source that cannot be reached, when the driver's
error object cannot be pickled (Exasol: pyexasol.ExaConnectionFailedError; e6data: grpc _InactiveRpcError)."""
import sys, time
sys.path.insert(0, "/tools")
from rd import *
for name, typ, opts in [
    ("pg-unreachable", "pg", {"host": "127.0.0.1", "port": 1, "dbname": "x", "user": "u"}),
    ("exasol-unreachable", "exasol", {"host": "127.0.0.1", "port": 1, "user": "u", "password": "p"}),
]:
    dss = {d["name"]: d["id"] for d in call("get", "/api/data_sources")[1]}
    if name not in dss:
        code, ds = call("post", "/api/data_sources", json={"name": name, "type": typ, "options": opts})
        assert code == 200, (code, ds)
        dss[name] = ds["id"]
    print("%-20s POST /api/data_sources/%d/test ->" % (name, dss[name]), call("post", "/api/data_sources/%d/test" % dss[name]))
