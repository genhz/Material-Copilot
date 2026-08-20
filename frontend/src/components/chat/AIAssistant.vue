<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { ChatDotRound, Close, Position, Loading } from '@element-plus/icons-vue'
import { useAIChat } from '../../composables/useAIChat'
import type { MaterialData } from '../../types/material'

const emit = defineEmits<{
  materialFound: [data: MaterialData, action: 'chat' | 'render']
}>()

const { messages, isChatting, sendMessage, clearChat } = useAIChat()
const chatVisible = ref(false)
const inputMessage = ref('')
const chatContainerRef = ref<HTMLElement | null>(null)

const handleSend = async () => {
  const text = inputMessage.value.trim()
  if (!text || isChatting.value) return
  inputMessage.value = ''

  const result = await sendMessage(text)
  if (result.materialData) {
    emit('materialFound', result.materialData, result.action)
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

watch(messages, async () => {
  await nextTick()
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}, { deep: true })
</script>

<template>
  <Teleport to="body">
    <!-- Chat Panel -->
    <Transition name="chat-slide">
      <div
        v-if="chatVisible"
        class="chat-panel"
      >
        <!-- Header -->
        <div class="chat-header">
          <div class="chat-header-title">
            <el-icon :size="18" color="#818cf8"><ChatDotRound /></el-icon>
            <span>AI 材料助手</span>
          </div>
          <div class="chat-header-actions">
            <el-button
              text
              size="small"
              class="clear-btn"
              @click="clearChat"
            >
              清除
            </el-button>
            <el-button
              text
              size="small"
              class="close-btn"
              @click="chatVisible = false"
            >
              <el-icon :size="16"><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- Messages -->
        <div ref="chatContainerRef" class="chat-messages">
          <div v-if="messages.length === 0" class="chat-welcome">
            <div class="welcome-icon">🤖</div>
            <p class="welcome-title">你好，我是 AI 材料助手</p>
            <p class="welcome-desc">输入材料化学式或提出问题</p>
            <div class="welcome-suggestions">
              <span
                v-for="s in ['Nd2Fe14B', 'Fe3O4', 'LiCoO2']"
                :key="s"
                class="suggestion-chip"
                @click="inputMessage = s"
              >
                {{ s }}
              </span>
            </div>
          </div>

          <div
            v-for="msg in messages"
            :key="msg.id"
            :class="['message', msg.role === 'user' ? 'message-user' : 'message-ai']"
          >
            <div
              v-if="msg.role !== 'user'"
              class="message-avatar"
            >
              🤖
            </div>
            <div class="message-bubble">
              <p class="message-content">{{ msg.content }}</p>
            </div>
          </div>

          <div v-if="isChatting" class="message message-ai">
            <div class="message-avatar">🤖</div>
            <div class="message-bubble message-bubble-loading">
              <el-icon class="is-loading" :size="18" color="#818cf8">
                <Loading />
              </el-icon>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="chat-input-area">
          <el-input
            v-model="inputMessage"
            placeholder="输入消息，按 Enter 发送..."
            :autosize="{ minRows: 1, maxRows: 4 }"
            type="textarea"
            resize="none"
            class="chat-input"
            @keydown="handleKeydown"
          />
          <el-button
            type="primary"
            :icon="Position"
            :disabled="isChatting || !inputMessage.trim()"
            circle
            class="send-btn"
            @click="handleSend"
          />
        </div>
      </div>
    </Transition>

    <!-- Floating Action Button -->
    <div
      class="ai-fab"
      :class="{ 'fab-active': chatVisible }"
      @click="chatVisible = !chatVisible"
    >
      <div class="fab-ring"></div>
      <div class="fab-icon">
        <el-icon :size="26" color="white">
          <ChatDotRound v-if="!chatVisible" />
          <Close v-else />
        </el-icon>
      </div>
      <div class="fab-tooltip">AI 助手</div>
    </div>
  </Teleport>
</template>

<style scoped>
.ai-fab {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 50;
  cursor: pointer;
}

.fab-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6, #a78bfa);
  opacity: 0.5;
  animation: fab-pulse 2s ease-in-out infinite;
}

.fab-icon {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s;
}

.fab-icon:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 28px rgba(99, 102, 241, 0.5);
}

.fab-icon:active {
  transform: scale(0.95);
}

.fab-active .fab-icon {
  background: linear-gradient(135deg, #475569, #334155);
}

.fab-tooltip {
  position: absolute;
  right: 68px;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(15, 23, 42, 0.9);
  color: #e2e8f0;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  backdrop-filter: blur(8px);
}

.ai-fab:hover .fab-tooltip {
  opacity: 1;
}

@keyframes fab-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.3;
  }
  50% {
    transform: scale(1.15);
    opacity: 0.1;
  }
}

.chat-panel {
  position: fixed;
  bottom: 100px;
  right: 32px;
  width: 400px;
  height: 560px;
  z-index: 50;
  background: rgba(15, 23, 42, 0.92);
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
  border-radius: 20px;
  border: 1px solid rgba(99, 102, 241, 0.2);
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 14px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.15);
}

.chat-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e2e8f0;
  font-size: 15px;
  font-weight: 600;
}

.chat-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.clear-btn,
.close-btn {
  color: #94a3b8;
}

.clear-btn:hover,
.close-btn:hover {
  color: #f1f5f9;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-messages::-webkit-scrollbar {
  width: 4px;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.3);
  border-radius: 4px;
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 0;
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.welcome-title {
  color: #e2e8f0;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.welcome-desc {
  color: #64748b;
  font-size: 13px;
  margin-bottom: 20px;
}

.welcome-suggestions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.suggestion-chip {
  padding: 6px 14px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 20px;
  color: #a5b4fc;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.suggestion-chip:hover {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.4);
  color: #c7d2fe;
}

.message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.message-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.6;
}

.message-ai .message-bubble {
  background: rgba(51, 65, 85, 0.5);
  color: #cbd5e1;
  border-bottom-left-radius: 4px;
}

.message-user .message-bubble {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-bubble-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
}

.chat-input-area {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid rgba(99, 102, 241, 0.15);
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-textarea__inner) {
  background: rgba(51, 65, 85, 0.4);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #e2e8f0;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
  resize: none;
  transition: border-color 0.2s;
}

.chat-input :deep(.el-textarea__inner:focus) {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.chat-input :deep(.el-textarea__inner::placeholder) {
  color: #64748b;
}

.send-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
}

.send-btn:disabled {
  background: rgba(51, 65, 85, 0.4);
}

.chat-slide-enter-active,
.chat-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-slide-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

.chat-slide-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}
</style>
