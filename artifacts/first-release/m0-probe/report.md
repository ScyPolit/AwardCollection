# M0 实际验证报告

执行日期：2026-11-06。范围仅限本探针合成样张，不代表全部模板、全部 Unicode 字符或目标 Ubuntu/Docker 环境均已通过。

## 结论

1. **中文与长文本最小样张通过。** Deng.ttf 对本次样张所有非空白字符的 cmap 覆盖完整，缺字列表为空。长作品名自动换为 2 行并由 24 pt 缩至 21.5 pt；18 人名单自动换为 3 行并由 22 pt 缩至 19 pt。两者都在指定文本框宽高内。
2. **双部门 pyHanko 增量签名最小样张通过。** 最终 PDF 检出 2 个签名。部门甲签名在追加部门乙签名后仍 `intact=true`、`valid=true`，覆盖其完整 revision；pyHanko 将后续变化判为可接受的表单填写。部门乙签名覆盖完整最终文件并同样完整、有效。
3. **信任边界：** 两张证书均为探针即时生成的自签测试证书。`trusted=true` 仅表示验证时显式把它们加入本次 `ValidationContext` 的信任根，不表示 Windows、Adobe 或学校终端默认信任。

## 实际证据

### 排版

- 字体：`C:\Windows\Fonts\Deng.ttf`，SHA-256 `e051009b42b454352a90ae0c9b8adb58bbdbcd168768750b35bc3357510de141`。
- 作品名文本框：542×72 pt；2 行；21.5 pt；最大行宽 537.5 pt；使用高度 58.05 pt。
- 成员文本框：542×78 pt；3 行；19 pt；最大行宽 532.0 pt；使用高度 76.95 pt。
- 未签 PDF：52,616 bytes，SHA-256 `425c1444e55b6a7c0734e688191d4c9b0238fa2ca58aa2614133c3cc3148f9b6`。
- 程序化原始记录：`evidence/layout-results.json`；视觉样张：`output/unsigned-preview.png`。

### 增量签名

| 签名字段 | intact | valid | trusted（仅测试信任） | 覆盖 | 修改判定 |
| --- | --- | --- | --- | --- | --- |
| DeptA_Signature | true | true | true | ENTIRE_REVISION | FORM_FILLING；后续签名为可接受修改 |
| DeptB_Signature | true | true | true | ENTIRE_FILE | NONE |

- 第一次签名文件：60,676 bytes，SHA-256 `7b15a916199c056f487ac6a165550637f085f2ed8db34eb1ac5ffc168cad02a1`。
- 最终文件：68,636 bytes，SHA-256 `4393b66cd03f975138f18c3b7ad6b6c693a85009ce27ea83ca682040f44f9f31`。
- 原始验证记录：`evidence/signature-results.json`。

## 依赖锁定建议

本探针实际使用：Python 3.12.9、pyHanko 0.31.0、pyhanko-certvalidator 0.29.1、cryptography 46.0.3、ReportLab 4.4.4、PyMuPDF 1.26.6、fonttools 4.62.1、pypdf 6.1.3。生产镜像应锁定完整传递依赖并生成 hashes；探针的 `requirements.txt` 只锁定直接依赖。

## 代码设计建议

- **统一排版内核：** 编辑器保存结构化文本框（x/y/w/h、字体、字号上下限、行距、换行规则），服务端以同一坐标规则生成正式 PDF；不要执行任意 HTML/JS。
- **适配顺序：** 先按 Unicode 字符/标点规则换行，再以 0.5 pt 步长缩小；达到最小字号仍溢出时返回批次行号、字段、实测宽高和缺字列表，阻止提交，不裁切。
- **字体前检：** 用 fontTools cmap 检查本批所有字符；容器内随包携带经许可的固定中文字体，并记录字体文件摘要。可再加 HarfBuzz/Pango 做复杂脚本 shaping；本次纯中文探针未覆盖复杂脚本。
- **签名流水线：** 完成背景、文字、编号、公章视觉层后再签名；每部门一个 `SigFieldSpec`，按冻结的部门顺序用 `IncrementalPdfFileWriter` 追加；每次签后立即验证全部已有签名并记录摘要，全部通过后才发布。
- **信任与密钥：** 正式部门证书及私钥与印章版本绑定，worker 只得到最小读取权限；归档证书链、签名字段、字节摘要和验证结果。自签证书需单独部署学校信任根，不能把数学有效等同身份可信。
- **修改策略：** 本探针证明后续签名可作为表单填写追加且前签完整；正式实现还应明确 DocMDP/FieldMDP 策略，测试 Adobe Acrobat、主流浏览器和目标阅览器的展示差异。

## 未执行 / 开放项

- 未在目标 Ubuntu 22 / Docker 镜像验证字体安装、FreeType 差异和 pyHanko 依赖兼容。
- 未做浏览器画布与 PDF 像素级视觉一致性比较；本次只生成服务端 PDF 及 PNG 预览。
- 未覆盖正式背景、公章、多页、竖版、5000 张批量、极端超长文本、emoji、生僻字、少数民族文字或复杂脚本。
- 未使用 Adobe Acrobat 或系统信任库验证；只使用 pyHanko 的显式测试信任上下文。
- 未验证可信时间戳、吊销检查、HSM/密钥服务、正式证书轮换与 DocMDP 限制。

因此，本结果足以支持“ReportLab/固定 TTF + fontTools 预检 + pyHanko 增量签名”进入下一阶段原型，但不足以宣称 M0 全场景或生产上线验收完成。
