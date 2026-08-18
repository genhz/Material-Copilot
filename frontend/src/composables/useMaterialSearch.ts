/**
 * 材料搜索 Composable
 * 管理当前选中的材料数据
 */
import { ref, computed } from 'vue'
import type { MaterialData } from '../types/material'
import { searchMaterial } from '../api/material'

const currentMaterial = ref<MaterialData | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)

export function useMaterialSearch() {
  const hasMaterial = computed(() => currentMaterial.value !== null)

  /**
   * 搜索材料
   */
  async function doSearch(formula: string) {
    console.log('[useMaterialSearch] doSearch called with:', formula)
    if (!formula.trim()) {
      console.warn('[useMaterialSearch] Empty formula')
      return
    }
    isLoading.value = true
    error.value = null
    try {
      console.log('[useMaterialSearch] Calling searchMaterial...')
      const data = await searchMaterial(formula.trim())
      console.log('[useMaterialSearch] Search succeeded:', data.formula)
      currentMaterial.value = data
    } catch (e: any) {
      console.error('[useMaterialSearch] Search failed:', e.message)
      error.value = e.message || '查询失败'
      currentMaterial.value = null
    } finally {
      isLoading.value = false
      console.log('[useMaterialSearch] Loading finished')
    }
  }

  /**
   * 直接设置材料数据（用于 AI 查询结果）
   */
  function setMaterial(data: MaterialData | null | undefined) {
    console.log('[useMaterialSearch] setMaterial called:', data?.formula)
    currentMaterial.value = data ?? null
    error.value = null
  }

  /**
   * 清除当前材料
   */
  function clearMaterial() {
    currentMaterial.value = null
    error.value = null
  }

  return {
    currentMaterial,
    isLoading,
    error,
    hasMaterial,
    doSearch,
    setMaterial,
    clearMaterial,
  }
}
