<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Close,
  Delete,
  VideoPlay,
} from '@element-plus/icons-vue'
import { useGeneration } from '../../composables/useGeneration'
import type { GeneratedCandidate } from '../../types/material'

const emit = defineEmits<{
  selectCandidate: [candidate: GeneratedCandidate]
  close: []
}>()

const {
  workflowResult,
  candidates,
  collection,
  selectedCandidateId,
  selectCandidate,
  clearGeneration,
} = useGeneration()

const statusLabel = computed(() => {
  if (workflowResult.value) {
    return workflowResult.value.status === 'partial'
      ? '部分完成'
      : '已完成'
  }
  return '准备中'
})

const modelLabel = computed(() => {
  if (workflowResult.value) {
    return `Workflow · ${workflowResult.value.jobs.length} jobs`
  }
  return '材料生成'
})

const conditionText = computed(() => {
  if (workflowResult.value) {
    return (
      `请求 ${workflowResult.value.requested_candidate_count}` +
      ` · 生成 ${workflowResult.value.candidate_count}` +
      ` · 失败 Job ${workflowResult.value.failed_job_count}`
    )
  }
  return '等待 Workflow 结果'
})

const statusType = computed(() => {
  if (workflowResult.value?.status === 'completed') return 'success'
  if (workflowResult.value?.status === 'partial') return 'warning'
  return 'primary'
})

const errorText = computed(() => {
  const failures = workflowResult.value?.failures || []
  if (!failures.length) return ''
  return failures
    .map((failure) => String(failure.reason || failure.error || failure))
    .join('\n')
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
    <el-card class="generation-panel" shadow="always">
      <header class="generation-header">
        <div>
          <div class="generation-eyebrow">
            {{ workflowResult ? 'Workflow' : 'MatterGen' }}
          </div>
          <h3>材料候选</h3>
        </div>
        <div class="generation-actions">
          <el-button
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
              :type="statusType"
              effect="light"
              size="small"
            >
              {{ statusLabel }}
            </el-tag>
            <span class="result-state">
              聚合结果
            </span>
          </div>
          <span class="status-progress">
            {{ workflowResult ? '100%' : '0%' }}
          </span>
        </div>
        <el-progress
          :percentage="workflowResult ? 100 : 0"
          :stroke-width="7"
          :show-text="false"
          :status="workflowResult?.status === 'partial' ? 'warning' : undefined"
        />
        <p class="status-note">
          <span>
            <strong>{{ modelLabel }}</strong>
          </span>
          <span>{{ conditionText }}</span>
        </p>
      </div>

      <el-alert
        v-if="errorText"
        :title="errorText"
        type="warning"
        :closable="false"
        show-icon
      />

      <div
        v-if="workflowResult"
        class="candidate-area"
      >
        <div class="candidate-summary">
          <span>有效候选 {{ candidates.length }}</span>
          <span v-if="collection?.invalid_count">
            无效 {{ collection.invalid_count }}
          </span>
        </div>

        <div v-if="workflowResult?.jobs.length" class="job-summary-list">
          <div
            v-for="(resultJob, index) in workflowResult.jobs"
            :key="resultJob.job_id"
            class="job-summary-row"
          >
            <span>Job {{ index + 1 }}</span>
            <span>{{ resultJob.candidate_count }} candidates</span>
            <el-tag
              :type="resultJob.status === 'completed' ? 'success' : 'danger'"
              size="small"
            >
              {{ resultJob.status }}
            </el-tag>
          </div>
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
    </el-card>
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
  color: var(--el-color-primary);
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
  font-size: 12px;
}

.job-summary-list {
  display: grid;
  gap: 6px;
  margin: 10px 0 14px;
}

.job-summary-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.status-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-state {
  color: var(--el-color-warning);
  font-size: 11px;
}

.status-note {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
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
  text-align: left;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}

.candidate-card:hover {
  background: var(--el-fill-color);
  border-color: var(--el-color-primary-light-5);
  transform: translateY(-1px);
}

.candidate-card.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.selected-label {
  margin-left: 8px;
  color: var(--el-color-primary);
  font-size: 10px;
  font-weight: 500;
}

.candidate-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.candidate-main strong {
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
