const Layout = () => import("@/layout/index.vue");

export default {
  path: "/business",
  name: "Business",
  component: Layout,
  redirect: "/business/competitions",
  meta: { icon: "ep:medal", title: "证书业务", rank: 1 },
  children: [
    { path: "/business/competitions", name: "Competitions", component: () => import("@/views/business/competitions.vue"), meta: { title: "竞赛管理" } },
    { path: "/business/batches", name: "Batches", component: () => import("@/views/business/batches.vue"), meta: { title: "名单与批次" } },
    { path: "/business/template-library", name: "TemplateLibrary", component: () => import("@/views/business/template-market/index.vue"), meta: { title: "证书模板库" } },
    { path: "/business/templates", name: "Templates", component: () => import("@/views/business/templates.vue"), meta: { title: "模板编辑器" } },
    { path: "/business/seals", name: "Seals", component: () => import("@/views/business/seals.vue"), meta: { title: "公章管理" } },
    { path: "/business/approvals", name: "Approvals", component: () => import("@/views/business/approvals.vue"), meta: { title: "会签待办" } },
    { path: "/business/certificates", name: "Certificates", component: () => import("@/views/business/certificates.vue"), meta: { title: "证书档案" } },
    { path: "/business/administration", name: "Administration", component: () => import("@/views/business/administration.vue"), meta: { title: "账号与公开设置", roles: ["admin", "super"] } },
    { path: "/business/logs", name: "BusinessLogs", component: () => import("@/views/business/logs.vue"), meta: { title: "操作日志", roles: ["admin", "super"] } },
    { path: "/business/emergency", name: "Emergency", component: () => import("@/views/business/emergency.vue"), meta: { title: "超管应急", roles: ["super"] } },
    { path: "/business/verification", name: "Verification", component: () => import("@/views/business/verification.vue"), meta: { title: "编号查验" } }
  ]
} satisfies RouteConfigsTable;
