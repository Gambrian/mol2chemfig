from flask import Flask, render_template, request, jsonify
import sys
import io
import re
import subprocess
import os
import base64
import tempfile
import traceback

from rdkit import Chem
from rdkit.Chem import Draw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ================= 资源路径处理 =================
def get_app_root():
    """获取应用运行根目录（兼容源码运行和 PyInstaller one-dir 发布）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return BASE_DIR


def get_resource_path(relative_path):
    """获取资源文件绝对路径（兼容 PyInstaller 打包后运行）。"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(BASE_DIR, relative_path)


def resolve_node_executable():
    """优先使用应用目录下的便携 Node，其次回退到系统 PATH。"""
    candidate_paths = [
        os.path.join(get_app_root(), 'node_runtime', 'node.exe'),
        os.path.join(BASE_DIR, 'node_runtime', 'node.exe'),
    ]
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            return candidate
    return 'node'


app = Flask(
    __name__,
    template_folder=get_resource_path('templates'),
    static_folder=get_resource_path('static')
)


# ================= 本地 TikZ 渲染 =================
def render_tikz_locally(tikz_code):
    """调用本地 Node.js 脚本渲染 TikZ/Chemfig。"""
    try:
        node_executable = resolve_node_executable()
        script_path = get_resource_path('render_tikz.js')
        env = os.environ.copy()

        # Windows 下隐藏黑色命令行窗口
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            [node_executable, script_path],
            input=tikz_code.encode('utf-8'),
            capture_output=True,
            check=False,
            creationflags=creation_flags,
            env=env
        )

        stdout_bytes = result.stdout
        stderr_bytes = result.stderr
        stderr_text = stderr_bytes.decode('utf-8', errors='replace')

        # 从 stdout 中提取 <svg>...</svg> 主体，同时把前后日志合并到 stderr 输出
        start_tag = b'<svg'
        end_tag = b'</svg>'
        start_idx = stdout_bytes.find(start_tag)
        end_idx = stdout_bytes.rfind(end_tag)

        log_parts = []
        if start_idx != -1:
            pre_svg_log = stdout_bytes[:start_idx].decode('utf-8', errors='replace').strip()
            if pre_svg_log:
                log_parts.append(pre_svg_log)

        if end_idx != -1:
            post_svg_log = stdout_bytes[end_idx + len(end_tag):].decode('utf-8', errors='replace').strip()
            if post_svg_log:
                log_parts.append(post_svg_log)

        if stderr_text.strip():
            log_parts.append(stderr_text.strip())

        context_parts = [
            '--- Render Context ---',
            f'Node executable: {node_executable}',
            f'Render script: {script_path}',
            f'Input length: {len(tikz_code)}',
            '--- Preview Code ---',
            tikz_code,
        ]

        if log_parts:
            context_parts.extend(log_parts)

        full_log = '\n'.join(context_parts).strip()

        if result.returncode != 0:
            return None, full_log or f'Process exited with code {result.returncode}'

        if start_idx != -1 and end_idx != -1:
            svg_bytes = stdout_bytes[start_idx:end_idx + len(end_tag)]
            return svg_bytes.decode('utf-8', errors='replace'), full_log

        return None, full_log or 'Could not find SVG tag in output'
    except Exception as exc:
        error_msg = f'Local render error: {exc}'
        return None, f'{error_msg}\n{traceback.format_exc()}'


def extract_render_error_summary(log_text):
    """从完整渲染日志中提取首个核心错误片段，便于前端高亮显示。"""
    if not log_text:
        return ''

    lines = str(log_text).splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('!'):
            continue

        snippet = [stripped]
        for follow in lines[idx + 1:]:
            follow_stripped = follow.rstrip()
            if not follow_stripped:
                break
            if follow_stripped.lstrip().startswith('? '):
                break
            if follow_stripped.startswith('--- '):
                break
            snippet.append(follow_stripped)
            if follow_stripped.lstrip().startswith('l.'):
                break
        return '\n'.join(snippet).strip()

    fallback_patterns = [
        'Undefined control sequence',
        'Emergency stop',
        'Runaway argument',
        'Missing $ inserted',
        'TeX capacity exceeded',
        'Could not find SVG tag in output',
        'Local render error:',
    ]
    for pattern in fallback_patterns:
        for line in lines:
            if pattern in line:
                return line.strip()

    return ''


