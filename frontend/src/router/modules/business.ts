const Layout = () => import("@/layout/index.vue");

export default {
  path: "/business",
  name: "Business",
  component: Layout,
  redirect: "/business/competitions",
  meta: { icon: "ep/medal", title: "证书业务", rank: 1 },
  children: [
    {
      path: "/business/competitions",
      name: "Competitions",
      component: () => import("@/views/business/competitions.vue"),
      meta: { icon: "ep/trophy", title: "竞赛管理" }
    },
    {
      path: "/business/batches",
      name: "Batches",
      component: () => import("@/views/business/batches.vue"),
      meta: { icon: "ep/document-copy", title: "名单与批次" }
    },
    {
      path: "/business/template-library",
      name: "TemplateLibrary",
      component: () => import("@/views/business/template-market/index.vue"),
      meta: { icon: "ep/collection", title: "证书模板库" }
    },
    {
      path: "/business/templates",
      name: "Templates",
      component: () => import("@/views/business/templates.vue"),
      meta: {
        icon: "ep/edit-pen",
        title: "模板编辑器",
        roles: ["admin", "super"]
      }
    },
    {
      path: "/business/fonts",
      name: "FontManagement",
      component: () => import("@/views/business/fonts.vue"),
      meta: {
        icon: "ri/font-size-2",
        title: "字体管理",
        roles: ["admin", "super"]
      }
    },
    {
      path: "/business/seals",
      name: "Seals",
      component: () => import("@/views/business/seals.vue"),
      meta: { icon: "ep/stamp", title: "公章管理", roles: ["admin", "super"] }
    },
    {
      path: "/business/approvals",
      name: "Approvals",
      component: () => import("@/views/business/approvals.vue"),
      meta: {
        icon: "ep/circle-check",
        title: "会签待办",
        roles: ["admin", "super"]
      }
    },
    {
      path: "/business/certificates",
      name: "Certificates",
      component: () => import("@/views/business/certificates.vue"),
      meta: { icon: "ep/document-checked", title: "证书档案" }
    },
    {
      path: "/business/administration",
      name: "Administration",
      component: () => import("@/views/business/administration.vue"),
      meta: {
        icon: "ep/user",
        title: "账号与公开设置",
        roles: ["admin", "super"]
      }
    },
    {
      path: "/business/logs",
      name: "BusinessLogs",
      component: () => import("@/views/business/logs.vue"),
      meta: { icon: "ep/tickets", title: "操作日志", roles: ["admin", "super"] }
    },
    {
      path: "/business/emergency",
      name: "Emergency",
      component: () => import("@/views/business/emergency.vue"),
      meta: { icon: "ep/warning-filled", title: "超管应急", roles: ["super"] }
    },
    {
      path: "/business/verification",
      name: "Verification",
      component: () => import("@/views/business/verification.vue"),
      meta: { icon: "ep/search", title: "编号查验" }
    }
  ]
} satisfies RouteConfigsTable;
