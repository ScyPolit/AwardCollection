# 项目结构与文件归属

```text
AwardCollection/
├── backend/          Django 业务、权限、管理命令和正式自动化测试
├── frontend/         管理界面及 ppt-editor/ 证书编辑子应用
├── converter/        隔离的 Office 格式转换服务
├── deploy/           初始化、升级、备份和公开模板打包程序
├── docs/             架构、部署、验收、品牌与上游许可记录
├── examples/         可公开再分发的三款可编辑证书模板
├── tools/            可复用的本地开发工具入口
├── resources/        素材归属说明；private/ 为未跟踪的学校原始素材
├── testTemp/         所有本地临时工作、缓存、运行数据与待发布产物
├── secrets/          私密部署文件，仅 .gitkeep 进入仓库
├── compose.yaml      Docker 服务与持久化数据卷
└── README.md         项目入口
```

`testTemp/history/` 归档过去位于根目录的 `.tmp-*` 文件和目录；`testTemp/development/` 是本地 SQLite 和默认媒体目录。历史临时脚本仅作记录，其中旧路径不会作为当前运行入口继续使用。可复用工具应迁入 `tools/` 或 `deploy/` 并使用工作区相对定位。

`backend/awards/tests.py`、`test_*.py` 属于正式测试源码，应随版本提交；`artifacts/` 是既有验收证据归档，不能等同于可随意删除的临时缓存。新临时截图和回归输出统一写入 `testTemp/<任务>/`，需要长期保留时再挑选不含真实人员信息的材料放入文档。

本机原 `docs/resorce/` 已迁到 `resources/private/`，包含原始设计稿、学校素材和授权字体，不公开提交。`.vscode/` 等个人编辑器设置保持原样。生产运行数据仍在 Docker 命名卷中，与本机临时目录无关。

`testTemp/`、`resources/private/`、私密配置、账号凭据、签名密钥及实际证书均不进入公开发行包。
