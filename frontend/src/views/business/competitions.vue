<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { createCompetition, listCompetitions, listDepartments, listUsers, type Competition, type Option } from "@/api/business";

const rows=ref<Competition[]>([]),departments=ref<Option[]>([]),users=ref<Option[]>([]),dialog=ref(false),saving=ref(false);
const form=reactive({name:"",award_presets:[] as string[],departments:[] as number[],collaborators:[] as number[]});
async function load(){[rows.value,departments.value,users.value]=await Promise.all([listCompetitions(),listDepartments(),listUsers()])}
function openCreate(){Object.assign(form,{name:"",award_presets:[],departments:[],collaborators:[]});dialog.value=true}
async function submit(){saving.value=true;try{await createCompetition(form);dialog.value=false;ElMessage.success("竞赛已创建并立即生效");await load()}finally{saving.value=false}}
onMounted(load);
</script>
<template><div class="page"><header><div><h2>竞赛管理</h2><p>创建竞赛并配置协作负责人及拟盖章部门</p></div><el-button type="primary" @click="openCreate">新建竞赛</el-button></header><el-table :data="rows" border><el-table-column prop="name" label="竞赛名称" min-width="220"/><el-table-column label="拟盖章部门" min-width="220"><template #default="s">{{s.row.department_names.join('、')}}</template></el-table-column><el-table-column label="协作负责人" min-width="200"><template #default="s">{{s.row.collaborator_names.join('、')}}</template></el-table-column><el-table-column label="状态" width="90"><template #default><el-tag type="success">生效</el-tag></template></el-table-column></el-table><el-dialog v-model="dialog" title="新建竞赛" width="560"><el-form label-position="top"><el-form-item label="竞赛名称" required><el-input v-model="form.name"/></el-form-item><el-form-item label="拟盖章部门" required><el-select v-model="form.departments" multiple class="full"><el-option v-for="item in departments" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item><el-form-item label="协作负责人"><el-select v-model="form.collaborators" multiple class="full"><el-option v-for="item in users" :key="item.id" :label="item.label" :value="item.id"/></el-select></el-form-item><el-form-item label="常用奖项"><el-select v-model="form.award_presets" multiple filterable allow-create class="full"/></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!form.name||!form.departments.length" @click="submit">创建</el-button></template></el-dialog></div></template>
<style scoped>.page{padding:20px}header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}h2{margin:0;font-size:20px;letter-spacing:0}p{margin:6px 0 0;color:#73767a}.full{width:100%}</style>
