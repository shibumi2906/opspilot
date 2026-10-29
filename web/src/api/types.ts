export type Mode = "scripted" | "real";
export interface PublicConfig {
  mode: Mode;
  model_id: string | null;
  synthetic: boolean;
  scenario_clock: string;
  timezone: string;
}
export interface Evidence {
  evidence_id: string;
  tool_name: string;
  observed_at: string;
  source_type: string;
  source_id: string;
  source_version: string | null;
  excerpt: string;
  facts: Record<string, unknown>;
}
export interface Hypothesis {
  hypothesis_id: string;
  summary: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  confidence_label: string;
  missing_checks: string[];
}
export interface TicketArguments {
  customer_id: string;
  title: string;
  description: string;
  priority: string;
  evidence_ids: string[];
}
export interface Action {
  preconditions?: {
    configuration?: string;
    unavailable?: string;
    integrations: {id: string; type: string; project_fingerprint: string}[];
    observations: {integration: string; status: string; credential: string}[];
  };
  wave?: number;
  key?: string;
  plan_status?: string;
  action_id: string;
  tool_name: "create_ticket" | "add_ticket_comment" | "notify_manager";
  arguments: TicketArguments | {
    customer_id: string;
    body: string;
    evidence_ids: string[];
    ticket_id?: string;
    recipient_id?: string;
  };
  arguments_hash: string;
  expected_version: number;
  logical_action_id: string;
  revision_hash: string;
  expires_at: string;
  approval_status: "pending" | "approved" | "rejected" | "expired" | "revoked" | "superseded";
  execution_status: "not_started" | "succeeded" | "failed" | "unknown" | "skipped_dependency";
  result: { ticket_id?: string; comment_id?: string; notification_id?: string; created_at: string; replayed: boolean } | null;
  verification: { status: string };
}
export interface Report {
  effects?: {action_id:string|null;key?:string;tool_name?:string;status:string;approval_status?:string;verification_status?:string;wave?:number}[];
  summary: string;
  facts: { statement: string; evidence_ids: string[] }[];
  hypotheses: Hypothesis[];
  missing_checks: string[];
  action_summary: string;
  ticket_id: string | null;
  verification_status: string;
  remaining_problem: string;
  outcome: string;
}
export interface Step {
  id: string;
  sequence: number;
  node: string;
  type: string;
  status: string;
  summary: string;
  started_at: string | null;
  duration_ms?: number | null;
}
export interface RunSnapshot {
  dto_version: number;
  snapshot_version: number;
  latest_event_id?: string;
  traces?: { label: string; url: string }[];
  schema_version: number;
  run_id: string;
  request: string;
  status:
    | "queued"
    | "running"
    | "waiting_for_input"
    | "waiting_for_approval"
    | "cancelling"
    | "cancelled"
    | "completed"
    | "failed"
    | "needs_attention";
  clarification?: {
    id: string;
    version: number;
    kind: "customer" | "integration" | "timezone";
    expires_at: string;
    options: { id: string; label: string }[];
    answered: boolean;
  } | null;
  cancellation?: { requested_at: string } | null;
  mode: Mode;
  model_id: string | null;
  language: string;
  outcome: string | null;
  timeline: Step[];
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  missing_checks: string[];
  plan?: {plan_id:string;version:number;hash:string;wave:number;nodes:{slot_id:string;key:string;tool_name:string;status:string;dependencies:string[];wave:number;action_id:string|null}[]} | null;
  actions?: Action[];
  action: Action | null;
  report: Report | null;
  error: { code: string; message?: string } | null;
  created_at: string;
  updated_at: string;
  usage: {
    llm_calls: number;
    read_calls: number;
    input_tokens: number | null;
    output_tokens: number | null;
    active_ms: number;
    human_wait_ms: number;
  };
}
export type Decision = "approve" | "reject";
