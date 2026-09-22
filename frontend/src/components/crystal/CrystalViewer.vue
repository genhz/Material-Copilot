<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { Operation } from '@element-plus/icons-vue'
import CrystalViewerControls from './CrystalViewerControls.vue'
import {
  MolstarAdapter,
  type AtomHoverInfo,
} from '../../services/molstarAdapter'
import { useCrystalViewSettings } from '../../composables/useCrystalViewSettings'

interface Props {
  cifData: string | null
  isLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  cifData: null,
  isLoading: false,
})

const containerRef = ref<HTMLElement | null>(null)
const adapter = new MolstarAdapter()
const { settings, resetSupercell } = useCrystalViewSettings()

const viewerReady = ref(false)
const isRendering = ref(false)
const renderError = ref<string | null>(null)
const hoverInfo = ref<AtomHoverInfo | null>(null)
const controlsOpen = ref(false)

let lastCif: string | null = null
let renderQueue = Promise.resolve()

const showControls = computed(() => Boolean(props.cifData))
const showLoading = computed(
  () => props.isLoading || !viewerReady.value || isRendering.value
)
const tooltipStyle = computed(() => {
  if (!hoverInfo.value) return {}

  const tooltipWidth = 196
  const tooltipHeight = 84
  const offset = 14
  const padding = 8
  const maxX = Math.max(padding, window.innerWidth - tooltipWidth - padding)
  const maxY = Math.max(padding, window.innerHeight - tooltipHeight - padding)

  return {
    left: `${Math.min(hoverInfo.value.x + offset, maxX)}px`,
    top: `${Math.min(hoverInfo.value.y + offset, maxY)}px`,
  }
})

adapter.onHover = (info) => {
  hoverInfo.value = info
}

function queueRender() {
  renderQueue = renderQueue
    .then(async () => {
      if (!viewerReady.value) return
      const cif = props.cifData
      if (!cif) {
        await adapter.render('', settings)
        return
      }

      isRendering.value = true
      renderError.value = null
      try {
        await adapter.render(cif, settings)
      } catch (error: any) {
        console.error('[Molstar] Render failed:', error)
        renderError.value = error?.message || '晶体结构渲染失败'
      } finally {
        isRendering.value = false
      }
    })
    .catch((error) => {
      console.error('[Molstar] Render queue failed:', error)
    })
}

async function initializeViewer() {
  if (!containerRef.value) return
  await nextTick()

  try {
    await adapter.mount(containerRef.value)
    viewerReady.value = true
    lastCif = props.cifData
    queueRender()
  } catch (error: any) {
    console.error('[Molstar] Initialization failed:', error)
    renderError.value = error?.message || '3D 查看器初始化失败'
  }
}

watch(
  () => props.cifData,
  (cif) => {
    if (cif !== lastCif) {
      lastCif = cif
      controlsOpen.value = false
      resetSupercell()
    }
    queueRender()
  }
)

watch(
  settings,
  () => {
    queueRender()
  },
  { deep: true }
)

onMounted(() => {
  initializeViewer()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  adapter.dispose()
})

function handleResize() {
  adapter.resize()
}

function resetView() {
  adapter.resetView()
}

defineExpose({
  resetView,
})
</script>

<template>
  <div class="crystal-viewer-container">
    <div ref="containerRef" class="viewer-container"></div>

    <Transition name="atom-tooltip">
      <div
        v-if="hoverInfo && !showLoading"
        class="atom-tooltip"
        :style="tooltipStyle"
        aria-hidden="true"
      >
        <strong class="atom-tooltip-symbol">{{ hoverInfo.symbol }}</strong>
        <span v-if="hoverInfo.atomicNumber" class="atom-tooltip-meta">
          原子序数 {{ hoverInfo.atomicNumber }}
        </span>
        <span v-if="hoverInfo.atomId != null" class="atom-tooltip-meta">
          原子 ID {{ hoverInfo.atomId }}
        </span>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="showLoading" class="loading-overlay">
        <div class="loading-spinner"></div>
        <span class="loading-text">
          {{ isLoading ? '正在获取材料数据...' : '正在构建晶体结构...' }}
        </span>
      </div>
    </Transition>

    <div v-if="renderError" class="render-error">
      <el-alert
        :title="renderError"
        type="error"
        :closable="false"
        show-icon
      />
    </div>

    <Teleport to="body">
      <div v-if="showControls" class="crystal-controls-overlay">
        <Transition name="slide-up">
          <CrystalViewerControls
            v-if="controlsOpen"
            @reset-view="resetView"
          />
        </Transition>
        <el-button
          :type="controlsOpen ? 'primary' : 'default'"
          size="small"
          :icon="Operation"
          @click="controlsOpen = !controlsOpen"
        >
          {{ controlsOpen ? '隐藏晶胞' : '晶胞显示' }}
        </el-button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.crystal-viewer-container {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

.viewer-container {
  width: 100%;
  height: 100%;
}

.atom-tooltip {
  position: absolute;
  z-index: 12;
  display: flex;
  flex-direction: column;
  width: min(180px, calc(100vw - 16px));
  padding: 8px 10px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  pointer-events: none;
  user-select: none;
}

.atom-tooltip-symbol {
  font-size: 18px;
  line-height: 1.2;
}

.atom-tooltip-meta {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.3;
  color: var(--el-text-color-regular);
}

.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  background: var(--el-mask-color-extra-light);
  backdrop-filter: blur(8px);
}

.loading-text {
  margin-top: 16px;
  font-size: 14px;
}

.loading-spinner {
  width: 38px;
  height: 38px;
  border: 3px solid var(--el-color-primary-light-7);
  border-top-color: var(--el-color-primary);
  border-radius: 50%;
  animation: crystal-spin 0.8s linear infinite;
}

@keyframes crystal-spin {
  to {
    transform: rotate(360deg);
  }
}

.render-error {
  position: fixed;
  top: 96px;
  left: 50%;
  z-index: 40;
  width: min(520px, calc(100vw - 48px));
  transform: translateX(-50%);
}

.crystal-controls-overlay {
  position: fixed;
  right: 24px;
  bottom: 92px;
  z-index: 32;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  width: min(380px, calc(100vw - 24px));
}

.fade-enter-active,
.fade-leave-active,
.atom-tooltip-enter-active,
.atom-tooltip-leave-active,
.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.fade-enter-from,
.fade-leave-to,
.atom-tooltip-enter-from,
.atom-tooltip-leave-to {
  opacity: 0;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(14px);
}

@media (max-width: 640px) {
  .crystal-controls-overlay {
    left: 12px;
    right: 12px;
    bottom: 12px;
  }
}
</style>
