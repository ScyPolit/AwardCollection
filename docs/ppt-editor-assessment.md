# PPT 编辑器选型与导入范围

根据用户要求先检索开源项目，再实施集成。最终复用 PPTist 原生编辑器，不重画 PowerPoint 界面。

| 项目 | 核实的特点 | 结论 |
|---|---|---|
| [PPTist](https://github.com/pipipi-pikachu/PPTist) | Vue 3 / TypeScript，富文本、形状、表格、图表、拖拽缩放、组合对齐、撤销、演示、PPTX / PPTist / JSON 导入导出 | 与现有 Vue 系统一致，独立子应用接入，改动少 |
| [ONLYOFFICE DocumentServer](https://github.com/ONLYOFFICE/DocumentServer) | 完整 Office 服务，部署和文档会话集成较重 | 首版不选 |
| [Slidev](https://github.com/slidevjs/slidev) | Markdown 演示文稿，侧重开发者工作流 | 不适合可视化编辑需求 |
| [CasualOffice](https://github.com/CasualOffice/slides) | React 技术栈，接入需要更多适配 | 首版不选 |

固定上游提交：`a8fcb4d92194678988bb1238bf7ac33f2e0baeaa`。源码位于 frontend/ppt-editor，保留上游 AGPL-3.0 许可证及修改说明，并在编辑器菜单中提供修改版源码链接。主系统继续采用 Pure Admin。

增加的证书功能：获奖字段绑定、公章占位、当前页签发、系统字体库、首行缩进字符数、空格保留、服务端签发预检和同一编辑器渲染。旧模板保持原 JSON 和渲染路径；只有用户显式保存时才创建 PPTist 版本。保存采用版本号检查，避免多人覆盖。

支持导入：PPTX；PPT / ODP 经本地 LibreOffice 转换；PPTist / JSON；PDF / PNG / JPG 作为页面背景。PPTX 中的普通文字和图形保持可编辑。嵌入程序、宏、ActiveX、外部资源和加密文件受到限制。复杂 Office 效果及字体替换需要人工预览确认，不能承诺与 Microsoft PowerPoint 的全部功能或文件表现完全一致。云端 AI 和在线素材服务未接入，运行不产生服务费用。

证书批量输出为选定的一页，PDF 继续部门增量签名，PNG 从最终 PDF 渲染；整份多页文稿仍保留在模板版本中供编辑。
