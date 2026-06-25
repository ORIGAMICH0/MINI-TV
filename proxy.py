#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniTV 统一本地代理 V2 —— 让浏览器里的 MiniTV.html 能即时调用三个模型。

原理：浏览器 → 本机 localhost:8787（本代理，带 CORS 头）→ 各家上游 API。
解决官方端点不允许浏览器跨域的问题，并把所有密钥关在代理里 —— HTML 文件零密钥。

✅ 所有 key 不写在本文件，也不写在 HTML：默认从你现有的三个 MCP 源文件 / 配置里读取，
   不新增任何副本：
     - OpenAI   ← openai-mcp-server/cowork_config_merged.json
     - Gemini   ← imagen-mcp/server.py     里的 API_KEY / BASE_URL
     - Seedance ← seedance-mcp/server.py   里的 API_KEY / BASE_URL / MODEL
   均可用环境变量覆盖。

V2 新增（P0 数据总线）：
  - /image 支持 references[]（参考图 → 图生图：Gemini inlineData / OpenAI images-edits）
  - /video/submit 支持 first_frame / last_frame（Seedance 首尾帧）
  - /asset 素材落盘到 assets\\YYYY-MM-DD\\ + manifest.jsonl 清单
  - /assets 素材清单查询、/asset/file 素材文件回传

