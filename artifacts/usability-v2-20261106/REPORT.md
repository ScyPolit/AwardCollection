# 2026-11-06 体验改进、字体、绘图与校徽验收

运行版本 `246348db2092261433cfe2f8bafc338f62f03a64`，应用 http://192.168.31.12:18080 ，仓库 https://github.com/ScyPolit/AwardCollection 。

## 最终功能

- 模板商城使用 Pure Admin 官方 CardList，原始页面、组件、MIT 许可及来源固定在 docs/upstream/pure-admin-card-list。提供真实缩略图、搜索、部门筛选、预览、选用和复制后编辑；同排卡片高度和操作区位置实测一致，长标题保留完整提示。
- 所有已登录用户均可在字体库和模板编辑器导入授权静态 TTF/TTC，并预览字体。负责人在模板只读时也能导入，不能因此修改模板；重命名、停用和启用仍由超管执行。匿名上传被拒绝，授权确认、40 MiB 上限、字体解析和重复文件校验保留。
- 内置七款免费固定字体：黑体、宋体、楷体、仿宋及三个英文家族。导入字体按 SHA256 固定内容；停用不覆盖文件，历史模板和原证书可继续读取。缺字先回退中文字体，仍缺字或文字溢出则阻止提交。
- 文字图层增加加粗、斜体、下划线，可组合使用。浏览器 SVG 与 PDF 使用相同字体、位置、描边、切变和下划线几何，PNG 从最终 PDF 渲染。
- 新增矩形、椭圆、直线和自由绘制；直线、自由线支持在画布拖动绘制，所有图形可拖动、调节位置/尺寸/线宽/线色，封闭图形可填充，并可上下调整层级。每条最多1000点、模板总计最多5000点；坐标、尺寸、颜色和文字样式有服务端校验，空缺几何不能保存。
- 登录、侧栏、横向导航和浏览器图标统一采用用户附件左侧校徽。原 PNG 未改写，通过 68×68 SVG 视口取左侧图案，加白色圆底保证深色可见；原图和摘要保留以便核对。
- 浅色、深色和窄屏布局复查，业务区域使用 Pure Admin / Element Plus 主题变量；证书画布保留输出原色。卡片、工具栏、弹窗和抽屉对齐，表格设置可读列宽并在表内滚动，编辑器侧栏可独立滚动。
- 日志、公章图片及版本、竞赛、账号、模板、名单、审批、证书、任务和消息均有详情入口。账号提交、重复错误反馈和取消行为修复；负责人为独立全局角色，没有部门绑定。
- 超管继承部门管理员能力，支持竞赛启用和废止；普通审批保留本人回避。实测废止阻止新批次并保留已签发文件，随后恢复启用。

## 实际验证

| 项目 | 结果 |
| --- | --- |
| 本地完整回归 | 50 项通过，103.137 秒；最终输入校验专项 3 项通过 |
| PostgreSQL 完整回归 | 50 项通过，447.454 秒，运行于 623c35f |
| 最终版本专项 | 文字/图形输出、非法/缺失几何、全员字体导入共 3 项通过，26.073 秒，运行于 246348d |
| 前端 | pnpm typecheck 和生产构建通过，约 2.34 MB |
| 页面基线 | 13 个后台页面（含工作台）×2主题×2屏宽，以及登录/公开查验8次，共60次；另复查新增绘图、字体权限及校徽页面 |
| 负责人导入 | 目标账号 test_v2_owner_20261106、角色owner、管理部门空；实际上传字体成功，管理按钮0个 |
| 模板编辑 | 真实鼠标绘制直线及自由线，添加矩形/椭圆、组合三种文字样式，保存后四类图形和样式均保留 |
| 样式签发 | 批次6，模板版本ID6（第3版），2/2会签后 done=2/2、attempts=1，无错误 |
| 最终文件 | 2026-AC-00005009、2026-AC-00005010；两PDF、两PNG、整批ZIP均可读取且逐字节一致 |
| 数字签名 | 两份新PDF共四个签名 intact/valid=true，自签 trusted=false符合预期 |
| 图形与字体 | 每份PDF至少5条矢量路径，加粗轮廓存在，中文可完整提取，全部配置字体家族嵌入 |
| 历史保留 | 批次2仍为issued，5000记录/5000PDF/5000PNG；三份历史样本摘要一致；批次5亦保留 |
| 部署与运维 | api/worker/web标签与健康接口一致，原db容器及三命名卷保留；备份COMPLETE和SHA256通过，维护timer active/enabled |

完整50项回归之后，最终版本只收紧图形完整字段校验并调整授权说明文字，已在目标PostgreSQL运行对应3项专项；不把两次测试写成53个不同用例。新样式与字体的实际双部门签发也已完成。

最终备份 `/opt/awardcollection-v1-test/backups/20261106-071107-wdlX9W`，回滚检查点 `/opt/awardcollection-v1-test/rollback/20261106-071101`。备份发生在新样式批次完成后，包含本轮导入字体、模板和证书。字体离线缓存按 manifest 核验，运行不访问字体服务。

## 证据与边界

- target-final-audit.json、postgres-regression-final.txt、postgres-focused-final.txt：最终主机与数据审计、完整和专项测试。
- target-styles-template-proof.json、target-styles-workflow-proof.json、target-styles-partial-approval.json：样式、四类图形、单部门不签发和最终任务状态。
- target-styles-signatures-fonts-zip.json、target-styles-download-proof.json、target-5009/5010.pdf/.png、target-batch-6.zip：签名、字体、矢量路径和文件一致性。
- target-owner-font-import-proof.json、owner-readonly-import-proof.json：负责人导入、无管理权与模板只读隔离。
- school-emblem-source-proof.json、school-logo-login.png、target-branding-final.png：校徽原图来源、摘要及实际显示。
- ui-verification-summary.json 和对应主题/屏宽截图：原页面检查；target-styles-editor-dark.png、target-styles-editor-mobile.png为新增编辑器复查。
- verify_target.py、verify_style_outputs.py、verify_outputs.py：可复核脚本，不含口令。

本轮没有重跑历史5000队，也没有其生成期间查询延迟的历史测量；未额外注入新版worker中断、租约抢占和大包内存压力。CLI原生下载事件受限，验证使用相同认证会话的正式下载接口。内置字库为免费替代风格，指定商用字库需由学校提供已有授权文件。图片不携带PDF数字签名，自签身份和同机备份的边界保持明确。独立防伪、学生凭编号领取、商业签章及异机备份仍在后期任务中。
