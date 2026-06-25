<div align="center">

# 🌊 MiniTV

**无限画布 + 节点工作流的本地 AI 创意生产工具**

把「文本 / 场景 / 姿势 / 图片 / 视频 / 分镜」摆上画布，连线即组合，一键出图出片。
为海外手游广告素材生产而设计，也适用于任何需要可视化编排 AI 生成的场景。

纯原生 JS + Python 标准库 · 零第三方依赖 · 本地运行 · 自带 API 不外泄

![License](https://img.shields.io/badge/license-MIT-green)
![No Dependencies](https://img.shields.io/badge/dependencies-0-blue)
![Python](https://img.shields.io/badge/python-stdlib%20only-yellow)

</div>

---

## 📸 截图

<div align="center">
<img src="docs/screenshot.png" width="920" alt="MiniTV 画布全景">
<br>
<i>一条完整工作流：场景 → 分镜脚本 → 三视图 / 九宫格分镜 / 资产图 → 视频出片</i>
</div>

---

## ✨ 功能

- **无限画布**：平移 / 缩放 / 框选 / 节点整体等比缩放，节点即「作品卡片」，参数就地展开不挡画布。
- **节点串联即组合**：连线把上游输出喂给下游——文字作上下文、场景作风格指令、骨架作姿势参考、图片作图生图参考、分镜图作视频首尾帧。多级自动回溯。
- **图片生成**：文生图 + 图生图（参考图）；内置预设 —— 角色三视图 / 人物特写 / 资产图 / 故事板单帧。
- **场景节点**：风格 / 地图 / 机位 / 角度 / 光线 五维结构化控制，选项库可自定义，设置沿连线向下继承。
- **姿势骨架节点**：2.5D 火柴人编辑器，拖关节摆姿势、拖空白旋转视角看空间、骨长按人体比例锁定；输出骨架参考图 + 姿势描述（软引导）。
- **视频生成**：文生视频 + 上游图片作首/尾帧。
- **多宫格分镜**：N×M 网格批量出图，支持全局统一风格 prompt、从分镜脚本一键填格。
- **文案 / 脚本**：内置剧情脚本 / 分镜脚本 / 钩子文案 / 资产清单 等 AI 预设。
- **中文友好**：prompt 直接写中文，提交时自动转成出图级英文（带缓存）。
- **素材库**：每次生成自动落盘归档，刷新不丢图。
- **多引擎**：OpenAI gpt-image / Gemini（Nano Banana）/ Seedance 视频，每个节点可单独选引擎。

## 🧱 架构

```
浏览器 (MiniTV.html, 零密钥编排)  ──HTTP──>  本机 proxy.py (执行引擎, 持配置)  ──>  各家 AI API
```

- **`MiniTV.html`** 是编排控制台：纯原生 JS，无任何外部依赖，不含密钥，可安全分享。
- **`proxy.py`** 是执行引擎：仅 Python 标准库（无需 pip），带 CORS，统一调度三个引擎，并解决浏览器跨域问题。
- 所有密钥只存在你本机的 `config.json` 与 proxy 运行时内存里；代理只监听 `127.0.0.1`，不对外。

## 🚀 快速开始

> 需要 [Python 3](https://www.python.org/downloads/)（Windows 安装时勾选 "Add Python to PATH"）。

1. **下载本仓库**（Code → Download ZIP，或 `git clone`）。
2. **配置自己的 API**：双击 `初始化配置.bat`（或 `python 初始化配置.py`），按提示填入你有的引擎 key、端点/中转地址、网络代理（如需）。生成 `config.json`。
3. **启动代理**：双击 `start.bat`，保持黑窗口开着（横幅会显示各引擎 OK / 缺失）。
4. **打开应用**：浏览器打开 `MiniTV.html`，左上角圆点变绿即代理已连上。
5. 拖个图片节点 → ⚙ 参数里写 prompt → 🎨 生成。

## 🔑 配置

三个引擎都是可选的，只填你有的。读取优先级：**环境变量 > `config.json` > 旧版本地回退**。

`config.json` 格式：
```json
{
  "openai":   {"api_key": "sk-...", "base_url": "https://api.openai.com/v1"},
  "gemini":   {"api_key": "...", "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
               "model": "gemini-2.5-flash-image", "pro_model": "gemini-3-pro-image-preview"},
  "seedance": {"api_key": "...", "base_url": "https://你的中转/api/v3", "model": "doubao-seedance-2-0-fast-260128"},
  "text_model": "gpt-4o",
  "http_proxy": "http://127.0.0.1:7890"
}
```
- `base_url`：用官方就用默认；用中转/代理服务就填它给的地址。
- `http_proxy`：访问墙外 API 需科学上网时填（如 `http://127.0.0.1:7890`），不需要就省略。
- 改端口：环境变量 `MINITV_PROXY_PORT`。

## 🔒 安全

- `MiniTV.html`、`proxy.py` 本身**不含任何密钥**，可安全公开 / 分享。
- key 只在 `config.json`（你的私密文件）和 proxy 运行时内存里。
- 仓库已带 `.gitignore`，**`config.json` 永远不会被提交**——但请始终注意不要手动上传它。
- 默认无访问密码。想加简易门（仅防肩窥）：编辑 `MiniTV.html` 顶部 `CONFIG.gatePassword`。真正的鉴权需在 `proxy.py` 服务端实现。

## 🗂 节点类型

| 节点 | 作用 | 连给下游时 |
|---|---|---|
| 文本 / 脚本 | 创意、脚本（含 AI 预设生成） | 作为 prompt 上下文 |
| 钩子 | 短文案 | 作为 prompt 上下文 |
| 场景 | 风格/机位/光线等结构化设置 | 拼进主 prompt，可继承 |
| 姿势骨架 | 2.5D 摆姿势 | 骨架图作参考 + 姿势描述进 prompt |
| 图片 | 出图（文生图/图生图/预设） | 图作下游参考图 / 视频首尾帧 |
| 多宫格分镜 | 批量分镜出图 | 各格图作参考 |
| 视频 | 出片 | — |

## ⚠️ 说明

- 姿势骨架是**软引导**（无 ControlNet），姿势还原约 7–8 成，不保证逐关节精确。
- Seedance 视频为异步生成，约 1–3 分钟，自动轮询。
- 多宫格为串行出图，量大较慢。

## 📄 License

[MIT](LICENSE) © 2026 ORIGAMICH0
