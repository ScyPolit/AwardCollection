<script setup lang="ts">
import { onMounted, ref } from "vue";
import { dashboard } from "@/api/business";
defineOptions({name:"Welcome"});
const data=ref({pendingApprovals:0,runningTasks:0,issuedThisMonth:0,unreadNotifications:0,recent:[] as any[]});
onMounted(async()=>data.value=await dashboard());
</script>
<template><div class="dashboard"><header><div><h1>证书签发工作台</h1><p>待办、生成任务和近期签发状态</p></div><el-tag type="success">系统运行正常</el-tag></header><div class="stats"><div><span>待审批批次</span><strong>{{data.pendingApprovals}}</strong></div><div><span>生成中任务</span><strong>{{data.runningTasks}}</strong></div><div><span>本月签发</span><strong>{{data.issuedThisMonth}}</strong></div><div><span>未读消息</span><strong>{{data.unreadNotifications}}</strong></div></div><section><h2>近期动态</h2><el-table v-if="data.recent.length" :data="data.recent"><el-table-column prop="title" label="事项" width="180"/><el-table-column prop="body" label="内容"/><el-table-column prop="created_at" label="时间" width="190"/></el-table><el-empty v-else description="尚无业务记录" :image-size="90"/></section></div></template>
<style scoped>.dashboard{padding:24px}header{display:flex;justify-content:space-between;align-items:center}h1{margin:0;font-size:24px;letter-spacing:0}header p{margin:8px 0 0;color:#73767a}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}.stats div,section{background:#fff;border:1px solid #ebeef5;padding:18px;border-radius:6px}.stats span{display:block;color:#73767a}.stats strong{display:block;margin-top:10px;font-size:28px}section h2{font-size:18px;letter-spacing:0}@media(max-width:800px){.stats{grid-template-columns:repeat(2,1fr)}}</style>
