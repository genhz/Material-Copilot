<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

const emit = defineEmits<{
  search: [formula: string]
}>()

const inputFormula = ref('')

const handleSearch = () => {
  const formula = inputFormula.value.trim()
  if (formula) {
    emit('search', formula)
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    e.preventDefault()
    handleSearch()
  }
}
</script>

<template>
  <div class="search-bar flex items-center gap-2">
    <el-input
      v-model="inputFormula"
      placeholder="输入化学式，例如 Nd2Fe14B..."
      size="large"
      class="search-input"
      @keydown="handleKeydown"
    >
      <template #prefix>
        <el-icon :size="16"><Search /></el-icon>
      </template>
    </el-input>
    <el-button
      type="primary"
      size="large"
      @click="handleSearch"
    >
      查询
    </el-button>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 380px;
}

.search-input {
  min-width: 260px;
}
</style>
