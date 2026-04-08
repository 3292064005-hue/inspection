<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>

<template>
  <section class="panel h-full p-4">
    <div class="mb-4 flex items-start justify-between gap-3">
      <div>
        <h3 class="panel-title">{{ title }}</h3>
        <p v-if="subtitle" class="panel-subtitle mt-1">{{ subtitle }}</p>
      </div>
      <slot name="actions" />
    </div>
    <div class="h-[calc(100%-48px)]">
      <slot />
    </div>
  </section>
</template>
