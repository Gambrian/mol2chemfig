# Chemfig 实验室 (SMILES & Molfile to Chemfig)

这是一个功能强大的 Web 服务，用于将化学 SMILES 字符串或 Molfile (V2000) 转换为 LaTeX 的 `chemfig` 宏包代码，并提供实时预览功能。

## 功能特点

- **多模式转换**: 
  - **SMILES 转换**: 输入 SMILES 即可自动生成对应的 `chemfig` 代码。
  - **Molfile 转换**: 支持粘贴 Molfile (V2000) 文本进行转换。
- **实时编辑与预览**:
  - 生成的代码可在网页端直接修改，并触发实时渲染。
  - **双重渲染对比**:
    - **RDKit 预览**: 转换时自动生成原始分子结构图，作为基准。
    - **TikZJax 渲染**: 使用本地 Node.js 渲染引擎驱动的 TikZJax 技术，实现高清矢量图实时渲染。
- **交互式操作**:
  - **大版面设计**: 优化了 UI 布局，提供超大渲染区域，方便观察分子细节。
  - **交互式 SVG**: 支持鼠标滚动缩放、左键拖拽平移，提供极致的预览体验。
  - **防抖渲染**: 优化渲染频率，减少后端压力。
  - **一键功能**: 支持一键复制代码、重置缩放、手动刷新渲染。

## 安装要求

### 1. Python 环境
建议使用 Python 3.8+。安装以下依赖：

```bash
# 安装 Web 框架
pip install flask

# 安装转换核心库
pip install mol2chemfigPy3

# 安装化学信息学库
pip install rdkit
```

### 2. Node.js 环境 (本地渲染引擎)
项目集成了本地 TikZJax 渲染引擎，需要安装 Node.js (推荐 v16+)。

```bash
# 在项目根目录下安装 Node 依赖
npm install
```

## 使用说明

### 1. 启动服务
```bash
python app.py
```
默认运行地址：`http://127.0.0.1:5000`

### 2. 操作流程
1. **SMILES 模式**: 访问首页，输入 SMILES（如 `CC(=O)Oc1ccccc1C(=O)O`）并点击转换。
2. **Molfile 模式**: 点击页面右上角切换，粘贴 Molfile 文本并点击转换。
3. **编辑与预览**: 在 **Chemfig 代码** 框中直接编辑代码，右侧 **TikZJax 渲染** 会在停止输入 0.8 秒后自动更新。
4. **交互**: 在渲染区域内使用滚轮缩放，按住鼠标左键可拖拽移动分子结构。

### 3. LaTeX 配置
在 LaTeX 文档中使用生成代码前，请确保包含以下宏包：
```latex
\usepackage{chemfig}
```

## 技术实现

- **后端 (Flask)**: 
  - 处理 SMILES 和 Molfile 转换逻辑。
  - 调用 `mol2chemfigPy3` 执行 LaTeX 逻辑转换。
  - 使用 `RDKit` 生成基准预览图。
- **本地渲染引擎 (Node.js)**:
  - 封装了 `render_tikz.js` 脚本，通过 `child_process` 调用 Node 环境运行 `tikzjax`，实现浏览器外的服务端渲染。
- **前端 (HTML5/JS)**: 
  - 使用 **Tailwind CSS** 构建现代化的 5:7 响应式布局。
  - 集成 **svg-pan-zoom** 库实现流畅的 SVG 交互。
  - 使用 **Base64** 编码传输预览图，确保零文件残留。

## 注意事项

- **Node 依赖**: 如果没有执行 `npm install`，右侧的 TikZJax 高清渲染功能将无法正常工作。
- **代码规范**: 手动修改代码时，请确保符合 `chemfig` 语法，否则渲染引擎可能返回错误。
