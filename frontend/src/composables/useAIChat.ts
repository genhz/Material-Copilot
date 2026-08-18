/**
 * AI 对话 Composable
 * 管理 AI 助手的会话状态
 */
import { ref } from 'vue'
import type { ChatMessage, MaterialData } from '../types/material'
import { chatAI } from '../api/material'

const messages = ref<ChatMessage[]>([])
const sessionId = ref<string | null>(null)
const isChatting = ref(false)

let messageIdCounter = 0

export function useAIChat() {
  /**
   * 发送消息
   */
  async function sendMessage(text: string): Promise<MaterialData | null> {
    const trimmed = text.trim()
    if (!trimmed || isChatting.value) return null

    // 添加用户消息
    messages.value.push({
      id: messageIdCounter++,
      role: 'user',
      content: trimmed,
    })

    isChatting.value = true

    try {
      const response = await chatAI({
        message: trimmed,
        session_id: sessionId.value,
      })

      // 更新会话 ID
      if (response.session_id) {
        sessionId.value = response.session_id
        localStorage.setItem('material_sandbox_session_id', response.session_id)
      }

      const materialData = response.material_data || null

      // 添加助手回复
      messages.value.push({
        id: messageIdCounter++,
        role: 'assistant',
        content: response.reply || '抱歉，我没有收到回复。',
        materialData,
      })

      return materialData
    } catch (error: any) {
      messages.value.push({
        id: messageIdCounter++,
        role: 'assistant',
        content: `请求失败：${error.message || '未知错误'}`,
      })
      return null
    } finally {
      isChatting.value = false
    }
  }

  /**
   * 清除会话
   */
  function clearChat() {
    sessionId.value = null
    localStorage.removeItem('material_sandbox_session_id')
    messages.value = []
    messageIdCounter = 0
  }

  /**
   * 初始化会话 ID
   */
  function initSession() {
    const stored = localStorage.getItem('material_sandbox_session_id')
    if (stored) {
      sessionId.value = stored
    }
  }

  initSession()

  return {
    messages,
    sessionId,
    isChatting,
    sendMessage,
    clearChat,
  }
}
