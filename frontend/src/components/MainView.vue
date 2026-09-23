<script setup lang="ts">
import { Grid } from '@element-plus/icons-vue'
import SearchBar from './crystal/SearchBar.vue'
import CrystalViewer from './crystal/CrystalViewer.vue'
import MaterialPanel from './data/MaterialPanel.vue'
import AIAssistant from './chat/AIAssistant.vue'
import GenerationPanel from './generation/GenerationPanel.vue'
import CampaignPanel from './generation/CampaignPanel.vue'
import { useMaterialSearch } from '../composables/useMaterialSearch'
import { useGeneration } from '../composables/useGeneration'
import { useCampaign } from '../composables/useCampaign'
import type { GeneratedCandidate, MaterialData } from '../types/material'
import type { WorkflowResult } from '../types/agent'

const {
  currentMaterial,
  isLoading,
  error,
  doSearch,
  setMaterial,
} = useMaterialSearch()

const {
  jobId: generationJobId,
  candidates: generatedCandidates,
  panelOpen: generationPanelOpen,
  openGeneration,
  openWorkflowResult,
  restoreGeneration,
  closePanel: closeGenerationPanel,
  reopenPanel: reopenGenerationPanel,
  selectCandidate,
} = useGeneration()

const {
  campaignId,
  panelOpen: campaignPanelOpen,
  openCampaign,
  restoreCampaign,
  closePanel: closeCampaignPanel,
  reopenPanel: reopenCampaignPanel,
} = useCampaign()

restoreGeneration()
restoreCampaign()

const handleSearch = (formula: string) => {
  doSearch(formula)
}

const handleClosePanel = () => {
  setMaterial(undefined as any)
}

const handleMaterialFound = (data: MaterialData, action: 'chat' | 'render') => {
  console.log('[MainView] materialFound:', { action, formula: data.formula })

  // 只有当 action 为 'render' 时才显示 3D 晶体和侧边栏
  // 如果是 'chat'，只更新对话，不打开侧边栏
  if (action === 'render') {
    setMaterial(data)
  }
  // 如果 action 是 'chat'，不更新 currentMaterial，侧边栏保持关闭
}

const handleGenerationStarted = (jobId: string) => {
  closeCampaignPanel()
  openGeneration(jobId)
}

const handleCampaignStarted = (nextCampaignId: string) => {
  closeGenerationPanel()
  openCampaign(nextCampaignId)
}

const handleWorkflowCompleted = (result: WorkflowResult) => {
  closeCampaignPanel()
  openWorkflowResult(result)
}

const handleGeneratedCandidate = (candidate: GeneratedCandidate) => {
  selectCandidate(candidate)
  setMaterial({
    formula: candidate.formula,
    material_id: candidate.material_id,
    band_gap: null,
    is_magnetic: null,
    formation_energy: null,
    cif: candidate.cif,
    density: candidate.density,
    spacegroup_symbol: candidate.spacegroup_symbol,
    spacegroup_number: candidate.spacegroup_number,
    crystal_system: candidate.crystal_system,
    formula_unit: candidate.formula_unit,
    magnetic_ordering: null,
    elements: candidate.elements,
    pretty_formula: candidate.pretty_formula,
  })
}
</script>

