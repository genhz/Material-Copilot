/**
 * 材料数据相关类型定义
 */

export interface SpaceGroupInfo {
  symbol: string
  number: number
}

export interface MaterialData {
  formula: string
  material_id: string
  band_gap: number | null
  is_magnetic: boolean | null
  formation_energy: number | null
  cif: string
  // Extended properties from backend
  density?: number | null
  spacegroup_symbol?: string | null
  spacegroup_number?: number | null
  crystal_system?: string | null
  formula_unit?: number | null
  magnetic_ordering?: string | null
  elements?: string[] | null
  pretty_formula?: string | null
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'ai'
  content: string
  materialData?: MaterialData | null
}

export interface ChatRequest {
  message: string
  session_id?: string | null
}

export type ChatAction = 'chat' | 'render' | 'generate' | 'campaign'

export interface ChatResponse {
  reply: string
  action: ChatAction
  material_data?: MaterialData | null
  job_id?: string | null
  campaign_id?: string | null
  session_id?: string | null
}

export interface ModelCondition {
  name: string
  type: 'float' | 'int' | 'string'
  required: boolean
  default: number | string | null
  description: string
  minimum?: number | null
  maximum?: number | null
  options: string[]
}

export interface MatterGenModelInfo {
  model_id: string
  display_name: string
  description: string
  category: string
  available: boolean
  conditions: Record<string, ModelCondition>
  missing_reason?: string | null
  download_url?: string | null
}

export type GenerationStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type GenerationPhase =
  | 'queued'
  | 'loading_model'
  | 'generating'
  | 'postprocessing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface GenerationRequest {
  model_id?: string | null
  conditions: Record<string, number | string>
  target_magnetic_density?: number | null
  hhi_score?: number | null
  num_candidates?: number
  guidance_scale?: number
  seed?: number | null
}

export interface GenerationJob {
  job_id: string
  status: GenerationStatus
  phase: GenerationPhase
  progress: number
  message?: string | null
  sequence: number
  model_id: string
  model_label?: string | null
  request: GenerationRequest
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface GeneratedCandidate {
  candidate_id: string
  material_id: string
  model_id: string
  model_label: string
  formula: string
  pretty_formula: string
  cif: string
  density?: number | null
  formula_unit?: number | null
  elements: string[]
  source: 'mattergen'
  generation_conditions: Record<string, unknown>
  validation: Record<string, unknown>
  spacegroup_symbol?: string | null
  spacegroup_number?: number | null
  crystal_system?: string | null
}

export interface CandidateCollection {
  candidates: GeneratedCandidate[]
  invalid_count: number
  total_count: number
  validation: Record<string, unknown>
}

export type CampaignStatus =
  | 'queued'
  | 'running'
  | 'partial'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface CampaignRunState {
  run_id: string
  model_id: string
  model_label: string
  conditions: Record<string, unknown>
  job_id?: string | null
  status: GenerationStatus
  progress: number
  error_message?: string | null
}

export interface CampaignJob {
  campaign_id: string
  name: string
  status: CampaignStatus
  progress: number
  runs: CampaignRunState[]
  created_at: string
  updated_at: string
  completed_at?: string | null
}

export interface CampaignCandidateGroup {
  model_id: string
  model_label: string
  conditions: Record<string, unknown>
  candidates: GeneratedCandidate[]
}

export interface CampaignCandidateCollection {
  campaign_id: string
  groups: CampaignCandidateGroup[]
  candidates: GeneratedCandidate[]
  total_count: number
}
