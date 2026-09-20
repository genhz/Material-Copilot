<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Close, Refresh, VideoPlay } from '@element-plus/icons-vue'
import {
  cancelGenerationJob,
  getGenerationCandidates,
  getGenerationJob,
} from '../../api/material'
import type {
  CandidateCollection,
  GeneratedCandidate,
  GenerationJob,
  GenerationStatus,
} from '../../types/material'

interface Props {
  jobId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  selectCandidate: [candidate: GeneratedCandidate]
  close: []
}>()

const job = ref<GenerationJob | null>(null)
const collection = ref<CandidateCollection | null>(null)
const error = ref<string | null>(null)
const isCancelling = ref(false)

let pollTimer: ReturnType<typeof setTimeout> | null = null
let requestToken = 0

const statusLabels: Record<GenerationStatus, string> = {
  queued: '排队中',
  running: '生成中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const progressPercent = computed(() => {
  return Math.round((job.value?.progress ?? 0) * 100)
})

const statusLabel = computed(() => {
  return job.value ? statusLabels[job.value.status] : '准备中'
})

const isActive = computed(() => {
  return job.value?.status === 'queued' || job.value?.status === 'running'
})

const candidates = computed(() => collection.value?.candidates ?? [])

function clearTimer() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function schedulePoll(jobId: string, token: number, delay: number) {
  clearTimer()
  pollTimer = setTimeout(() => {
    void poll(jobId, token)
  }, delay)
}

async function poll(jobId: string, token: number) {
  try {
    const next = await getGenerationJob(jobId)
    if (token !== requestToken) return

    job.value = next
    error.value = null

    if (next.status === 'completed') {
      collection.value = await getGenerationCandidates(jobId)
      return
    }

    if (next.status === 'queued' || next.status === 'running') {
      schedulePoll(jobId, token, next.status === 'queued' ? 1000 : 2000)
    }
  } catch (requestError: any) {
    if (token !== requestToken) return
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '无法查询生成任务'
    schedulePoll(jobId, token, 5000)
  }
}

async function cancel() {
  if (!job.value || !isActive.value || isCancelling.value) return

  isCancelling.value = true
  try {
    job.value = await cancelGenerationJob(job.value.job_id)
    clearTimer()
  } catch (requestError: any) {
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '取消失败'
  } finally {
    isCancelling.value = false
  }
}

watch(
  () => props.jobId,
  async (jobId) => {
    requestToken += 1
    const token = requestToken
    clearTimer()
    job.value = null
    collection.value = null
    error.value = null
    await poll(jobId, token)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  requestToken += 1
  clearTimer()
})
</script>

