import { computed, ref } from 'vue'
import {
  generationRealtimeUrl,
  useRealtimeSocket,
  type RealtimeMessage,
} from './useRealtimeSocket'
import type {
  AgentMessage,
  AgentResultEvent,
  ExecutionPlan,
  PlanStep,
  WorkflowRunState,
} from '../types/agent'

const messages = ref<AgentMessage[]>([])
const currentPlan = ref<ExecutionPlan | null>(null)
const workflow = ref<WorkflowRunState | null>(null)
const isPlanning = ref(false)
const lastResult = ref<AgentResultEvent | null>(null)
const sessionId = ref(
  localStorage.getItem('material_agent_session_id') || crypto.randomUUID()
)

localStorage.setItem('material_agent_session_id', sessionId.value)

let socketApi: ReturnType<typeof useRealtimeSocket> | null = null
let lastSequence = 0
let streamMessageId: string | null = null
let messageCounter = 0

function nextMessageId(prefix = 'message') {
  messageCounter += 1
  return `${prefix}-${messageCounter}`
}

function appendAssistantDelta(content: string) {
  if (!content) return
  if (!streamMessageId) {
    streamMessageId = nextMessageId('assistant')
    messages.value.push({
      id: streamMessageId,
      role: 'assistant',
      kind: 'text',
      content: '',
      streaming: true,
    })
  }

  const message = messages.value.find((item) => item.id === streamMessageId)
  if (message?.kind === 'text') {
    message.content += content
  }
}

function finishAssistantStream(content?: string) {
  if (!streamMessageId) {
    if (content) {
      messages.value.push({
        id: nextMessageId('assistant'),
        role: 'assistant',
        kind: 'text',
        content,
      })
    }
    return
  }

  const message = messages.value.find((item) => item.id === streamMessageId)
  if (message?.kind === 'text') {
    if (content && !message.content.trim()) {
      message.content = content
    }
    message.streaming = false
  }
  streamMessageId = null
}

function upsertStep(step: PlanStep) {
  const plans = [
    currentPlan.value,
    ...messages.value
      .filter((message) => message.kind === 'plan')
      .map((message) => message.plan),
  ].filter(Boolean) as ExecutionPlan[]

  for (const plan of plans) {
    const index = plan.steps.findIndex((item) => item.id === step.id)
    if (index >= 0) {
      plan.steps.splice(index, 1, step)
    } else {
      plan.steps.push(step)
    }
  }
}

function setCurrentPlan(plan: ExecutionPlan) {
  currentPlan.value = plan
  const existing = messages.value.find(
    (message) =>
      message.kind === 'plan' && message.planId === plan.plan_id
  )

  if (existing?.kind === 'plan') {
    existing.plan = plan
    existing.revision = plan.revision
    return
  }

  messages.value.push({
    id: nextMessageId('plan'),
    role: 'assistant',
    kind: 'plan',
    planId: plan.plan_id,
    revision: plan.revision,
    plan,
  })
}

function applyEvent(message: RealtimeMessage) {
  const sequence = Number(message.sequence || 0)
  if (sequence > lastSequence) {
    lastSequence = sequence
  }

  const payload = message as RealtimeMessage & Record<string, any>

  switch (message.type) {
    case 'agent.run.started':
      isPlanning.value = true
      streamMessageId = null
      break
    case 'assistant.delta':
      appendAssistantDelta(String(payload.content || ''))
      break
    case 'assistant.completed': {
      const result = payload as AgentResultEvent
      lastResult.value = result
      finishAssistantStream(result.message)
      isPlanning.value = false
      break
    }
    case 'plan.proposed':
    case 'plan.revised':
      setCurrentPlan(payload.plan as ExecutionPlan)
      workflow.value = null
      break
    case 'plan.confirmed':
      if (currentPlan.value) {
        currentPlan.value.status = 'confirmed'
      }
      break
    case 'step.started':
    case 'step.completed':
    case 'step.failed':
    case 'step.blocked':
    case 'step.skipped':
    case 'step.progress': {
      const step = payload.step as PlanStep | undefined
      if (step) {
        upsertStep(step)
      } else if (currentPlan.value && payload.step_id) {
        const existing = currentPlan.value.steps.find(
          (item) => item.id === payload.step_id
        )
        if (existing) {
          existing.progress = Number(payload.progress || existing.progress)
          if (message.type === 'step.completed') existing.status = 'completed'
          if (message.type === 'step.failed') existing.status = 'failed'
          if (message.type === 'step.blocked') existing.status = 'blocked'
          if (message.type === 'step.skipped') existing.status = 'skipped'
        }
      }
      break
    }
    case 'generation.retry.scheduled':
      messages.value.push({
        id: nextMessageId('retry'),
        role: 'assistant',
        kind: 'text',
        content:
          `步骤 ${payload.step_id} 执行失败，正在重试 ` +
          `${payload.attempt}/${payload.max_attempts}。\n` +
          `原因：${payload.message || '未知错误'}`,
      })
      break
    case 'workflow.completed':
      workflow.value = payload.workflow as WorkflowRunState
      setCurrentPlan(payload.plan as ExecutionPlan)
      break
    case 'workflow.aborted': {
      workflow.value = payload.workflow as WorkflowRunState
      setCurrentPlan(payload.plan as ExecutionPlan)
      const blocked = (payload.blocked_step_ids || []).join('、') || '无'
      messages.value.push({
        id: nextMessageId('aborted'),
        role: 'assistant',
        kind: 'text',
        content:
          `执行已终止。\n\n` +
          `原因：${payload.reason || '上游步骤失败'}\n\n` +
          `未执行步骤：${blocked}`,
      })
      break
    }
    case 'workflow.failed':
      workflow.value = payload.workflow as WorkflowRunState
      if (currentPlan.value) currentPlan.value.status = 'failed'
      break
    case 'workflow.cancelled':
      if (workflow.value) workflow.value.status = 'cancelled'
      if (currentPlan.value) currentPlan.value.status = 'cancelled'
      break
    case 'agent.snapshot':
      applySnapshot(payload.snapshot)
      for (const event of (payload.snapshot as any)?.events || []) {
        applyEvent(event)
      }
      break
    case 'error':
      messages.value.push({
        id: nextMessageId('error'),
        role: 'assistant',
        kind: 'text',
        content: `错误：${payload.message || '未知错误'}`,
      })
      isPlanning.value = false
      break
  }
}

