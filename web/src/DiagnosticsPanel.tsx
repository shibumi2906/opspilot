import {useEffect,useState} from "react";
import {useIdentity} from "./AuthGate";
type Job = {id:string;run_id:string;kind:string;status:string;attempts:number;claim_epoch:number|null;error_code:string|null;traceparent:string|null};
type TraceEvent = {sequence:number;service:string;kind:string;name:string;trace_id?:string;span_id?:string;links?:{trace_id:string;span_id:string}[];attributes:Record<string,string|number>};
type Diagnostics = {
 database:{waiting_age_seconds:number;active_seconds:number;queue_latency_seconds:number;queue_age_seconds:number;queued_runs:number;active_runs:number;waiting_runs:number;expired_leases:number;lease_churn:number;unknown_operations:number;auth_denials_60s:number;exhausted_budgets:number;jobs:Job[]};
 collector:{available:boolean;reason?:string;integrity?:string;events?:TraceEvent[];retention_pruned?:number;retention_seconds?:number};
 retained_metrics:{record_count:number;upstream_errors:number;llm_attempts:number;mcp_calls:number;window:string};
 alerts:{code:string;severity:string;observed:number|boolean;threshold:number}[];
};
export function DiagnosticsPanel(){
 const identity=useIdentity();
 const [run,setRun]=useState(new URLSearchParams(location.search).get("run_id")||"");
 const [selected,setSelected]=useState(run);
 const [data,setData]=useState<Diagnostics|null>(null);
 const [error,setError]=useState("");
 const [nonce,setNonce]=useState(0);
 useEffect(()=>{
   const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
   const load=async()=>{
     try{
       const path=selected?"/api/v2/runs/"+encodeURIComponent(selected)+"/diagnostics":"/api/v2/diagnostics";
       const response=await fetch(path,{cache:"no-store",signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)])});
       if(!response.ok)throw new Error(response.status===404?"No authorized diagnostics for this run.":"Diagnostics unavailable.");
       const next=await response.json() as Diagnostics;
       if(!controller.signal.aborted){setData(next);setError("");}
     }catch(e){if(!controller.signal.aborted){setData(null);setError(e instanceof Error?e.message:"Diagnostics unavailable.");}}
     if(!controller.signal.aborted)timer=setTimeout(()=>void load(),5000);
   };
   setData(null);void load();
   return()=>{controller.abort();clearTimeout(timer);};
 },[selected,nonce,identity?.tenant_id]);
 return <section aria-label="Operator diagnostics" className="panel" data-testid="diagnostics">
   <h2>Operator diagnostics</h2>
   <p>Current tenant · saved command state and protected telemetry</p>
   <form onSubmit={e=>{e.preventDefault();setSelected(run.trim());setNonce(n=>n+1);}}>
     <label>Run ID<input aria-label="Diagnostic run ID" value={run} onChange={e=>setRun(e.target.value)} placeholder="All authorized runs" pattern="[0-9a-fA-F-]{36}" /></label>
     <button type="submit">Refresh diagnostics</button>
     <button type="button" onClick={()=>{setRun("");setSelected("");setNonce(n=>n+1);}}>Tenant overview</button>
   </form>
   {error&&<p role="alert">{error}</p>}
   {!data&&!error&&<p role="status">Loading diagnostics…</p>}
   {data&&<>
     <dl className="usage-grid">
       <dt>Queued / active / waiting</dt><dd>{data.database.queued_runs} / {data.database.active_runs} / {data.database.waiting_runs}</dd>
       <dt>Oldest eligible queue age</dt><dd>{Math.round(data.database.queue_age_seconds)} seconds</dd>
       <dt>Active time / current wait age / mean initial queue latency</dt><dd>{Math.round(data.database.active_seconds)} / {Math.round(data.database.waiting_age_seconds)} / {Math.round(data.database.queue_latency_seconds)} seconds</dd>
       <dt>Expired leases / lease churn</dt><dd>{data.database.expired_leases} / {data.database.lease_churn}</dd>
       <dt>Unknown operations / exhausted budgets</dt><dd>{data.database.unknown_operations} / {data.database.exhausted_budgets}</dd>
       <dt>Authentication denials in last minute</dt><dd>{data.database.auth_denials_60s}</dd>
       <dt>Retained upstream errors / LLM attempts / MCP calls</dt><dd>{data.retained_metrics.upstream_errors} / {data.retained_metrics.llm_attempts} / {data.retained_metrics.mcp_calls}<br/>{data.retained_metrics.window}</dd>
       <dt>Telemetry</dt><dd data-testid="collector-status">{data.collector.available?"Available · integrity "+data.collector.integrity:"Unavailable · "+data.collector.reason}</dd>
       <dt>Retained telemetry</dt><dd>{data.collector.retention_seconds??"unknown"} seconds; pruned {data.collector.retention_pruned??"unknown"}</dd>
     </dl>
     <h3>Alert conditions</h3>
     {data.alerts.length?<ul>{data.alerts.map((a,i)=><li key={i}><strong>{a.code}</strong> · {a.severity} · observed {String(a.observed)} / threshold {a.threshold}</li>)}</ul>:<p>No current alert condition.</p>}
     <h3>Commands and ownership</h3>
     <div style={{overflowX:"auto"}}><table><thead><tr><th>Run / command</th><th>State</th><th>Attempt / epoch</th><th>Reason</th><th>Trace context</th></tr></thead>
       <tbody>{data.database.jobs.map(j=><tr key={j.id}><td>{j.run_id}<br/>{j.id}</td><td>{j.kind} · {j.status}</td><td>{j.attempts} / {j.claim_epoch??"unclaimed"}</td><td>{j.error_code??"—"}</td><td>{j.traceparent??"Legacy or unavailable"}</td></tr>)}</tbody></table></div>
     <h3>Trace and diagnostic records</h3>
     <p>Metadata only. Missing records may reflect retention or exporter outage.</p>
     <ul>{(data.collector.events??[]).slice(0,100).map(e=><li key={e.sequence}><strong>{e.name}</strong> · {e.service} · {e.kind}<br/>
       {e.trace_id&&<>Trace {e.trace_id} · span {e.span_id??"—"}<br/></>}
       {e.attributes.job_id&&<>Command {e.attributes.job_id} · epoch {e.attributes.worker_epoch??"—"}<br/></>}
       {!!e.links?.length&&<>Linked traces: {e.links.map(l=>l.trace_id).join(", ")}</>}
     </li>)}</ul>
   </>}
 </section>;
}
