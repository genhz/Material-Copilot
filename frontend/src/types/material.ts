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

export type ChatAction = 'chat' | 'render' | 'generate'

export interface ChatResponse {
  reply: string
  action: ChatAction
  material_data?: MaterialData | null
  job_id?: string | null
  session_id?: string | null
}

export type GenerationStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface GenerationRequest {
  target_magnetic_density: number
  num_candidates?: number
  guidance_scale?: number
  seed?: number | null
}

export interface GenerationJob {
  job_id: string
  status: GenerationStatus
  progress: number
  model_id: string
  request: GenerationRequest
  error_code?: string | null
  error_message?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface GeneratedCandidate {
  candidate_id: string
  material_id: string
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
