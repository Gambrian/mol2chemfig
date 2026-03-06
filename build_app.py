import PyInstaller.__main__
import os
import shutil

# 定义应用名称
APP_NAME = "ChemfigLab"

def build():
    # 确保清理旧的构建文件
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)

    # PyInstaller 打包参数
    params = [
        'gui_launcher.py',            # 主入口改为 GUI 管理器
        f'--name={APP_NAME}',         # 生成的 exe 名称
        '--onedir',                   # 生成一个目录
        '--noconsole',                # 运行时不显示黑窗口
        '--hidden-import=app',        # 关键：显式包含 app.py 模块
        '--add-data=templates;templates', # 包含模板
        '--add-data=render_tikz.js;.',    # 包含 Node 脚本
        '--add-data=package.json;.',      # 包含 npm 依赖配置
        # 显式包含 indigo 的原生 DLL 文件
        '--add-data=C:\\Python314\\Lib\\site-packages\\indigo\\lib\\windows-x86_64\\indigo.dll;indigo/lib/windows-x86_64',
        '--add-data=C:\\Python314\\Lib\\site-packages\\indigo\\lib\\windows-x86_64\\indigo-renderer.dll;indigo/lib/windows-x86_64',
        '--add-data=C:\\Python314\\Lib\\site-packages\\indigo\\lib\\windows-x86_64\\indigo-inchi.dll;indigo/lib/windows-x86_64',
        '--clean',
    ]

    print(f"开始打包 {APP_NAME}...")
    PyInstaller.__main__.run(params)

    # 打包后的扫尾工作
    dist_path = os.path.join('dist', APP_NAME)
    
    print(f"\n打包完成！EXE 位于: {dist_path}")
    print("注意：由于 TikZJax 依赖 Node.js，请确保运行环境中已安装 Node.js，")
    print("或者将 Node.js 便携版放置在应用根目录下。")

if __name__ == "__main__":
    build()
