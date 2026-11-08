<!-- Adapted from pure-admin/vue-pure-admin ListCard.vue, MIT; pinned source in docs/upstream/pure-admin-card-list. -->
<script setup lang="ts">
import type { Template } from "@/api/business";
import PreparedPreview from "@/components/PreparedPreview.vue";
defineProps<{ product: Template; canCopy: boolean; checked?: boolean }>();
function layerCount(product: Template) {
  return product.latest_version?.summary?.element_count || 0;
}
defineEmits<{
  preview: [product: Template];
  select: [product: Template];
  copy: [product: Template];
  edit: [product: Template];
  check: [product: Template, checked: boolean];
}>();
</script>
<template>
  <div class="list-card-item">
    <div class="list-card-item_detail bg-bg_color">
      <el-checkbox
        :model-value="checked"
        :aria-label="`选择模板${product.name}`"
        @change="$emit('check', product, Boolean($event))"
        >选择模板</el-checkbox
      >
      <div
        class="thumbnail"
        role="button"
        tabindex="0"
        :aria-label="`预览${product.name}`"
        @click="$emit('preview', product)"
        @keydown.enter.self="$emit('preview', product)"
        @keydown.space.self.prevent="$emit('preview', product)"
      >
        <PreparedPreview
          v-if="product.latest_version"
          :version="product.latest_version.id"
          :alt="product.name"
        />
      </div>
      <el-row justify="space-between" class="card-meta"
        ><el-tag
          size="small"
          class="department-tag"
          :title="product.department_name"
          >{{ product.department_name }}</el-tag
        >
        <div class="list-card-item_detail--operation">
          <el-tag :type="product.published ? 'success' : 'info'" size="small"
            >{{ product.published ? "共享模板" : "部门模板" }} · v{{
              product.latest_version?.number
            }}</el-tag
          >
        </div></el-row
      >
      <p class="list-card-item_detail--name text-text_color_primary">
        <el-button
          link
          :title="product.name"
          @click="$emit('preview', product)"
          >{{ product.name }}</el-button
        >
      </p>
      <p class="list-card-item_detail--desc text-text_color_regular">
        {{ product.latest_version?.summary?.page?.width || 842 }} ×
        {{ product.latest_version?.summary?.page?.height || 595 }} ·
        {{ layerCount(product) }} 个元素
      </p>
      <div class="card-actions">
        <el-button size="small" @click="$emit('preview', product)"
          >预览</el-button
        ><el-button
          size="small"
          type="primary"
          :disabled="!product.published"
          @click="$emit('select', product)"
          >选用模板</el-button
        ><el-button v-if="canCopy" size="small" @click="$emit('copy', product)"
          >复制后编辑</el-button
        ><el-button
          v-if="canCopy"
          size="small"
          link
          @click="$emit('edit', product)"
          >进入编辑器</el-button
        >
      </div>
    </div>
  </div>
</template>
<style lang="scss" scoped>
.list-card-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  margin-bottom: 16px;
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
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
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
      flex-shrink: 0;

      &--tag {
        border: 0;
      }
    }

    &--name {
      height: 48px;
      margin: 16px 0 8px;
      overflow: hidden;
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
.card-meta {
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  height: 24px;
}
.department-tag {
  min-width: 0;
}
.department-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
}
.list-card-item_detail--name :deep(.el-button) {
  display: block;
  width: 100%;
  height: 48px;
  white-space: normal;
  text-align: left;
}
.list-card-item_detail--name :deep(.el-button > span) {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 24px;
}
.card-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 28px;
  gap: 8px;
  margin-top: auto;
}
.card-actions :deep(.el-button) {
  width: 100%;
  margin: 0;
}
@media (max-width: 700px) {
  .list-card-item_detail {
    padding: 20px;
  }
}
</style>
