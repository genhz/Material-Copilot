/**
 * 材料 API 请求层
 */
import axios from 'axios'
import type { MaterialData, ChatRequest, ChatResponse } from '../types/material'

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