依赖：仅 Python 标准库，无需 pip 安装。
运行：双击同目录 start.bat，或命令行 `python proxy.py`
"""
import os, re, json, time, uuid, base64, ssl, hashlib, mimetypes, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

PORT = int(os.environ.get("MINITV_PROXY_PORT", "8787"))
HERE = os.path.dirname(os.path.abspath(__file__))

# ── 配置来源优先级：环境变量 > config.json（运行 初始化配置.py 生成）> records 回退 ──
# 分发给他人时不要附带 config.json / records —— 本文件与 HTML 均零密钥。
CONFIG_FILE = os.path.join(HERE, "config.json")


def _load_config():
    try:
        return json.load(open(CONFIG_FILE, encoding="utf-8"))
    except Exception:
        return {}


_CFG = _load_config()


def _cfg(provider, field, default=None):
    return (_CFG.get(provider) or {}).get(field) or default


# ── records 回退（兼容旧版从本地 MCP 源读取；无此目录则自动跳过）──────────
REC = os.environ.get("MINITV_RECORDS", _CFG.get("records_dir") or "")
OPENAI_CFG   = os.path.join(REC, "openai-mcp-server", "cowork_config_merged.json")
IMAGEN_SRC   = os.path.join(REC, "imagen-mcp", "server.py")
SEEDANCE_SRC = os.path.join(REC, "seedance-mcp", "server.py")

# ── 素材库目录（与本文件同目录）────────────────────────────────
ASSET_DIR = os.path.join(HERE, "assets")
MANIFEST  = os.path.join(ASSET_DIR, "manifest.jsonl")


def _pyconst(path, name, default=None):
    try:
        txt = open(path, encoding="utf-8").read()
        m = re.search(rf'^{name}\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        return m.group(1) if m else default
    except Exception:
        return default


def _openai_key_records():
    try:
        d = json.load(open(OPENAI_CFG, encoding="utf-8"))
        return d["mcpServers"]["openai-bridge"]["env"]["OPENAI_API_KEY"].strip()
    except Exception:
        return None


# ── 各家配置（env > config.json > records 回退）──────────────────
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY") or _cfg("openai", "api_key") or _openai_key_records()
OPENAI_KEY  = OPENAI_KEY.strip() if OPENAI_KEY else None
OPENAI_BASE = (os.environ.get("OPENAI_BASE_URL") or _cfg("openai", "base_url") or "https://api.openai.com/v1").rstrip("/")

GEMINI_KEY  = os.environ.get("GEMINI_API_KEY") or _cfg("gemini", "api_key") or _pyconst(IMAGEN_SRC, "API_KEY")
GEMINI_BASE = (os.environ.get("GEMINI_BASE_URL") or _cfg("gemini", "base_url") or _pyconst(IMAGEN_SRC, "BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models")).rstrip("/")
GEMINI_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL") or _cfg("gemini", "model") or "gemini-2.5-flash-image"
GEMINI_PRO_MODEL     = os.environ.get("GEMINI_PRO_MODEL") or _cfg("gemini", "pro_model") or "gemini-3-pro-image-preview"

TEXT_MODEL = os.environ.get("MINITV_TEXT_MODEL") or _CFG.get("text_model") or "gpt-4o"   # /text 文字生成用的模型

SD_KEY   = os.environ.get("SEEDANCE_API_KEY") or _cfg("seedance", "api_key") or _pyconst(SEEDANCE_SRC, "API_KEY")
SD_BASE  = os.environ.get("SEEDANCE_BASE_URL") or _cfg("seedance", "base_url") or _pyconst(SEEDANCE_SRC, "BASE_URL")
SD_MODEL = os.environ.get("SEEDANCE_MODEL") or _cfg("seedance", "model") or _pyconst(SEEDANCE_SRC, "MODEL", "doubao-seedance-2-0-fast-260128")
SD_TASKS = (SD_BASE.rstrip("/") + "/contents/generations/tasks") if SD_BASE else None

# ── 可选网络代理（访问墙外 API 用）：env > config.json ──
HTTP_PROXY = os.environ.get("MINITV_HTTP_PROXY") or _CFG.get("http_proxy")
_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({"http": HTTP_PROXY, "https": HTTP_PROXY})) if HTTP_PROXY else None

# OpenAI gpt-image 支持的尺寸
_OAI_SIZE = {"1:1": "1024x1024",
             "9:16": "1024x1536", "3:4": "1024x1536", "4:5": "1024x1536", "2:3": "1024x1536",
             "16:9": "1536x1024", "3:2": "1536x1024", "5:4": "1536x1024"}


# ── TLS 白名单降级：Seedance 中转域名是自签名证书，仅对它跳过校验 ──
# （OpenAI / Gemini 官方域名保持完整证书校验，不做全局降级）
INSECURE_HOSTS = set(h.strip() for h in os.environ.get("MINITV_INSECURE_HOSTS", "").split(",") if h.strip())
if SD_BASE:
    _sd_host = urlparse(SD_BASE).hostname
    if _sd_host:
        INSECURE_HOSTS.add(_sd_host)
_UNVERIFIED_CTX = ssl._create_unverified_context()


def _http(url, data=None, headers=None, method="POST", timeout=300):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    ctx = _UNVERIFIED_CTX if (urlparse(url).hostname in INSECURE_HOSTS) else None
    try:
        if _PROXY_OPENER:
            with _PROXY_OPENER.open(req, timeout=timeout) as r:
                return r.status, r.read()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 502, json.dumps({"error": {"message": "upstream: " + str(e)}}).encode()


# ── 参考图 / 素材工具 ──────────────────────────────────────
def _sniff_mime(data, kind="image"):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "video/mp4" if kind == "video" else "image/png"


def _safe_asset_path(rel):
    """仅允许访问 assets 目录内的文件，防路径穿越。"""
    fp = os.path.abspath(os.path.join(ASSET_DIR, rel))
    if fp.startswith(os.path.abspath(ASSET_DIR)) and os.path.isfile(fp):
        return fp
    return None


def _load_ref(ref, kind="image"):
    """参考图来源三选一：dataURL / 本代理素材URL / 远程URL → (mime, bytes) 或 None"""
    try:
        ref = str(ref or "")
        if ref.startswith("data:"):
            head, b64 = ref.split(",", 1)
            mime = head[5:].split(";")[0] or "image/png"
            return mime, base64.b64decode(b64)
        if "/asset/file" in ref:
            qs = parse_qs(urlparse(ref).query)
            rel = (qs.get("p") or [""])[0]
            fp = _safe_asset_path(rel)
            if fp:
                data = open(fp, "rb").read()
                return _sniff_mime(data, kind), data
        if ref.startswith("http"):
            code, raw = _http(ref, method="GET", timeout=120)
            if code < 400 and raw[:1] != b"{":
                return _sniff_mime(raw, kind), raw
    except Exception as e:
        print("[proxy] 参考图读取失败:", e)
    return None


def _to_dataurl(mime, data):
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())


def _multipart(fields, files):
    """标准库手搓 multipart/form-data。files: [(字段名, 文件名, mime, bytes)]"""
    bound = "----minitv" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bound, k, v)).encode()
    for name, fn, mime, data in files:
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                % (bound, name, fn, mime)).encode()
        out += data + b"\r\n"
    out += ("--%s--\r\n" % bound).encode()
    return "multipart/form-data; boundary=" + bound, bytes(out)


# ── 三个能力 ───────────────────────────────────────────────
def gen_openai(prompt, aspect, model, quality, refs=None):
    if not OPENAI_KEY:
        return {"error": "OpenAI key 缺失"}
    size = _OAI_SIZE.get(aspect, "1024x1024")
    if refs:
        # 带参考图 → images/edits（multipart），gpt-image-1 支持多图输入
        fields = {"model": model or "gpt-image-1", "prompt": prompt,
                  "size": size, "n": "1", "quality": quality or "high"}
        files = [("image[]", "ref%d.png" % i, m, d) for i, (m, d) in enumerate(refs)]
        ctype, body = _multipart(fields, files)
        code, raw = _http(OPENAI_BASE + "/images/edits", body,
                          {"Content-Type": ctype, "Authorization": "Bearer " + OPENAI_KEY})
    else:
        body = {"model": model or "gpt-image-1", "prompt": prompt,
                "size": size, "n": 1, "quality": quality or "high"}
        code, raw = _http(OPENAI_BASE + "/images/generations", json.dumps(body).encode(),
                          {"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_KEY})
    try:
        j = json.loads(raw)
    except Exception:
        return {"error": f"{code}: {raw[:300]!r}"}
    if code >= 400:
        return {"error": f"{code} " + str(j.get("error", {}).get("message", j))}
    d = (j.get("data") or [{}])[0]
    if d.get("b64_json"):
        return {"image": "data:image/png;base64," + d["b64_json"]}
    if d.get("url"):
        return {"image_url": d["url"]}
    return {"error": "OpenAI 返回无图片字段"}


def gen_gemini(prompt, aspect, model, refs=None):
    if not GEMINI_KEY:
        return {"error": "Gemini key 缺失"}
    use = model or GEMINI_DEFAULT_MODEL
    if refs and "pro" not in use:
        use = GEMINI_PRO_MODEL          # 带参考图自动升级 pro 模型
        print("[proxy] 带参考图，自动切换模型 →", use)
    url = f"{GEMINI_BASE}/{use}:generateContent?key={GEMINI_KEY}"
    parts = []
    for mime, data in (refs or []):
        parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}})
    parts.append({"text": prompt})
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                     "imageConfig": {"aspectRatio": aspect or "1:1", "imageSize": "1K"}}}
    code, raw = _http(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    try:
        j = json.loads(raw)
    except Exception:
        return {"error": f"{code}: {raw[:300]!r}"}
    if code >= 400:
        return {"error": f"{code} " + str(j.get("error", {}).get("message", j))}
    for c in j.get("candidates", []):
        for p in (c.get("content", {}) or {}).get("parts", []):
            inl = p.get("inlineData")
            if inl and inl.get("data"):
                return {"image": "data:" + inl.get("mimeType", "image/png") + ";base64," + inl["data"]}
    return {"error": "Gemini 返回无图片（可能被安全策略拦截）"}


def _shrink_image(mime, data):
    """若装了 Pillow 则把首尾帧压到 ≤1280 边 JPEG（大幅减小载荷）；没装则原样返回。"""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        im.thumbnail((1280, 1280))
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        out = buf.getvalue()
        if len(out) < len(data):
            print(f"[proxy] 帧图压缩 {len(data)//1024}KB → {len(out)//1024}KB")
            return "image/jpeg", out
    except Exception:
        pass
    return mime, data


def gen_text(prompt, system=None, context=None, temperature=0.8):
    """LLM 文字生成（P1 预设系统用）：走 OpenAI chat completions。"""
    if not OPENAI_KEY:
        return {"error": "OpenAI key 缺失"}
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    user = (("【上下文/背景资料】\n" + context.strip() + "\n\n") if (context or "").strip() else "") + prompt
    msgs.append({"role": "user", "content": user})
    body = {"model": TEXT_MODEL, "messages": msgs, "temperature": temperature}
    code, raw = _http(OPENAI_BASE + "/chat/completions", json.dumps(body).encode(),
                      {"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_KEY},
                      timeout=120)
    try:
        j = json.loads(raw)
    except Exception:
        return {"error": f"{code}: {raw[:300]!r}"}
    if code >= 400:
        return {"error": f"{code} " + str(j.get("error", {}).get("message", j))}
    try:
        return {"text": j["choices"][0]["message"]["content"]}
    except Exception:
        return {"error": "返回格式异常：" + str(j)[:300]}


_CJK = re.compile(r'[一-鿿]')
_TRANS_CACHE = {}


def _ensure_english(prompt):
    """prompt 含中文时自动转英文提交（带缓存，失败回退原文）。返回 (prompt, 是否翻译了)。"""
    if not _CJK.search(prompt) or not OPENAI_KEY:
        return prompt, False
    key = hashlib.md5(prompt.encode("utf-8")).hexdigest()
    if key in _TRANS_CACHE:
        return _TRANS_CACHE[key], True
    r = gen_text(
        "Rewrite the following image/video generation prompt into pure natural English. "
        "Translate all Chinese into precise, visual English suitable for AI image generation. "
        "Keep all existing English parts, structure markers (such as '||', 'Reference context', "
        "'FRONT, SIDE PROFILE, BACK'), numbers and proper nouns unchanged. "
        "Output ONLY the rewritten prompt, no explanations.\n\n" + prompt,
        temperature=0.2)
    en = (r.get("text") or "").strip().strip("`").strip()
    if en:
        _TRANS_CACHE[key] = en
        print(f"[proxy] 中文prompt已转英文（{len(prompt)}→{len(en)}字符）")
        return en, True
    print("[proxy] 翻译失败，按原文提交：", r.get("error"))
    return prompt, False


def video_submit(prompt, aspect, duration, resolution, first=None, last=None):
    if not (SD_KEY and SD_TASKS):
        return {"error": "Seedance 配置缺失"}
    content = [{"type": "text", "text": prompt}]
    if first:
        content.append({"type": "image_url", "image_url": {"url": _to_dataurl(*_shrink_image(*first))}, "role": "first_frame"})
    if last:
        content.append({"type": "image_url", "image_url": {"url": _to_dataurl(*_shrink_image(*last))}, "role": "last_frame"})
    body = {"model": SD_MODEL, "content": content,
            "resolution": resolution or "720p", "ratio": aspect or "9:16", "duration": int(duration or 8)}
    payload = json.dumps(body).encode()
    print(f"[proxy] video submit 载荷 {len(payload)//1024}KB（帧图 {('有' if first or last else '无')}）")
    code, raw = _http(SD_TASKS, payload,
                      {"Content-Type": "application/json", "Authorization": "Bearer " + SD_KEY}, timeout=180)
    try:
        j = json.loads(raw)
    except Exception:
        return {"error": f"{code}: {raw[:400]!r}"}
    if code >= 400:
        return {"error": f"{code} " + str(j)[:400]}
    vurl = j.get("video_url") or j.get("url")
    if vurl:
        return {"video_url": vurl}
    tid = j.get("id") or j.get("task_id")
    if tid:
        return {"task_id": tid}
    return {"error": "未拿到 task_id：" + str(j)[:300]}


def video_status(task_id):
    if not (SD_KEY and SD_TASKS):
        return {"error": "Seedance 配置缺失"}
    code, raw = _http(f"{SD_TASKS}/{task_id}", None,
                      {"Authorization": "Bearer " + SD_KEY}, method="GET", timeout=20)
    try:
        j = json.loads(raw)
    except Exception:
        return {"error": f"{code}: {raw[:300]!r}"}
    if code >= 400:
        return {"error": f"{code} " + str(j)[:300]}
    st = (j.get("status") or j.get("state") or (j.get("data") or {}).get("status", "")).lower()
    if st in ("completed", "success", "done", "finished", "succeed", "succeeded"):
        vurl = None
        content = j.get("content") or (j.get("data") or {}).get("content")
        if isinstance(content, dict):
            vurl = content.get("video_url") or content.get("url")
        elif isinstance(content, list):
            for it in content:
                if isinstance(it, dict):
                    vurl = it.get("video_url") or it.get("url")
                    if vurl:
                        break
        if not vurl:
            for k in ["video_url", "url", "output", "result", "file_url", "download_url"]:
                if isinstance(j.get(k), str):
                    vurl = j[k]; break
                if isinstance(j.get("data"), dict) and isinstance(j["data"].get(k), str):
                    vurl = j["data"][k]; break
        return {"status": "completed", "video_url": vurl} if vurl else {"status": "completed", "video_url": None}
    if st in ("failed", "error", "cancelled"):
        return {"status": "failed"}
    return {"status": "pending"}


# ── 素材库 ─────────────────────────────────────────────────
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4"}


def asset_save(body):
    kind = body.get("kind") or "image"
    loaded = None
    if body.get("dataURL"):
        loaded = _load_ref(body["dataURL"], kind)
    elif body.get("url"):
        loaded = _load_ref(body["url"], kind)
    if not loaded:
        return {"error": "无法获取素材内容（dataURL/url 均失败）"}
    mime, data = loaded
    day = time.strftime("%Y-%m-%d")
    ddir = os.path.join(ASSET_DIR, day)
    os.makedirs(ddir, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", str(body.get("name") or kind))[:40] or kind
    aid = time.strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6]
    fn = f"{aid}_{name}{_EXT.get(mime, '.bin')}"
    with open(os.path.join(ddir, fn), "wb") as f:
        f.write(data)
    rel = day + "/" + fn
    entry = {"id": aid, "ts": int(time.time()), "date": day, "kind": kind,
             "file": rel, "name": name, "mime": mime, "bytes": len(data),
             "meta": body.get("meta") or {}}
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "id": aid, "file": rel,
            "url": f"http://localhost:{PORT}/asset/file?p={quote(rel)}"}


def assets_list(limit=60, kind=None):
    try:
        lines = open(MANIFEST, encoding="utf-8").read().splitlines()
    except Exception:
        return {"assets": []}
    out = []
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if kind and e.get("kind") != kind:
            continue
        e["url"] = f"http://localhost:{PORT}/asset/file?p={quote(e['file'])}"
        out.append(e)
        if len(out) >= limit:
            break
    return {"assets": out}


# ── HTTP 服务 ──────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code, obj):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _send_bytes(self, data, mime):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._send(200, {"ok": True, "v": 2,
                                    "openai": bool(OPENAI_KEY), "gemini": bool(GEMINI_KEY),
                                    "seedance": bool(SD_KEY)})
        if u.path == "/video/status":
            qs = parse_qs(u.query)
            tid = (qs.get("id") or [""])[0]
            if not tid:
                return self._send(400, {"error": "缺少 id"})
            return self._send(200, video_status(tid))
        if u.path == "/assets":
            qs = parse_qs(u.query)
            limit = int((qs.get("limit") or ["60"])[0])
            kind = (qs.get("kind") or [None])[0]
            return self._send(200, assets_list(limit, kind))
        if u.path == "/asset/file":
            qs = parse_qs(u.query)
            rel = (qs.get("p") or [""])[0]
            fp = _safe_asset_path(rel)
            if not fp:
                return self._send(404, {"error": "素材不存在"})
            mime = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            return self._send_bytes(open(fp, "rb").read(), mime)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        if u.path == "/image":
            prov = (body.get("provider") or "openai").lower()
            prompt = body.get("prompt", "")
            aspect = body.get("aspect", "1:1")
            if not prompt.strip():
                return self._send(400, {"error": "prompt 为空"})
            refs = []
            for r in (body.get("references") or [])[:4]:
                loaded = _load_ref(r)
                if loaded:
                    refs.append(loaded)
            if (body.get("references") and not refs):
                return self._send(200, {"error": "参考图全部读取失败"})
            prompt, translated = _ensure_english(prompt)
            if prov == "gemini":
                res = gen_gemini(prompt, aspect, body.get("model"), refs)
            else:
                res = gen_openai(prompt, aspect, body.get("model"), body.get("quality"), refs)
            if translated and isinstance(res, dict) and not res.get("error"):
                res["prompt_en"] = prompt
            return self._send(200, res)
        if u.path == "/video/submit":
            if not body.get("prompt", "").strip():
                return self._send(400, {"error": "prompt 为空"})
            first = _load_ref(body["first_frame"]) if body.get("first_frame") else None
            last  = _load_ref(body["last_frame"])  if body.get("last_frame")  else None
            if body.get("first_frame") and not first:
                return self._send(200, {"error": "首帧图读取失败"})
            vprompt, translated = _ensure_english(body["prompt"])
            res = video_submit(vprompt, body.get("aspect"),
                               body.get("duration"), body.get("resolution"), first, last)
            if translated and isinstance(res, dict) and not res.get("error"):
                res["prompt_en"] = vprompt
            return self._send(200, res)
        if u.path == "/asset":
            return self._send(200, asset_save(body))
        if u.path == "/text":
            if not body.get("prompt", "").strip():
                return self._send(400, {"error": "prompt 为空"})
            return self._send(200, gen_text(body["prompt"], body.get("system"), body.get("context")))
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print("[proxy]", self.command, self.path.split("?")[0])


if __name__ == "__main__":
    os.makedirs(ASSET_DIR, exist_ok=True)
    print("=" * 56)
    print(" MiniTV 统一本地代理 V2（图生图 / 首尾帧 / 素材库）")
    src = "config.json" if os.path.exists(CONFIG_FILE) else ("records 回退" if os.path.exists(OPENAI_CFG) else "无")
    print(f"  配置来源 : {src}")
    print(f"  OpenAI   : {'OK' if OPENAI_KEY else '缺失 ❌'}  ({OPENAI_BASE}) 文本模型={TEXT_MODEL}")
    print(f"  Gemini   : {'OK' if GEMINI_KEY else '缺失 ❌'}  参考图模型={GEMINI_PRO_MODEL}")
    print(f"  Seedance : {'OK' if SD_KEY else '缺失 ❌'}  model={SD_MODEL}")
    print(f"  素材库   : {ASSET_DIR}")
    if HTTP_PROXY:
        print(f"  网络代理 : {HTTP_PROXY}")
    if INSECURE_HOSTS:
        print(f"  TLS豁免  : {', '.join(sorted(INSECURE_HOSTS))}（自签名中转域，仅这些域跳过证书校验）")
    if not (OPENAI_KEY or GEMINI_KEY or SD_KEY):
        print("-" * 56)
        print("  ⚠ 尚未配置任何 API。请先运行：  python 初始化配置.py")
        print("    它会引导你填入自己的 API 端点 / 代理 / key，生成 config.json")
    print(f"  监听     : http://localhost:{PORT}")
    print("  保持本窗口开着即可使用 MiniTV；关闭窗口即停止。")
    print("=" * 56)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
