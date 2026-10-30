"""Native TLS/authorization/redaction probe. Only synthetic metadata is submitted."""
import argparse
import asyncio
import json
import os
import ssl
import time
from pathlib import Path
from uuid import uuid4

import httpx
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from opspilot.config import Settings
from opspilot.observability.protocol import attributes
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.auth_helpers import session_client

SENTINEL = "F16_SENTINEL_PRIVATE_PASSWORD_COOKIE_SQL_PROMPT_749e5a"
ROOT = Path("/run/observability-probe")
REPORT = Path("/reports")
TENANT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

def context(root=ROOT, certificate=True, trusted=True):
    ctx = ssl.create_default_context(cafile=str(root / "ca.crt") if trusted else None)
    if certificate:
        ctx.load_cert_chain(root / "client.crt", root / "client.key")
    return ctx

def client(root=ROOT):
    return httpx.Client(verify=context(root), trust_env=False, timeout=4,
        headers={"Authorization": "Bearer " + (root / "token").read_text().strip()})

def native():
    results={}
    for name,ctx,url in (
        ("missing_client_certificate",context(certificate=False),"https://collector:4318"),
        ("untrusted_server_ca",context(trusted=False),"https://collector:4318"),
        ("hostname_mismatch",context(),"https://collector-wrong:4318"),
    ):
        try:
            with httpx.Client(verify=ctx,trust_env=False,timeout=3) as c:
                c.get(url+"/internal/events",params={"tenant":TENANT})
        except httpx.TransportError:
            results[name]=True
        else:
            raise AssertionError(name)
    with client() as c:
        base="https://collector:4318"
        path=base+"/internal/events"
        assert c.get(path,params={"tenant":TENANT},headers={"Authorization":"Bearer "+"0"*64}).status_code==403
        results["invalid_bearer_rejected"]=True
        with client(Path("/run/observability-worker")) as worker:
            assert worker.get(path,params={"tenant":TENANT}).status_code==403
        results["write_identity_cannot_read"]=True
        invalid=c.get(path,params={"tenant":SENTINEL})
        assert invalid.status_code==400 and SENTINEL not in invalid.text
        assert c.post(base+"/v1/traces",content=b"x"*262145,headers={"Content-Type":"application/x-protobuf"}).status_code==413
        assert c.post(base+"/v1/traces",content=SENTINEL).status_code==415
        results["body_media_query_bounds"]=True
        run,actor=str(uuid4()),str(uuid4())
        import base64
        trace=base64.b64encode(uuid4().bytes).decode()
        span=base64.b64encode(uuid4().bytes[:8]).decode()
        safe={"run_id":run,"tenant_id":TENANT,"actor_id":actor,"job_id":str(uuid4()),"worker_epoch":7}
        attrs=attributes({**safe,"password":SENTINEL,"prompt":SENTINEL,"sql":SENTINEL,"event":"log.error"})
        resource={"attributes":attributes({"service.name":SENTINEL,"secret":SENTINEL})}
        payloads={
          "traces":ParseDict({"resourceSpans":[{"resource":resource,"scopeSpans":[{"spans":[{
            "traceId":trace,"spanId":span,"name":"command.process","startTimeUnixNano":str(time.time_ns()-40000000000),
            "endTimeUnixNano":str(time.time_ns()-35000000000),"attributes":attrs,
            "status":{"code":2,"message":SENTINEL},"events":[{"name":SENTINEL}]}]}]}]},ExportTraceServiceRequest()),
          "logs":ParseDict({"resourceLogs":[{"resource":resource,"scopeLogs":[{"logRecords":[{
            "traceId":trace,"spanId":span,"timeUnixNano":str(time.time_ns()),"body":{"stringValue":SENTINEL},
            "attributes":attrs,"severityNumber":17}]}]}]},ExportLogsServiceRequest()),
          "metrics":ParseDict({"resourceMetrics":[{"resource":resource,"scopeMetrics":[{"metrics":[{
            "name":"opspilot.upstream_errors","description":SENTINEL,"gauge":{"dataPoints":[{
            "asDouble":3,"timeUnixNano":str(time.time_ns()),"attributes":attributes({"phase":"mcp","tenant_id":TENANT,"password":SENTINEL})}]}}]}]}]},ExportMetricsServiceRequest())
        }
        for kind,message in payloads.items():
            r=c.post(base+"/v1/"+kind,content=message.SerializeToString(),
                headers={"Content-Type":"application/x-protobuf","X-Request-Secret":SENTINEL})
            assert r.status_code==200,(kind,r.status_code)
        response=c.get(path,params={"tenant":TENANT,"run":run}).json()
        assert response["integrity"]=="verified"
        assert len(response["events"])==2
        assert any(e.get("source_clock_skew") for e in response["events"])
        assert any(e["name"]=="log.error" for e in response["events"])
        assert SENTINEL not in json.dumps(response)
        points=response["services"]["opspilot-probe"]["metrics"][0]["points"]
        assert points==[{"value":3.0,"labels":{"phase":"mcp"}}]
        results.update(native_mtls=True,ingress_redaction=True,metrics_positive_schema=True,
            source_clock_warning=True,protected_read=True,synthetic_records=2)
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/"collector-native.json").write_text(json.dumps({"passed":True,"checks":results},indent=2))
    print(json.dumps({"passed":True,"checks":len(results)}))

async def availability(mode):
    async with httpx.AsyncClient(base_url=os.environ["TEST_API_URL"],timeout=5) as c:
        await session_client(c,Settings())
        r=await c.get("/api/v2/diagnostics")
        assert r.status_code==200
        data=r.json()
        codes={a["code"] for a in data["alerts"]}
        if mode=="outage":
            assert not data["collector"]["available"]
            assert "COLLECTOR_UNAVAILABLE" in codes
            # Authoritative admission and queued state work with collector unavailable.
            r=await c.post("/api/v2/runs",json={"request":"Status GreenShop","client_request_id":str(uuid4())})
            assert r.status_code==202
            snap=await c.get(r.json()["snapshot_url"])
            assert snap.status_code==200 and snap.json()["status"]=="queued"
            assert data["exporter"]["queued_logs"]<=256
        elif mode=="tampered":
            assert not data["collector"]["available"]
            assert "COLLECTOR_INTEGRITY_FAILED" in codes
        else:
            assert data["collector"]["available"] and data["collector"]["integrity"]=="verified"
        REPORT.mkdir(parents=True,exist_ok=True)
        (REPORT/("collector-"+mode+".json")).write_text(json.dumps({"passed":True,"mode":mode,
            "collector_available":data["collector"]["available"],"alert_codes":sorted(codes)},indent=2))
        print(json.dumps({"passed":True,"mode":mode}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["native","outage","tampered","recovered"],default="native")
    args=p.parse_args()
    if args.mode=="native":native()
    else:asyncio.run(availability(args.mode))
