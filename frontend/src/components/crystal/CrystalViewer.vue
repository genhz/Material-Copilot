<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'

interface Props {
  cifData: string | null
  isLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  cifData: null,
  isLoading: false,
})

const containerRef = ref<HTMLElement | null>(null)
let viewer: any = null

// 元素颜色映射 (Jmol 配色方案)
const elementColors: Record<string, string> = {
  H: '#FFFFFF', He: '#D9FFFF',
  Li: '#CC80FF', Be: '#C2FF00', B: '#FFB5B5', C: '#909090',
  N: '#3050F8', O: '#FF0D0D', F: '#90E050', Ne: '#B3E3F5',
  Na: '#AB5CF2', Mg: '#8AFF00', Al: '#BFA6A6', Si: '#F0C8A0',
  P: '#FF8000', S: '#FFFF30', Cl: '#1FF01F', Ar: '#80D1E3',
  K: '#8F40D4', Ca: '#3DFF00', Sc: '#E6E6E6', Ti: '#BFC2C7',
  V: '#A6A6AB', Cr: '#8A99C7', Mn: '#9C7AC7', Fe: '#E06633',
  Co: '#F090A0', Ni: '#50D050', Cu: '#C88033', Zn: '#7D80B0',
  Ga: '#C28F8F', Ge: '#668F8F', As: '#BD80E3', Se: '#FFA100',
  Br: '#A62929', Kr: '#5CB8D1',
  Rb: '#702EB0', Sr: '#00FF00', Y: '#94FFFF', Zr: '#94E0E0',
  Nb: '#73C2C9', Mo: '#54B5B5', Tc: '#3B9E9E', Ru: '#248F8F',
  Rh: '#0A7D8C', Pd: '#006985', Ag: '#C0C0C0', Cd: '#FFD98F',
  In: '#A67573', Sn: '#668080', Sb: '#9E63B5', Te: '#D47A00',
  I: '#940094', Xe: '#429EB0',
  Cs: '#57178F', Ba: '#00C900', La: '#70D4FF', Ce: '#FFFFC7',
  Pr: '#D9FFC7', Nd: '#C7FFC7', Pm: '#A3FFC7', Sm: '#8FFFC7',
  Eu: '#61FFC7', Gd: '#45FFC7', Tb: '#30FFC7', Dy: '#1FFFC7',
  Ho: '#00FF9C', Er: '#00E675', Tm: '#00D452', Yb: '#00BF38',
  Lu: '#00AB24', Hf: '#4DC2FF', Ta: '#4DA6FF', W: '#2194D6',
  Re: '#267DAB', Os: '#266696', Ir: '#175487', Pt: '#D0D0E0',
  Au: '#FFD123', Hg: '#B8B8D0', Tl: '#A6544D', Pb: '#575961',
  Bi: '#9E4FB5', Po: '#AB5C00', At: '#754F45', Rn: '#428296',
}

// 获取元素符号 (从原子标签中提取)
function getElementSymbol(label: string): string {
  const match = label.match(/^([A-Z][a-z]?)/)
  return match ? match[1] : label
}

const initViewer = async () => {
  if (!containerRef.value) return
  await nextTick()

  if (typeof ($3Dmol as any) !== 'undefined') {
    viewer = ($3Dmol as any).createViewer(containerRef.value, {
      backgroundColor: '#0f172a',
      disableCartoon: true,
      antialias: true,
      orthographic: false,
    })

    if (!props.cifData) {
      viewer.addLabel('等待加载晶体结构...', {
        position: { x: 0, y: 0, z: 0 },
        fontSize: 20,
        fontColor: '#64748b',
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
      })
      viewer.render()
    }
  } else {
    console.error('$3Dmol not loaded')
  }
}

watch(
  () => props.cifData,
  async (newCif) => {
    if (!viewer || !newCif) return
    await nextTick()
    viewer.clear()

    try {
      viewer.addModel(newCif, 'cif')

      // 球棍模型
      viewer.setStyle({}, {
        sphere: { radius: 0.35, scale: 0.8 },
        stick: { radius: 0.12 },
      })

      // 添加元素标签
      const model = viewer.getModel()
      if (model) {
        const atoms = model.atoms
        atoms.forEach((atom: any) => {
          const elem = getElementSymbol(atom.elem)
          const color = elementColors[elem] || '#FFFFFF'

          viewer.addLabel(elem, {
            position: { x: atom.x, y: atom.y, z: atom.z },
            fontSize: 14,
            fontColor: color,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            borderColor: color,
            borderWidth: 1,
            padding: 3,
          })
        })
      }

      viewer.zoomTo()
      viewer.addUnitCell()
      viewer.render()
    } catch (e) {
      console.error('Failed to render CIF structure:', e)
      viewer.addLabel('结构渲染失败', {
        position: { x: 0, y: 0, z: 0 },
        fontSize: 16,
        fontColor: '#ef4444',
      })
      viewer.render()
    }
  }
)

onMounted(() => {
  initViewer()
  // 窗口大小变化时重绘
  window.addEventListener('resize', () => {
    if (viewer) viewer.resize()
  })
})

onBeforeUnmount(() => {
  if (viewer) {
    viewer.clear()
    viewer = null
  }
})
</script>

<template>
  <div class="crystal-viewer-container">
    <div
      v-if="isLoading"
      class="loading-overlay"
    >
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <span class="loading-text">正在加载晶体结构...</span>
    </div>

    <div ref="containerRef" class="viewer-container"></div>

    <div class="hint-overlay">
      <span>🖱️ 拖拽旋转 · 滚轮缩放 · 右键平移</span>
    </div>
  </div>
</template>

<script lang="ts">
import { Loading } from '@element-plus/icons-vue'
export default { components: { Loading } }
</script>

<style scoped>
.crystal-viewer-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: #0f172a;
  overflow: hidden;
}

.viewer-container {
  width: 100%;
  height: 100%;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.loading-text {
  color: #94a3b8;
  margin-top: 16px;
  font-size: 14px;
}

.hint-overlay {
  position: absolute;
  bottom: 20px;
  right: 20px;
  background: rgba(0, 0, 0, 0.6);
  color: #94a3b8;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  backdrop-filter: blur(4px);
}
</style>
