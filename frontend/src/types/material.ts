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
  // Extended properties (may be present in API response)
  density?: number | null
  spacegroup?: SpaceGroupInfo | null
  crystal_system?: string | null
  formula_unit?: number | null
  magnetic_ordering?: string | null
  elements?: string[]
  pretty_formula?: string
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

export interface ChatResponse {
  reply: string
  material_data?: MaterialData | null
  session_id?: string | null
}
