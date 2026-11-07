<script setup lang="ts">
defineOptions({ inheritAttrs: false });
</script>
<template>
  <el-image v-bind="$attrs"
    ><template #placeholder
      ><el-skeleton animated
        ><template #template
          ><el-skeleton-item
            variant="image"
            style="
              width: 100%;
              height: 100%;
              min-height: 100px;
            " /></template></el-skeleton></template
    ><template #error
      ><slot name="error"
        ><div class="image-error">图片加载失败，请重试</div></slot
      ></template
    ></el-image
  >
</template>
<style scoped>
.image-error {
  display: grid;
  place-items: center;
  min-height: 100px;
  padding: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}
</style>
