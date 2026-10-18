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
  action_id: string;
  tool_name: "create_ticket";
  arguments: TicketArguments;
  arguments_hash: string;
  approval_status: "pending" | "approved" | "rejected";
  execution_status: "not_started" | "succeeded" | "failed" | "unknown";
  result: { ticket_id: string; created_at: string; replayed: boolean } | null;
  verification: { status: string };
}
export interface Report {
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
  schema_version: number;
  run_id: string;
  request: string;
  status:
    "queued" | "running" | "waiting_for_approval" | "completed" | "failed";
  mode: Mode;
  model_id: string | null;
  language: string;
  outcome: string | null;
  timeline: Step[];
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  missing_checks: string[];
  action: Action | null;
  report: Report | null;
  error: { code: string; message?: string } | null;
  created_at: string;
  updated_at: string;
  usage: {
    llm_calls: number;
    read_calls: number;
    active_ms: number;
    human_wait_ms: number;
  };
}
export type Decision = "approve" | "reject";
