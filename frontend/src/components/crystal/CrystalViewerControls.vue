<script setup lang="ts">
import { computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useCrystalViewSettings } from '../../composables/useCrystalViewSettings'

const emit = defineEmits<{
  resetView: []
}>()

const {
  settings,
  setPreset,
  setSupercell,
  resetSupercell,
  setShowUnitCell,
} = useCrystalViewSettings()

const preset = computed({
  get() {
    const { a, b, c } = settings.supercell
    return a === b && b === c && a <= 3 ? String(a) : 'custom'
  },
  set(value: string) {
    if (value === 'custom') {
      setSupercell({ a: 2, b: 1, c: 1 })
      return
    }
    setPreset(Number(value))
  },
})
</script>

<template>
  <el-card class="crystal-controls-card" shadow="always">
    <template #header>
      <el-text tag="b">晶胞显示</el-text>
    </template>

    <el-radio-group v-model="preset" size="small">
      <el-radio-button value="1">1×1×1</el-radio-button>
      <el-radio-button value="2">2×2×2</el-radio-button>
      <el-radio-button value="3">3×3×3</el-radio-button>
      <el-radio-button value="custom">自定义</el-radio-button>
    </el-radio-group>

    <el-form label-position="top" size="small" class="axis-form">
      <el-row :gutter="8">
        <el-col :span="8">
          <el-form-item label="a">
            <el-input-number
              :model-value="settings.supercell.a"
              :min="1"
              :max="4"
              controls-position="right"
              class="axis-input"
              @update:model-value="setSupercell({ a: Number($event) })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="b">
            <el-input-number
              :model-value="settings.supercell.b"
              :min="1"
              :max="4"
              controls-position="right"
              class="axis-input"
              @update:model-value="setSupercell({ b: Number($event) })"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="c">
            <el-input-number
              :model-value="settings.supercell.c"
              :min="1"
              :max="4"
              controls-position="right"
              class="axis-input"
              @update:model-value="setSupercell({ c: Number($event) })"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <el-space wrap>
      <el-checkbox
        :model-value="settings.showUnitCell"
        @update:model-value="setShowUnitCell(Boolean($event))"
      >
        晶胞边框
      </el-checkbox>
      <el-button size="small" :icon="Refresh" @click="emit('resetView')">
        重置视角
      </el-button>
      <el-button size="small" @click="resetSupercell">
        恢复单胞
      </el-button>
    </el-space>
  </el-card>
</template>

<style scoped>
.crystal-controls-card {
  width: min(380px, calc(100vw - 24px));
}

.axis-form {
  margin-top: 12px;
}

.axis-input {
  width: 100%;
}
</style>
