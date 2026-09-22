<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { ChatDotRound, Close, Position, Loading } from '@element-plus/icons-vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useAIChat } from '../../composables/useAIChat'
import type { MaterialData } from '../../types/material'

const emit = defineEmits<{
  materialFound: [data: MaterialData, action: 'chat' | 'render']
  generationStarted: [jobId: string]
  campaignStarted: [campaignId: string]
}>()

const { messages, isChatting, sendMessage, clearChat } = useAIChat()
const chatVisible = ref(false)
const inputMessage = ref('')
const chatContainerRef = ref<HTMLElement | null>(null)

const renderMarkdown = (content: string) => {
  const html = marked.parse(content, {
    async: false,
    breaks: true,
    gfm: true,
  })

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a',
      'p',
      'br',
      'strong',
      'em',
      'del',
      'blockquote',
      'ul',
      'ol',
      'li',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'code',
      'pre',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'hr',
    ],
    ALLOWED_ATTR: ['href', 'title'],
  })
}

const suggestions = [
  { label: '查看 Fe3O4', text: '查看 Fe3O4 的晶体结构' },
  {
    label: '设计高磁密度材料',
    text: '帮我设计两个高磁密度磁性材料候选',
  },
  {
    label: '探索新材料',
    text: '给我一些还没被材料库收录的新型磁性材料候选',
  },
  {
    label: '多模型全面探索',
    text: '使用所有模型全面探索新型磁性材料',
  },
]

const handleSend = async () => {
  const text = inputMessage.value.trim()
  if (!text || isChatting.value) return
  inputMessage.value = ''

  const result = await sendMessage(text)
  if (result.action === 'campaign' && result.campaignId) {
    emit('campaignStarted', result.campaignId)
  } else if (result.action === 'generate' && result.jobId) {
    emit('generationStarted', result.jobId)
  } else if (result.materialData) {
    emit(
      'materialFound',
      result.materialData,
      result.action === 'render' ? 'render' : 'chat'
    )
  }
}

const handleSuggestion = async (text: string) => {
  inputMessage.value = text
  await handleSend()
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
      <el-card
        v-if="chatVisible"
        class="chat-panel"
        shadow="always"
      >
        <template #header>
          <div class="chat-header-title">
            <el-icon><ChatDotRound /></el-icon>
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
        </template>

        <!-- Messages -->
        <div ref="chatContainerRef" class="chat-messages">
          <div v-if="messages.length === 0" class="chat-welcome">
            <div class="welcome-icon">🤖</div>
            <p class="welcome-title">你好，我是 AI 材料助手</p>
            <p class="welcome-desc">输入材料化学式或提出问题</p>
            <div class="welcome-suggestions">
              <el-tag
                v-for="suggestion in suggestions"
                :key="suggestion.label"
                effect="plain"
                class="suggestion-chip"
                @click="handleSuggestion(suggestion.text)"
              >
                {{ suggestion.label }}
              </el-tag>
            </div>
          </div>

          <div
            v-for="msg in messages"
            :key="msg.id"
            :class="['message', msg.role === 'user' ? 'message-user' : 'message-ai']"
          >
            <el-avatar v-if="msg.role !== 'user'" :size="32">
              🤖
            </el-avatar>
            <div class="message-bubble">
              <p
                v-if="msg.role === 'user'"
                class="message-content message-plain"
              >
                {{ msg.content }}
              </p>
              <div
                v-else
                class="message-content message-markdown"
                v-html="renderMarkdown(msg.content)"
              />
            </div>
          </div>

          <div v-if="isChatting" class="message message-ai">
            <el-avatar :size="32">🤖</el-avatar>
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
      </el-card>
    </Transition>

    <!-- Floating Action Button -->
    <el-tooltip content="AI 助手" placement="left">
      <el-button
        class="ai-fab"
        type="primary"
        circle
        size="large"
        :icon="chatVisible ? Close : ChatDotRound"
        @click="chatVisible = !chatVisible"
      />
    </el-tooltip>
  </Teleport>
</template>

<style scoped>
.ai-fab {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 50;
}

.chat-panel {
  position: fixed;
  bottom: 100px;
  right: 32px;
  width: 400px;
  height: 560px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-panel :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-panel :deep(.el-card__body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 0;
}

.chat-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
}

.chat-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
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
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.welcome-desc {
  font-size: 13px;
  margin-bottom: 20px;
}

.welcome-suggestions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.message-user {
  flex-direction: row-reverse;
}

.message-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.6;
}

.message-ai .message-bubble {
  background: var(--el-fill-color-light);
  border-bottom-left-radius: 4px;
}

.message-user .message-bubble {
  background: var(--el-color-primary);
  color: var(--el-color-white);
  border-bottom-right-radius: 4px;
}

.message-content {
  margin: 0;
  word-break: break-word;
}

.message-plain {
  white-space: pre-wrap;
}

.message-markdown {
  white-space: normal;
}

.message-markdown :deep(> :first-child) {
  margin-top: 0;
}

.message-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.message-markdown :deep(p) {
  margin: 0 0 8px;
}

.message-markdown :deep(h1),
.message-markdown :deep(h2),
.message-markdown :deep(h3),
.message-markdown :deep(h4) {
  margin: 14px 0 8px;
  line-height: 1.35;
}

.message-markdown :deep(h1) {
  font-size: 18px;
}

.message-markdown :deep(h2) {
  font-size: 16px;
}

.message-markdown :deep(h3),
.message-markdown :deep(h4) {
  font-size: 14px;
}

.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  margin: 6px 0 8px;
  padding-left: 20px;
}

.message-markdown :deep(li + li) {
  margin-top: 4px;
}

.message-markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 10px;
  color: var(--el-text-color-secondary);
  border-left: 3px solid var(--el-border-color);
}

.message-markdown :deep(code) {
  padding: 1px 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  background: var(--el-fill-color-darker);
  border-radius: 4px;
}

.message-markdown :deep(pre) {
  margin: 8px 0;
  padding: 10px;
  overflow-x: auto;
  background: var(--el-fill-color-darker);
  border-radius: 6px;
}

.message-markdown :deep(pre code) {
  padding: 0;
  white-space: pre;
  background: transparent;
}

.message-markdown :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}

.message-markdown :deep(a:hover) {
  text-decoration: underline;
}

.message-markdown :deep(table) {
  display: block;
  width: 100%;
  margin: 8px 0;
  overflow-x: auto;
  border-collapse: collapse;
}

.message-markdown :deep(th),
.message-markdown :deep(td) {
  padding: 5px 8px;
  text-align: left;
  border: 1px solid var(--el-border-color);
}

.message-markdown :deep(th) {
  font-weight: 600;
  background: var(--el-fill-color-light);
}

.message-markdown :deep(hr) {
  margin: 12px 0;
  border: 0;
  border-top: 1px solid var(--el-border-color-light);
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
  border-top: 1px solid var(--el-border-color-light);
}

.chat-input {
  flex: 1;
}

.send-btn {
  flex-shrink: 0;
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