function applySnapshot(snapshot: any) {
  if (!snapshot) return
  messages.value = (snapshot.messages || []).map((message: any) => ({
    id: nextMessageId(message.role),
    role: message.role,
    kind: 'text',
    content: message.content,
  }))
  if (snapshot.plan) {
    setCurrentPlan(snapshot.plan)
  } else {
    currentPlan.value = null
  }
  workflow.value = snapshot.workflow || null
  lastSequence = Number(snapshot.last_sequence || 0)
}

function handleSocketReconnect() {
  socketApi?.subscribe('agent.session', sessionId.value)
  socketApi?.send({
    action: 'agent.snapshot',
    session_id: sessionId.value,
    last_sequence: lastSequence,
    request_id: crypto.randomUUID(),
  })
}

function ensureSocket() {
  if (socketApi) return socketApi
  socketApi = useRealtimeSocket(
    applyEvent,
    handleSocketReconnect
  )
  socketApi.connect(generationRealtimeUrl())
  socketApi.subscribe('agent.session', sessionId.value)
  return socketApi
}

function sendMessage(text: string) {
  const content = text.trim()
  if (!content) return
  ensureSocket()
  messages.value.push({
    id: nextMessageId('user'),
    role: 'user',
    kind: 'text',
    content,
  })
  socketApi?.send({
    action: 'agent.message',
    session_id: sessionId.value,
    message: content,
    request_id: crypto.randomUUID(),
  })
  isPlanning.value = true
}

function confirmPlan() {
  if (!currentPlan.value) return
  socketApi?.send({
    action: 'agent.confirm',
    session_id: sessionId.value,
    plan_id: currentPlan.value.plan_id,
    revision: currentPlan.value.revision,
    request_id: crypto.randomUUID(),
  })
}

function revisePlan(instruction: string) {
  const content = instruction.trim()
  if (!currentPlan.value || !content) return
  messages.value.push({
    id: nextMessageId('user'),
    role: 'user',
    kind: 'text',
    content: `修改执行计划：${content}`,
  })
  socketApi?.send({
    action: 'agent.revise',
    session_id: sessionId.value,
    plan_id: currentPlan.value.plan_id,
    revision: currentPlan.value.revision,
    message: content,
    request_id: crypto.randomUUID(),
  })
  isPlanning.value = true
}

function cancelWorkflow() {
  socketApi?.send({
    action: 'agent.cancel',
    session_id: sessionId.value,
    request_id: crypto.randomUUID(),
  })
}

function clearSession() {
  socketApi?.send({
    action: 'agent.clear',
    session_id: sessionId.value,
    request_id: crypto.randomUUID(),
  })
  messages.value = []
  currentPlan.value = null
  workflow.value = null
  lastResult.value = null
  streamMessageId = null
  lastSequence = 0
}

const isExecuting = computed(() => {
  const status = workflow.value?.status
  return status === 'confirmed' || status === 'running'
})

const primaryJobId = computed(
  () =>
    workflow.value?.result?.primary_job_id ||
    workflow.value?.result?.jobs[0]?.job_id ||
    workflow.value?.job_ids[0] ||
    null
)

const workflowResult = computed(() => workflow.value?.result || null)

const isConnected = computed(() => socketApi?.isConnected.value || false)

export function useAgentSession() {
  ensureSocket()

  return {
    messages,
    currentPlan,
    workflow,
    isConnected,
    isPlanning,
    isExecuting,
    primaryJobId,
    workflowResult,
    lastResult,
    sessionId,
    sendMessage,
    confirmPlan,
    revisePlan,
    cancelWorkflow,
    clearSession,
  }
}
