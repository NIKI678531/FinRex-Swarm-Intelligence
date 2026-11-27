<template>
  <header class="hv2-nav">
    <div class="hv2-nav__brand" @click="$router.push('/')">
      <span class="brand-square"></span>
      FINREX
      <span class="brand-meta">REV 2.0 · BLUEPRINT</span>
    </div>

    <nav class="hv2-nav__ports">
      <slot />
    </nav>
  </header>
</template>

<script setup>
</script>

<style scoped>
.hv2-nav {
  display: flex; align-items: center; justify-content: space-between;
  height: 64px;
  padding: 0 var(--s-6);
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-border);
  position: sticky; top: 0; z-index: 20;
}
.hv2-nav__brand {
  display: inline-flex; align-items: center; gap: 10px;
  font-weight: 700; letter-spacing: .12em;
  color: var(--c-brand);
  cursor: pointer;
}
.brand-square {
  display: inline-block; width: 14px; height: 14px;
  background: linear-gradient(135deg, var(--c-accent) 0%, var(--c-brand) 100%);
  border-radius: 3px;
}
.brand-meta {
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .14em;
  color: var(--c-text-subtle);
  font-weight: 500;
  margin-left: 6px;
  padding-left: 10px;
  border-left: 1px solid var(--c-border);
}

.hv2-nav__ports { display: inline-flex; gap: 10px; align-items: center; }

.port-btn {
  display: inline-flex; align-items: center; gap: 8px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--c-border-strong);
  border-radius: 999px;
  background: var(--c-bg);
  color: var(--c-text);
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  transition: border-color .2s ease, background .2s ease, transform .15s ease;
}
.port-btn:hover {
  border-color: var(--c-brand);
  background: var(--c-accent-soft);
  transform: translateY(-1px);
}
.port-tag {
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .12em;
  color: var(--c-accent);
  background: var(--c-accent-soft);
  padding: 2px 6px;
  border-radius: 4px;
}
.port-label { color: var(--c-text); }
.port-arrow { color: var(--c-text-subtle); font-weight: 400; }
.port-btn:hover .port-arrow { color: var(--c-brand); }

.port-sep {
  display: inline-block; width: 1px; height: 22px;
  background: var(--c-border);
  margin: 0 4px;
}
</style>
