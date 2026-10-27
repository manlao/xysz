# -*- coding: utf-8 -*-
"""按官方 nvapp-windows-local 样例结构完全重建市场包源 + zip。

官方样例（从官方市场 zip 提取）：
connectors/nvapp-windows-local/
├── .codebuddy-plugin/plugin.json   ← name(英文)/description(英文)/
│                                      extensions.ai.workbuddy.connector.
│                                      {auth_mode, name(中文), name_en, type,
│                                       description_zh/en, examples_zh/en,
│                                       minWorkbuddyVersion}
│                                      + legacyReason: "stdio-env-template"
│                                      + schemaVersion: "1.0.0"
│                                      + keywords: ["connector","mcp"]
├── mcp.json                         ← 无点前缀（实测无点/点前缀均可）stdio + env ${VAR}
├── ai.workbuddy/token-schema.json
├── assets/icon.png                  ← 顶层 assets/
└── skills/
"""
import json
import os
import shutil
import zipfile

SRC = r"D:\WealthManager\xysz\WealthManager\ad_mcp\connector\amazingdata"
PKG = r"D:\WealthManager\xysz\WealthManager\ad_mcp\connector\marketplace"
C = PKG + r"\connectors\amazingdata-mcp"
meta = json.load(open(SRC + r"\connector-meta.json", encoding="utf-8"))

# ===== 0) 清理旧结构文件 =====
for legacy in (C + r"\mcp.json", C + r"\connector-meta.json",
               C + r"\icon.png", C + r"\ai.workbuddy\assets",
               PKG + r"\install.ps1"):
    if os.path.isdir(legacy):
        shutil.rmtree(legacy, ignore_errors=True)
    elif os.path.exists(legacy):
        os.remove(legacy)

# ===== 1) 目录（官方结构）=====
os.makedirs(C + r"\.codebuddy-plugin", exist_ok=True)
os.makedirs(C + r"\assets", exist_ok=True)
os.makedirs(C + r"\skills\amazingdata", exist_ok=True)

# ===== 2) plugin.json：严格照抄官方 nvapp 结构 =====
pj = {
    "description": meta["description_en"],
    "extensions": {
        "ai.workbuddy": {
            "connector": {
                "auth_mode": "token",
                "description_en": meta["description_en"],
                "description_zh": meta["description_zh"],
                "examples_en": meta["examples_en"],
                "examples_zh": meta["examples_zh"],
                "minWorkbuddyVersion": "4.24.0",
                "name": meta["name_zh"],
                "name_en": meta["name_en"],
                "type": "mcp",
            },
            "legacyReason": "stdio-env-template",
            "schemaVersion": "1.0.0",
        }
    },
    "keywords": ["connector", "mcp"],
    "name": "amazingdata-mcp",
    "version": "1.0.6",
}
json.dump(pj, open(C + r"\.codebuddy-plugin\plugin.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ===== 2b) connector-meta.json：官网文档规范必填（腾讯审核要求存在；
#           WorkBuddy 运行时忽略，不影响已验证的表单/图标/中文名流程）=====
meta_json = {
    "name": meta["name_zh"],
    "name_en": meta["name_en"],
    "description": meta["description_en"],
    "description_zh": meta["description_zh"],
    "description_en": meta["description_en"],
    "source": "amazingdata-mcp",
    "type": "mcp",
    "version": "1.0.6",
    "examples_zh": meta["examples_zh"],
    "examples_en": meta["examples_en"],
    "auth_mode": "token",
    "minWorkbuddyVersion": "4.24.0",
}
json.dump(meta_json, open(C + r"\connector-meta.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ===== 3) mcp.json：无点前缀 + stdio + env（用户名/密码占位符；
#           HOST/PORT 官方默认值写死，用户不再填写）=====
mcp = {"mcpServers": {"amazingdata": {
    "type": "stdio", "command": "npx",
    "args": ["-y", "https://gitee.com/cgs2026/xysz/releases/download/v1.0.0/amazingdata-mcp-launcher-1.0.6.tgz"],
    "env": {"AD_USERNAME": "${AD_USERNAME}", "AD_PASSWORD": "${AD_PASSWORD}",
            "AD_HOST": "101.230.159.235", "AD_PORT": "8600",
            "SystemDrive": "C:", "SystemRoot": "C:\\Windows",
            "PYTHONIOENCODING": "utf-8"},
    "timeout": 600000}}}
json.dump(mcp, open(C + r"\mcp.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
_legacy = C + r"\.mcp.json"
if os.path.exists(_legacy):
    os.remove(_legacy)

# ===== 4) token-schema（官方位置 ai.workbuddy/；连接器根目录再放一份兼容旧解析）=====
shutil.copy(SRC + r"\token-schema.json", C + r"\ai.workbuddy\token-schema.json")
shutil.copy(SRC + r"\token-schema.json", C + r"\token-schema.json")

# ===== 5) 图标：assets/icon.png + 包根 icon.png（腾讯审核要求根目录有 icon） =====
import base64
import re as _re
svg = open(SRC + r"\icon.svg", "rb").read().decode("utf-8")
m = _re.search(r"base64,([A-Za-z0-9+/=]+)", svg)
_png = base64.b64decode(m.group(1))
open(C + r"\assets\icon.png", "wb").write(_png)
open(C + r"\icon.png", "wb").write(_png)

# ===== 6) skills（README 不再进包：腾讯审核包与市场包均不需要） =====
shutil.copy(SRC + r"\skills\amazingdata\SKILL.md",
            C + r"\skills\amazingdata\SKILL.md")
_rm = C + r"\README.md"
if os.path.exists(_rm):
    os.remove(_rm)

# ===== 7) marketplace.json：官方极简 4 字段条目 =====
p0 = {"description": meta["description_en"], "name": "amazingdata-mcp",
      "source": "./connectors/amazingdata-mcp", "version": "1.0.6"}
json.dump({"name": "workbuddy-connector-plugins-local",
           "description": "China Galaxy Securities local debug marketplace",
           "owner": {"name": "China Galaxy Securities", "email": "dev@example.com"},
           "plugins": [p0]},
          open(PKG + r"\.codebuddy-plugin\marketplace.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ===== 8) 打包 zip =====
OUT = PKG + r"\connector-plugins.zip"
n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f == "connector-plugins.zip":
                continue
            full = os.path.join(root, f)
            zf.write(full, os.path.relpath(full, PKG).replace("\\", "/"))
            n += 1

print("rebuild(official-structure) done:")
for root, dirs, files in os.walk(PKG):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        print("   ", os.path.relpath(os.path.join(root, f), PKG).replace("\\", "/"))
print("zip:", n, "files,", os.path.getsize(OUT), "bytes")

# ===== 9) 同步到 WorkBuddy 市场缓存 =====
CACHE = os.path.expandvars(
    r"%USERPROFILE%\.workbuddy\plugins\marketplaces\workbuddy-connector-plugins-official")
shutil.rmtree(CACHE, ignore_errors=True)
with zipfile.ZipFile(OUT) as zf:
    zf.extractall(CACHE)
mm = os.path.expandvars(r"%USERPROFILE%\.workbuddy\connectors\marketplace-meta")
shutil.rmtree(mm, ignore_errors=True)
print("cache synced + fingerprint cleared")
