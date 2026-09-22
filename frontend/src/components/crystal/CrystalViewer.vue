<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import CrystalViewerControls from './CrystalViewerControls.vue'
import { MolstarAdapter } from '../../services/molstarAdapter'
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

let lastCif: string | null = null
let renderQueue = Promise.resolve()

const showControls = computed(() => Boolean(props.cifData))
const showLoading = computed(
  () => props.isLoading || !viewerReady.value || isRendering.value
)

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

    <Transition name="slide-up">
      <div v-if="showControls" class="crystal-controls-overlay">
        <CrystalViewerControls @reset-view="resetView" />
      </div>
    </Transition>
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
  bottom: 58px;
  left: 50%;
  z-index: 32;
  transform: translateX(-50%);
}

.fade-enter-active,
.fade-leave-active,
.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translate(-50%, 14px);
}

@media (max-width: 640px) {
  .crystal-controls-overlay {
    bottom: 52px;
    width: calc(100vw - 24px);
  }
}
</style>
