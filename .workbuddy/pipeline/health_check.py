#!/usr/bin/env python3
"""
价值发现 · 预检与自愈 v1.0
每次自动化运行前的第一道工序。检查环境完整性，自动修复已知问题。
退出码: 0=全部通过, 1=有警告（可继续）, 2=致命错误（阻断）
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import sys
import shutil
import subprocess

# ============================================================
# 路径定义
# ============================================================
VENV_DIR = os.path.expandvars(r"%USERPROFILE%\.workbuddy\binaries\python\envs\default")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
VENV_SITE_PACKAGES = os.path.join(VENV_DIR, "Lib", "site-packages")
SYSTEM_PYTHON = r"C:\Users\DD\AppData\Local\Programs\Python\Python312\python.exe"
SYSTEM_SITE_PACKAGES = r"C:\Users\DD\AppData\Local\Programs\Python\Python312\Lib\site-packages"

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(PIPELINE_DIR))

OK = "  [OK]"
WARN = "  [WARN]"
FAIL = "  [FAIL]"
FIXED = "  [FIXED]"


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
        print(f"{FAIL} {label}{' ' + detail if detail else ''}", end=" ")
        try:
            fix_fn()
            print(FIXED)
            return True
        except Exception as e:
            print(f"  修复失败: {e}")
            return False


def main():
    print("=" * 50)
    print("价值发现 · 预检与自愈 v1.0")
    print("=" * 50)
    all_ok = True
    has_warnings = False

    # ---- 1. Python venv 存在 ----
    print("\n[1/5] Python 虚拟环境")
    venv_ok = check("venv 目录存在", os.path.isdir(VENV_DIR))
    if not venv_ok:
        print(f"{FAIL} 致命: venv 不存在，无法继续")
        return 2
    check("python.exe 可用", os.path.isfile(VENV_PYTHON),
          f"路径: {VENV_PYTHON}")

    # ---- 2. 依赖包 ----
    print("\n[2/5] Python 依赖包")

    # requests
    def fix_requests():
        subprocess.run(
            [VENV_PYTHON, "-m", "pip", "install", "--no-cache-dir",
             "--index-url", "https://pypi.org/simple/", "requests"],
            capture_output=True, timeout=60,
            env={**os.environ, "PIP_REQUIRE_VIRTUALENV": "false"}
        )

    reqs_ok = True
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-c", "import requests; print(requests.__version__)"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "PIP_REQUIRE_VIRTUALENV": "false"}
        )
        reqs_ok = result.returncode == 0
        detail = result.stdout.strip() if reqs_ok else "尝试自动安装..."
    except Exception:
        reqs_ok = False
        detail = "执行异常"

    if not reqs_ok:
        reqs_ok = auto_fix("requests 库", False, fix_requests)
    else:
        check("requests 库", True, detail)

    # PySocks
    socks_ok = False
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-c", "import socks"],
            capture_output=True, timeout=10,
            env={**os.environ, "PIP_REQUIRE_VIRTUALENV": "false"}
        )
        socks_ok = result.returncode == 0
    except Exception:
        pass

    def fix_socks():
        src = os.path.join(SYSTEM_SITE_PACKAGES, "socks.py")
        dst = os.path.join(VENV_SITE_PACKAGES, "socks.py")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            # Also copy sockshandler.py if needed
            src_h = os.path.join(SYSTEM_SITE_PACKAGES, "sockshandler.py")
            if os.path.exists(src_h):
                shutil.copy2(src_h, os.path.join(VENV_SITE_PACKAGES, "sockshandler.py"))
        else:
            # Fallback: try pip install via system python site-packages
            # Copy the entire PySocks package if it exists as a folder
            socks_dir = os.path.join(SYSTEM_SITE_PACKAGES, "socks")
            if os.path.isdir(socks_dir):
                shutil.copytree(socks_dir, os.path.join(VENV_SITE_PACKAGES, "socks"), dirs_exist_ok=True)
            else:
                raise RuntimeError(f"系统Python也没有PySocks: {src}")

    socks_ok = auto_fix("PySocks (SOCKS代理支持)", socks_ok, fix_socks,
                         "已从系统Python复制" if socks_ok else "")

    if not reqs_ok or not socks_ok:
        all_ok = False

    # ---- 3. 关键API连通性 ----
    print("\n[3/5] 关键API连通性")

    connectivity_ok = True
    tests = [
        ("UAPIs (热榜API)", "https://uapis.cn"),
        ("TrendsMCP (国际热榜)", "https://api.trendsmcp.ai"),
        ("腾讯自选股 (行情)", "https://qt.gtimg.cn"),
    ]

    for label, url in tests:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            urllib.request.urlopen(req, timeout=8)
            check(label, True)
        except Exception as e:
            check(label, False, str(e)[:80])
            connectivity_ok = False

    if not connectivity_ok:
        has_warnings = True

    # ---- 4. 数据管道存在 ----
    print("\n[4/5] 管道脚本")
    scripts = [
        "data_fetcher.py",
        "stock_fetcher.py",
        "update_html.py",
        "source_registry.py",
    ]
    for s in scripts:
        path = os.path.join(PIPELINE_DIR, s)
        check(s, os.path.isfile(path))

    # ---- 5. HTML文件 ----
    print("\n[5/5] HTML文件")
    html_path = os.path.join(PROJECT_DIR, "发现榜.html")
    check("发现榜.html", os.path.isfile(html_path),
          f"大小: {os.path.getsize(html_path) if os.path.isfile(html_path) else 0} bytes")

    # ---- 结论 ----
    print("\n" + "=" * 50)
    if not all_ok:
        print("结果: [WARN] 有警告，可继续运行但部分源可能失败")
        return 1
    if has_warnings:
        print("结果: [WARN] 连通性警告，继续运行")
        return 1
    print("结果: [OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