<template>
  <Transition name="generation-slide">
    <section class="generation-panel">
      <header class="generation-header">
        <div>
          <div class="generation-eyebrow">MatterGen</div>
          <h3>磁性材料候选</h3>
        </div>
        <div class="generation-actions">
          <el-button
            v-if="isActive"
            text
            size="small"
            :loading="isCancelling"
            @click="cancel"
          >
            取消
          </el-button>
          <el-button text circle size="small" @click="emit('close')">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </header>

      <div class="generation-status">
        <div class="status-row">
          <el-tag
            :type="
              job?.status === 'completed'
                ? 'success'
                : job?.status === 'failed'
                  ? 'danger'
                  : job?.status === 'cancelled'
                    ? 'info'
                    : 'primary'
            "
            effect="dark"
            size="small"
          >
            {{ statusLabel }}
          </el-tag>
          <span class="status-progress">{{ progressPercent }}%</span>
        </div>
        <el-progress
          :percentage="progressPercent"
          :stroke-width="7"
          :show-text="false"
          :status="job?.status === 'failed' ? 'exception' : undefined"
        />
        <p class="status-note">
          目标磁密度
          <strong>
            {{
              job?.request
                ? `${job.request.target_magnetic_density} Å⁻³`
                : '加载中'
            }}
          </strong>
        </p>
      </div>

      <el-alert
        v-if="error || job?.error_message"
        :title="error || job?.error_message || ''"
        type="error"
        :closable="false"
        show-icon
      />

      <div v-if="job?.status === 'queued'" class="waiting-state">
        <el-icon class="is-loading" :size="24"><Refresh /></el-icon>
        <span>任务正在等待 MatterGen Worker。</span>
      </div>

      <div v-else-if="isActive" class="waiting-state">
        <el-icon class="is-loading" :size="24"><Refresh /></el-icon>
        <span>正在执行扩散采样，M4 上可能需要较长时间。</span>
      </div>

      <div v-else-if="job?.status === 'cancelled'" class="waiting-state">
        <span>生成任务已取消。</span>
      </div>

      <div v-else-if="job?.status === 'completed'" class="candidate-area">
        <div class="candidate-summary">
          <span>有效候选 {{ candidates.length }}</span>
          <span v-if="collection?.invalid_count">
            无效 {{ collection.invalid_count }}
          </span>
        </div>

        <div v-if="candidates.length" class="candidate-list">
          <button
            v-for="candidate in candidates"
            :key="candidate.candidate_id"
            class="candidate-card"
            @click="emit('selectCandidate', candidate)"
          >
            <div class="candidate-main">
              <strong>{{ candidate.pretty_formula }}</strong>
              <span>{{ candidate.candidate_id }}</span>
            </div>
            <div class="candidate-metrics">
              <span v-if="candidate.density != null">
                {{ candidate.density.toFixed(2) }} g/cm³
              </span>
              <span v-if="candidate.formula_unit != null">
                {{ candidate.formula_unit }} atoms
              </span>
            </div>
            <el-icon :size="16"><VideoPlay /></el-icon>
          </button>
        </div>

        <el-empty
          v-else
          description="没有可解析的候选结构"
          :image-size="64"
        />
      </div>
    </section>
  </Transition>
</template>

<style scoped>
.generation-panel {
  position: fixed;
  left: 24px;
  bottom: 24px;
  z-index: 35;
  width: min(430px, calc(100vw - 48px));
  max-height: min(620px, calc(100vh - 130px));
  overflow-y: auto;
  padding: 18px;
  color: #e2e8f0;
  background: rgba(15, 23, 42, 0.94);
  border: 1px solid rgba(99, 102, 241, 0.24);
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(22px) saturate(150%);
}

.generation-header,
.status-row,
.candidate-summary,
.candidate-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.generation-header {
  gap: 12px;
  margin-bottom: 16px;
}

.generation-header h3 {
  margin: 2px 0 0;
  font-size: 16px;
}

.generation-eyebrow {
  color: #818cf8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.generation-actions {
  display: flex;
  align-items: center;
}

.generation-status {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

.status-progress,
.status-note,
.candidate-main span,
.candidate-metrics,
.candidate-summary {
  color: #94a3b8;
  font-size: 12px;
}

.status-note {
  margin: 0;
}

.status-note strong {
  color: #cbd5e1;
}

.waiting-state {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 88px;
  color: #94a3b8;
  font-size: 13px;
}

.candidate-area {
  display: grid;
  gap: 10px;
}

.candidate-list {
  display: grid;
  gap: 8px;
}

.candidate-card {
  width: 100%;
  gap: 12px;
  padding: 12px;
  color: inherit;
  text-align: left;
  background: rgba(51, 65, 85, 0.42);
  border: 1px solid rgba(99, 102, 241, 0.16);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}

.candidate-card:hover {
  background: rgba(51, 65, 85, 0.62);
  border-color: rgba(129, 140, 248, 0.48);
  transform: translateY(-1px);
}

.candidate-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.candidate-main strong {
  color: #f1f5f9;
  font-size: 14px;
}

.candidate-metrics {
  display: flex;
  gap: 8px;
  white-space: nowrap;
}

.generation-slide-enter-active,
.generation-slide-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.generation-slide-enter-from,
.generation-slide-leave-to {
  opacity: 0;
  transform: translateY(16px);
}

@media (max-width: 640px) {
  .generation-panel {
    left: 12px;
    bottom: 12px;
    width: calc(100vw - 24px);
    max-height: calc(100vh - 120px);
  }

  .candidate-card {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
