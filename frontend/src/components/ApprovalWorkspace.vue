<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useWindowSize } from "@vueuse/core";
import { useBusinessAccess } from "@/utils/businessAccess";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  batchDetail,
  chooseApprovalSeal,
  decideApproval,
  listSeals,
  type Approval,
  type Seal
} from "@/api/business";
import { useModuleTask } from "@/composables/useModuleTask";
import { usePreparedFile } from "@/composables/usePreparedFile";
import { useLiveStore } from "@/store/modules/live";
import ModuleRegion from "./ModuleRegion.vue";
import SmartImage from "./SmartImage.vue";
import BulkActions from "./BulkActions.vue";
const props = defineProps<{
  modelValue: boolean;
  batchId?: number;
  requirementId?: number;
}>();
const emit = defineEmits<{ "update:modelValue": [boolean]; changed: [] }>();
const task = useModuleTask(),
  optionsTask = useModuleTask(),
  rosterTask = useModuleTask();
const { isAdmin } = useBusinessAccess();
const live = useLiveStore(),
  syncTask = useModuleTask();
const { width: windowWidth } = useWindowSize();
const data = ref<any>(),
  seals = ref<Seal[]>([]),
  busy = ref(false),
  page = ref(1),
  selectedRows = ref<any[]>([]),
  roster = ref();
