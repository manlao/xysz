"""星耀数智连接器引导脚本（含依赖自动安装）。

链路：npx → bootstrap.js → 本脚本 → server.py
1. 元数据快检：fastmcp / pandas / tgw / AmazingData 是否齐全，缺则全量安装
   （Gitee Release 下载私有 whl：先 tgw 后 AmazingData，顺序不可颠倒；
   公共包走清华镜像，失败回退官方 PyPI）；
2. 真实导入探针：在子进程中实际 import（WorkBuddy 精简环境可能看不到
   用户级 site-packages，元数据检查会误判"就绪"）；结果按
   「python 路径 + 四大件版本」签名缓存到 logs/deps_verified.flag，
   常规启动签名命中即跳过，server 启动异常时自动清除兜底；
3. 自愈循环：探针发现缺模块时补装——公共包按 pip 名装，私有包
   （tgw / AmazingData）PyPI 不存在，回退 Gitee Release 全量安装，
   最多 3 轮；
4. 登录预检：仅在本轮发生过依赖安装时执行，确认 tgw 在新环境可用；
   常规启动不做（server.py 自行登录），避免 tgw 单点会话被重复登录挤占；
5. 全部通过后在当前进程内启动 server.py，stdout 全程保持 MCP 协议通道干净。

诊断：本脚本将自身及全部子进程的 stderr 镜像写入 logs/bootstrap_run.log
（黑匣子，超限自动截断），server.log 与 bootstrap_status.txt 也在 logs/ 下。
手动修复：直接运行 `python bootstrap.py`（自动补装依赖并启动服务）。
"""
import ast
import importlib.util
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib.metadata import distributions

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
LOG_DIR = os.path.join(HERE, "logs")

REQUIRED = ("fastmcp", "pandas", "requests", "tgw", "AmazingData")
IMPORT_TARGETS = ("fastmcp", "pandas", "requests", "tgw", "AmazingData")
# 私有包（仅 Gitee Release 有，PyPI 不存在）→ 缺失时回退全量安装
PRIVATE_MODULES = ("tgw", "AmazingData")

# Gitee Release v1.0.0 附件（实测可直连下载，含 68MB 大文件）
RELEASE_BASE = "https://gitee.com/cgs2026/xysz/releases/download/v1.0.0"
RELEASE_API = "https://gitee.com/api/v5/repos/cgs2026/xysz/releases/tags/v1.0.0"
TGW_WHL_NAME = "tgw-1.0.9.2-py3-none-any.whl"
# AmazingData 最低可接受版本：运行时通过 Gitee API 列出 Release 全部附件，
# 自动选取「匹配当前 Python 的最高版本」安装——升级只需传新 whl，代码零改动。
AMAZINGDATA_MIN_VERSION = (1, 1, 9)
SUPPORTED_PY_TAGS = ("cp38", "cp39", "cp310", "cp311", "cp312", "cp313", "cp314")
DOWNLOAD_RETRIES = 3  # 下载重试次数（网络抖动容错）
# wheel 下载缓存目录（避免重复下载 68MB 的 tgw）
CACHE_DIR = os.path.join(tempfile.gettempdir(), "amazingdata_mcp_wheels")
MIRRORS = (
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
)

# 服务器地址/端口官方默认值：用户只需填用户名+密码，无需再填 IP/端口
DEFAULT_AD_HOST = "101.230.159.235"
DEFAULT_AD_PORT = "8600"

LOGIN_PROBE_CODE = (
    "import AmazingData as ad\n"
    "ok = ad.login(\n"
    "    __import__('os').environ['AD_USERNAME'],\n"
    "    __import__('os').environ['AD_PASSWORD'],\n"
    "    __import__('os').environ['AD_HOST'],\n"
    "    int(__import__('os').environ['AD_PORT']),\n"
    ")\n"
    "print('LOGIN_PRECHECK_OK' if ok else 'LOGIN_PRECHECK_FALSE')\n"
)


def apply_env_defaults():
    """HOST/PORT 未注入（或仍是占位符字面量）时写官方默认值。

    必须在 credentials_state/login 之前调用，且写入的是进程环境变量——
    login 预检子进程与 runpy 启动的 server.py 都会继承。"""
    for k, dft in (("AD_HOST", DEFAULT_AD_HOST), ("AD_PORT", DEFAULT_AD_PORT)):
        v = os.environ.get(k) or ""
        if not v.strip() or v.startswith("${"):
            os.environ[k] = dft

