<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';
import AppShell from '@/app/layouts/AppShell.vue';
import { useHmiBootstrap } from '@/features/bootstrap/useHmiBootstrap';

const { start, stop } = useHmiBootstrap();

onMounted(() => {
  void start();
});

onBeforeUnmount(() => {
  stop();
});
</script>

<template>
  <AppShell />
</template>
