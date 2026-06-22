// 应用路由：项目主页 → 新建 → 分组列表 → 组详情 → 完成。
// 用 hash 历史（Tauri webview 无服务端路由，hash 最稳）。
import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./pages/ProjectsHome.vue") },
  { path: "/new", name: "new", component: () => import("./pages/NewProject.vue") },
  // 设置页（自用版：配置 Ark key / 模型 id）。商业版构建移除此路由
  { path: "/settings", name: "settings", component: () => import("./pages/SettingsPage.vue") },
  {
    path: "/projects/:id",
    name: "groups",
    component: () => import("./pages/GroupList.vue"),
    props: true,
  },
  {
    path: "/projects/:id/groups/:gk",
    name: "group",
    component: () => import("./pages/GroupDetail.vue"),
    props: true,
  },
  {
    path: "/projects/:id/review",
    name: "review",
    component: () => import("./pages/ReviewPage.vue"),
    props: true,
  },
  {
    path: "/projects/:id/complete",
    name: "complete",
    component: () => import("./pages/CompletePage.vue"),
    props: true,
  },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