const form = reactive({
  requirement: undefined as number | undefined,
  seal: undefined as number | undefined,
  decision: "approved",
  comment: "",
  issueRows: ""
});
const preview = usePreparedFile();
const previewChanged = ref(false);
const choices = computed<Approval[]>(() =>
  (data.value?.approvals || []).filter(
    (r: Approval) => r.can_review && !r.decision
  )
);
const requirement = computed(() =>
  choices.value.find(r => r.id === form.requirement)
);
const sealOptions = computed(() =>
  seals.value
    .filter(s => s.active && s.department === requirement.value?.department)
    .flatMap(s =>
      s.versions.map(v => ({
        id: v.id,
        label: `${s.name} · v${v.number}`,
        seal: s.id
      }))
    )
);
const stateLabel: Record<string, string> = {
  draft: "草稿",
  review: "部门会签中",
  returned: "已退回",
  queued: "等待生成",
  issued: "已签发",
  failed: "生成失败"
};
const total = computed(() => data.value?.approvals.length || 0);
const approved = computed(
  () =>
    data.value?.approvals.filter((r: Approval) => r.decision === "approved")
      .length || 0
);
watch(
  () => form.requirement,
  () => {
    form.seal = requirement.value?.seal_version || undefined;
    form.comment = "";
    form.issueRows = "";
    previewChanged.value = false;
  }
);
watch(
  () => form.seal,
  value => {
    previewChanged.value =
      !!requirement.value &&
      value !== (requirement.value.seal_version || undefined);
  }
);
async function load() {
  if (!props.batchId) return;
  const id = props.batchId;
  data.value = undefined;
  page.value = 1;
  try {
    await task.run(
      () => batchDetail(id),
      value => {
        if (!props.modelValue || props.batchId !== id) return;
        data.value = value;
        form.requirement =
          choices.value.find(r => r.id === props.requirementId)?.id ||
          choices.value[0]?.id;
        form.seal = requirement.value?.seal_version || undefined;
        if (value.award_count)
          preview.start({ kind: "batch_thumbnail", batch: props.batchId });
      }
    );
  } catch {}
}
async function loadOptions() {
  if (!isAdmin.value) return;
  try {
    await optionsTask.run(listSeals, value => {
      seals.value = value;
    });
  } catch {}
}
async function rosterPage() {
  const id = props.batchId;
  if (!id) return;
  try {
    await rosterTask.run(
      () => batchDetail(id, page.value),
      value => {
        if (!props.modelValue || props.batchId !== id || !data.value) return;
        data.value.awards = value.awards;
        data.value.award_count = value.award_count;
      }
    );
  } catch {}
}
async function syncStatus() {
  if (
    !props.modelValue ||
    !props.batchId ||
    !data.value ||
    busy.value ||
    task.loading.value
  )
    return;
  const id = props.batchId;
  try {
    await syncTask.run(
      () => batchDetail(id, page.value),
      value => {
        if (
          !props.modelValue ||
          props.batchId !== id ||
          !data.value ||
          busy.value
        )
          return;
        const old = data.value,
          previous = requirement.value;
        const changed =
          old.configuration.preview_revision !==
          value.configuration.preview_revision;
        data.value = value;
        if (old.batch.current_version !== value.batch.current_version) {
          form.requirement = choices.value[0]?.id;
          form.comment = "";
          form.issueRows = "";
          ElMessage.warning("名单已修订，请重新核对当前版本后审批");
        } else if (!choices.value.some(r => r.id === form.requirement))
          form.requirement = choices.value[0]?.id;
        else if (
          previous &&
          requirement.value?.seal_version !== previous.seal_version
        ) {
          form.seal = requirement.value?.seal_version || undefined;
          ElMessage.info("本部门用章已由其他管理员更新，请重新核对");
        }
        if (changed && !previewChanged.value && value.award_count)
          preview.start({ kind: "batch_thumbnail", batch: props.batchId });
      }
    );
  } catch {}
}
watch(() => live.revision, syncStatus);
async function saveAndPreview() {
  if (busy.value || !props.batchId) return;
  busy.value = true;
  try {
    const row = requirement.value;
    if (row && previewChanged.value) {
      if (!form.seal) return ElMessage.warning("请选择本部门公章");
      const updated = await chooseApprovalSeal(
        row.id,
        form.seal,
        row.seal_version
      );
      data.value.approvals = data.value.approvals.map((r: Approval) =>
        r.id === updated.id ? updated : r
      );
      previewChanged.value = false;
      emit("changed");
    }
    await preview.start({ kind: "batch_thumbnail", batch: props.batchId });
  } catch {
  } finally {
    busy.value = false;
  }
}
async function submit() {
  const row = requirement.value;
  if (!row || busy.value) return;
  if (form.decision === "approved" && !form.seal)
    return ElMessage.warning("请选择本部门公章");
  if (form.decision === "returned" && !form.comment.trim())
    return ElMessage.warning("请填写退回原因");
  const issueRows = form.issueRows.trim()
    ? form.issueRows
        .split(/[、，,\s]+/)
        .filter(Boolean)
        .map(Number)
    : [];
  if (
    issueRows.some(n => !Number.isInteger(n) || n < 2) ||
    issueRows.length > 200
  )
    return ElMessage.warning("问题行号应为从2开始的整数，最多200行");
  try {
    await ElMessageBox.confirm(
      form.decision === "approved"
        ? `确认代表“${row.department_name}”通过审批，并使用所选公章？`
        : "确认退回整个批次？负责人修订后需重新会签。",
      "确认审批"
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    await decideApproval(row.id, form.decision, form.comment, {
      ...(form.seal && form.decision === "approved"
        ? { seal_version: form.seal }
        : {}),
      expected_seal_version: row.seal_version,
      issue_rows: issueRows
    });
    ElMessage.success(
      form.decision === "approved" ? "本部门审批已通过" : "批次已退回"
    );
    emit("changed");
    await load();
  } catch {
  } finally {
    busy.value = false;
  }
}
watch(
  () => [props.modelValue, props.batchId],
  () => {
    preview.stop();
    if (props.modelValue && props.batchId) {
      load();
      loadOptions();
    }
  },
  { immediate: true }
);
</script>
<template>
  <el-drawer
    :model-value="modelValue"
    title="审批信息详情"
    size="min(1240px, 98vw)"
    :close-on-click-modal="!busy"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <ModuleRegion
      :loading="task.loading.value"
      :error="task.error.value"
      :empty="!data"
      @retry="load"
    >
      <template v-if="data">
        <el-descriptions
          :column="windowWidth < 700 ? 1 : 2"
          border
          class="summary"
        >
          <el-descriptions-item label="竞赛">{{
            data.batch.competition_name
          }}</el-descriptions-item>
          <el-descriptions-item label="批次">{{
            data.batch.name
          }}</el-descriptions-item>
          <el-descriptions-item label="状态"
            ><el-tag>{{
              stateLabel[data.batch.status] || data.batch.status
            }}</el-tag>
            · v{{ data.batch.current_version }}</el-descriptions-item
          >
          <el-descriptions-item label="获奖记录"
            >{{ data.award_count }} 条</el-descriptions-item
          >
          <el-descriptions-item label="模板">{{
            data.configuration.template_name
          }}</el-descriptions-item>
          <el-descriptions-item label="输出格式">{{
            data.configuration.output_formats.join(" + ").toUpperCase()
          }}</el-descriptions-item>
        </el-descriptions>
        <section class="progress-panel">
          <strong>部门会签 {{ approved }} / {{ total }}</strong
          ><el-progress
            :percentage="total ? Math.round((approved / total) * 100) : 0"
          />
          <div class="department-chips">
            <el-tag
              v-for="item in data.approvals"
              :key="item.id"
              :type="
                item.decision === 'approved'
                  ? 'success'
                  : item.decision === 'returned'
                    ? 'danger'
                    : 'info'
              "
              >{{ item.department_name }} ·
              {{
                item.decision === "approved"
                  ? "已通过"
                  : item.decision === "returned"
                    ? "已退回"
                    : item.seal_selected
                      ? "待审批"
                      : "待选章"
              }}</el-tag
            >
          </div>
        </section>
        <div class="review-grid">
          <section class="review-form">
            <h3>本部门审批</h3>
            <el-alert
              v-if="!choices.length"
              title="当前没有可处理的部门审批，以下为已保存记录。"
              :closable="false"
              type="info"
            />
            <el-form v-else label-position="top" @submit.prevent="submit">
              <el-form-item label="审批部门" required
                ><el-select v-model="form.requirement" :disabled="busy"
                  ><el-option
                    v-for="r in choices"
                    :key="r.id"
                    :label="r.department_name"
                    :value="r.id" /></el-select
              ></el-form-item>
              <el-form-item
                label="本部门公章版本"
                :required="form.decision === 'approved'"
                ><el-select
                  v-model="form.seal"
                  :loading="optionsTask.loading.value"
                  :disabled="busy"
                  filterable
                  clearable
                  placeholder="请选择本部门启用的公章"
                  ><el-option
                    v-for="s in sealOptions"
                    :key="s.id"
                    :label="s.label"
                    :value="s.id"
                /></el-select>
                <el-alert
                  v-if="optionsTask.error.value"
                  :title="optionsTask.error.value"
                  type="error"
                  :closable="false"
                /><el-button
                  v-if="optionsTask.error.value"
                  link
                  @click="loadOptions"
                  >重试公章列表</el-button
                >
              </el-form-item>
              <el-form-item label="审批决定" required
                ><el-radio-group v-model="form.decision" :disabled="busy"
                  ><el-radio value="approved">通过</el-radio
                  ><el-radio value="returned"
                    >整批退回</el-radio
                  ></el-radio-group
                ></el-form-item
              >
              <el-form-item
                label="审批意见 / 退回原因"
                :required="form.decision === 'returned'"
                ><el-input
                  v-model="form.comment"
                  type="textarea"
                  :rows="4"
                  maxlength="4000"
                  show-word-limit
                  :disabled="busy"
              /></el-form-item>
              <el-form-item label="问题行号（可选）"
                ><el-input
                  v-model="form.issueRows"
                  placeholder="例如 2, 5, 8，与 Excel 来源行号一致"
                  :disabled="busy"
              /></el-form-item>
              <div class="review-buttons">
                <el-button
                  :loading="busy"
                  :disabled="optionsTask.loading.value"
                  @click="saveAndPreview"
                  >保存用章并预览</el-button
                ><el-button
                  native-type="submit"
                  :type="form.decision === 'approved' ? 'primary' : 'danger'"
                  :loading="busy"
                  :disabled="optionsTask.loading.value"
                  >提交审批</el-button
                >
              </div>
            </el-form>
          </section>
          <section class="review-preview" aria-label="证书样式预览">
            <div class="preview-title">
              <h3>证书样式预览</h3>
              <el-button :loading="busy" @click="saveAndPreview"
                >刷新预览</el-button
              >
            </div>
            <el-alert
              v-if="previewChanged"
              title="公章选择已改变，请保存用章并预览后确认。"
              :closable="false"
              type="warning"
            />
            <el-alert
              v-if="
                preview.error.value || preview.file.value?.status === 'failed'
              "
              :title="preview.error.value || preview.file.value?.error"
              type="error"
              :closable="false"
            />
            <div
              v-else-if="
                preview.loading.value ||
                !preview.file.value ||
                !['ready', 'failed'].includes(preview.file.value.status)
              "
              class="preview-placeholder"
              role="status"
              aria-live="polite"
            >
              <el-skeleton animated
                ><template #template
                  ><el-skeleton-item
                    variant="image"
                    style="width: 100%; height: 280px" /></template
              ></el-skeleton>
              <p>正在后台准备证书样张，其他功能可继续使用…</p>
            </div>
            <SmartImage
              v-else-if="
                preview.file.value?.status === 'ready' && !previewChanged
              "
              :src="preview.file.value.download_url"
              fit="contain"
              :preview-src-list="[preview.file.value.download_url!]"
              preview-teleported
              class="certificate-image"
            />
            <p class="hint">
              采用当前名单首条数据。未确认的部门公章暂不展示，正式证书需全部部门通过后生成。
            </p>
          </section>
        </div>
        <el-tabs>
          <el-tab-pane label="获奖名单"
            ><BulkActions
              :selected="selectedRows"
              readonly-reason="审批中的名单只读；需要更正时整批退回。"
              @clear="roster?.clearSelection()" /><ModuleRegion
              :loading="rosterTask.loading.value"
              :error="rosterTask.error.value"
              @retry="rosterPage"
              ><el-table
                ref="roster"
                :data="data.awards"
                row-key="source_row"
                border
                @selection-change="selectedRows = $event"
                ><el-table-column type="selection" width="48" /><el-table-column
                  prop="source_row"
                  label="来源行"
                  width="80" /><el-table-column label="成员" min-width="200"
                  ><template #default="s">{{
                    s.row.members.join("、")
                  }}</template></el-table-column
                ><el-table-column
                  prop="award_name"
                  label="奖项"
                  min-width="120" /><el-table-column
                  prop="team_name"
                  label="团队"
                  min-width="150" /><el-table-column
                  prop="work_name"
                  label="作品名称"
                  min-width="200"
                  show-overflow-tooltip /></el-table></ModuleRegion
            ><el-pagination
              v-model:current-page="page"
              :total="data.award_count"
              :page-size="50"
              layout="total, prev, pager, next"
              @current-change="rosterPage"
          /></el-tab-pane>
          <el-tab-pane label="部门审批记录"
            ><el-table :data="data.approvals" border
              ><el-table-column
                prop="department_name"
                label="部门"
                min-width="160"
              /><el-table-column
                prop="seal_label"
                label="用章状态"
                min-width="180"
              /><el-table-column label="审批人 / 意见" min-width="240"
                ><template #default="s"
                  >{{ s.row.decision_detail?.actor || "尚未审批" }}
                  <p>{{ s.row.decision_detail?.comment }}</p>
                  <small v-if="s.row.decision_detail?.issue_rows?.length"
                    >问题行：{{
                      s.row.decision_detail.issue_rows.join("、")
                    }}</small
                  ></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          >
        </el-tabs>
      </template>
    </ModuleRegion>
    <template #footer
      ><el-button :disabled="busy" @click="emit('update:modelValue', false)"
        >关闭</el-button
      ></template
    >
  </el-drawer>
</template>
<style scoped>
.summary {
  margin-bottom: 16px;
}
.summary :deep(.el-descriptions__label) {
  width: 100px;
  white-space: nowrap;
}
.progress-panel {
  padding: 14px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 18px;
}
.department-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.review-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(360px, 1.2fr);
  gap: 20px;
  margin-bottom: 20px;
}
.review-form,
.review-preview {
  padding: 16px;
  min-width: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-bg-color);
}
h3 {
  margin: 0 0 16px;
  font-size: 16px;
}
.el-select {
  width: 100%;
}
.preview-title,
.review-buttons {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.preview-title h3 {
  margin: 0;
}
.preview-title {
  margin-bottom: 14px;
}
.certificate-image {
  width: 100%;
  min-height: 300px;
}
.preview-placeholder {
  padding: 20px 0;
  text-align: center;
}
.hint,
.preview-placeholder p {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.el-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
@media (max-width: 820px) {
  .review-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
