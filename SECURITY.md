# Security Policy

## Supported Versions

AwardCollection 尚未发布稳定版本。当前仅维护 `main` 分支，不提供生产安全支持承诺。

## Reporting a Vulnerability

请不要在公开 Issue 中披露可利用细节、凭据、私钥、公章原件或个人数据。

建议通过 GitHub 仓库的 **Security > Report a vulnerability** 私下提交报告。如果私密报告入口不可用，请先创建一个不包含敏感细节的 Issue，请维护者提供私下沟通方式。

报告中请包含：

- 受影响的提交或版本；
- 风险类型与可能影响；
- 最小复现步骤；
- 已知缓解措施；
- 是否涉及真实凭据或个人数据（不要直接附上这些数据）。

## Deployment Responsibilities

部署者需要自行负责 HTTPS、系统补丁、网络隔离、强随机密钥、信任根分发、异机备份和访问审计。仓库中的测试自签证书或测试素材不能用于生产环境。
