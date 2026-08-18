<script setup lang="ts">
import type { MaterialData } from '../../types/material'

interface Props {
  material: MaterialData | null
}

defineProps<Props>()

const getBandGapType = (v: number | null): 'success' | 'warning' | 'danger' | 'info' => {
  if (v === null) return 'info'
  if (v === 0) return 'danger'
  if (v < 1) return 'warning'
  return 'success'
}

const getBandGapLabel = (v: number | null): string => {
  if (v === null) return '未知'
  if (v === 0) return '金属'
  if (v < 1) return '半导体'
  return '绝缘体'
}

const getMagneticTag = (v: boolean | null) => {
  if (v === null) return { type: 'info' as const, text: '未知' }
  return v ? { type: 'warning' as const, text: '具有磁性' } : { type: 'success' as const, text: '无磁性' }
}

const getEnergyStatus = (v: number | null): 'success' | 'warning' | 'danger' | 'info' => {
  if (v === null) return 'info'
  if (v < -1.5) return 'success'
  if (v < 0) return 'warning'
  return 'danger'
}

const getEnergyLabel = (v: number | null): string => {
  if (v === null) return '未知'
  return v < 0 ? '稳定' : '亚稳'
}
</script>

<template>
  <div v-if="material" class="space-y-4">
    <!-- 标题区 -->
    <div class="flex items-center gap-3 pb-3 border-b border-gray-200">
      <el-tag type="primary" size="large" effect="dark">
        {{ material.formula }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        {{ material.material_id }}
      </el-tag>
    </div>

    <!-- 数据卡片网格 -->
    <el-row :gutter="16">
      <!-- 带隙 -->
      <el-col :span="12">
        <el-card shadow="hover" class="data-card">
          <template #header>
            <div class="flex justify-between items-center">
              <span class="text-gray-500 text-sm">带隙 (Band Gap)</span>
              <el-tag :type="getBandGapType(material.band_gap)" size="small">
                {{ getBandGapLabel(material.band_gap) }}
              </el-tag>
            </div>
          </template>
          <el-statistic :value="material.band_gap ?? 0" :precision="3" suffix="eV">
            <template #prefix>
              <el-icon v-if="material.band_gap === 0" color="#ef4444"><WarningFilled /></el-icon>
              <el-icon v-else-if="(material.band_gap ?? 100) < 1" color="#f59e0b"><Warning /></el-icon>
              <el-icon v-else color="#10b981"><CircleCheckFilled /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>

      <!-- 磁性 -->
      <el-col :span="12">
        <el-card shadow="hover" class="data-card">
          <template #header>
            <div class="flex justify-between items-center">
              <span class="text-gray-500 text-sm">磁性 (Magnetism)</span>
            </div>
          </template>
          <div class="flex items-center gap-2">
            <el-tag :type="getMagneticTag(material.is_magnetic).type" size="large">
              {{ getMagneticTag(material.is_magnetic).text }}
            </el-tag>
          </div>
        </el-card>
      </el-col>

      <!-- 形成能 -->
      <el-col :span="24">
        <el-card shadow="hover" class="data-card">
          <template #header>
            <div class="flex justify-between items-center">
              <span class="text-gray-500 text-sm">形成能 (Formation Energy)</span>
              <el-tag :type="getEnergyStatus(material.formation_energy)" size="small">
                {{ getEnergyLabel(material.formation_energy) }}
              </el-tag>
            </div>
          </template>
          <el-statistic :value="material.formation_energy ?? 0" :precision="4" suffix="eV/atom">
            <template #prefix>
              <el-icon v-if="material.formation_energy !== null && material.formation_energy < 0" color="#10b981"><SuccessFilled /></el-icon>
              <el-icon v-else color="#f59e0b"><WarningFilled /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <!-- 说明 -->
    <el-divider border-style="dashed" />
    <el-descriptions :column="1" size="small" border>
      <el-descriptions-item label="带隙说明">
        <el-text type="info" size="small">带隙为 0 表示材料为金属导体，0-1eV 为半导体，>1eV 为绝缘体</el-text>
      </el-descriptions-item>
      <el-descriptions-item label="形成能说明">
        <el-text type="info" size="small">形成能越负表示结构越稳定，负值越大越稳定</el-text>
      </el-descriptions-item>
    </el-descriptions>
  </div>

  <!-- 空状态 -->
  <el-empty v-else description="暂无材料数据" :image-size="80" />
</template>

<script lang="ts">
import { Warning, WarningFilled, CircleCheckFilled, SuccessFilled } from '@element-plus/icons-vue'
export default { components: { Warning, WarningFilled, CircleCheckFilled, SuccessFilled } }
</script>

<style scoped>
.data-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: linear-gradient(to right, #f8fafc, #f1f5f9);
}
.data-card :deep(.el-card__body) {
  padding: 16px;
}
</style>
