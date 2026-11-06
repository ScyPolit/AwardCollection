# 当前交付上下文（PPT / 通知 / 安全升级）

用户授权：直接改进、测试、部署 Docker、上传 GitHub。追加要求：全部业务界面规整，详情改成结构化字段并提供权限内修改；通知跳转和已读持久化。明确确认 ICAN 也清理，scypolit1 / 创新创业学院 / 数媒 也删除，只保留原 superadmin。

必须保留线上模板 id=4（原名“测试专用 A4 横版模板 副本”）最新 canvas 原样，重命名“标准模板”。保留其全部版本、正式部门 6、公章 7、用户导入的正式字体及签名素材。原始 canvas 和摘要保存在 Windows 私密 agent-handoff 目录，不可提交 Git。不要在目标验收时修改 id=4；使用独立 TEST ONLY V4 模板。

已完成：PPTist 原生编辑器接入，首行缩进/空格/字体/字段/公章桥接，同一引擎 PDF 渲染；PPTX/PPT/ODP/PDF/图片/JSON/PPTist 导入；权限内 CRUD 与结构化详情；实时 SSE、菜单角标、生成进度、通知深链接及服务端已读；生产依赖漏洞修复、冻结 HMAC、文件摘要校验、隔离 Office 转换器、非 root 运行及免费自签 HTTPS。选型和安全边界见 ppt-editor-assessment.md / security-review-v4.md。

本地已通过 69 项全回归（168.828 秒）及追加生成重试专项 1 项（2.148 秒）。前后两个前端 typecheck / build 通过；生产依赖扫描未检出已知漏洞。13 个页面浅色/深色均巡检，原生编辑器深色主题保留纸面和调色盘原色。

待完成：将当前源码提交推送；使用新版 deploy/apply_release.py 备份、构建并部署。新脚本不再依赖测试批次 2，保留原三命名卷和数据库容器，先启 API 完成迁移再启动 worker/web，额外启动无外网转换容器。部署时撤销旧 HTTP 登录会话，重新登录 HTTPS 地址 https://192.168.31.12:18443。自签证书首次需信任。

目标完成全链路和 PostgreSQL 回归后，再备份并执行 clear_demo_business 的 dry run，核对 id=4 SHA 与正式素材范围后 --apply。不得删除卷或重置 CertificateSequence。清理命令保留审计，并精确删除对应证书文件；签名密钥与字体素材不清理。清理后应只有一个超管、一个可见标准模板、零竞赛/批次/证书/任务/通知。最后再备份一次。

实际运行版本、备份路径及目标验收数据尚未在本轮更新到最终状态；不能把“本地通过”描述为“已部署”。私密凭据仅在 C:/Users/SCY-Polit/AppData/Local/AwardCollection/agent-handoff/first-release-20261106-8a1e 中的 DPAPI 文件及浏览器 auth profile 中，不能打印或提交。
