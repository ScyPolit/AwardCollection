# 部署配置

正式部署使用根目录 `compose.yaml`，Compose 项目固定为 `awardcollection-v1-test`。复制 `.env.example` 为 `.env`，并在 `secrets/db_password.txt` 写入与 `POSTGRES_PASSWORD` 相同的随机口令。所有实际密钥均不得提交 Git。

`web` 是唯一映射宿主机端口的服务；数据库仅存在于项目内部网络。首次启动前检查 18080 未占用。
