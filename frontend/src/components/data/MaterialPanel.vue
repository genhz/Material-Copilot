<script setup lang="ts">
import { computed } from 'vue'
import type { MaterialData } from '../../types/material'

interface Props {
  material: MaterialData | null
  isLoading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
}>()

const hasData = computed(() => !!props.material)

const formationEnergyText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.formation_energy != null
    ? `${props.material.formation_energy.toFixed(4)} eV/atom`
    : 'N/A'
})

const bandGapText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.band_gap != null
    ? `${props.material.band_gap.toFixed(3)} eV`
    : 'N/A'
})

const bandGapType = computed(() => {
  if (!props.material) return 'info'
  if (props.material.band_gap == null) return 'info'
  if (props.material.band_gap === 0) return 'danger'
  if (props.material.band_gap < 2.0) return 'warning'
  return 'success'
})

const densityText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.density != null
    ? `${props.material.density.toFixed(2)} g/cm³`
    : 'N/A'
})

const spaceGroupText = computed(() => {
  if (!props.material) return 'N/A'
  const sym = props.material.spacegroup_symbol
  const num = props.material.spacegroup_number
  if (sym && num != null) {
    return `${sym} (${num})`
  }
  return 'N/A'
})

const crystalSystemText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.crystal_system || 'N/A'
})

const formulaText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.pretty_formula || props.material.formula || 'N/A'
})

const formulaUnitText = computed(() => {
  if (!props.material) return 'N/A'
  return props.material.formula_unit != null
    ? `${props.material.formula_unit}`
    : 'N/A'
})

const elementsList = computed(() => {
  if (!props.material) return []
  return props.material.elements || []
})
</script>

<template>
  <div class="material-panel" :class="{ 'panel-visible': hasData }">
    <!-- Header -->
    <div class="panel-header">
      <div class="header-title">
        <span class="header-icon">🧊</span>
        <span class="header-text">晶体结构数据</span>
      </div>
      <el-button
        v-if="hasData"
        text
        :icon="Close"
        class="close-btn"
        @click="emit('close')"
      />
    </div>

    <!-- Content -->
    <div v-if="isLoading" class="panel-loading">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <span class="loading-text">正在获取材料数据...</span>
    </div>

    <div v-else-if="hasData && material" class="panel-content">
      <!-- Formula Section -->
      <div class="section">
        <div class="section-title">化学式</div>
        <div class="formula-display">{{ formulaText }}</div>
        <div class="formula-id">
          <el-tag size="small" type="info" effect="plain">
            {{ material.material_id }}
          </el-tag>
        </div>
      </div>

      <!-- Basic Properties -->
      <div class="section">
        <div class="section-title">基本性质</div>
        <el-descriptions :column="1" border size="small" class="descriptions">
          <el-descriptions-item label="空间群">
            <el-tag size="small" type="primary">{{ spaceGroupText }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="晶系">
            <el-tag size="small" type="info">{{ crystalSystemText }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="晶胞原子数">
            {{ formulaUnitText }}
          </el-descriptions-item>
          <el-descriptions-item label="密度">
            {{ densityText }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- Electronic Properties -->
      <div class="section">
        <div class="section-title">电子性质</div>
        <el-descriptions :column="1" border size="small" class="descriptions">
          <el-descriptions-item label="带隙">
            <el-tag :type="bandGapType" size="small">
              {{ bandGapText }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="生成能">
            {{ formationEnergyText }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- Magnetic Properties -->
      <div v-if="material.magnetic_ordering" class="section">
        <div class="section-title">磁性</div>
        <el-tag
          :type="material.magnetic_ordering === 'FM' ? 'danger' : 'warning'"
          size="small"
        >
          {{ material.magnetic_ordering }}
        </el-tag>
      </div>

      <!-- Elements -->
      <div v-if="elementsList.length > 0" class="section">
        <div class="section-title">组成元素</div>
        <div class="elements-list">
          <el-tag
            v-for="elem in elementsList"
            :key="elem"
            size="small"
            class="element-tag"
          >
            {{ elem }}
          </el-tag>
        </div>
      </div>
    </div>

    <div v-else class="panel-empty">
      <el-empty description="搜索材料以查看详情" :image-size="80" />
    </div>
  </div>
</template>

<script lang="ts">
import { Close, Loading } from '@element-plus/icons-vue'
export default { components: { Close, Loading } }
</script>

<style scoped>
.material-panel {
  position: fixed;
  top: 0;
  left: 0;
  width: 360px;
  height: 100vh;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(20px) saturate(150%);
  -webkit-backdrop-filter: blur(20px) saturate(150%);
  border-right: 1px solid rgba(99, 102, 241, 0.2);
  z-index: 20;
  display: flex;
  flex-direction: column;
  transform: translateX(-100%);
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.3);
}

.panel-visible {
  transform: translateX(0);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 16px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.15);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 20px;
}

.header-text {
  font-size: 16px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.5px;
}

.close-btn {
  color: #94a3b8;
}

.close-btn:hover {
  color: #f1f5f9;
}

.panel-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94a3b8;
}

.loading-text {
  font-size: 13px;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.panel-content::-webkit-scrollbar {
  width: 4px;
}

.panel-content::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.3);
  border-radius: 4px;
}

.section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #818cf8;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
}

.formula-display {
  font-size: 28px;
  font-weight: 700;
  padding: 16px 0 8px;
  text-align: center;
  background: linear-gradient(135deg, #818cf8, #c084fc);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.formula-id {
  text-align: center;
  margin-bottom: 8px;
}

.descriptions {
  --el-descriptions-item-label-background: rgba(99, 102, 241, 0.1);
  --el-descriptions-item-bordered-label-background: rgba(99, 102, 241, 0.1);
  --el-descriptions-border-color: rgba(99, 102, 241, 0.15);
  --el-descriptions-text-color: #cbd5e1;
}

.elements-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.element-tag {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.25);
  color: #a5b4fc;
}

.panel-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
