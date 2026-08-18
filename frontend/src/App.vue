<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import MainView from './components/MainView.vue'

const isDarkMode = ref(true)

onMounted(() => {
  // 从 localStorage 读取主题偏好
  const saved = localStorage.getItem('theme')
  if (saved === 'light') {
    isDarkMode.value = false
  } else if (saved === 'dark') {
    isDarkMode.value = true
  } else {
    // 跟随系统
    isDarkMode.value = window.matchMedia('(prefers-color-scheme: dark)').matches
  }
})

watch(isDarkMode, (dark) => {
  const el = document.documentElement
  if (dark) {
    el.classList.add('dark')
  } else {
    el.classList.remove('dark')
  }
  localStorage.setItem('theme', dark ? 'dark' : 'light')
}, { immediate: true })
</script>

<template>
  <MainView :is-dark-mode="isDarkMode" @toggle-theme="isDarkMode = !isDarkMode" />
</template>
