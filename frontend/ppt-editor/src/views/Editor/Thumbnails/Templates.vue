<script setup lang="ts">
import CertificateLayouts from '@/components/CertificateLayouts.vue'
defineEmits<{ selected: [] }>()
</script>
<template><CertificateLayouts insert-only @selected="$emit('selected')" /></template>
