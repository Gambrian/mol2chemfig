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
        if node_ready:
            self._ensure_node_packages()
            
        self.root.after(0, self._finalize_env_check, node_ready)

    def _ensure_node(self):
        # 检查系统路径
        try:
            subprocess.run(["node", "-v"], capture_output=True, check=True)
            self.log("检测到系统已安装 Node.js")
            return True
        except:
            pass

        # 检查便携目录
        node_exe = self.app_root / NODE_DIR / "node.exe"
        if node_exe.exists():
            os.environ["PATH"] = str(node_exe.parent) + os.pathsep + os.environ["PATH"]
            self.log("使用内置便携版 Node.js")
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
            return True
        except Exception as e:
            self.log(f"下载失败: {str(e)}")
            messagebox.showerror("错误", f"Node.js 下载失败: {e}")
            return False

    def _ensure_node_packages(self):
        node_modules_dir = self.app_root / "node_modules"
        if not node_modules_dir.exists():
            self.log("正在安装 Node.js 渲染依赖 (npm install)...")
            try:
                # 使用淘宝镜像
                result = subprocess.run(
                    ["npm", "install", "--registry=https://registry.npmmirror.com"],
                    cwd=self.app_root,
                    capture_output=True,
                    text=True,
                    check=True
                )
                if result.stdout.strip():
                    self.log(result.stdout.strip())
                self.log("Node.js 依赖安装完成")
            except Exception as e:
                self.log(f"依赖安装失败: {e}")

    def _finalize_env_check(self, success):
        if success:
            self.status_label.config(text="状态: 环境就绪", foreground="green")
            self.start_btn.config(state=tk.NORMAL)
            self.log("环境检查完毕，点击“启动服务”开始使用。")
        else:
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
