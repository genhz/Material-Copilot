<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Check,
  Close,
  Edit,
  Loading,
  VideoPause,
  Warning,
} from '@element-plus/icons-vue'
import type {
  ExecutionPlan,
  PlanStep,
  WorkflowRunState,
} from '../../types/agent'

interface Props {
  plan: ExecutionPlan | null
  workflow: WorkflowRunState | null
  isConnected: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  confirm: []
  revise: [instruction: string]
  cancel: []
}>()

const revisionText = ref('')

const statusLabel = computed(() => {
  const capabilityStatus = props.plan?.capability_status
  if (capabilityStatus && capabilityStatus !== 'ready') {
    return (
      {
        clarification: '需要补充信息',
        unsupported: '暂不支持',
        unavailable: '当前不可执行',
      }[capabilityStatus] || capabilityStatus
    )
  }
  const status = props.workflow?.status || props.plan?.status
  const labels: Record<string, string> = {
    awaiting_confirmation: '等待确认',
    draft: '草稿',
    clarification: '需要补充信息',
    ready: '可执行',
    confirmed: '已确认',
    executing: '执行中',
    running: '执行中',
    completed: '已完成',
    partial: '部分完成',
    failed: '失败',
    cancelled: '已取消',
    aborted: '已终止',
  }
  return status ? labels[status] || status : '尚未生成'
})

const statusType = computed(() => {
  const capabilityStatus = props.plan?.capability_status
  if (capabilityStatus === 'clarification') return 'warning'
  if (capabilityStatus === 'unsupported') return 'danger'
  if (capabilityStatus === 'unavailable') return 'warning'
  const status = props.workflow?.status || props.plan?.status
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (
    status === 'partial' ||
    status === 'cancelled' ||
    status === 'aborted'
  ) {
    return 'warning'
  }
  if (status === 'executing' || status === 'running') return 'primary'
  return 'info'
})

function stepType(step: PlanStep) {
  if (step.status === 'completed') return 'success'
  if (step.status === 'failed') return 'danger'
  if (step.status === 'running') return 'primary'
  if (step.status === 'blocked' || step.status === 'skipped') return 'warning'
  return 'info'
}

function submitRevision() {
  const value = revisionText.value.trim()
  if (!value) return
  emit('revise', value)
  revisionText.value = ''
}

const canRevise = computed(
  () =>
    props.plan?.capability_status === 'ready' ||
    props.plan?.capability_status === 'clarification'
)

const canConfirm = computed(
  () => props.plan?.capability_status === 'ready'
)
</script>