@app.route('/render_local', methods=['POST'])
def render_local():
    data = request.json
    code = data.get('code', '')
    if not code:
        return jsonify({'error': 'No code provided'}), 400

    svg, stderr = render_tikz_locally(code)
    if svg:
        return jsonify({'svg': svg, 'stderr': stderr, 'error_summary': extract_render_error_summary(stderr)})
    return jsonify({
        'error': 'Render failed',
        'stderr': stderr,
        'error_summary': extract_render_error_summary(stderr)
    }), 500


# ================= 转换辅助函数 =================
# 说明：
# mol2chemfigPy3（底层 Indigo）在处理 R 位点时，会在“隐式氢计数”阶段报错。
# 为了不修改三方包源码，这里采用“可逆替换”方案：
# 1) 识别输入中的 R / R1 / R# / M  RGP / Alias；
# 2) 临时替换为合法占位元素（Fe/Cu/...）；
# 3) 按原逻辑调用 mol2chemfigPy3；
# 4) 转换完成后再把占位元素替换回 R 标签。
# 这样可以保持部署简单：只分发本项目代码，不维护 fork 包。
R_PLACEHOLDER_SYMBOLS = [
    'Fe', 'Cu', 'Zn', 'Ni', 'Co', 'Cr', 'Mn', 'Ti', 'V', 'Mo', 'W',
    'Pd', 'Pt', 'Hg', 'Ag', 'Au', 'Li', 'Na', 'K', 'Mg', 'Ca', 'Al',
    'Ga', 'In', 'Tl', 'Bi'
]
SMILES_R_TOKEN_RE = re.compile(r"\[(R\d*)\]|(?<![A-Za-z])([Rr]\d*)(?![a-z])")


def _safe_int(value, default=0):
    """安全整型转换，失败时返回默认值。"""
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _normalize_r_label(label):
    """将 r/r1 规范化为 R/R1；非 R 标签返回 None。"""
    if not label:
        return None
    token = str(label).strip()
    match = re.fullmatch(r'[Rr](\d*)', token)
    if not match:
        return None
    suffix = match.group(1)
    return f'R{suffix}' if suffix else 'R'


def _format_r_label_for_chemfig(label):
    """把 R1 这种标签转成 chemfig 中更易读的 R_{1}。"""
    normalized = _normalize_r_label(label)
    if not normalized:
        return label
    match = re.fullmatch(r'R(\d+)', normalized)
    if not match:
        return normalized
    return f'R_{{{match.group(1)}}}'


def _pick_placeholder_symbols(count, used_symbols=None):
    """从占位元素池挑选不冲突的符号。"""
    used = {str(s).strip() for s in (used_symbols or set())}
    available = [symbol for symbol in R_PLACEHOLDER_SYMBOLS if symbol not in used]
    if len(available) < count:
        raise ValueError(
            f'R group count ({count}) exceeds available placeholder symbols ({len(available)}).'
        )
    return available[:count]


def _replace_placeholders_with_rlabels(chemfig_code, placeholder_to_label):
    """把 chemfig 中的占位元素还原成 R 标签。"""
    result = chemfig_code
    for placeholder, label in placeholder_to_label.items():
        r_label = _format_r_label_for_chemfig(label)
        pattern = rf'(?<![A-Za-z]){re.escape(placeholder)}(?![a-z])'
        result = re.sub(pattern, r_label, result)
    return result


def _contains_mol2chemfig_error(text):
    """识别 mol2chemfig 以字符串形式返回的错误输出。"""
    if text is None:
        return True
    stripped = str(text).strip()
    if not stripped:
        return True
    lower = stripped.lower()
    if stripped.startswith('Traceback'):
        return True
    if 'IndigoException' in stripped:
        return True
    if lower == 'invalid input data':
        return True
    return False


def _clean_chemfig_output(chemfig_code):
    """清理对前端 TikZ 预览不友好的片段，统一输出格式。"""
    def replace_charge_for_preview(match):
        charge_spec = match.group(1)
        atom_body = match.group(2).strip()
        if r'\.' in charge_spec:
            return rf'\chemabove{{{atom_body}}}{{\scriptstyle \bullet}}'
        return match.group(0)

    chemfig_code = re.sub(
        r'\\charge\{([^{}]*)\}\{([^{}]+)\}',
        replace_charge_for_preview,
        chemfig_code
    )
    chemfig_code = re.sub(r'\\mcfcringle\{.*?\}', '', chemfig_code)
    chemfig_code = chemfig_code.replace(',,,,draw=none', '').replace(',,,,mcfwavy', '')
    chemfig_code = re.sub(
        r'\\mcfright\{([^{}]+)\}\{((?:[^{}]|\{[^{}]*\})+)\}',
        r'\1\2',
        chemfig_code
    )
    chemfig_code = re.sub(
        r'\\mcfleft\{([^{}]+)\}\{((?:[^{}]|\{[^{}]*\})+)\}',
        r'\2\1',
        chemfig_code
    )
    chemfig_code = chemfig_code.replace(r'\mcfabove', r'\chemabove')
    chemfig_code = chemfig_code.replace(r'\mcfbelow', r'\chembelow')
    chemfig_code = chemfig_code.replace(r'\mcfplus', '+')
    chemfig_code = chemfig_code.replace(r'\mcfminus', '-')
    chemfig_code = re.sub(r'%.*', '', chemfig_code).replace('\n', ' ').strip()
    chemfig_code = re.sub(r'\s+', ' ', chemfig_code)
    return chemfig_code


