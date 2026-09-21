import { computed, ref } from 'vue'
import {
  cancelGenerationJob,
  getGenerationCandidates,
  getGenerationJob,
} from '../api/material'
import {
  generationRealtimeUrl,
  useRealtimeSocket,
  type RealtimeMessage,
} from './useRealtimeSocket'
import type {
  CandidateCollection,
  GeneratedCandidate,
  GenerationJob,
} from '../types/material'

const STORAGE_KEY = 'material_generation_job_id'

const jobId = ref<string | null>(null)
const job = ref<GenerationJob | null>(null)
const collection = ref<CandidateCollection | null>(null)
const selectedCandidateId = ref<string | null>(null)
const panelOpen = ref(false)
const error = ref<string | null>(null)
const isCancelling = ref(false)

let fallbackTimer: ReturnType<typeof setTimeout> | null = null
let requestToken = 0

const { isConnected, connect, close, subscribe, unsubscribe } =
  useRealtimeSocket(handleRealtimeMessage, handleRealtimeReconnect)

const candidates = computed(() => collection.value?.candidates ?? [])
const selectedCandidate = computed(
  () =>
    candidates.value.find(
      (candidate) => candidate.candidate_id === selectedCandidateId.value
    ) ?? null
)
const isActive = computed(
  () => job.value?.status === 'queued' || job.value?.status === 'running'
)
const progressPercent = computed(() =>
  Math.round((job.value?.progress ?? 0) * 100)
)

function clearFallbackTimer() {
  if (fallbackTimer) {
    clearTimeout(fallbackTimer)
    fallbackTimer = null
  }
}

function scheduleFallbackPoll(currentJobId: string, token: number) {
  clearFallbackTimer()
  fallbackTimer = setTimeout(async () => {
    await refreshSnapshot(currentJobId, token)
    if (!isConnected.value && isActive.value) {
      scheduleFallbackPoll(currentJobId, token)
    }
  }, 15000)
}

async function loadCandidates(currentJobId: string, token: number) {
  try {
    const nextCollection = await getGenerationCandidates(currentJobId)
    if (token !== requestToken) return
    collection.value = nextCollection
  } catch (requestError: any) {
    if (token !== requestToken) return
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '无法读取候选结构'
  }
}

async function refreshSnapshot(currentJobId: string, token: number) {
  try {
    const next = await getGenerationJob(currentJobId)
    if (token !== requestToken) return

    job.value = next
    error.value = null

    if (next.status === 'completed') {
      await loadCandidates(currentJobId, token)
      unsubscribe('generation.job', currentJobId)
      clearFallbackTimer()
    }
  } catch (requestError: any) {
    if (token !== requestToken) return
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '无法查询生成任务'
  }
}

function handleRealtimeMessage(message: RealtimeMessage) {
  if (
    message.channel !== 'generation.job' ||
    message.resource_id !== jobId.value
  ) {
    return
  }

  if (message.type === 'error') {
    error.value = message.message || 'WebSocket 订阅失败'
    return
  }

  if (!message.job) return

  const next = message.job as GenerationJob
  job.value = next
  error.value = null

  if (next.status === 'completed') {
    void loadCandidates(next.job_id, requestToken)
    unsubscribe('generation.job', next.job_id)
    clearFallbackTimer()
  }
}

function handleRealtimeReconnect() {
  clearFallbackTimer()
  if (jobId.value) {
    void refreshSnapshot(jobId.value, requestToken)
  }
}

function openGeneration(nextJobId: string) {
  const changed = jobId.value !== nextJobId
  jobId.value = nextJobId
  panelOpen.value = true
  localStorage.setItem(STORAGE_KEY, nextJobId)

  if (!changed) return

  requestToken += 1
  const token = requestToken
  clearFallbackTimer()
  job.value = null
  collection.value = null
  selectedCandidateId.value = null
  error.value = null
  subscribe('generation.job', nextJobId)
  connect(generationRealtimeUrl())
  void refreshSnapshot(nextJobId, token)
  if (!isConnected.value) {
    scheduleFallbackPoll(nextJobId, token)
  }
}

function restoreGeneration() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (!stored) return

  jobId.value = stored
  panelOpen.value = false
  subscribe('generation.job', stored)
  connect(generationRealtimeUrl())
  void refreshSnapshot(stored, requestToken)
}

function closePanel() {
  panelOpen.value = false
}

function reopenPanel() {
  if (jobId.value) {
    panelOpen.value = true
  }
}

function selectCandidate(candidate: GeneratedCandidate) {
  selectedCandidateId.value = candidate.candidate_id
}

async function cancel() {
  if (!job.value || !isActive.value || isCancelling.value) return

  isCancelling.value = true
  try {
    job.value = await cancelGenerationJob(job.value.job_id)
    clearFallbackTimer()
  } catch (requestError: any) {
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '取消失败'
  } finally {
    isCancelling.value = false
  }
}

function clearGeneration() {
  if (jobId.value) {
    unsubscribe('generation.job', jobId.value)
  }
  close()
  clearFallbackTimer()
  localStorage.removeItem(STORAGE_KEY)
  jobId.value = null
  job.value = null
  collection.value = null
  selectedCandidateId.value = null
  panelOpen.value = false
  error.value = null
}

export function useGeneration() {
  return {
    jobId,
    job,
    candidates,
    collection,
    selectedCandidateId,
    selectedCandidate,
    panelOpen,
    error,
    isCancelling,
    isConnected,
    isActive,
    progressPercent,
    openGeneration,
    restoreGeneration,
    closePanel,
    reopenPanel,
    selectCandidate,
    cancel,
    clearGeneration,
  }
}
