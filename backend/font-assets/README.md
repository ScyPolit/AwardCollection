# 随部署提供的字体

系统内置 7 款可免费分发的中英文字体。字体由构建脚本按固定版本下载并校验，完整 CJK 二进制不进入 Git；Docker 镜像内已包含完整字体，运行时不下载。来源、固定版本、原始归档 SHA256 与实际部署字体 SHA256 记录在 manifest.json；原始许可文件随附。构建和运行无需购买字体服务，不访问在线字体 CDN。

| 字体 | 来源与许可 |
| --- | --- |
| 黑体风格：文泉驿正黑 | Debian fonts-wqy-zenhei 0.9.45-8，GPL-2 字体嵌入例外/M+ |
| 宋体风格：文鼎明体 | Debian fonts-arphic-uming 0.2.20080216.2-11，ARPHIC Public License |
| 楷体风格：文鼎楷体 | Debian fonts-arphic-ukai 0.2.20080216.2-5，ARPHIC Public License |
| 仿宋风格：朱雀仿宋 | TrionesType/zhuque v0.212，SIL OFL 1.1 |
| 英文无衬线、衬线、等宽：Liberation | Debian fonts-liberation2 2.1.5-1，SIL OFL 1.1 |

为了让浏览器和 PDF 使用同一个字体文件，前三款从上游 TTC 提取第 0 个字体面，保留全部字形；转换说明已写入字体的许可描述元数据，转换脚本为 backend/tools/prepare_fonts.py，仓库根目录 tools/prepare_fonts.py 为开发入口。原始 TTF 文件保持字节不变。ARPHIC 字体转换结果继续按原许可免费提供，文泉驿字体转换结果继续按原字体许可提供；本系统代码的许可不覆盖这些字体。

可用于常见公文风格排版，字体名称准确展示实际字体，不冒充学校指定商业字体。学校已有授权的精确字体可在管理员页面导入静态 TTF/TTC。导入需要确认系统使用、格式转换、嵌入和展示授权。

排版先检查所选字体字形，英文与中文混排时自动使用文泉驿补齐中文；如果仍缺字则指出字符及 Unicode 编码，阻止静默生成方框或乱码。前端 SVG 预览与 PDF 共用本地字体、换行、字号及基线坐标。

启动容器时会把经过校验的字体复制到媒体卷的 protected/font-library/builtin，以便本机备份包含完整字体。
