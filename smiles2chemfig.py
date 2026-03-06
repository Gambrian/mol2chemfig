#!/usr/bin/env python3
import sys
import io
from pathlib import Path

# ================= 配置区域 =================
CONFIG = {
    "mode": "single",           # 选项: "single" (单条转换) 或 "batch" (批量转换)
    
    # 单条转换配置
    "single_smiles": "OCC",     # 当 mode 为 single 时使用的 SMILES
    
    # 批量转换配置
    "input_file": "smiles.txt", # 输入文件路径
    "output_file": "chem.txt",  # 输出文件路径
    
    # 转换设置
    "normalize": True,          # 是否使用 RDKit 规范化 SMILES
    "clean_output": True,       # 是否清理 LaTeX 注释和换行
}
# ============================================

def normalize_smiles(smiles: str) -> str:
    try:
        from rdkit import Chem
    except ImportError:
        raise ImportError("未安装 RDKit，无法做 SMILES 规范化。")
    
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise ValueError(f"SMILES 解析失败: {smiles}")
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)

def smiles_to_chemfig(smiles: str):
    try:
        from mol2chemfigPy3 import mol2chemfig
    except ImportError:
        raise ImportError("请安装 mol2chemfigPy3: pip install mol2chemfigPy3")

    smi = smiles.strip()
    if CONFIG["normalize"]:
        smi = normalize_smiles(smi)
        #print(smi)  "OCC"/"CCO"会被归一化为CCO
    
    # 捕获 stdout
    original_stdout = sys.stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output
    try:
        mol2chemfig(smi)
        chemfig = captured_output.getvalue().strip()
    finally:
        sys.stdout = original_stdout

    if CONFIG["clean_output"]:
        import re
        # 移除 % 开头的注释和换行符
        chemfig = re.sub(r'%.*', '', chemfig).replace("\n", "")
    
    return chemfig

def batch_convert():
    in_path = Path(CONFIG["input_file"])
    out_path = Path(CONFIG["output_file"])

    if not in_path.exists():
        print(f"错误: 找不到输入文件 {in_path}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(in_path, "r", encoding="utf-8") as fin:
        lines = fin.readlines()

    results = []
    success = 0
    for i, line in enumerate(lines):
        smi = line.strip()
        if not smi: continue
        try:
            chem = smiles_to_chemfig(smi)
            results.append(chem)
            success += 1
        except Exception as e:
            results.append(f"% Error on line {i+1}: {e}")
            print(f"行 {i+1} 转换失败: {e}")

    with open(out_path, "w", encoding="utf-8") as fout:
        fout.write("\n".join(results) + "\n")
    
    print(f"批量转换完成: 成功 {success}/{len(lines)} 条 -> {out_path}")

def main():
    if CONFIG["mode"] == "batch":
        print(f"--- 正在执行批量模式 ---")
        batch_convert()
    else:
        print(f"--- 正在执行单条模式 ---")
        try:
            result = smiles_to_chemfig(CONFIG["single_smiles"])
            print("\n生成的 Chemfig 代码:\n")
            print(result)
        except Exception as e:
            print(f"转换出错: {e}")

if __name__ == "__main__":
    main()