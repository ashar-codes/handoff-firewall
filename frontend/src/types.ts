export type User = {
  id: string;
  tenant_id: string;
  name: string;
  email: string;
  role: string;
  active: boolean;
};
export type Rule = {
  id: string;
  label: string;
  fields: string[];
  mandatory: boolean;
  condition: { field: string; equals: string } | null;
  review: boolean;
  owner_id: string | null;
  depends_on: string[];
  expected: string | null;
  description: string;
  precedence: string;
};
export type Template = {
  id: string;
  name: string;
  source: string;
  destination: string;
  version: number;
  rules: Rule[];
  rule_hash: string;
};
export type Status = {
  state: string;
  reason: string;
  facts: string[];
  rule_version?: number;
};
export type Handoff = {
  id: string;
  title: string;
  business_key: string;
  source: string;
  destination: string;
  workflow_name: string;
  owner_id: string;
  template_id: string;
  goal: string;
  state: string;
  revision: number;
  readiness: number;
  created_at: number;
  updated_at: number;
  sample: boolean;
  error: string | null;
  statuses: Record<string, Status>;
  context: Record<string, string>;
};
export type DocumentRecord = {
  id: string;
  name: string;
  sha256: string;
  version: number;
  active: boolean;
  text: string;
  parse_error: string | null;
  created_at: number;
};
export type Fact = {
  id: string;
  requirement_id: string;
  document_id: string | null;
  value: string;
  field: string;
  quote: string;
  location: string;
  source_hash: string;
  source_version: number;
  method: string;
  accepted: boolean;
  supersedes: string[];
  accepted_by: string | null;
};
export type Action = {
  id: string;
  case_id: string;
  kind: string;
  owner_id: string;
  status: string;
  reason: string;
  effort: number;
  approval_required: boolean;
  fingerprint: string;
  created_at: number;
  payload: {
    requirements: string[];
    message: string;
    recipient: string;
    connector: string;
    candidate_facts: string[];
    evidence?: {
      id: string;
      value: string;
      quote: string;
      location: string;
      source_version: number;
      source_hash: string;
    }[];
    fields: Record<string, string[]>;
  };
  snapshot: unknown;
  prerequisites: string[];
  result?: { answered_requirements?: string[]; effect?: string } | null;
};
export type AuditEvent = {
  id: string;
  case_id: string | null;
  seq: number;
  kind: string;
  agent: string | null;
  summary: string;
  created_at: number;
  data: { target?: string; [key: string]: unknown };
};
export type Detail = Handoff & {
  template: Template;
  documents: DocumentRecord[];
  facts: Fact[];
  actions: Action[];
  events: AuditEvent[];
  conflicts: {
    id: string;
    requirement_id: string;
    facts: string[];
    explanation: string;
    expected_value: string | null;
  }[];
  jobs: { id: string; status: string }[];
};
