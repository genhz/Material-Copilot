import type { MaterialData } from './material'

export type PlanStatus =
  | 'awaiting_confirmation'
  | 'confirmed'
  | 'executing'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'cancelled'

export type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export interface PlanObjective {
  property: string
  operator: string
  target: number
  kind: 'hard' | 'soft'
}

export interface PlanStep {
  id: string
  kind: 'generate' | 'filter' | 'rank'
  title: string
  description: string
  status: StepStatus
  model_id?: string | null
  conditions: Record<string, unknown>
  num_candidates?: number | null
  guidance_scale?: number | null
  seed?: number | null
  job_id?: string | null
  progress: number
  error_message?: string | null
}

export interface ExecutionPlan {
  plan_id: string
  session_id: string
  revision: number
  status: PlanStatus
  original_message: string
  summary: string
  assumptions: string[]
  questions: string[]
  request_spec: {
    goal: string
    material_type?: string | null
    required_elements: string[]
    allowed_elements: string[]
    excluded_elements: string[]
    chemical_system?: string | null
    objectives: PlanObjective[]
  }
  steps: PlanStep[]
}

export interface WorkflowRunState {
  workflow_id: string
  plan_id: string
  session_id: string
  status:
    | 'queued'
    | 'running'
    | 'completed'
    | 'partial'
    | 'failed'
    | 'cancelled'
  progress: number
  current_step_id?: string | null
  job_ids: string[]
  candidate_count: number
  error_message?: string | null
}

export interface AgentResultEvent {
  message: string
  action?: string
  material_data?: MaterialData | null
  job_id?: string | null
  campaign_id?: string | null
  plan_id?: string | null
}