<template>
  <div class="immersive-container">
    <!-- Full-screen 3D Crystal Viewer (Background Layer) -->
    <CrystalViewer
      :cif-data="currentMaterial?.cif ?? null"
      :is-loading="isLoading"
    />

    <!-- Floating Search Bar - Top Center -->
    <div class="search-overlay">
      <el-card shadow="always" class="search-card">
        <div class="search-content">
          <span class="search-logo">🔬</span>
          <SearchBar @search="handleSearch" />
        </div>
      </el-card>
    </div>

    <!-- Error Alert -->
    <Transition name="fade">
      <div v-if="error" class="error-overlay">
        <el-alert
          :title="error"
          type="error"
          :closable="true"
          show-icon
        />
      </div>
    </Transition>

    <!-- Empty State Hint -->
    <Transition name="fade">
      <div v-if="!currentMaterial && !isLoading && !error" class="hint-overlay">
        <el-card shadow="always" class="hint-card">
          <div class="hint-icon">🔬</div>
          <h2 class="hint-title">材料结构可视化沙盘</h2>
          <p class="hint-desc">
            输入化学式搜索材料，或与 AI 助手对话查询
          </p>
          <div class="hint-tags">
            <el-tag
              v-for="formula in ['Nd2Fe14B', 'Fe3O4', 'LiCoO2', 'SiO2']"
              :key="formula"
              class="hint-tag"
              effect="plain"
              @click="handleSearch(formula)"
            >
              {{ formula }}
            </el-tag>
          </div>
        </el-card>
      </div>
    </Transition>

    <!-- Material Data Panel - Left Side Drawer -->
    <Transition name="slide-right">
      <div v-if="currentMaterial" class="content-overlay">
        <MaterialPanel
          :material="currentMaterial"
          :is-loading="isLoading"
          @close="handleClosePanel"
        />

      </div>
    </Transition>

    <!-- Bottom Hint - Centered -->
    <div class="bottom-hint">
      <el-text type="info" size="small">
        🖱️ 拖拽旋转 · 滚轮缩放 · 右键平移
      </el-text>
    </div>

    <!-- MatterGen Candidate Panel -->
    <GenerationPanel
      v-if="generationPanelOpen"
      @select-candidate="handleGeneratedCandidate"
      @close="closeGenerationPanel"
    />

    <CampaignPanel
      v-if="campaignPanelOpen"
      @select-candidate="handleGeneratedCandidate"
      @close="closeCampaignPanel"
    />

    <el-button
      v-if="generationJobId && !generationPanelOpen && !campaignId"
      class="generation-reopen"
      :icon="Grid"
      @click="reopenGenerationPanel"
    >
      候选列表 {{ generatedCandidates.length }}
    </el-button>

    <el-button
      v-if="campaignId && !campaignPanelOpen"
      class="generation-reopen campaign-reopen"
      :icon="Grid"
      @click="reopenCampaignPanel"
    >
      多模型任务
    </el-button>

    <!-- AI Assistant (Top Layer) -->
    <AIAssistant
      @material-found="handleMaterialFound"
      @generation-started="handleGenerationStarted"
      @campaign-started="handleCampaignStarted"
      @workflow-completed="handleWorkflowCompleted"
    />
  </div>
</template>

<style scoped>
.immersive-container {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

/* Search Bar Overlay */
.search-overlay {
  position: fixed;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-card {
  width: max-content;
}

.search-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-logo {
  font-size: 24px;
}

/* Error Overlay */
.error-overlay {
  position: fixed;
  top: 100px;
  left: 50%;
  width: min(520px, calc(100vw - 48px));
  transform: translateX(-50%);
  z-index: 40;
}

/* Hint Overlay */
.hint-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 25;
  pointer-events: none;
}

.hint-card {
  text-align: center;
  pointer-events: auto;
  max-width: 420px;
}

.hint-icon {
  font-size: 56px;
  margin-bottom: 16px;
  opacity: 0.8;
}

.hint-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
}

.hint-desc {
  font-size: 13px;
  margin: 0 0 24px;
  line-height: 1.6;
}

.hint-tags {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

.hint-tag {
  cursor: pointer;
  user-select: none;
}

/* Content Overlay */
.content-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  pointer-events: none;
}

.content-overlay > * {
  pointer-events: auto;
}

/* Bottom Hint - Centered */
.bottom-hint {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  pointer-events: none;
  user-select: none;
}

.generation-reopen {
  position: fixed;
  right: 24px;
  bottom: 98px;
  z-index: 40;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-right-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

.slide-right-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

@media (max-width: 640px) {
  .generation-reopen {
    right: 12px;
    bottom: 96px;
  }
}
</style>