# 黑匣子日志上限（字节），超过则只保留尾部，避免长期运行无限膨胀
BLACKBOX_MAX_BYTES = 2 * 1024 * 1024


def log(msg):
    # stdout 是 MCP 协议通道，所有日志只能走 stderr
    print("[AmazingData] " + msg, file=sys.stderr, flush=True)


def setup_blackbox():
    """把 stderr 镜像到文件（黑匣子），并给每次 spawn 打时间戳头。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, "bootstrap_run.log")
        _rotate_if_needed(path)
        f = open(path, "ab", buffering=0)
        f.write(("\n==== bootstrap spawn %s pid=%s ====\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid())).encode())
        os.dup2(f.fileno(), 2)
    except OSError:
        pass


def _rotate_if_needed(path, keep=BLACKBOX_MAX_BYTES // 2):
    """日志超过上限时截断，只保留尾部 keep 字节（历史 spawn 记录价值低）。"""
    try:
        if os.path.exists(path) and os.path.getsize(path) > BLACKBOX_MAX_BYTES:
            with open(path, "rb") as f:
                f.seek(-keep, os.SEEK_END)
                tail = f.read()
            with open(path, "wb") as f:
                f.write("...[日志已截断]...\n".encode("utf-8") + tail)
    except OSError:
        pass


INSTANCE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "amazingdata_mcp_bootstrap.lock")


def acquire_instance_lock(timeout=900):
    """单实例锁：WorkBuddy 重试会并发拉起多个 bootstrap，并发 pip 安装必互相踩踏。

    后到的进程在此等待先到的完成安装（最长 timeout 秒），拿到锁后依赖多半
    已就绪，ensure_deps 走毫秒级快检快车道。返回锁文件句柄（关闭即释放）。
    Windows 用 msvcrt.locking，Linux/macOS 用 fcntl.flock；都不可用时退化为无锁。
    """
    if os.name == "nt":
        try:
            import msvcrt
        except ImportError:
            return None
        try:
            fh = open(INSTANCE_LOCK_PATH, "a+")
        except OSError:
            return None

        def _try_lock():
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        try:
            import fcntl
        except ImportError:
            return None  # 锁不可用则退化为无锁（不阻塞主流程）
        try:
            fh = open(INSTANCE_LOCK_PATH, "a+")
        except OSError:
            return None

        def _try_lock():
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    waited = False
    start = time.time()
    while True:
        try:
            _try_lock()
            fh.seek(0)
            fh.write(str(os.getpid()))
            if waited:
                log("前序安装实例已完成，继续启动流程。")
            return fh
        except OSError:
            if not waited:
                log("检测到另一个 bootstrap 正在安装依赖，等待其完成（最长 %ds）..." % timeout)
                waited = True
            if time.time() - start > timeout:
                fh.close()
                return None
            time.sleep(2)


def write_status(ok, detail):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "bootstrap_status.txt"), "a", encoding="utf-8") as f:
            f.write("[%s] %s %s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                "OK" if ok else "FAIL",
                detail,
            ))
    except OSError:
        pass


# ---------------- 依赖签名缓存 ----------------

# 依赖验证缓存：全部可导入后记录「python 路径 + 四大件版本」签名，
# 后续启动签名一致则跳过导入探针（常规连接省 ~5s）；runpy 失败时清除兜底。
DEPS_FLAG = os.path.join(LOG_DIR, "deps_verified.flag")
_SIG_MODULES = {"fastmcp", "pandas", "tgw", "amazingdata"}


def deps_signature():
    parts = ["python=" + sys.executable]
    try:
        for d in distributions():
            name = (d.metadata["Name"] or "").lower()
            if name in _SIG_MODULES:
                parts.append("%s==%s" % (name, d.version))
    except Exception:
        return "unavailable"
    return ";".join(sorted(parts))


def deps_flag_valid():
    try:
        with open(DEPS_FLAG, "r", encoding="utf-8") as f:
            return f.read().strip() == deps_signature()
    except OSError:
        return False


def write_deps_flag():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(DEPS_FLAG, "w", encoding="utf-8") as f:
            f.write(deps_signature())
    except OSError:
        pass


def clear_deps_flag():
    try:
        os.remove(DEPS_FLAG)
    except OSError:
        pass


# ---------------- 依赖检测与安装 ----------------

def deps_ok():
    installed = {d.metadata["Name"].lower() for d in distributions()}
    missing = [n for n in REQUIRED if n.lower() not in installed]
    if missing:
        log("缺少依赖: " + ", ".join(missing))
    return not missing


def download(url, dest):
    """下载文件到 dest（.part 临时文件 + 原子替换），已缓存则跳过；失败自动重试。"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        log("使用缓存: " + dest)
        return dest
    last_err = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            log("下载 " + url + ("（第 %d 次尝试）" % attempt if attempt > 1 else ""))
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                os.replace(tmp, dest)
            log("已保存: %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1048576.0))
            return dest
        except urllib.error.HTTPError:
            raise  # 4xx/5xx 客户端错误重试无意义，直接抛给调用方处理
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            log("下载失败: " + str(e))
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(2 * attempt)  # 递增退避：2s / 4s
    raise last_err


def pip_install(*args):
    """多镜像安装：腾讯云 → 清华 → 官方 PyPI 依次回退（兼容受限网络环境）。

    实测部分企业/审核网络对清华源返回 403（pip 表现为 versions: none），
    故前置腾讯云镜像、保留清华源、官方 PyPI 兜底。
    stdout/stderr 全部重定向到本进程 stderr，不污染 MCP 协议通道。
    """
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    for idx, mirror in enumerate(MIRRORS):
        try:
            subprocess.check_call(base + ["-i", mirror] + list(args),
                                  stdout=sys.stderr, stderr=sys.stderr)
            return True
        except subprocess.CalledProcessError:
            log("%s 安装失败，切换下一个源重试..." % mirror.split("/")[2])
    try:
        subprocess.check_call(base + list(args),
                              stdout=sys.stderr, stderr=sys.stderr)
        return True
    except subprocess.CalledProcessError:
        return False


def latest_amazingdata_whl(py_tag):
    """通过 Gitee API 列出 Release 附件，选匹配 py_tag 的最高版本 whl。

    返回 (版本元组, whl 文件名, 下载 URL)；无匹配返回 None。
    """
    req = urllib.request.Request(RELEASE_API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        release = json.loads(resp.read().decode("utf-8"))
    pattern = re.compile(r"^AmazingData-(\d+\.\d+\.\d+)-(%s)-none-any\.whl$" % py_tag)
    best = None
    for asset in release.get("assets") or []:
        m = pattern.match(asset.get("name") or "")
        if not m:
            continue
        ver = tuple(int(x) for x in m.group(1).split("."))
        if ver < AMAZINGDATA_MIN_VERSION:
            continue
        if best is None or ver > best[0]:
            best = (ver, asset["name"], asset.get("browser_download_url"))
    return best


def install_all():
    """全量安装：Gitee Release 私有 whl（先 tgw 后 AmazingData）+ 公共依赖。

    返回 True 表示安装成功。顺序不可颠倒：AmazingData 声明依赖 tgw>=1.0.9.1，
    若先装 AmazingData，pip 会去 PyPI 解析私有包 tgw 而报错。
    """
    py_tag = "cp{0}{1}".format(sys.version_info.major, sys.version_info.minor)
    if py_tag not in SUPPORTED_PY_TAGS:
        log("不支持的 Python 版本: %s（支持: %s）" % (py_tag, " / ".join(SUPPORTED_PY_TAGS)))
        return False
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except OSError:
        pass
    # 1. tgw
    try:
        tgw_whl = download(RELEASE_BASE + "/" + TGW_WHL_NAME,
                           os.path.join(CACHE_DIR, TGW_WHL_NAME))
    except Exception as e:
        log("tgw 下载失败: %s" % e)
        return False
    # --force-reinstall --no-deps：无论本地是否已装同/旧版本，强制以 Gitee whl 覆盖；
    # --no-deps 保证私有包安装完全不依赖镜像源可用性（公共依赖由第 3 步显式装齐）
    if not pip_install("--force-reinstall", "--no-deps", tgw_whl):
        return False
    # 2. AmazingData（Gitee API 列附件，选匹配 py_tag 的最高版本）
    try:
        best = latest_amazingdata_whl(py_tag)
    except Exception as e:
        log("获取 Gitee Release 附件列表失败: %s" % e)
        return False
    if not best:
        log("Gitee Release v1.0.0 上未找到 AmazingData >= %s 且匹配 %s 的 wheel，"
            "请确认新 whl 已上传 Release。" % (
                ".".join(map(str, AMAZINGDATA_MIN_VERSION)), py_tag))
        return False
    ad_ver, ad_name, ad_url = best
    log("选定 AmazingData %s（%s）" % (".".join(map(str, ad_ver)), ad_name))
    try:
        ad_whl = download(ad_url or (RELEASE_BASE + "/" + ad_name),
                          os.path.join(CACHE_DIR, ad_name))
    except Exception as e:
        log("AmazingData 下载失败: %s" % e)
        return False
    # 同上：强制覆盖本地已有版本（含同版本），私有包安装不触网
    if not pip_install("--force-reinstall", "--no-deps", ad_whl):
        return False
    # 3. 公共依赖：显式列全（ AmazingData whl 声明的依赖在 --no-deps 下不会自动装）
    return pip_install("fastmcp>=4.0.3", "pandas", "requests",
                       "pydantic>=2.6.4", "numba>=0.65.0",
                       "scipy>=1.15.1", "statsmodels>=0.15.0")


def ensure_deps():
    """元数据快检 + 全量安装。返回 (依赖是否齐备, 本轮是否发生过安装)。"""
    if deps_ok():
        return True, False
    log("首次运行检测到依赖未安装，开始自动安装（tgw 安装包约 67MB，预计 3~5 分钟，请耐心等待）...")
    if not install_all() or not deps_ok():
        log("依赖自动安装失败。请重新连接连接器（将自动重试），或手动运行: python bootstrap.py")
        return False, True
    log("依赖安装完成。")
    return True, True


def probe_imports():
    """在子进程中真实 import 所有目标模块，返回缺失的 pip 包名列表。"""
    code = (
        "import importlib, sys\n"
        "missing = []\n"
        "for m in %r:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "    except Exception as e:\n"
        "        missing.append(m + ':' + type(e).__name__ + ':' + str(e))\n"
        "print('MISSING=' + repr(missing))\n" % (list(IMPORT_TARGETS),)
    )
    try:
        r = subprocess.run([sys.executable, "-c", code],
                           stdout=subprocess.PIPE, stderr=sys.stderr, timeout=180)
    except subprocess.TimeoutExpired:
        log("导入探针超时（180s）。")
        return None
    if r.returncode != 0:
        log("导入探针异常退出（code=%s / 0x%08X）。" % (r.returncode, r.returncode & 0xFFFFFFFF))
        return None
    out = r.stdout.decode("utf-8", errors="replace")
    m = re.search(r"MISSING=(\[.*\])", out)
    if not m:
        log("导入探针输出异常: " + out[:200])
        return None
    missing = []
    try:
        items = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        log("导入探针输出无法解析: " + m.group(1)[:200])
        return None
    for item in items:
        mod, exc_type, exc_msg = item.split(":", 2)
        if exc_type == "ModuleNotFoundError":
            # 区分两种情形：顶层包真的没装（pip 补装有效）vs 包已装但内部
            # import 失败（重装无效，必须暴露真实缺失的模块名）。
            try:
                spec_ok = importlib.util.find_spec(mod) is not None
            except Exception:
                spec_ok = False
            if spec_ok:
                log("模块 %s 已安装但导入失败（ModuleNotFoundError: %s）"
                    % (mod, exc_msg[:300]))
            else:
                log("模块 %s 未安装，需要补装" % mod)
                missing.append(mod)
        else:
            log("模块 %s 导入失败（%s: %s）" % (mod, exc_type, exc_msg[:200]))
    return missing


def self_heal(max_rounds=3):
    """导入探针 + 补装循环。返回 (最终是否全部可导入, 本轮是否发生过补装)。

    签名缓存命中时跳过探针（依赖环境自上次验证后未变）。
    公共包（fastmcp / pandas）按 pip 名直接补装；
    私有包（tgw / AmazingData）PyPI 不存在，回退 Gitee Release 全量安装。
    """
    if deps_flag_valid():
        log("依赖签名校验通过（缓存命中），跳过导入探针。")
        return True, False
    installed = False
    for round_no in range(1, max_rounds + 1):
        missing = probe_imports()
        if missing is None:
            return False, installed
        if not missing:
            if round_no > 1:
                log("第 %d 轮自愈后所有依赖均可导入。" % round_no)
            write_deps_flag()
            return True, installed
        installed = True
        if any(mod in PRIVATE_MODULES for mod in missing):
            log("缺少私有依赖 %s，开始全量安装（第 %d/%d 轮）..." % (
                "/".join(m for m in missing if m in PRIVATE_MODULES), round_no, max_rounds))
            if not install_all():
                log("全量安装执行失败。")
                return False, installed
            continue
        pip_names = [m.replace("_", "-") for m in missing]
        log("运行环境缺少模块: %s，开始补装（第 %d/%d 轮）..." % (
            ", ".join(missing), round_no, max_rounds))
        if not pip_install(*pip_names):
            log("模块补装失败: %s" % ", ".join(pip_names))
            return False, installed
    return False, installed


# ---------------- 登录预检与启动 ----------------

CRED_KEYS = ("AD_USERNAME", "AD_PASSWORD", "AD_HOST", "AD_PORT")


def refresh_pth_and_dlls():
    """修复「首次冷装后 server 必挂」的根因（pywintypes 导入失败）。

    pip 以子进程方式装 pywin32 时会写入 pywin32.pth，但 .pth 只在解释器
    启动那一刻读取一次；本 bootstrap 进程先于安装启动，runpy.run_path
    是在老进程里跑 server.py，.pth 里的 win32\\lib、pywin32_system32
    不在 sys.path 上 → import pywintypes 必然 ModuleNotFoundError，
    第二次连接（全新解释器）才正常。对策：runpy 前重跑 site.main()
    补处理全部 .pth，并显式注册 pywin32 的 DLL 目录。"""
    try:
        import site
        site.main()  # 重新处理 site-packages/*.pth（幂等，重复路径无害）
        log("site 路径已刷新（.pth 已重新处理）。")
    except Exception as e:
        log("site.main() 刷新失败（忽略）：%s" % e)
    for sp in list(sys.path):
        try:
            if (sp and os.path.isdir(sp)
                    and os.path.basename(os.path.normpath(sp)).lower()
                    == "pywin32_system32"):
                os.add_dll_directory(sp)
        except (AttributeError, OSError):
            pass


def credentials_state():
    """检查环境变量里的凭证是否由 WorkBuddy 真正注入。

    返回 (ok, missing_key)：占位符未替换（字面量 ${...}）、空值或端口非数字
    均视为未注入——首次连接必须由用户在连接器面板填写，
    或在会话中通过 mcp_login 工具手动输入，不允许拿占位符去登录。
    """
    for k in CRED_KEYS:
        v = os.environ.get(k) or ""
        if not v.strip() or v.startswith("${"):
            return False, k
    try:
        int(os.environ.get("AD_PORT"))
    except (TypeError, ValueError):
        return False, "AD_PORT"
    return True, None


def login_precheck(timeout=60):
    """带超时的真实登录预检：确认 tgw 在当前 spawn 环境能完成登录。

    返回 (ok, detail)。退出码非 0 表示原生库崩溃，超时表示登录挂起。
    仅在「本轮发生过依赖安装」且凭证已注入时调用，避免每次连接重复登录 tgw 单点会话。
    """
    try:
        r = subprocess.run([sys.executable, "-u", "-c", LOGIN_PROBE_CODE],
                           stdout=subprocess.PIPE, stderr=sys.stderr, timeout=timeout)
    except subprocess.TimeoutExpired:
        write_status(False, "登录预检超时(%ds)：tgw 登录挂起，疑似网络受限或会话冲突" % timeout)
        log("登录预检超时(%ds)。" % timeout)
        return False, "登录预检超时(%ds)" % timeout
    out = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0:
        detail = "登录预检崩溃：退出码 %s (0x%08X)（tgw 原生库崩溃特征）" % (
            r.returncode, r.returncode & 0xFFFFFFFF)
        write_status(False, detail)
        log(detail)
        return False, detail
    if "LOGIN_PRECHECK_OK" not in out:
        detail = "登录预检未通过：登录返回失败（输出尾部: %s）" % out[-200:].replace("\n", " ")
        write_status(False, detail)
        log(detail)
        return False, detail
    log("登录预检通过。")
    return True, "登录预检通过"


def main():
    setup_blackbox()
    apply_env_defaults()  # HOST/PORT 默认值必须在凭证检查与登录预检之前写入
    # --deps-only：仅确保依赖就绪后退出（供 launcher --prepare 在 detached
    # 启动 server 前调用；streamable-http 模式下 WorkBuddy 直连端口，
    # server 由 launcher 以 detached 方式拉起）
    deps_only = "--deps-only" in sys.argv
    log("bootstrap 启动，python=%s" % sys.executable)
    # 并发防护：等前一个安装实例结束再动手（拿到锁后依赖通常已就绪）
    _lock_fh = acquire_instance_lock()
    if _lock_fh is None:
        write_status(False, "等待前序安装实例超时（15 分钟），请重新连接重试")
        sys.exit(1)
    deps_ready, installed_ensure = ensure_deps()
    healed, installed_heal = (False, False)
    if deps_ready:
        healed, installed_heal = self_heal()
    _lock_fh.close()  # 安装阶段结束即释放，server 运行期间不占锁
    if not healed:
        clear_deps_flag()
        write_status(False, "依赖未就绪，详见 stderr/上方日志")
        log("启动失败。排查步骤：① 查看本目录 logs/bootstrap_status.txt 与 bootstrap_run.log；"
            "② 重新连接连接器（将自动重试安装）。")
        sys.exit(1)
    cred_ok, missing = credentials_state()
    if not cred_ok:
        # 凭证未注入：首次连接由用户在面板填写，或在会话中用 mcp_login 手动输入。
        # 不在此处失败——服务仍可用，AI 可引导用户手动登录。
        log("凭证未注入（%s）：请在连接器面板填写账号/密码，"
            "或在会话中调用 mcp_login 手动登录。" % missing)
        write_status(True, "依赖就绪，等待用户手动提供凭证（%s 未注入）" % missing)
    else:
        installed_now = installed_ensure or installed_heal
        if installed_now:
            # 仅在本轮发生过安装时做真实登录预检：验证 tgw 在新环境可用。
            # 常规启动不做（server.py 会自行登录），避免 tgw 单点会话被重复登录挤占。
            ok, detail = login_precheck()
            if not ok:
                clear_deps_flag()
                log("启动中止：%s。请查看 logs/bootstrap_run.log 定位。" % detail)
                sys.exit(1)
            write_status(True, "依赖安装完成 + 登录成功（预检通过），启动 server.py")
        else:
            write_status(True, "依赖就绪（签名缓存校验），直接启动 server.py")
    if deps_only:
        log("--deps-only：依赖已就绪，退出（server 由 launcher detached 拉起）")
        return
    log("依赖就绪，正在启动 MCP 服务（stdio 模式）...")
    refresh_pth_and_dlls()  # 首次冷装后必须补读 .pth，否则 pywintypes 必挂
    # 兜底：极端环境（site 被禁用 / .pth 写到意外位置）下补读仍可能失败。
    # 此时不再 runpy，改用全新解释器子进程启动 server —— 100% 等价「第二次连接」，
    # 从机制上保证首次冷装不会因 pywin32 未生效而失败。stdio 直连透传。
    if os.name == "nt":
        try:
            import importlib.util as _ilu
            _missing = _ilu.find_spec("pywintypes") is None
        except Exception:
            _missing = False
        if _missing:
            log("pywintypes 仍不可见：降级为新进程启动 server（等价第二次连接）。")
            try:
                rc = subprocess.call([sys.executable, "-u", SERVER],
                                     stdin=sys.stdin, stdout=sys.stdout,
                                     stderr=sys.stderr)
                raise SystemExit(rc)
            except SystemExit:
                raise
            except BaseException as e:
                log("子进程启动失败（回退 runpy）：%s" % e)
    # stdio 模式：WorkBuddy 经管道协议通信；凭证由 connector-meta.json 的
    # auth_mode=token 触发表单收集、经 env 注入（${AD_USERNAME} 等占位符替换）。
    sys.argv = [SERVER]
    try:
        runpy.run_path(SERVER, run_name="__main__")
    except SystemExit:
        raise
    except BaseException as e:
        # server 启动即崩（如依赖损坏而签名未变）→ 清缓存标志，下次连接强制重新探针
        clear_deps_flag()
        write_status(False, "server.py 启动异常：%s: %s" % (type(e).__name__, str(e)[:200]))
        raise


if __name__ == "__main__":
    main()
