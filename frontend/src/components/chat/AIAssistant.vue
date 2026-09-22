<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  ChatDotRound,
  Close,
  Position,
} from '@element-plus/icons-vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import ExecutionPlanPanel from '../agent/ExecutionPlanPanel.vue'
import { useAgentSession } from '../../composables/useAgentSession'
import type { MaterialData } from '../../types/material'

const emit = defineEmits<{
  materialFound: [data: MaterialData, action: 'chat' | 'render']
  generationStarted: [jobId: string]
  campaignStarted: [campaignId: string]
}>()

const {
  messages,
  currentPlan,
  workflow,
  isConnected,
  isPlanning,
  primaryJobId,
  lastResult,
  sendMessage,
  confirmPlan,
  revisePlan,
  cancelWorkflow,
  clearSession,
} = useAgentSession()

const workspaceVisible = ref(false)
const inputMessage = ref('')
const chatContainerRef = ref<HTMLElement | null>(null)
let handledJobId: string | null = null
let handledResult: unknown = null

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
    text: '帮我设计高磁密度磁性材料候选',
  },
  {
    label: '探索钕铁磁体',
    text: '请探索钕铁合金磁性性能较优的晶体结构',
  },
  {
    label: '无稀土磁体',
    text: '设计不含稀土元素的高磁密度磁体候选',
  },
]

function handleSend() {
  const text = inputMessage.value.trim()
  if (!text || isPlanning.value) return
  inputMessage.value = ''
  sendMessage(text)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

watch(messages, async () => {
  await nextTick()
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}, { deep: true })

watch(primaryJobId, (jobId) => {
  if (!jobId || jobId === handledJobId) return
  handledJobId = jobId
  emit('generationStarted', jobId)
})

watch(lastResult, (result) => {
  if (!result || result === handledResult) return
  handledResult = result
  if (result.campaign_id) {
    emit('campaignStarted', result.campaign_id)
  } else if (result.material_data) {
    emit(
      'materialFound',
      result.material_data,
      result.action === 'render' ? 'render' : 'chat'
    )
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="workspace">
      <section v-if="workspaceVisible" class="agent-workspace">
        <header class="workspace-header">
          <div class="workspace-title">
            <el-icon><ChatDotRound /></el-icon>
            <div>
              <strong>AI 材料工作区</strong>
              <span>{{ isConnected ? '实时连接' : '正在重连' }}</span>
            </div>
          </div>
          <div class="workspace-actions">
            <el-button text size="small" @click="clearSession">
              清除会话
            </el-button>
            <el-button
              text
              circle
              size="small"
              @click="workspaceVisible = false"
            >
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </header>

        <div class="workspace-body">
          <section class="conversation-panel">
            <div ref="chatContainerRef" class="chat-messages">
              <div v-if="messages.length === 0" class="chat-welcome">
                <div class="welcome-icon">🤖</div>
                <h2>先讨论方案，再开始生成</h2>
                <p>
                  我会先解析元素和目标，给出执行计划。只有你确认后，任务才会执行。
                </p>
                <div class="welcome-suggestions">
                  <el-tag
                    v-for="suggestion in suggestions"
                    :key="suggestion.label"
                    effect="plain"
                    class="suggestion-chip"
                    @click="sendMessage(suggestion.text)"
                  >
                    {{ suggestion.label }}
                  </el-tag>
                </div>
              </div>

              <div
                v-for="message in messages"
                :key="message.id"
                class="message"
                :class="
                  message.role === 'user'
                    ? 'message-user'
                    : 'message-assistant'
                "
              >
                <el-avatar v-if="message.role === 'assistant'" :size="30">
                  🤖
                </el-avatar>
                <div class="message-bubble">
                  <p
                    v-if="message.role === 'user'"
                    class="message-content message-plain"
                  >
                    {{ message.content }}
                  </p>
                  <div
                    v-else
                    class="message-content message-markdown"
                    v-html="renderMarkdown(message.content)"
                  />
                  <span v-if="message.streaming" class="stream-cursor" />
                </div>
              </div>
            </div>

            <div class="chat-input-area">
              <el-input
                v-model="inputMessage"
                type="textarea"
                resize="none"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="描述材料目标，例如：探索 Nd-Fe-B 高磁密度候选"
                @keydown="handleKeydown"
              />
              <el-button
                type="primary"
                :icon="Position"
                :disabled="isPlanning || !inputMessage.trim()"
                circle
                @click="handleSend"
              />
            </div>
          </section>

          <aside class="plan-pane">
            <ExecutionPlanPanel
              :plan="currentPlan"
              :workflow="workflow"
              :is-connected="isConnected"
              @confirm="confirmPlan"
              @revise="revisePlan"
              @cancel="cancelWorkflow"
            />
          </aside>
        </div>
      </section>
    </Transition>

    <el-tooltip
      v-if="!workspaceVisible"
      content="AI 助手"
      placement="left"
    >
      <el-button
        class="ai-fab"
        type="primary"
        circle
        size="large"
        :icon="workspaceVisible ? Close : ChatDotRound"
        @click="workspaceVisible = !workspaceVisible"
      />
    </el-tooltip>
  </Teleport>
</template>

<style scoped>
.agent-workspace {
  position: fixed;
  inset: 18px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  max-width: 1280px;
  margin: auto;
  overflow: hidden;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  box-shadow: var(--el-box-shadow-dark);
}

.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 58px;
  padding: 0 18px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.workspace-title,
.workspace-actions {
  display: flex;
  align-items: center;
}

.workspace-title {
  gap: 10px;
}

.workspace-title div {
  display: flex;
  flex-direction: column;
}

.workspace-title span {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.workspace-actions {
  gap: 4px;
}

.workspace-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  flex: 1;
  min-height: 0;
}

.conversation-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.chat-messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 24px;
  overflow-y: auto;
}

.chat-welcome {
  max-width: 520px;
  margin: auto;
  text-align: center;
}

.welcome-icon {
  font-size: 52px;
}

.chat-welcome h2 {
  margin: 12px 0 8px;
  font-size: 20px;
}

.chat-welcome p {
  margin: 0 0 20px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.welcome-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.suggestion-chip {
  cursor: pointer;
}

.message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.message-user {
  flex-direction: row-reverse;
}

.message-bubble {
  max-width: min(78%, 760px);
  padding: 11px 14px;
  font-size: 14px;
  line-height: 1.7;
  background: var(--el-fill-color-light);
  border-radius: 12px;
}

.message-user .message-bubble {
  color: var(--el-color-white);
  background: var(--el-color-primary);
}

.message-content {
  margin: 0;
  overflow-wrap: anywhere;
}

.message-plain {
  white-space: pre-wrap;
}

.message-markdown :deep(> :first-child) {
  margin-top: 0;
}

.message-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.message-markdown :deep(p) {
  margin: 0 0 9px;
}

.message-markdown :deep(pre) {
  padding: 10px 12px;
  overflow-x: auto;
  background: var(--el-fill-color-darker);
  border-radius: 6px;
}

.message-markdown :deep(code) {
  padding: 1px 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--el-fill-color-darker);
  border-radius: 4px;
}

.message-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
}

.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  padding-left: 22px;
}

.message-markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}

