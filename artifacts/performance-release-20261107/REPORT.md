# 2026-11-07 权限、下载与性能修复

本地 87 项 Django 测试通过。新增覆盖负责人字体/公章禁用、部门越权、冻结部门可见范围、身份变更后的下载与通知、ZIP 去重及落盘、2 MiB 模板快照不会进入打包查询、文件篡改拦截、签名 PDF 不重写而补生成 PNG、超大页面像素上限、过期租约和输出格式。前端两个工程类型检查及生产构建通过。

浏览器给证书列表请求人工延迟 4.5 秒，局部骨架屏可见且全局遮罩为 0，等待期间能切换竞赛管理。图库只为可见卡片准备缩略图，进入可见区域后正常完成加载。本地 SQLite 并发预览的事务锁冲突已改为 IMMEDIATE 事务并增加等待超时；生产 PostgreSQL 不采用此配置。

502 的线上证据：批次 10 已完成 300/300；原接口查询重复解码约 2.3 MB 的冻结模板，300 份快照对象约占 674 MiB，加上查询缓冲和应用本身超过 1 GiB 限额。Nginx 记录 upstream prematurely closed connection，Gunicorn 收到 SIGKILL，容器 OOM 计数增加。新实现流式读取文件路径字段并分块写 ZIP，不选择模板 JSON；下载交由 Nginx。

目标 PostgreSQL 87 项全量回归通过；最终后端的权限、通知、应急、作废与已读专项 20 项通过。后端已部署 `6e722dc2f07b78fc8126a0686eb82ea8db677d3e`，发布器核对历史内容未变。备份为 `/opt/awardcollection-v1-test/backups/20261107-081745-O7Ifmt`，检查点 `/opt/awardcollection-v1-test/rollback/20261107-081738`。此轮不清理任何现有正式业务数据。

实际 300 份批次已由线上 worker 准备好 2,001,382,026 字节 ZIP；准备完成通知可直接打开对应批次，链接使用服务器地址且没有 Blob。HTTPS HEAD 返回 200、准确的 Content-Length、attachment 和 Accept-Ranges；Range 返回 206，范围为 `bytes 0-1023/2001382026`，1024 字节以 ZIP 标记 PK 开头。

同批 600 个文件在禁用交换内存、512 MiB 限额的只读验证容器中完成打包与全包 CRC 检查；进程峰值 RSS 71.61 MiB，OOM / OOM kill 均为 0。容器内存含文件缓存，在限额附近正常回收；不将 RSS 冒充容器总内存。

证书编辑器验证：GitHub 图标和放映入口移除，可见内容不含“幻灯片/放映”；四款本地证书排版正常展示。添加空白页后由 1 页变 2 页，添加排版后变 3 页；替换不改变页数，撤销可恢复原排版；F5 不进入演示，证书编号保持动态字段，本地 QA 模板成功保存版本 2。线上标准模板未作编辑。

最终前端 `49418cf5fce37605494f822d9ea9187f6332b858` 已通过仅 web 发布器部署，检查点 `/opt/awardcollection-v1-test/rollback/web-20261107-084123`。API、worker、数据库、转换器身份与创建时间保持不变，全部模板版本和历史证书样本摘要相同。线上再次确认编辑器加载遮罩消失、四款排版可见、“添加页面”保留，GitHub 按钮和演示字样均为零。表单异步选项、公开查验设置的局部加载与保存保护也已包含在最终前端中。

最终运行检查中，web / api / db 健康，worker / converter 运行；API cgroup OOM / OOM kill 均为 0，最近 20 分钟无新增 API SIGKILL 或 web 502。受保护的内部下载路径直接访问返回 404。原数据库容器创建时间及正式账号、300 份已发布证书均保留。备份四项 SHA256 校验通过。

完整 HTTPS 下载验证通过：2,001,382,026 字节在 171.67 秒内以 256 KiB 缓冲写入本地磁盘，SHA256 与服务器完全相同；300 个 PDF、300 个 PNG 共 600 个条目的全包 CRC 均通过。原生浏览器自动保存尝试在自动化环境被取消，浏览器请求本身返回 200；完整传输使用同一鉴权链接验证，未将此项冒充原生浏览器保存成功。验证后删除本地真实证书 ZIP、临时会话文件及服务器只读基准测试产生的副本，保留服务器正式下载包与全部正式数据。

证据入口：[后端发布](backend-release.json)、[前端发布](web-release.json)、[线上编辑器](production-editor.json)、[服务状态](final-server-state.json)、[正式数据与 ZIP 状态](production-state.json)、[完整下载验证](full-download-check.json)、[512 MiB 打包验证](target-memory-check.json)、[备份校验](backup-verification.txt)。
