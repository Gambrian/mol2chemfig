import PyInstaller.__main__
import os
import shutil
from importlib.util import find_spec
from pathlib import Path

# 定义应用名称
APP_NAME = "ChemfigLab"


def get_indigo_libs():
    """自动定位已安装 indigo 包中的 Windows 动态库。"""
    spec = find_spec('indigo')
    if spec is None or spec.origin is None:
        return []

    package_dir = Path(spec.origin).resolve().parent
    lib_dir = package_dir / 'lib' / 'windows-x86_64'
    dll_names = ['indigo.dll', 'indigo-renderer.dll', 'indigo-inchi.dll']
    libs = []
    for dll_name in dll_names:
        dll_path = lib_dir / dll_name
        if dll_path.exists():
            libs.append((dll_path, f'indigo/lib/windows-x86_64/{dll_name}'))
    return libs

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
        '--clean',
    ]

    for source_path, relative_target in get_indigo_libs():
        target_dir = str(Path(relative_target).parent).replace('/', '\\')
        params.append(f'--add-data={source_path};{target_dir}')

    print(f"开始打包 {APP_NAME}...")
    PyInstaller.__main__.run(params)

    # 打包后的扫尾工作
    dist_path = os.path.join('dist', APP_NAME)
    
    print(f"\n打包完成！EXE 位于: {dist_path}")
    print("说明：当前构建不会打包 node_modules，首次启动时会自动通过 npm 镜像安装渲染依赖。")
    print("仍需确保运行环境中存在 Node.js，或者将 Node.js 便携版放置在应用根目录下。")

if __name__ == "__main__":
    build()
