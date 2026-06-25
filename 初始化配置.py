#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniTV 初始化配置 —— 第一次使用时运行这个，填入你自己的 API 信息，生成 config.json。

用法：双击本文件，或命令行 `python 初始化配置.py`
说明：
  - 三个引擎（OpenAI 出图/写文案、Gemini 出图、Seedance 出视频）都是可选的，
    只填你有的，留空回车跳过；跳过的引擎在 MiniTV 里就用不了。
  - "代理地址/中转地址"= 你的 API 端点（base url）。用官方就直接回车用默认；
    用中转/代理服务就填它给你的地址。
  - 如果你访问 OpenAI 需要科学上网，可在最后填"网络代理"（如 http://127.0.0.1:7890）。
  - 生成的 config.json 含明文 key，属你的私密文件，请勿外发、勿随工程分享。
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "config.json")


def ask(prompt, default=""):
    s = input(prompt + (f" [{default}]" if default else "") + "：").strip()
    return s or default


def section(title):
    print("\n" + "─" * 50)
    print("● " + title)
    print("─" * 50)


def main():
    print("=" * 50)
    print(" MiniTV 配置向导")
    print(" 只填你有的，没有的直接回车跳过。")
    print("=" * 50)

    cfg = {}
    old = {}
    if os.path.exists(CONFIG_FILE):
        try:
            old = json.load(open(CONFIG_FILE, encoding="utf-8"))
            print("（检测到已有 config.json，回车则保留原值）")
        except Exception:
            old = {}

    def og(p, f, d=""):
        return (old.get(p) or {}).get(f) or d

    # OpenAI
    section("OpenAI（用于：文生图 gpt-image / 写脚本文案 / 中文转英文）")
    o_key = ask("  OpenAI API Key（sk-... ，没有就回车跳过）", og("openai", "api_key"))
    if o_key:
        o_base = ask("  OpenAI 端点/中转地址", og("openai", "base_url", "https://api.openai.com/v1"))
        cfg["openai"] = {"api_key": o_key, "base_url": o_base}

    # Gemini
    section("Gemini（用于：文生图 / 图生图 Nano Banana）")
    g_key = ask("  Gemini API Key（没有就回车跳过）", og("gemini", "api_key"))
    if g_key:
        g_base = ask("  Gemini 端点/中转地址", og("gemini", "base_url", "https://generativelanguage.googleapis.com/v1beta/models"))
        g_model = ask("  默认出图模型", og("gemini", "model", "gemini-2.5-flash-image"))
        g_pro = ask("  带参考图(图生图)模型", og("gemini", "pro_model", "gemini-3-pro-image-preview"))
        cfg["gemini"] = {"api_key": g_key, "base_url": g_base, "model": g_model, "pro_model": g_pro}

    # Seedance
    section("Seedance（用于：生成视频）")
    s_key = ask("  Seedance API Key（没有就回车跳过）", og("seedance", "api_key"))
    if s_key:
        s_base = ask("  Seedance 端点/中转地址（如 https://xxx.com/api/v3）", og("seedance", "base_url"))
        s_model = ask("  视频模型", og("seedance", "model", "doubao-seedance-2-0-fast-260128"))
        cfg["seedance"] = {"api_key": s_key, "base_url": s_base, "model": s_model}

    # 公共
    section("其他（可选，回车跳过）")
    tm = ask("  文案/翻译用的文本模型", old.get("text_model", "gpt-4o"))
    if tm:
        cfg["text_model"] = tm
    proxy = ask("  网络代理（访问墙外API用，如 http://127.0.0.1:7890；不需要就回车）", old.get("http_proxy", ""))
    if proxy:
        cfg["http_proxy"] = proxy

    if not (cfg.get("openai") or cfg.get("gemini") or cfg.get("seedance")):
        print("\n⚠ 你没填任何一个引擎的 key，config.json 不会生成。至少填一个才能用。")
        input("按回车退出…")
        return

    json.dump(cfg, open(CONFIG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n" + "=" * 50)
    print("✓ 已生成 config.json：")
    print("   OpenAI  :", "已配置" if cfg.get("openai") else "（未填，用不了）")
    print("   Gemini  :", "已配置" if cfg.get("gemini") else "（未填，用不了）")
    print("   Seedance:", "已配置" if cfg.get("seedance") else "（未填，用不了）")
    print("\n⚠ config.json 含你的明文 key，请勿外发、勿随工程分享。")
    print("下一步：双击 start.bat 启动代理，再用浏览器打开 MiniTV.html。")
    print("=" * 50)
    input("按回车退出…")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n已取消。")
