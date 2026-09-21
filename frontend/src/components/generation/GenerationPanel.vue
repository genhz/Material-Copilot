<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Close,
  Delete,
  Refresh,
  VideoPlay,
} from '@element-plus/icons-vue'
import { useGeneration } from '../../composables/useGeneration'
import type {
  GeneratedCandidate,
  GenerationStatus,
} from '../../types/material'

const emit = defineEmits<{
  selectCandidate: [candidate: GeneratedCandidate]
  close: []
}>()

const {
  job,
  candidates,
  collection,
  selectedCandidateId,
  error,
  isCancelling,
  isConnected,
  isActive,
  progressPercent,
  selectCandidate,
  cancel,
  clearGeneration,
} = useGeneration()

const statusLabels: Record<GenerationStatus, string> = {
  queued: '排队中',
  running: '生成中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const statusLabel = computed(() => {
  return job.value ? statusLabels[job.value.status] : '准备中'
})

const modelLabel = computed(() => {
  return job.value?.model_label || job.value?.model_id || '材料生成'
})

const conditionText = computed(() => {
  const conditions = job.value?.request.conditions || {}
  const entries = Object.entries(conditions)
  if (!entries.length && job.value?.request.target_magnetic_density != null) {
    return `dft_mag_density=${job.value.request.target_magnetic_density}`
  }
  return entries.length
    ? entries.map(([key, value]) => `${key}=${value}`).join(' · ')
    : '无条件生成'
})

const selectedIndex = computed(() => {
  return candidates.value.findIndex(
    (candidate) => candidate.candidate_id === selectedCandidateId.value
  )
})

function chooseCandidate(candidate: GeneratedCandidate) {
  selectCandidate(candidate)
  emit('selectCandidate', candidate)
}

function moveSelection(offset: number) {
  if (!candidates.value.length) return

  const current = selectedIndex.value >= 0 ? selectedIndex.value : 0
  const nextIndex =
    (current + offset + candidates.value.length) % candidates.value.length
  chooseCandidate(candidates.value[nextIndex])
}
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
          <el-button
            v-else
            text
            circle
            size="small"
            title="清除候选列表"
            @click="clearGeneration"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
          <el-button text circle size="small" @click="emit('close')">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </header>

      <div class="generation-status">
        <div class="status-row">
          <div class="status-tags">
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
            <span
              class="connection-state"
              :class="{ connected: isConnected }"
            >
              {{ isConnected ? '实时' : '重连中' }}
            </span>
          </div>
          <span class="status-progress">{{ progressPercent }}%</span>
        </div>
        <el-progress
          :percentage="progressPercent"
          :stroke-width="7"
          :show-text="false"
          :status="job?.status === 'failed' ? 'exception' : undefined"
        />
        <p class="status-note">
          <span>
            <strong>{{ modelLabel }}</strong>
          </span>
          <span>{{ conditionText }}</span>
          <span v-if="job?.message">{{ job.message }}</span>
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
        <span>
          {{ job?.message || '正在执行扩散采样，M4 上可能需要较长时间。' }}
        </span>
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

        <div v-if="candidates.length" class="candidate-navigation">
          <el-button
            text
            size="small"
            :icon="ArrowLeft"
            @click="moveSelection(-1)"
          >
            上一个
          </el-button>
          <span>
            {{ selectedIndex >= 0 ? selectedIndex + 1 : '-' }}
            / {{ candidates.length }}
          </span>
          <el-button
            text
            size="small"
            @click="moveSelection(1)"
          >
            下一个
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
        </div>

        <div v-if="candidates.length" class="candidate-list">
          <button
            v-for="candidate in candidates"
            :key="candidate.candidate_id"
            :class="[
              'candidate-card',
              { selected: candidate.candidate_id === selectedCandidateId },
            ]"
            @click="chooseCandidate(candidate)"
          >
            <div class="candidate-main">
              <strong>
                {{ candidate.pretty_formula }}
                <span
                  v-if="candidate.candidate_id === selectedCandidateId"
                  class="selected-label"
                >
                  正在查看
                </span>
              </strong>
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
  right: 24px;
  top: 96px;
  bottom: 24px;
  z-index: 35;
  width: min(390px, calc(100vw - 48px));
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
.candidate-navigation,
.candidate-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.candidate-navigation {
  gap: 10px;
  color: #94a3b8;
  font-size: 12px;
}

.candidate-navigation > span {
  min-width: 44px;
  text-align: center;
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

.status-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.connection-state {
  color: #f59e0b;
  font-size: 11px;
}

.connection-state.connected {
  color: #34d399;
}

.status-note {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
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

.candidate-card.selected {
  background: rgba(99, 102, 241, 0.18);
  border-color: rgba(129, 140, 248, 0.72);
  box-shadow: inset 3px 0 0 #818cf8;
}

.selected-label {
  margin-left: 8px;
  color: #a5b4fc;
  font-size: 10px;
  font-weight: 500;
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
    right: 12px;
    top: auto;
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
