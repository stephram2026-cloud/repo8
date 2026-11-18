"""Tiny API client used by the proof scripts (runs inside the app image)."""
import json, os, time
import requests

BASE = os.environ.get("RD_BASE", "http://server:5000")
KEY = os.environ["RD_KEY"]  # API key of an admin user in your lab database
H = {"Authorization": "Key " + KEY}


def call(method, path, **kw):
    r = requests.request(method, BASE + path, headers=H, timeout=180, **kw)
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]
    return r.status_code, body


def run(query, ds=1, max_age=0, **extra):
    payload = {"query": query, "data_source_id": ds, "max_age": max_age}
    payload.update(extra)
    return call("post", "/api/query_results", json=payload)


def job(job_id):
    return call("get", "/api/jobs/" + job_id)


def cancel(job_id):
    return call("delete", "/api/jobs/" + job_id)


def wait(job_id, statuses=(3, 4), timeout=60, show=False):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        code, body = job(job_id)
        if show and body != last:
            print("  [%5.1fs] %s %s" % (time.time() - t0, code, json.dumps(body)))
        last = body
        if code != 200 or body["job"]["status"] in statuses:
            return code, body
        time.sleep(0.5)
    return "timeout", last
