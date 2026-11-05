# M0 最小验证：中文排版、长文本、多部门增量签名

> 全部材料均为“测试专用”，不是学校或部门的正式证书、公章或签名凭据。

## 实际执行

环境：Windows 10.0.26100、Python 3.12.9。实际执行时间见 `evidence/environment.txt`。

```powershell
cd F:\project\AwardCollection\artifacts\first-release\m0-probe
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe probe.py
```

可选：设置 `M0_FONT` 指向待部署的中文 TTF。默认使用本机 `C:\Windows\Fonts\Deng.ttf`；生产容器不得假定存在 Windows 字体，应随镜像携带经授权的字体。

## 产物

- `output/unsigned.pdf`：含中文、长作品名、18 人名单的未签样张。
- `output/unsigned-preview.png`：样张栅格预览。
- `output/signed-dept-a.pdf`：部门甲第一次签名后的中间版本。
- `output/signed-final.pdf`：部门乙增量追加签名后的最终版本。
- `evidence/layout-results.json`：字体覆盖、文本框、字号、行数、宽高和摘要。
- `evidence/signature-results.json`：两个签名的完整性、密码学有效性、测试信任和覆盖范围。
- `evidence/environment.txt`：实际依赖环境。
- `test-keys/*.p12`：运行时生成的测试私钥，仅用于本探针，口令固定且公开，严禁复用。

## 安全边界

`test-keys` 中的 PKCS#12 不是正式密钥。生产实现应从受保护的密钥挂载或密钥服务读取，绝不提交仓库、放进镜像层或返回前端。
