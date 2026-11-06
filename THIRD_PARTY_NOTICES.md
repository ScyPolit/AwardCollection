# 第三方组件与素材

此文档说明主要来源，不替代每个依赖自己的许可证。Python 与 JavaScript 依赖版本由对应的约束文件及锁文件记录，再分发时应同时保留相关声明。

| 组件 / 素材 | 本仓库位置 | 许可与来源 |
| --- | --- | --- |
| AwardCollection 原创业务代码、项目品牌 SVG | 根目录、backend、业务适配等 | [MIT](LICENSE)；不覆盖第三方代码和上传素材 |
| Pure Admin 管理界面基础 | frontend | 上游 [pure-admin-thin](https://github.com/pure-admin/pure-admin-thin)，[MIT 声明](frontend/LICENSE) |
| 模板库卡片页参考 | docs/upstream/pure-admin-card-list | [来源与改动说明](docs/upstream/pure-admin-card-list/SOURCE.md)，保留上游 MIT |
| PPTist 编辑器及本项目修改 | frontend/ppt-editor | [AGPL-3.0](frontend/ppt-editor/LICENSE)，[修改说明及源代码地址](frontend/ppt-editor/MODIFICATIONS.md) |
| 内置字体 | backend/font-assets | [固定来源、摘要与授权](backend/font-assets/README.md) |
| 学校标识、部门公章、用户字体、模板内容 | 实例静态资源及上传文件 | 独立素材；部署方需取得相应授权，代码许可不授予这些素材的权利 |

仓库同时包含 MIT 与 AGPL 组件，不能仅依据根目录 LICENSE 将完整发行物描述为“全部 MIT”。请阅读所使用组件的许可，保留版权与修改声明，并履行适用的相应源代码提供要求。编辑器界面提供修改版源代码入口。

项目 README 中的 AwardCollection Logo 与封面是原创项目标识；其中的示意证书不作为真实签发凭证，也不代表学校认可或授权。