.message-markdown :deep(th),
.message-markdown :deep(td) {
  padding: 5px 8px;
  border: 1px solid var(--el-border-color);
}

.stream-cursor {
  display: inline-block;
  width: 7px;
  height: 15px;
  margin-left: 4px;
  vertical-align: text-bottom;
  background: var(--el-color-primary);
  animation: cursor-blink 0.8s steps(1) infinite;
}

@keyframes cursor-blink {
  50% {
    opacity: 0;
  }
}

.chat-input-area {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 14px 18px;
  border-top: 1px solid var(--el-border-color-light);
}

.plan-pane {
  min-height: 0;
  background: var(--el-bg-color-page);
  border-left: 1px solid var(--el-border-color-light);
}

.ai-fab {
  position: fixed;
  right: 32px;
  bottom: 32px;
  z-index: 55;
}

.workspace-enter-active,
.workspace-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.workspace-enter-from,
.workspace-leave-to {
  opacity: 0;
  transform: translateY(18px) scale(0.98);
}

@media (max-width: 900px) {
  .agent-workspace {
    inset: 0;
    border: 0;
    border-radius: 0;
  }

  .workspace-body {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .conversation-panel,
  .plan-pane {
    min-height: 60vh;
  }

  .plan-pane {
    border-top: 1px solid var(--el-border-color-light);
    border-left: 0;
  }
}
</style>