def _finalize_chemfig_outputs(chemfig_code, clean_output=True):
    """同时保留原始输出与预览友好输出。"""
    raw_output = str(chemfig_code).strip()
    preview_output = _clean_chemfig_output(raw_output) if clean_output else raw_output
    return {
        'raw': raw_output,
        'preview': preview_output,
    }


def _prepare_smiles_rgroups(smiles):
    """
    SMILES 路径的 R 兼容预处理：
    - 把 R/R1 先替换为占位元素；
    - 返回“替换后的 SMILES + 占位元素到 R 标签映射”。
    """
    matches = []
    for match in SMILES_R_TOKEN_RE.finditer(smiles):
        label = _normalize_r_label(match.group(1) or match.group(2))
        if label:
            matches.append(label)

    if not matches:
        return smiles, {}

    unique_labels = list(dict.fromkeys(matches))
    used_symbols = set(re.findall(r'\[([A-Z][a-z]?)', smiles))
    used_symbols.update(re.findall(r'(?<![a-z])([A-Z][a-z]?)', smiles))
    placeholders = _pick_placeholder_symbols(len(unique_labels), used_symbols=used_symbols)
    label_to_placeholder = dict(zip(unique_labels, placeholders))

    def replacer(match):
        label = _normalize_r_label(match.group(1) or match.group(2))
        if not label:
            return match.group(0)
        return f'[{label_to_placeholder[label]}]'

    replaced_smiles = SMILES_R_TOKEN_RE.sub(replacer, smiles)
    placeholder_to_label = {v: k for k, v in label_to_placeholder.items()}
    return replaced_smiles, placeholder_to_label


