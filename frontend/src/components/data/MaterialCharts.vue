<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { DataAnalysis } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { MaterialData } from '../../types/material'

interface Props {
  material: MaterialData | null
}

const props = defineProps<Props>()

const radarChartRef = ref<HTMLElement | null>(null)
const barChartRef = ref<HTMLElement | null>(null)

let radarChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null

const initCharts = () => {
  if (radarChartRef.value) {
    radarChart = echarts.init(radarChartRef.value, undefined, { renderer: 'canvas' })
  }
  if (barChartRef.value) {
    barChart = echarts.init(barChartRef.value, undefined, { renderer: 'canvas' })
  }
}

const updateCharts = () => {
  const m = props.material
  if (!m) return

  // 雷达图：综合物性对比
  if (radarChart) {
    const bandGapValue = m.band_gap !== null ? Math.min(m.band_gap / 5 * 100, 100) : 0
    const formationEnergyValue = m.formation_energy !== null
      ? Math.max((m.formation_energy + 3) / 3 * 50, 0)
      : 0

    radarChart.setOption({
      title: { text: '物性雷达图', left: 'center', textStyle: { color: '#64748b', fontSize: 14 } },
      tooltip: {},
      radar: {
        indicator: [
          { name: '带隙', max: 100 },
          { name: '结构稳定性', max: 100 },
          { name: '磁性指数', max: 100 },
        ],
        radius: '65%',
        axisName: { color: '#64748b', fontSize: 12 },
      },
      series: [{
        type: 'radar',
        data: [{
          value: [
            bandGapValue,
            formationEnergyValue,
            m.is_magnetic ? 85 : 15,
          ],
          name: m.formula,
          areaStyle: { color: 'rgba(99, 102, 241, 0.2)' },
          lineStyle: { color: '#6366f1', width: 2 },
          itemStyle: { color: '#6366f1' },
        }],
      }],
    })
  }

  // 柱状图：数值对比
  if (barChart) {
    barChart.setOption({
      title: { text: '关键数值', left: 'center', textStyle: { color: '#64748b', fontSize: 14 } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '15%', right: '5%', bottom: '15%', top: '25%' },
      xAxis: {
        type: 'category',
        data: ['带隙 (eV)', '形成能 (eV/atom)'],
        axisLabel: { color: '#64748b', fontSize: 11 },
        axisLine: { lineStyle: { color: '#909399' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: [
        {
          name: '带隙',
          type: 'bar',
          data: [m.band_gap !== null ? m.band_gap : 0],
          itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
          label: {
            show: true,
            position: 'top',
            formatter: (params: any) => params.value.toFixed(3),
            color: '#3b82f6',
            fontSize: 11,
          },
        },
        {
          name: '形成能',
          type: 'bar',
          data: [m.formation_energy !== null ? m.formation_energy : 0],
          itemStyle: {
            color: m.formation_energy !== null && m.formation_energy < 0 ? '#10b981' : '#f59e0b',
            borderRadius: [4, 4, 0, 0],
          },
          label: {
            show: true,
            position: m.formation_energy !== null && m.formation_energy < 0 ? 'bottom' : 'top',
            formatter: (params: any) => params.value.toFixed(4),
            color: '#64748b',
            fontSize: 11,
          },
        },
      ],
    })
  }
}

watch(() => props.material, () => {
  nextTick(() => {
    updateCharts()
  })
})

onMounted(() => {
  nextTick(() => {
    initCharts()
    updateCharts()
  })
})

window.addEventListener('resize', () => {
  radarChart?.resize()
  barChart?.resize()
})

onBeforeUnmount(() => {
  radarChart?.dispose()
  barChart?.dispose()
})
</script>

<template>
  <div v-if="material" class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div ref="radarChartRef" class="w-full h-[250px] bg-white rounded-xl border border-gray-200"></div>
    <div ref="barChartRef" class="w-full h-[250px] bg-white rounded-xl border border-gray-200"></div>
  </div>
  <el-empty v-else description="暂无数据可展示" :image-size="60">
    <template #image>
      <el-icon :size="50" color="#9ca3af"><DataAnalysis /></el-icon>
    </template>
  </el-empty>
</template>
