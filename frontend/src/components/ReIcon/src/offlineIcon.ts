// 这里存放本地图标，在 src/layout/index.vue 文件中加载，避免在首启动加载
import { getSvgInfo } from "@pureadmin/utils";
import { addIcon } from "@iconify/vue/dist/offline";

// https://icon-sets.iconify.design/ep/?keyword=ep
import EpHomeFilled from "~icons/ep/home-filled?raw";

// https://icon-sets.iconify.design/ri/?keyword=ri
import RiSearchLine from "~icons/ri/search-line?raw";
import RiInformationLine from "~icons/ri/information-line?raw";

import BusinessIcon0 from "~icons/ep/medal?raw";
import BusinessIcon1 from "~icons/ep/trophy?raw";
import BusinessIcon2 from "~icons/ep/document-copy?raw";
import BusinessIcon3 from "~icons/ep/collection?raw";
import BusinessIcon4 from "~icons/ep/edit-pen?raw";
import BusinessIcon5 from "~icons/ri/font-size-2?raw";
import BusinessIcon6 from "~icons/ep/stamp?raw";
import BusinessIcon7 from "~icons/ep/circle-check?raw";
import BusinessIcon8 from "~icons/ep/document-checked?raw";
import BusinessIcon9 from "~icons/ep/user?raw";
import BusinessIcon10 from "~icons/ep/tickets?raw";
import BusinessIcon11 from "~icons/ep/warning-filled?raw";
import BusinessIcon12 from "~icons/ep/search?raw";

const icons = [
  ["ep/medal", BusinessIcon0],
  ["ep/trophy", BusinessIcon1],
  ["ep/document-copy", BusinessIcon2],
  ["ep/collection", BusinessIcon3],
  ["ep/edit-pen", BusinessIcon4],
  ["ri/font-size-2", BusinessIcon5],
  ["ep/stamp", BusinessIcon6],
  ["ep/circle-check", BusinessIcon7],
  ["ep/document-checked", BusinessIcon8],
  ["ep/user", BusinessIcon9],
  ["ep/tickets", BusinessIcon10],
  ["ep/warning-filled", BusinessIcon11],
  ["ep/search", BusinessIcon12],

  // Element Plus Icon: https://github.com/element-plus/element-plus-icons
  ["ep/home-filled", EpHomeFilled],
  // Remix Icon: https://github.com/Remix-Design/RemixIcon
  ["ri/search-line", RiSearchLine],
  ["ri/information-line", RiInformationLine]
];

// 本地菜单图标，后端在路由的 icon 中返回对应的图标字符串并且前端在此处使用 addIcon 添加即可渲染菜单图标
icons.forEach(([name, icon]) => {
  addIcon(name as string, getSvgInfo(icon as string));
});
