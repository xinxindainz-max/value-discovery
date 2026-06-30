#!/usr/bin/env python3
"""
价值发现 · 预检与自愈 v2.0
每次自动化运行前的第一道工序。检查环境完整性，自动修复已知问题。
支持 Windows (本地 WorkBuddy) 和 Linux (GitHub Actions) 双环境。
退出码: 0=全部通过, 1=有警告（可继续）, 2=致命错误（阻断）
v2.0: 跨平台支持、Ghost 源检测、API Key 预检
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import platform
import shutil
import subprocess
import json

# ============================================================
# 环境检测
# ============================================================
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

def get_python_cmd():
    """返回当前环境的 Python 命令"""
    if IS_GITHUB_ACTIONS:
        return "python3"
    if IS_WINDOWS:
        return os.path.join(VENV_DIR, "Scripts", "python.exe") if os.path.exists(VENV_DIR) else sys.executable
    return sys.executable

# ============================================================
# 路径定义（按环境分支）
# ============================================================
if IS_WINDOWS:
    VENV_DIR = os.path.expandvars(r"%USERPROFILE%\.workbuddy\binaries\python\envs\default")
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
    VENV_SITE_PACKAGES = os.path.join(VENV_DIR, "Lib", "site-packages")
    SYSTEM_PYTHON = r"C:\Users\DD\AppData\Local\Programs\Python\Python312\python.exe"
    SYSTEM_SITE_PACKAGES = r"C:\Users\DD\AppData\Local\Programs\Python\Python312\Lib\site-packages"
else:
    VENV_DIR = None
    VENV_PYTHON = None
    VENV_SITE_PACKAGES = None
    SYSTEM_PYTHON = None
    SYSTEM_SITE_PACKAGES = None

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(PIPELINE_DIR))

OK = "  [OK]"
WARN = "  [WARN]"
FAIL = "  [FAIL]"
FIXED = "  [FIXED]"
SKIP = "  [SKIP]"


def check(label, condition, detail=""):
    """统一输出格式"""
    icon = OK if condition else FAIL
    msg = f"{icon} {label}"
    if detail:
        msg += f"  {detail}"
    print(msg)
    return condition


def auto_fix(label, condition, fix_fn, detail=""):
    """检查条件，失败则自动修复"""
    if condition:
        print(f"{OK} {label}")
        return True
    else:
        print(f"{FAIL} {label}{' ' + detail if detail else ''}")
        try:
            fix_fn()
            print(f"{FIXED}")
            return True
        except Exception as e:
            print(f"  修复失败: {e}")
            return False


def run_python(code, timeout=10):
    """安全执行一段 Python 代码，返回 (success, output)"""
    try:
        result = subprocess.run(
            [get_python_cmd(), "-c", code],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 50)
    print(f"价值发现 · 预检与自愈 v2.0")
    print(f"环境: {platform.system()} {'(GitHub Actions)' if IS_GITHUB_ACTIONS else '(本地)'}")
    print(f"Python: {get_python_cmd()}")
    print("=" * 50)
    all_ok = True
    has_warnings = False

    # ================================================================
    # 1. Python 环境
    # ================================================================
    print("\n[1/7] Python 环境")
    py_ok, py_ver = run_python("import sys; print(sys.version.split()[0])")
    if not check("Python 可用", py_ok, py_ver if py_ok else "无"):
        print(f"{FAIL} 致命: Python 不可用")
        return 2

    # ================================================================
    # 2. 依赖包（跨平台自愈）
    # ================================================================
    print("\n[2/7] Python 依赖包")

    # requests — 无则 pip install
    reqs_ok, reqs_ver = run_python("import requests; print(requests.__version__)")
    if not reqs_ok:
        reqs_ok = auto_fix("requests 库", False, lambda: subprocess.run(
            [get_python_cmd(), "-m", "pip", "install", "--quiet", "requests"],
            capture_output=True, timeout=120
        ), "自动安装中...")
    else:
        check("requests 库", True, reqs_ver)

    # PySocks — 仅 Windows 需要（GitHub Actions Ubuntu 直连无需代理）
    if IS_WINDOWS:
        socks_ok, _ = run_python("import socks")
        def fix_socks():
            src = os.path.join(SYSTEM_SITE_PACKAGES, "socks.py")
            dst = os.path.join(VENV_SITE_PACKAGES, "socks.py")
            if os.path.exists(src):
                shutil.copy2(src, dst)
                src_h = os.path.join(SYSTEM_SITE_PACKAGES, "sockshandler.py")
                if os.path.exists(src_h):
                    shutil.copy2(src_h, os.path.join(VENV_SITE_PACKAGES, "sockshandler.py"))
            else:
                socks_dir = os.path.join(SYSTEM_SITE_PACKAGES, "socks")
                if os.path.isdir(socks_dir):
                    shutil.copytree(socks_dir, os.path.join(VENV_SITE_PACKAGES, "socks"), dirs_exist_ok=True)
                else:
                    raise RuntimeError(f"系统Python也没有PySocks: {src}")
        socks_ok = auto_fix("PySocks (SOCKS代理)", socks_ok, fix_socks, "已从系统Python复制" if socks_ok else "")
        if not socks_ok:
            all_ok = False
    else:
        print(f"{SKIP} PySocks — Linux 环境不需要")

    if not reqs_ok:
        all_ok = False

    # ================================================================
    # 3. API 连通性 + 关键 API Key 有效性
    # ================================================================
    print("\n[3/7] 关键 API 连通性")
    connectivity_ok = True

    # UAPIs
    uapis_ok, _ = run_python(
        "import urllib.request; "
        "req=urllib.request.Request('https://uapis.cn',headers={'User-Agent':'Mozilla/5.0'}); "
        "urllib.request.urlopen(req,timeout=8).close(); print('OK')", timeout=10
    )
    if not check("UAPIs (热榜聚合API)", uapis_ok):
        connectivity_ok = False
        has_warnings = True

    # 腾讯自选股行情
    qt_ok, _ = run_python(
        "import urllib.request; "
        "resp=urllib.request.urlopen('https://qt.gtimg.cn/q=sz000333',timeout=8); "
        "data=resp.read().decode('gbk'); print('OK' if '美的' in data else 'NO_DATA')", timeout=10
    )
    if not check("腾讯自选股 (股票行情)", qt_ok):
        connectivity_ok = False
        has_warnings = True

    # TrendsMCP — 不仅测连通，还测 Key 是否有效
    tmc_ok, tmc_msg = run_python(
        "import urllib.request,json; "
        "req=urllib.request.Request('https://api.trendsmcp.ai/api',"
        "data=json.dumps({'mode':'health'}).encode(),"
        "headers={'Authorization':'Bearer tmcp_live_rl5x9g3gvyux2nwhfsgvkmfn9bw0nl2s',"
        "'Content-Type':'application/json'},method='POST'); "
        "resp=urllib.request.urlopen(req,timeout=10); "
        "data=json.loads(resp.read()); print(data.get('status','UNKNOWN'))", timeout=12
    )
    tmc_valid = tmc_ok and not ("401" in (tmc_msg or "") or "403" in (tmc_msg or "") or "UNAUTHORIZED" in (tmc_msg or "").upper() or "INVALID" in (tmc_msg or "").upper())
    if tmc_ok:
        check(f"TrendsMCP API (国际热榜) — {tmc_msg}", tmc_valid,
              "⚠ Key 可能已过期" if not tmc_valid else "Key 有效")
    else:
        check("TrendsMCP API (国际热榜)", False, str(tmc_msg)[:80])
    if not tmc_valid:
        has_warnings = True
        print(f"  {WARN} TrendsMCP Key 失效会导致国际榜全红，但不阻断国内源")

    if not connectivity_ok:
        has_warnings = True

    # ================================================================
    # 4. Ghost 源检测（上次运行失败率超50%的源标记为 Ghost）
    # ================================================================
    print("\n[4/7] Ghost 源检测")
    ghost_count = 0
    last_run_path = os.path.join(PIPELINE_DIR, "data", "latest.json")
    if os.path.exists(last_run_path):
        try:
            with open(last_run_path, "r", encoding="utf-8") as f:
                last = json.load(f)
            if "sources" in last:
                for key, src in last["sources"].items():
                    if src.get("status") != "ok":
                        ghost_count += 1
                        if ghost_count <= 5:
                            print(f"  {WARN} 上次 {src.get('label', key)} 状态: {src.get('status')} — {src.get('error', '')[:60]}")
                if ghost_count > 5:
                    print(f"  {WARN} ... 另有 {ghost_count - 5} 个源上次失败")
                if ghost_count == 0:
                    print(f"{OK} 上次全绿，无 Ghost 源")
                elif ghost_count > 10:
                    print(f"  {WARN} 上次失败源过多 ({ghost_count})，可能网络大面积故障")
        except Exception as e:
            print(f"  {SKIP} 读取上次数据失败: {e}")
    else:
        print(f"  {SKIP} 无上次运行数据（首次运行）")

    # ================================================================
    # 5. 管道脚本完整性
    # ================================================================
    print("\n[5/7] 管道脚本完整性")
    scripts = [
        "data_fetcher.py",
        "stock_fetcher.py",
        "update_html.py",
        "source_registry.py",
    ]
    all_scripts_ok = True
    for s in scripts:
        path = os.path.join(PIPELINE_DIR, s)
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        if not check(s, exists and size > 100,
                     f"大小: {size} bytes" if exists else "缺失"):
            all_scripts_ok = False

    if not all_scripts_ok:
        print(f"  {FAIL} 关键脚本缺失或损坏，阻断运行")
        return 2

    # ================================================================
    # 6. HTML 文件完整性
    # ================================================================
    print("\n[6/7] HTML 文件检查")
    html_path = os.path.join(PROJECT_DIR, "发现榜.html")
    html_exists = os.path.isfile(html_path)
    html_size = os.path.getsize(html_path) if html_exists else 0
    html_min_size = 5000  # HTML 至少5KB才算有效

    if not check("发现榜.html", html_exists and html_size > html_min_size,
                 f"大小: {html_size} bytes" + (" (过小，可能损坏)" if html_size < html_min_size and html_exists else "")):
        print(f"  {FAIL} HTML 文件缺失或损坏")
        return 2

    # 检查 HTML 是否包含关键标记
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    has_cst = "CST" in html_content
    has_source_bar = "src-tag" in html_content
    if not check("HTML 包含时间戳 (CST)", has_cst):
        has_warnings = True
    if not check("HTML 包含源状态栏 (src-tag)", has_source_bar):
        has_warnings = True

    # ================================================================
    # 7. 标签对齐检查
    # ================================================================
    print("\n[7/7] 标签对齐检查")
    try:
        from source_registry import ALL_LABELS, validate_html_labels
        import re
        html_labels = set(re.findall(r'class="src-tag[^"]*"[^>]*>([^<]+)</span>', html_content))
        matched, unmatched = validate_html_labels(html_labels)
        if unmatched:
            print(f"  {FAIL} HTML 中存在未注册标签: {unmatched}")
            print(f"    请在 source_registry.py 中注册或修正 HTML 标签")
            has_warnings = True
        else:
            print(f"{OK} 所有 {len(matched)} 个 HTML 标签均已注册")
    except Exception as e:
        print(f"  {SKIP} 标签检查失败: {e}")

    # ================================================================
    # 结论
    # ================================================================
    print("\n" + "=" * 50)
    if not all_ok:
        print("结果: [WARN] 有警告，可继续运行但部分源可能失败")
        return 1
    if has_warnings:
        print("结果: [WARN] 连通性/Key 告警，继续运行")
        return 1
    print("结果: [OK] 全部通过 · 环境健康")
    return 0


if __name__ == "__main__":
    sys.exit(main())
