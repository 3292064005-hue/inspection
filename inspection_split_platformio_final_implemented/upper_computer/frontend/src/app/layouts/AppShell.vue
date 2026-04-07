<script setup lang="ts">
import { RouterView } from 'vue-router';
import TopStatusBar from '@/widgets/TopStatusBar.vue';
import SideNavigation from '@/widgets/SideNavigation.vue';
import NoticeStack from '@/widgets/NoticeStack.vue';
import ConfirmDialog from '@/widgets/ConfirmDialog.vue';
import AuthGate from '@/widgets/AuthGate.vue';
</script>

<template>
  <div class="min-h-screen">
    <TopStatusBar />
    <div class="mx-auto flex max-w-[1920px] gap-4 px-4 pb-4 pt-2">
      <SideNavigation />
      <main class="min-h-[calc(100vh-88px)] flex-1 overflow-hidden rounded-3xl border border-slate-800/70 bg-slate-950/50 p-4">
        <RouterView />
      </main>
    </div>
    <NoticeStack />
    <ConfirmDialog />
    <AuthGate />
  </div>
</template>
