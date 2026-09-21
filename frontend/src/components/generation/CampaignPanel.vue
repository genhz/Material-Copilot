<script setup lang="ts">
import { Close, Delete, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { useCampaign } from '../../composables/useCampaign'
import type { GeneratedCandidate } from '../../types/material'

const emit = defineEmits<{
  selectCandidate: [candidate: GeneratedCandidate]
  close: []
}>()

const {
  campaign,
  candidates,
  collection,
  error,
  isCancelling,
  isConnected,
  isActive,
  cancel,
  clearCampaign,
} = useCampaign()
</script>

<template>
  <section class="campaign-panel">
    <header class="campaign-header">
      <div>
        <div class="campaign-eyebrow">Multi-model</div>
        <h3>{{ campaign?.name || '多模型材料探索' }}</h3>
      </div>
      <div class="campaign-actions">
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
          title="清除 Campaign"
          @click="clearCampaign"
        >
          <el-icon><Delete /></el-icon>
        </el-button>
        <el-button text circle size="small" @click="emit('close')">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </header>

    <div class="campaign-meta">
      <el-tag
        :type="
          campaign?.status === 'completed'
            ? 'success'
            : campaign?.status === 'failed'
              ? 'danger'
              : campaign?.status === 'partial'
                ? 'warning'
                : 'primary'
        "
        effect="dark"
        size="small"
      >
        {{ campaign?.status || '加载中' }}
      </el-tag>
      <span>{{ isConnected ? '实时' : '重连中' }}</span>
      <span>{{ Math.round((campaign?.progress || 0) * 100) }}%</span>
    </div>

    <el-progress
      :percentage="Math.round((campaign?.progress || 0) * 100)"
      :show-text="false"
      :stroke-width="7"
    />

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />

    <div v-if="isActive" class="campaign-running">
      <el-icon class="is-loading" :size="22"><Refresh /></el-icon>
      <span>多个模型正在按顺序执行。</span>
    </div>

    <div class="run-list">
      <div
        v-for="run in campaign?.runs || []"
        :key="run.run_id"
        class="run-item"
      >
        <div>
          <strong>{{ run.model_label }}</strong>
          <span>{{ run.status }}</span>
        </div>
        <el-progress
          :percentage="Math.round(run.progress * 100)"
          :show-text="false"
          :stroke-width="5"
        />
      </div>
    </div>

    <div
      v-if="campaign && !isActive"
      class="campaign-candidates"
    >
      <div class="candidate-summary">
        <span>候选总数 {{ candidates.length }}</span>
        <span>模型 {{ collection?.groups.length || 0 }}</span>
      </div>

      <section
        v-for="group in collection?.groups || []"
        :key="group.model_id"
        class="candidate-group"
      >
        <h4>{{ group.model_label }}</h4>
        <button
          v-for="candidate in group.candidates"
          :key="candidate.candidate_id"
          class="candidate-card"
          @click="emit('selectCandidate', candidate)"
        >
          <div>
            <strong>{{ candidate.pretty_formula }}</strong>
            <span>{{ candidate.candidate_id }}</span>
          </div>
          <el-icon><VideoPlay /></el-icon>
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.campaign-panel {
  position: fixed;
  top: 96px;
  right: 24px;
  bottom: 24px;
  z-index: 34;
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

.campaign-header,
.campaign-actions,
.campaign-meta,
.run-item > div,
.candidate-summary,
.candidate-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.campaign-header {
  gap: 12px;
  margin-bottom: 14px;
}

.campaign-header h3 {
  margin: 2px 0 0;
  font-size: 16px;
}

.campaign-eyebrow {
  color: #818cf8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.campaign-meta,
.candidate-summary,
.run-item span,
.candidate-card span {
  color: #94a3b8;
  font-size: 12px;
}

.campaign-meta {
  margin-bottom: 8px;
}

.campaign-running {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 80px;
  color: #94a3b8;
  font-size: 13px;
}

.run-list,
.campaign-candidates,
.candidate-group {
  display: grid;
  gap: 10px;
}

.run-list {
  margin-top: 14px;
}

.run-item {
  display: grid;
  gap: 7px;
  padding: 10px 12px;
  background: rgba(51, 65, 85, 0.38);
  border-radius: 10px;
}

.campaign-candidates {
  margin-top: 16px;
}

.candidate-group h4 {
  margin: 6px 0 0;
  color: #cbd5e1;
  font-size: 13px;
}

.candidate-card {
  width: 100%;
  gap: 10px;
  padding: 10px 12px;
  color: inherit;
  text-align: left;
  background: rgba(51, 65, 85, 0.42);
  border: 1px solid rgba(99, 102, 241, 0.16);
  border-radius: 10px;
  cursor: pointer;
}

.candidate-card:hover {
  border-color: rgba(129, 140, 248, 0.55);
}

.candidate-card > div {
  display: grid;
  gap: 3px;
}

@media (max-width: 640px) {
  .campaign-panel {
    top: auto;
    left: 12px;
    right: 12px;
    bottom: 12px;
    max-height: calc(100vh - 120px);
  }
}
</style>
