<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  shape: {
    kind: string;
    width: number;
    height: number;
    strokeWidth: number;
    stroke: string;
    fill: string;
    points?: number[][];
  };
}>();
const pad = computed(() => props.shape.strokeWidth / 2);
const points = computed(() =>
  (props.shape.points || [])
    .map(
      p =>
        `${pad.value + p[0] * (props.shape.width - pad.value * 2)},${pad.value + p[1] * (props.shape.height - pad.value * 2)}`
    )
    .join(" ")
);
</script>
<template>
  <svg
    width="100%"
    height="100%"
    :viewBox="`0 0 ${shape.width} ${shape.height}`"
    :stroke="shape.strokeWidth > 0 ? shape.stroke : 'none'"
    :stroke-width="shape.strokeWidth"
    stroke-linejoin="round"
    stroke-linecap="round"
    :fill="shape.fill"
  >
    <rect
      v-if="shape.kind === 'rect'"
      :x="pad"
      :y="pad"
      :width="Math.max(0, shape.width - pad * 2)"
      :height="Math.max(0, shape.height - pad * 2)"
    />
    <ellipse
      v-else-if="shape.kind === 'ellipse'"
      :cx="shape.width / 2"
      :cy="shape.height / 2"
      :rx="Math.max(0, shape.width / 2 - pad)"
      :ry="Math.max(0, shape.height / 2 - pad)"
    />
    <polyline v-else :points="points" fill="none" />
  </svg>
</template>
