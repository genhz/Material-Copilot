<script setup lang="ts">
import { ref } from 'vue'
import { Grid, Sunny, Moon } from '@element-plus/icons-vue'
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

interface Props {
  isDarkMode: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  toggleTheme: []
}>()

const {
  currentMaterial,
  isLoading,
  error,
  doSearch,
  setMaterial,
} = useMaterialSearch()

const showCharts = ref(false)
const {
  jobId: generationJobId,
  candidates: generatedCandidates,
  panelOpen: generationPanelOpen,
  openGeneration,
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

const handleThemeToggle = () => {
  emit('toggleTheme')
}

const handleGenerationStarted = (jobId: string) => {
  closeCampaignPanel()
  openGeneration(jobId)
}

const handleCampaignStarted = (nextCampaignId: string) => {
  closeGenerationPanel()
  openCampaign(nextCampaignId)
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
      :is-dark-mode="isDarkMode"
    />

    <!-- Floating Search Bar - Top Center -->
    <div class="search-overlay">
      <div class="search-bar-wrapper">
        <span class="search-logo">🔬</span>
        <SearchBar @search="handleSearch" />
      </div>
    </div>

    <!-- Theme Toggle - Top Right -->
    <div class="theme-toggle">
      <el-switch
        :model-value="isDarkMode"
        :active-action-icon="Moon"
        :inactive-action-icon="Sunny"
        @update:model-value="handleThemeToggle"
      />
    </div>

    <!-- Error Alert -->
    <Transition name="fade">
      <div v-if="error" class="error-overlay">
        <el-alert
          :title="error"
          type="error"
          :closable="true"
          show-icon
          class="error-alert"
        />
      </div>
    </Transition>

    <!-- Empty State Hint -->
    <Transition name="fade">
      <div v-if="!currentMaterial && !isLoading && !error" class="hint-overlay">
        <div class="hint-card">
          <div class="hint-icon">🔬</div>
          <h2 class="hint-title">材料结构可视化沙盘</h2>
          <p class="hint-desc">
            输入化学式搜索材料，或与 AI 助手对话查询
          </p>
          <div class="hint-tags">
            <span class="hint-tag" @click="handleSearch('Nd2Fe14B')">Nd₂Fe₁₄B</span>
            <span class="hint-tag" @click="handleSearch('Fe3O4')">Fe₃O₄</span>
            <span class="hint-tag" @click="handleSearch('LiCoO2')">LiCoO₂</span>
            <span class="hint-tag" @click="handleSearch('SiO2')">SiO₂</span>
          </div>
        </div>
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

        <!-- Charts Panel - Right Side -->
        <div class="charts-panel">
          <div class="charts-toggle">
            <el-button
              :type="showCharts ? 'primary' : 'default'"
              size="small"
              @click="showCharts = !showCharts"
            >
              {{ showCharts ? '隐藏图表' : '显示图表' }}
            </el-button>
          </div>
          <Transition name="slide-up">
            <div v-if="showCharts" class="charts-card">
              <div class="charts-header">
                <el-icon :size="18" color="#818cf8"><TrendCharts /></el-icon>
                <span>物性分析图表</span>
              </div>
              <div class="charts-content">
                <div class="chart-item">
                  <div class="chart-label">
                    <span class="chart-dot" style="background: #6366f1;"></span>
                    带隙
                  </div>
                  <div class="chart-value">
                    {{ currentMaterial?.band_gap != null ? `${currentMaterial.band_gap.toFixed(3)} eV` : 'N/A' }}
                  </div>
                </div>
                <div class="chart-item">
                  <div class="chart-label">
                    <span class="chart-dot" style="background: #8b5cf6;"></span>
                    生成能
                  </div>
                  <div class="chart-value">
                    {{ currentMaterial?.formation_energy != null ? `${currentMaterial.formation_energy.toFixed(4)} eV/atom` : 'N/A' }}
                  </div>
                </div>
                <div class="chart-item">
                  <div class="chart-label">
                    <span class="chart-dot" style="background: #a78bfa;"></span>
                    密度
                  </div>
                  <div class="chart-value">
                    {{ currentMaterial?.density != null ? `${currentMaterial.density.toFixed(2)} g/cm³` : 'N/A' }}
                  </div>
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </Transition>

    <!-- Bottom Hint - Centered -->
    <div class="bottom-hint">
      🖱️ 拖拽旋转 · 滚轮缩放 · 右键平移
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

    <button
      v-if="generationJobId && !generationPanelOpen && !campaignId"
      class="generation-reopen"
      type="button"
      @click="reopenGenerationPanel"
    >
      <el-icon :size="18"><Grid /></el-icon>
      <span>候选列表 {{ generatedCandidates.length }}</span>
    </button>

    <button
      v-if="campaignId && !campaignPanelOpen"
      class="generation-reopen campaign-reopen"
      type="button"
      @click="reopenCampaignPanel"
    >
      <el-icon :size="18"><Grid /></el-icon>
      <span>多模型任务</span>
    </button>

    <!-- AI Assistant (Top Layer) -->
    <AIAssistant
      @material-found="handleMaterialFound"
      @generation-started="handleGenerationStarted"
      @campaign-started="handleCampaignStarted"
    />
  </div>
</template>

<script lang="ts">
import { TrendCharts } from '@element-plus/icons-vue'
export default { components: { TrendCharts } }
</script>

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

.search-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(20px) saturate(150%);
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  padding: 10px 16px 10px 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.search-logo {
  font-size: 24px;
}

/* Theme Toggle */
.theme-toggle {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 50;
}

.theme-toggle :deep(.el-switch) {
  --el-switch-on-color: #6366f1;
  --el-switch-off-color: #fbbf24;
}

/* Error Overlay */
.error-overlay {
  position: fixed;
  top: 100px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
}

.error-alert {
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
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
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(20px) saturate(150%);
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 24px;
  padding: 40px 48px;
  text-align: center;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
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
  color: #e2e8f0;
  margin: 0 0 8px;
}

.hint-desc {
  font-size: 13px;
  color: #64748b;
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
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 20px;
  color: #a5b4fc;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.hint-tag:hover {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.4);
  color: #c7d2fe;
  transform: translateY(-2px);
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

/* Charts Panel */
.charts-panel {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 25;
  width: 420px;
}

.charts-toggle {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.charts-card {
  background: rgba(15, 23, 42, 0.88);
  backdrop-filter: blur(20px) saturate(150%);
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.charts-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e2e8f0;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.15);
}

.charts-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chart-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: rgba(51, 65, 85, 0.4);
  border-radius: 10px;
}

.chart-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: 13px;
}

.chart-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.chart-value {
  color: #e2e8f0;
  font-size: 14px;
  font-weight: 600;
}

/* Bottom Hint - Centered */
.bottom-hint {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  color: rgba(148, 163, 184, 0.7);
  font-size: 13px;
  pointer-events: none;
  user-select: none;
  backdrop-filter: blur(4px);
  padding: 6px 16px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.3);
}

.generation-reopen {
  position: fixed;
  right: 24px;
  bottom: 98px;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  color: #e2e8f0;
  background: rgba(15, 23, 42, 0.92);
  border: 1px solid rgba(99, 102, 241, 0.32);
  border-radius: 12px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  cursor: pointer;
  backdrop-filter: blur(16px);
}

.generation-reopen:hover {
  border-color: rgba(129, 140, 248, 0.6);
  background: rgba(30, 41, 59, 0.96);
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

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-up-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

@media (max-width: 640px) {
  .generation-reopen {
    right: 12px;
    bottom: 96px;
  }
}
</style>
