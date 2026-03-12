import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import subprocess
import os
import sys
import webbrowser
import time
import urllib.request
import zipfile
import shutil
from pathlib import Path

# 导入 Flask app
from app import app as flask_app

# ================= 配置与常量 =================
PORT = 5000
NODE_PORTABLE_URL = "https://npmmirror.com/mirrors/node/v18.17.0/node-v18.17.0-win-x64.zip"
NODE_DIR = "node_runtime"
APP_NAME = "Chemfig 实验室管理器"
NPM_REGISTRY = "https://registry.npmmirror.com"
REQUIRED_NODE_PACKAGES = ["node-tikzjax"]

# 用于重定向日志的类
class LogRedirector:
    def __init__(self, callback):
        self.callback = callback
    def write(self, s):
        self.callback(s)
    def flush(self):
        pass

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return str(base_dir / relative_path)

class AppManager:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("700x500")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.app_root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        self.resource_root = Path(get_resource_path('.')).resolve()
        
        self.flask_thread = None
        self.is_running = False
        
        self.setup_ui()
        self.redirect_output()
        self.check_environment()

    def setup_ui(self):
        # 顶部状态栏
        self.status_frame = ttk.Frame(self.root, padding="10")
        self.status_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(self.status_frame, text="状态: 检查环境中...", font=("Microsoft YaHei", 10))
        self.status_label.pack(side=tk.LEFT)
        
        # 控制按钮
        self.btn_frame = ttk.Frame(self.root, padding="10")
        self.btn_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(self.btn_frame, text="启动服务", command=self.start_service, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(self.btn_frame, text="停止服务", command=self.stop_service, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.open_btn = ttk.Button(self.btn_frame, text="在浏览器打开页面", command=self.open_browser, state=tk.DISABLED)
        self.open_btn.pack(side=tk.LEFT, padx=5)
        
        # 日志区域
        self.log_frame = ttk.LabelFrame(self.root, text="后台运行日志", padding="10")
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_area = scrolledtext.ScrolledText(self.log_frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def redirect_output(self):
        # 将 stdout 和 stderr 重定向到 GUI 日志区
        sys.stdout = LogRedirector(self.log_from_thread)
        sys.stderr = LogRedirector(self.log_from_thread)

    def log_from_thread(self, message):
        if message.strip():
            # 使用 after 确保在主线程更新 UI
            self.root.after(0, lambda: self.log(message.strip()))

    def log(self, message):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_area.see(tk.END)

    def check_environment(self):
        self.log("正在检测环境...")
        threading.Thread(target=self._env_check_thread, daemon=True).start()

    def _env_check_thread(self):
        # 1. 检测 Node.js
        node_ready = self._ensure_node()

        # 2. 检测依赖包 (npm install)
        packages_ready = False
        if node_ready:
            packages_ready = self._ensure_node_packages()

        self.root.after(0, self._finalize_env_check, node_ready, packages_ready)

    def _ensure_node(self):
        # 检查系统路径
        try:
            subprocess.run(["node", "-v"], capture_output=True, check=True)
            self.log("检测到系统已安装 Node.js")
            os.environ.setdefault("CHEMFIGLAB_NODE_SOURCE", "system")
            return True
        except:
            pass

        # 检查便携目录
        node_exe = self.app_root / NODE_DIR / "node.exe"
        if node_exe.exists():
            os.environ["PATH"] = str(node_exe.parent) + os.pathsep + os.environ["PATH"]
            self.log("使用内置便携版 Node.js")
            os.environ["CHEMFIGLAB_NODE_SOURCE"] = "portable"
            return True

        # 自动下载
        if messagebox.askyesno("环境缺失", "未检测到 Node.js 环境（用于 TikZJax 渲染）。\n是否立即从镜像站自动下载并安装便携版？"):
            return self._download_node()
        return False

    def _download_node(self):
        try:
            self.log(f"正在从镜像下载 Node.js: {NODE_PORTABLE_URL}")
            zip_path = self.app_root / "node_temp.zip"
            temp_dir = self.app_root / "temp_node"
            node_dir = self.app_root / NODE_DIR
            
            def progress(count, block_size, total_size):
                if total_size > 0:
                    percent = int(count * block_size * 100 / total_size)
                    if percent % 10 == 0:
                        self.root.after(0, lambda: self.status_label.config(text=f"状态: 正在下载 Node.js ({percent}%)"))

            urllib.request.urlretrieve(NODE_PORTABLE_URL, str(zip_path), reporthook=progress)
            
            self.log("下载完成，正在解压...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # 移动文件到 node_runtime
            inner_dir = next(temp_dir.iterdir())
            if node_dir.exists():
                shutil.rmtree(node_dir)
            shutil.move(str(inner_dir), str(node_dir))
            
            # 清理
            shutil.rmtree(temp_dir)
            zip_path.unlink()
            
            os.environ["PATH"] = str(node_dir) + os.pathsep + os.environ["PATH"]
            self.log("Node.js 便携版安装成功")
            os.environ["CHEMFIGLAB_NODE_SOURCE"] = "portable"
            return True
        except Exception as e:
            self.log(f"下载失败: {str(e)}")
            messagebox.showerror("错误", f"Node.js 下载失败: {e}")
            return False

    def _resolve_node_executable(self):
        portable_node = self.app_root / NODE_DIR / "node.exe"
        if portable_node.exists():
            return portable_node
        return Path("node")

    def _resolve_npm_command(self):
        node_exe = self._resolve_node_executable()
        npm_cli = self.app_root / NODE_DIR / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if npm_cli.exists() and node_exe.exists():
            return [str(node_exe), str(npm_cli)]
        return ["npm"]

    def _get_local_npm_project_root(self):
        package_json = Path(get_resource_path("package.json")).resolve()
        return package_json.parent

    def _get_system_npm_root(self):
        try:
            result = subprocess.run(
                ["npm", "root", "-g"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                return None
            npm_root = result.stdout.strip()
            return npm_root or None
        except Exception:
            return None

    def _configure_node_path(self, npm_root):
        if not npm_root:
            return

        current = os.environ.get("NODE_PATH", "")
        parts = [part for part in current.split(os.pathsep) if part]
        if npm_root not in parts:
            parts.insert(0, npm_root)
            os.environ["NODE_PATH"] = os.pathsep.join(parts)

    def _has_required_node_packages(self, base_dir):
        for package_name in REQUIRED_NODE_PACKAGES:
            package_dir = Path(base_dir) / package_name
            if not package_dir.exists():
                return False
        return True

    def _try_use_system_node_packages(self):
        npm_root = self._get_system_npm_root()
        if not npm_root:
            self.log("未检测到系统全局 npm 包目录")
            return False

        if not self._has_required_node_packages(npm_root):
            self.log(f"系统全局 npm 包目录存在，但缺少依赖: {npm_root}")
            return False

        self._configure_node_path(npm_root)
        self.log(f"复用系统全局 Node.js 渲染依赖: {npm_root}")
        return True

    def _ensure_node_packages(self):
        local_project_root = self._get_local_npm_project_root()
        local_node_modules = local_project_root / "node_modules"
        if self._has_required_node_packages(local_node_modules):
            self._configure_node_path(str(local_node_modules))
            self.log(f"检测到本地 Node.js 渲染依赖已存在: {local_node_modules}")
            return True

        node_source = os.environ.get("CHEMFIGLAB_NODE_SOURCE", "")
        if node_source == "system" and self._try_use_system_node_packages():
            return True

        self.log(f"正在安装 Node.js 渲染依赖 (npm install)... 目录: {local_project_root}")
        try:
            result = subprocess.run(
                self._resolve_npm_command() + [
                    "install",
                    "--registry",
                    NPM_REGISTRY,
                    "--no-fund",
                    "--no-audit",
                    "--omit=dev",
                ],
                cwd=local_project_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.stdout.strip():
                self.log(result.stdout.strip())
            if result.stderr.strip():
                self.log(result.stderr.strip())

            if result.returncode != 0:
                self.log(f"依赖安装失败，npm exit code={result.returncode}")
                return False

            if self._has_required_node_packages(local_node_modules):
                self._configure_node_path(str(local_node_modules))
                self.log("Node.js 依赖安装完成")
                return True

            self.log("npm install 已执行，但仍未找到所需依赖")
            return False
        except Exception as e:
            self.log(f"依赖安装失败: {e}")
            return False

    def _finalize_env_check(self, node_ready, packages_ready):
        if node_ready and packages_ready:
            self.status_label.config(text="状态: 环境就绪", foreground="green")
            self.start_btn.config(state=tk.NORMAL)
            self.log("环境检查完毕，点击“启动服务”开始使用。")
            return

        if node_ready and not packages_ready:
            self.status_label.config(text="状态: Node 已就绪，但渲染依赖安装失败", foreground="orange")
            self.start_btn.config(state=tk.NORMAL)
            self.log(f"提示：请检查网络或镜像源是否可访问。当前镜像: {NPM_REGISTRY}")
            return

        self.status_label.config(text="状态: 缺少 Node 环境 (渲染功能将受限)", foreground="orange")
        self.start_btn.config(state=tk.NORMAL)

    def start_service(self):
        if self.is_running: return
        
        self.log("正在通过多线程启动 Flask 服务...")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.open_btn.config(state=tk.NORMAL)
        self.status_label.config(text="状态: 服务运行中", foreground="green")
        
        # 在后台线程运行 Flask
        self.flask_thread = threading.Thread(target=self._run_flask, daemon=True)
        self.flask_thread.start()
        
        # 自动打开浏览器
        self.root.after(2000, self.open_browser)

    def _run_flask(self):
        try:
            # 这里的 flask_app 是从 app.py 导入的
            # 使用 werkzeug 运行
            flask_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
        except Exception as e:
            self.log_from_thread(f"Flask 运行异常: {str(e)}")
        finally:
            self.is_running = False
            self.root.after(0, self._on_service_stopped)

    def _on_service_stopped(self):
        self.log("服务已停止")
        self.status_label.config(text="状态: 已停止", foreground="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.open_btn.config(state=tk.DISABLED)

    def stop_service(self):
        self.log("提示: 线程模式下无法直接强杀 Flask。请直接关闭管理器窗口来退出程序。")
        # 实际开发中可以通过请求一个特定的 shutdown 路由来实现，但这里简单处理
        self.stop_btn.config(state=tk.DISABLED)

    def open_browser(self):
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    def on_closing(self):
        if self.is_running:
            if messagebox.askokcancel("退出", "服务正在运行，确定要彻底退出吗？"):
                self.root.destroy()
                os._exit(0) # 强制退出所有线程
        else:
            self.root.destroy()
            os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = AppManager(root)
    root.mainloop()
