<!-- Adapted from pure-admin/vue-pure-admin ListCard.vue, MIT; pinned source in docs/upstream/pure-admin-card-list. -->
<script setup lang="ts">
import type { Template } from "@/api/business";
defineProps<{ product: Template; canCopy: boolean }>();
defineEmits<{
  preview: [product: Template];
  select: [product: Template];
  copy: [product: Template];
  edit: [product: Template];
}>();
</script>
<template>
  <div class="list-card-item">
    <div class="list-card-item_detail bg-bg_color">
      <button
        class="thumbnail"
        type="button"
        :aria-label="`预览${product.name}`"
        @click="$emit('preview', product)"
      >
        <el-image
          :src="`/api/v1/templates/${product.id}/thumbnail/?version=${product.latest_version?.id}`"
          fit="contain"
          loading="lazy"
          ><template #error><span>点击查看模板详情</span></template></el-image
        >
      </button>
      <el-row justify="space-between"
        ><el-tag size="small">{{ product.department_name }}</el-tag>
        <div class="list-card-item_detail--operation">
          <el-tag :type="product.published ? 'success' : 'info'" size="small"
            >{{ product.published ? "共享模板" : "部门模板" }} · v{{
              product.latest_version?.number
            }}</el-tag
          >
        </div></el-row
      >
      <p class="list-card-item_detail--name text-text_color_primary">
        <el-button link @click="$emit('preview', product)">{{
          product.name
        }}</el-button>
      </p>
      <p class="list-card-item_detail--desc text-text_color_regular">
        {{ product.latest_version?.canvas?.page?.width || 842 }} ×
        {{ product.latest_version?.canvas?.page?.height || 595 }} ·
        {{ product.latest_version?.canvas?.layers?.length || "默认" }} 个图层
      </p>
      <el-space wrap
        ><el-button size="small" @click="$emit('preview', product)"
          >预览</el-button
        ><el-button
          size="small"
          type="primary"
          :disabled="!product.published"
          @click="$emit('select', product)"
          >选用模板</el-button
        ><el-button v-if="canCopy" size="small" @click="$emit('copy', product)"
          >复制后编辑</el-button
        ><el-button size="small" link @click="$emit('edit', product)"
          >进入编辑器</el-button
        ></el-space
      >
    </div>
  </div>
</template>
<style lang="scss" scoped>
.list-card-item {
  display: flex;
  flex-direction: column;
  margin-bottom: 12px;
  overflow: hidden;
  cursor: pointer;
  border-radius: 3px;

  .thumbnail {
    display: block;
    width: 100%;
    height: 180px;
    margin: 0 0 16px;
    padding: 0;
    border: 0;
    background: var(--el-fill-color-light);
    cursor: pointer;
  }
  .thumbnail :deep(.el-image) {
    width: 100%;
    height: 100%;
  }
  &_detail {
    flex: 1;
    min-height: 140px;
    padding: 24px 32px;

    &--logo {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 46px;
      height: 46px;
      font-size: 26px;
      color: #0052d9;
      background: #e0ebff;
      border-radius: 50%;

      &__disabled {
        color: #a1c4ff;
      }
    }

    &--operation {
      display: flex;
      height: 100%;

      &--tag {
        border: 0;
      }
    }

    &--name {
      margin: 24px 0 8px;
      font-size: 16px;
      font-weight: 400;
    }

    &--desc {
      display: -webkit-box;
      height: 40px;
      margin-bottom: 24px;
      overflow: hidden;
      text-overflow: ellipsis;
      -webkit-line-clamp: 2;
      font-size: 12px;
      line-height: 20px;
      -webkit-box-orient: vertical;
    }
  }

  &__disabled {
    .list-card-item_detail--name,
    .list-card-item_detail--desc {
      color: var(--el-text-color-disabled);
    }

    .list-card-item_detail--operation--tag {
      color: #bababa;
    }
  }
}
</style>