def _prepare_molblock_rgroups(mol_block):
    """
    Molfile(V2000) 路径的 R 兼容预处理：
    - 识别 R / R# / M  RGP / Alias 记录；
    - 统一建立 atom -> R 标签映射；
    - 将这些原子改写为占位元素；
    - 返回“改写后的 molblock + 占位元素到 R 标签映射”。
    """
    lines = mol_block.splitlines()
    if not lines:
        return mol_block, {}

    counts_line_index = None
    for idx, line in enumerate(lines):
        if 'V2000' in line:
            counts_line_index = idx
            break
    if counts_line_index is None:
        return mol_block, {}

    counts_line = lines[counts_line_index]
    atom_count = _safe_int(counts_line[0:3], 0)
    bond_count = _safe_int(counts_line[3:6], 0)
    atom_start = counts_line_index + 1
    bond_start = atom_start + atom_count
    property_start = bond_start + bond_count

    # 防御性检查：计数行和实际行数不一致时直接退出兼容逻辑
    if atom_count <= 0 or len(lines) < atom_start + atom_count:
        return mol_block, {}

    atom_symbols = {}
    for atom_idx in range(1, atom_count + 1):
        line_index = atom_start + atom_idx - 1
        atom_line = lines[line_index]
        symbol = atom_line[31:34].strip() if len(atom_line) >= 34 else ''
        atom_symbols[atom_idx] = symbol

    rgp_labels = {}
    alias_labels = {}
    rgp_line_indices = []
    alias_records = []
    i = property_start
    while i < len(lines):
        line = lines[i]
        if line.startswith('M  RGP'):
            rgp_line_indices.append(i)
            tokens = line.split()
            pair_count = _safe_int(tokens[2], 0) if len(tokens) >= 3 else 0
            for pair_index in range(pair_count):
                atom_token_index = 3 + 2 * pair_index
                group_token_index = atom_token_index + 1
                if group_token_index >= len(tokens):
                    break
                atom_idx = _safe_int(tokens[atom_token_index], 0)
                group_idx = _safe_int(tokens[group_token_index], 0)
                if atom_idx > 0:
                    rgp_labels[atom_idx] = f'R{group_idx}' if group_idx > 0 else 'R'
            i += 1
            continue

        if line.startswith('A  '):
            tokens = line.split()
            atom_idx = _safe_int(tokens[1], 0) if len(tokens) >= 2 else 0
            alias_text = lines[i + 1].strip() if i + 1 < len(lines) else ''
            alias_records.append((i, i + 1, atom_idx, alias_text))
            if atom_idx > 0 and alias_text:
                alias_labels[atom_idx] = alias_text
            i += 2
            continue

        i += 1

    # 合并三种来源的 R 信息：原子符号 / RGP / Alias
    atom_label_map = {}
    for atom_idx, symbol in atom_symbols.items():
        normalized_symbol = symbol.strip()
        if normalized_symbol.upper() == 'R#':
            normalized_label = _normalize_r_label(rgp_labels.get(atom_idx, 'R'))
        else:
            normalized_label = _normalize_r_label(normalized_symbol)
        if normalized_label:
            atom_label_map[atom_idx] = normalized_label

    for atom_idx, label in rgp_labels.items():
        normalized = _normalize_r_label(label)
        if normalized:
            atom_label_map[atom_idx] = normalized

    for atom_idx, alias in alias_labels.items():
        normalized = _normalize_r_label(alias)
        if normalized:
            atom_label_map[atom_idx] = normalized

    if not atom_label_map:
        return mol_block, {}

    # 每种 R 标签分配一个占位元素，便于后续精准回填
    unique_labels = list(dict.fromkeys(atom_label_map.values()))
    placeholders = _pick_placeholder_symbols(
        len(unique_labels),
        used_symbols=set(atom_symbols.values())
    )
    label_to_placeholder = dict(zip(unique_labels, placeholders))
    placeholder_to_label = {v: k for k, v in label_to_placeholder.items()}

    output_lines = list(lines)
    for atom_idx, label in atom_label_map.items():
        line_index = atom_start + atom_idx - 1
        atom_line = output_lines[line_index]
        if len(atom_line) < 34:
            atom_line = atom_line.ljust(34)
        placeholder_symbol = label_to_placeholder[label]
        output_lines[line_index] = f'{atom_line[:31]}{placeholder_symbol:<3}{atom_line[34:]}'

    # 删除原始 R 相关记录，避免后续解析继续把它当 R-site 处理
    remove_line_indices = set(rgp_line_indices)
    for alias_line_idx, alias_text_idx, atom_idx, _ in alias_records:
        if atom_idx in atom_label_map:
            remove_line_indices.add(alias_line_idx)
            if alias_text_idx < len(output_lines):
                remove_line_indices.add(alias_text_idx)

    sanitized_lines = [
        line for idx, line in enumerate(output_lines) if idx not in remove_line_indices
    ]
    sanitized_mol = '\n'.join(sanitized_lines)
    if mol_block.endswith('\n'):
        sanitized_mol += '\n'
    return sanitized_mol, placeholder_to_label