<template>
  <section class="plan-panel">
    <header class="plan-header">
      <div>
        <span class="plan-eyebrow">Workflow</span>
        <h3>执行计划</h3>
      </div>
      <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
    </header>

    <div class="plan-content">
      <el-empty
        v-if="!plan"
        description="发送生成需求后，这里会出现可确认的执行计划"
        :image-size="64"
      />

      <template v-else>
        <div class="plan-summary">{{ plan.summary }}</div>

      <section class="plan-section">
        <h4>元素约束</h4>
        <div class="tag-list">
          <el-tag
            v-for="element in plan.request_spec.required_elements"
            :key="`required-${element}`"
            type="success"
            size="small"
          >
            必须 {{ element }}
          </el-tag>
          <el-tag
            v-for="element in plan.request_spec.allowed_elements"
            :key="`allowed-${element}`"
            effect="plain"
            size="small"
          >
            允许 {{ element }}
          </el-tag>
          <el-tag
            v-for="element in plan.request_spec.excluded_elements"
            :key="`excluded-${element}`"
            type="danger"
            effect="plain"
            size="small"
          >
            禁止 {{ element }}
          </el-tag>
          <span
            v-if="
              !plan.request_spec.required_elements.length &&
              !plan.request_spec.allowed_elements.length &&
              !plan.request_spec.excluded_elements.length
            "
            class="muted"
          >
            未指定元素限制
          </span>
        </div>
      </section>

      <section
        v-if="plan.request_spec.objectives.length"
        class="plan-section"
      >
        <h4>目标性质</h4>
        <div
          v-for="objective in plan.request_spec.objectives"
          :key="`${objective.property}-${objective.target}`"
          class="objective-row"
        >
          <span>{{ objective.property }}</span>
          <strong>
            {{ objective.operator }} {{ objective.target }}
          </strong>
          <el-tag size="small" effect="plain">
            {{ objective.kind === 'hard' ? '硬约束' : '软目标' }}
          </el-tag>
        </div>
      </section>

      <el-alert
        v-for="question in plan.questions"
        :key="question"
        :title="question"
        type="warning"
        :closable="false"
        show-icon
      />

      <section class="plan-section">
        <h4>执行步骤</h4>
        <div class="step-list">
          <div
            v-for="step in plan.steps"
            :key="step.id"
            class="plan-step"
            :class="{ active: workflow?.current_step_id === step.id }"
          >
            <el-icon
              class="step-icon"
              :class="`step-icon-${step.status}`"
              :size="18"
            >
              <Loading v-if="step.status === 'running'" class="is-loading" />
              <Check v-else-if="step.status === 'completed'" />
              <Close v-else-if="step.status === 'failed'" />
              <Warning
                v-else-if="step.status === 'blocked' || step.status === 'skipped'"
              />
              <Edit v-else />
            </el-icon>
            <div class="step-body">
              <div class="step-title">
                <strong>{{ step.title }}</strong>
                <el-tag :type="stepType(step)" size="small">
                  {{ step.status }}
                </el-tag>
              </div>
              <p>{{ step.description }}</p>
              <div v-if="step.model_id" class="step-meta">
                {{ step.model_id }}
                <span v-if="step.num_candidates">
                  · {{ step.num_candidates }} candidates
                </span>
              </div>
              <el-progress
                v-if="step.kind === 'generate'"
                :percentage="Math.round(step.progress * 100)"
                :show-text="false"
                :status="step.status === 'failed' ? 'exception' : undefined"
              />
              <el-text v-if="step.error_message" type="danger" size="small">
                {{ step.error_message }}
              </el-text>
            </div>
          </div>
        </div>
      </section>

      </template>
    </div>

    <section
      v-if="plan?.status === 'awaiting_confirmation'"
      class="revision-area"
    >
      <el-input
        v-if="canRevise"
        v-model="revisionText"
        type="textarea"
        :rows="3"
        resize="none"
        placeholder="需要修改计划？例如：允许 B，候选数改为 10"
      />
      <div class="plan-actions">
        <el-button
          :icon="Edit"
          :disabled="!canRevise || !revisionText.trim()"
          @click="submitRevision"
        >
          修改计划
        </el-button>
        <el-button
          v-if="canConfirm"
          type="primary"
          :icon="Check"
          :disabled="!isConnected || !canConfirm"
          @click="emit('confirm')"
        >
          确认执行
        </el-button>
      </div>
    </section>

    <div
      v-else-if="
        workflow?.status === 'running' ||
        workflow?.status === 'confirmed'
      "
      class="revision-area"
    >
      <div class="plan-actions">
        <el-button :icon="VideoPause" @click="emit('cancel')">
          停止任务
        </el-button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.plan-panel {
  width: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
}

.plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.plan-header h3 {
  margin: 2px 0 0;
  font-size: 18px;
}

.plan-eyebrow {
  color: var(--el-color-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.plan-content {
  padding: 18px 20px 24px;
}

.plan-summary {
  padding: 12px 14px;
  margin-bottom: 18px;
  color: var(--el-text-color-regular);
  line-height: 1.7;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.plan-section {
  margin-bottom: 20px;
}

.plan-section h4 {
  margin: 0 0 10px;
  font-size: 13px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.objective-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.step-list {
  display: grid;
  gap: 10px;
}

.plan-step {
  display: flex;
  gap: 10px;
  padding: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.plan-step.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-9);
}

.step-body {
  flex: 1;
  min-width: 0;
}

.step-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.step-body p {
  margin: 5px 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.step-meta {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.revision-area {
  flex-shrink: 0;
  padding: 14px 20px 16px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-page);
}

.plan-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.step-icon-pending {
  color: var(--el-text-color-secondary);
}

.step-icon-running {
  color: var(--el-color-primary);
}

.step-icon-completed {
  color: var(--el-color-success);
}

.step-icon-failed {
  color: var(--el-color-danger);
}
</style>
