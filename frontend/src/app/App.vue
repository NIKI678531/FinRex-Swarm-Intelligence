<template>
  <router-view />
</template>

<script setup>
// 使用 Vue Router 来管理页面
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #0f172a;
  background-color: #f8fbff;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #1e40af, #0ea5e9);
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>
