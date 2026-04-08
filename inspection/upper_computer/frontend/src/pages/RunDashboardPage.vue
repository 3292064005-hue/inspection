<script setup lang="ts">
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import ControlPanel from '@/widgets/ControlPanel.vue';
import EventTimeline from '@/widgets/EventTimeline.vue';
import FaultPanel from '@/widgets/FaultPanel.vue';
import LiveImagePanel from '@/widgets/LiveImagePanel.vue';
import ResultCard from '@/widgets/ResultCard.vue';
import SampleStrip from '@/widgets/SampleStrip.vue';
import StatsBoard from '@/widgets/StatsBoard.vue';
import StatusFlow from '@/widgets/StatusFlow.vue';
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <StatusFlow />
    <div class="grid flex-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
      <div class="flex min-h-0 flex-col gap-4">
        <ControlPanel />
        <FaultPanel />
      </div>

      <div class="min-h-0">
        <LiveImagePanel />
      </div>

      <div class="flex min-h-0 flex-col gap-4">
        <ResultCard />
        <StatsBoard />
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
      <SampleStrip />
      <EventTimeline />
    </div>
  </div>
</template>
