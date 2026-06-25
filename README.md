# MiniTV · 个人创意工作流画布

LibTV 的最小个人版：无限画布 + 节点工作流，三个模型全部通过**本地代理**即时出图/出片。

## 目录结构
```
MINI TV/
├─ MiniTV.html     主程序（零密钥，浏览器打开）
├─ proxy.py        本地代理（零密钥，加 CORS，从 config.json 读配置）
├─ 初始化配置.py    首次使用的配置向导 → 生成 config.json
├─ 初始化配置.bat   双击运行配置向导
├─ start.bat       一键启动代理
├─ config.json     你的私密配置（运行向导后生成；勿外发）
└─ README.md       本说明
```

## 首次使用（只需一次）
**双击 `初始化配置.bat`**（或命令行 `python 初始化配置.py`），按提示填入你自己的：
- API key（OpenAI / Gemini / Seedance，只填你有的，没有就回车跳过）
- 端点 / 中转地址（用官方直接回车用默认；用中转就填它给的地址）
- 网络代理（如果访问墙外 API 需要科学上网，填如 `http://127.0.0.1:7890`，否则回车跳过）

填完会生成 `config.json`。**没运行过它直接启动 proxy 会提示"尚未配置"。**

## 怎么用（每次）
1. **双击 `start.bat`** 启动本地代理，保持那个黑窗口开着（横幅会显示各引擎 OK/缺失）。
2. 浏览器打开 **`MiniTV.html`**（密码默认 `tkoo`）。
3. 左上角圆点变绿 = 代理已连上。图片节点点「🎨 生成」，视频节点点「🎬 生成视频」。

## 三个引擎
- **OpenAI**（默认出图）：官方 gpt-image-1，质量高、稍慢。
- **Gemini**：Nano Banana，快且便宜。左上角下拉随时切换出图引擎。
- **Seedance**：视频，异步 1–3 分钟，自动轮询，完成后内嵌播放。

## 密钥从哪来（重要）
proxy.py 与 MiniTV.html **都不含任何密钥**。配置读取优先级：
1. **环境变量**（`OPENAI_API_KEY` / `GEMINI_API_KEY` / `SEEDANCE_API_KEY` / `OPENAI_BASE_URL` / `MINITV_HTTP_PROXY` 等）
2. **`config.json`**（运行 `初始化配置.py` 生成 —— 推荐方式）
3. **records 回退**（兼容旧版从本地 MCP 源目录读取；没有此目录则自动跳过）

## 分发给别人（重要）
本工程可直接打包发给别人用，因为没有内置任何 key：
- 要发的：`MiniTV.html`、`proxy.py`、`初始化配置.py`、`初始化配置.bat`、`start.bat`、`README.md`
- **不要发**：`config.json`（你的明文 key）、`assets/`（你生成的素材）——这两个是你的私密内容
- 对方拿到后：双击 `初始化配置.bat` 填自己的 key → `start.bat` → 打开 HTML，即可用。

## 安全说明（必读）
- `MiniTV.html`、`proxy.py` 本身**不含密钥**，可安全分享。
- key 只在 `config.json`（本机私密文件）和 proxy 运行时内存里，代理只监听 `127.0.0.1`，不对外。
- 密码门只防肩窥，挡不住看源码的人——真正的鉴权请在 proxy.py 里加（后期）。
- `config.json` 含明文 key，**勿外发、勿随工程分享**。

## 改配置
- 改 key / 端点 / 中转 / 网络代理 / 模型：重新运行 `初始化配置.py`（覆盖 config.json），或手动编辑 `config.json`。
- 切换默认出图引擎 / 改密码：编辑 `MiniTV.html` 顶部 `CONFIG`（每个节点也可单独选引擎）。
- 改端口：环境变量 `MINITV_PROXY_PORT`。

## config.json 格式
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
每个引擎都可选，只填你有的。