# ================= 转换核心 =================
def normalize_smiles(smiles: str) -> str:
    """使用 RDKit 规范化 SMILES。"""
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise ValueError(f'SMILES 解析失败: {smiles}')
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def get_smiles_preview(smiles):
    """生成 SMILES 的 Base64 PNG 预览图。"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            img = Draw.MolToImage(mol, size=(400, 400))
            buffered = io.BytesIO()
            img.save(buffered, format='PNG')
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return f'data:image/png;base64,{img_str}'
    except Exception as exc:
        print(f'Preview error: {exc}')
    return None


def smiles_to_chemfig_outputs(smiles: str, normalize=True, clean_output=True):
    """
    将 SMILES 转换为 chemfig，并同时返回原始输出与预览输出。

    关键流程：
    A. 先做 R 位点预处理（如有）
    B. 非 R 输入走原有 RDKit kekulize 流程
    C. 调用 mol2chemfig 转换
    D. 若用了占位元素，再回填为 R 标签
    """
    try:
        from mol2chemfigPy3 import mol2chemfig
    except ImportError:
        raise ImportError('服务器未安装 mol2chemfigPy3')

    smi = smiles.strip()

    # A. R 位点预处理
    smi, placeholder_to_label = _prepare_smiles_rgroups(smi)

    # B. 普通 SMILES 保持原有凯库勒化行为
    if not placeholder_to_label:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            if normalize:
                smi = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
                mol = Chem.MolFromSmiles(smi)
            Chem.Kekulize(mol, clearAromaticFlags=True)
            smi = Chem.MolToSmiles(mol, kekuleSmiles=True)

    # C. 标准转换
    try:
        chemfig = mol2chemfig(smi, aromatic=False, inline=True)
        if _contains_mol2chemfig_error(chemfig):
            raise Exception(chemfig.strip() if chemfig else 'conversion returned empty result')
    except Exception as exc:
        raise Exception(f'转换异常: {exc}')

    # D. 回填占位元素 -> R 标签
    if placeholder_to_label:
        chemfig = _replace_placeholders_with_rlabels(chemfig, placeholder_to_label)

    return _finalize_chemfig_outputs(chemfig, clean_output=clean_output)


def smiles_to_chemfig(smiles: str, normalize=True, clean_output=True):
    """兼容旧调用：默认返回预览友好的 chemfig。"""
    outputs = smiles_to_chemfig_outputs(
        smiles,
        normalize=normalize,
        clean_output=clean_output
    )
    return outputs['preview']


def mol_to_chemfig_outputs(mol_block: str, clean_output=True):
    """将 Molfile 转换为 chemfig，并同时返回原始输出与预览输出。"""
    try:
        from mol2chemfigPy3 import mol2chemfig
    except ImportError:
        raise ImportError('服务器未安装 mol2chemfigPy3')

    prepared_mol, placeholder_to_label = _prepare_molblock_rgroups(mol_block)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.mol', delete=False) as tf:
        tf.write(prepared_mol)
        temp_path = tf.name

    try:
        chemfig_code = mol2chemfig(temp_path, aromatic=False, inline=True)

        if _contains_mol2chemfig_error(chemfig_code):
            raise Exception(
                chemfig_code.strip() if chemfig_code else 'conversion returned empty result'
            )

        if placeholder_to_label:
            chemfig_code = _replace_placeholders_with_rlabels(
                chemfig_code, placeholder_to_label
            )

        return _finalize_chemfig_outputs(chemfig_code, clean_output=clean_output)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ================= 路由 =================
@app.route('/')
def index():
    return render_template('mol.html')


@app.route('/smiles')
def smiles_page():
    return render_template('index.html')


@app.route('/mol')
def mol_page():
    return render_template('mol.html')


def get_mol_preview(mol_block):
    """生成 Molfile 的 Base64 PNG 预览图。"""
    try:
        mol = Chem.MolFromMolBlock(mol_block)
        if mol:
            img = Draw.MolToImage(mol, size=(400, 400))
            buffered = io.BytesIO()
            img.save(buffered, format='PNG')
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return f'data:image/png;base64,{img_str}'
    except Exception as exc:
        print(f'Mol preview error: {exc}')
    return None


@app.route('/convert_mol', methods=['POST'])
def convert_mol():
    """
    Molfile 转换接口。

    实现方式与 SMILES 一致：
    1) 预处理 R 位点为占位元素；
    2) 调用原生 mol2chemfig；
    3) 转回 R 标签；
    4) 清理输出。
    """
    data = request.json
    mol_block = data.get('mol', '')

    if not mol_block:
        return jsonify({'error': '请输入 Molfile 内容'}), 400

    try:
        outputs = mol_to_chemfig_outputs(mol_block)
        preview_url = get_mol_preview(mol_block)
        return jsonify({
            'chemfig': outputs['preview'],
            'chemfig_preview': outputs['preview'],
            'chemfig_raw': outputs['raw'],
            'preview_url': preview_url
        })
    except Exception as exc:
        error_details = traceback.format_exc()
        print(f'Mol 转换接口出错:\n{error_details}')
        return jsonify({'error': str(exc), 'details': error_details}), 500


@app.route('/convert', methods=['POST'])
def convert():
    data = request.json
    smiles = data.get('smiles', '')

    if not smiles:
        return jsonify({'error': '请输入 SMILES 字符串'}), 400

    try:
        outputs = smiles_to_chemfig_outputs(smiles)
        preview_url = get_smiles_preview(smiles)

        return jsonify({
            'smiles': smiles,
            'chemfig': outputs['preview'],
            'chemfig_preview': outputs['preview'],
            'chemfig_raw': outputs['raw'],
            'preview_url': preview_url
        })
    except Exception as exc:
        error_details = traceback.format_exc()
        print(f'转换接口出错:\n{error_details}')
        return jsonify({'error': str(exc), 'details': error_details}), 500


if __name__ == '__main__':
    print('--- Flask Service Initializing ---')
    print('Starting server on http://127.0.0.1:5000')
    app.run(debug=False, host='0.0.0.0', port=5000)
