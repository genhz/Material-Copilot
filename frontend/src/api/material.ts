/**
 * 材料 API 请求层
 */
import axios from 'axios'
import type {
  CampaignCandidateCollection,
  CampaignJob,
  CandidateCollection,
  ChatRequest,
  ChatResponse,
  GenerationJob,
  GenerationRequest,
  MatterGenModelInfo,
  MaterialData,
} from '../types/material'

const api = axios.create({
  baseURL: '', // 使用 Vite 代理
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

// 添加请求拦截器，方便调试
api.interceptors.request.use((config) => {
  console.log('[API Request]', config.method?.toUpperCase(), config.url, config.params)
  return config
})

api.interceptors.response.use(
  (response) => {
    console.log('[API Response OK]', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('[API Error]', error.message, error.config?.url)
    return Promise.reject(error)
  }
)

/**
 * 直接搜索材料（通过化学式查询）
 * 直接调用 Materials Project API，不经过大模型
 */
export async function searchMaterial(formula: string): Promise<MaterialData> {
  const resp = await api.get<MaterialData>('/api/material/search', {
    params: { formula: formula.trim() },
  })
  return resp.data
}

/**
 * AI 对话请求
 */
export async function chatAI(request: ChatRequest): Promise<ChatResponse> {
  const resp = await api.post<ChatResponse>('/api/chat', request)
  return resp.data
}

/**
 * 清除会话
 */
export async function clearSession(sessionId: string): Promise<void> {
  await api.post('/api/chat/clear', null, { params: { session_id: sessionId } })
}

/**
 * 创建 MatterGen 磁性材料生成任务
 */
export async function createGenerationJob(
  request: GenerationRequest
): Promise<GenerationJob> {
  const resp = await api.post<GenerationJob>('/api/generation/jobs', request)
  return resp.data
}

/**
 * 查询生成任务状态
 */
export async function getGenerationJob(jobId: string): Promise<GenerationJob> {
  const resp = await api.get<GenerationJob>(
    `/api/generation/jobs/${encodeURIComponent(jobId)}`
  )
  return resp.data
}

/**
 * 获取已完成任务的候选结构
 */
export async function getGenerationCandidates(
  jobId: string
): Promise<CandidateCollection> {
  const resp = await api.get<CandidateCollection>(
    `/api/generation/jobs/${encodeURIComponent(jobId)}/candidates`
  )
  return resp.data
}

/**
 * 取消生成任务
 */
export async function cancelGenerationJob(jobId: string): Promise<GenerationJob> {
  const resp = await api.post<GenerationJob>(
    `/api/generation/jobs/${encodeURIComponent(jobId)}/cancel`
  )
  return resp.data
}

export async function getGenerationModels(): Promise<MatterGenModelInfo[]> {
  const resp = await api.get<MatterGenModelInfo[]>('/api/generation/models')
  return resp.data
}

export async function createGenerationCampaign(payload: {
  name: string
  runs: Array<{
    model_id: string
    conditions: Record<string, unknown>
    num_candidates: number
    guidance_scale?: number
    seed?: number | null
  }>
  max_concurrency?: number
}): Promise<CampaignJob> {
  const resp = await api.post<CampaignJob>(
    '/api/generation/campaigns',
    payload
  )
  return resp.data
}

export async function getGenerationCampaign(
  campaignId: string
): Promise<CampaignJob> {
  const resp = await api.get<CampaignJob>(
    `/api/generation/campaigns/${encodeURIComponent(campaignId)}`
  )
  return resp.data
}

export async function getCampaignCandidates(
  campaignId: string
): Promise<CampaignCandidateCollection> {
  const resp = await api.get<CampaignCandidateCollection>(
    `/api/generation/campaigns/${encodeURIComponent(campaignId)}/candidates`
  )
  return resp.data
}

export async function cancelGenerationCampaign(
  campaignId: string
): Promise<CampaignJob> {
  const resp = await api.post<CampaignJob>(
    `/api/generation/campaigns/${encodeURIComponent(campaignId)}/cancel`
  )
  return resp.data
}
