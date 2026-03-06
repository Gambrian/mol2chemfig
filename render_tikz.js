const { default: tex2svg } = require('node-tikzjax');

async function render() {
    let input = process.argv[2] || '\\chemfig{C1=CC=CC=C1}';
    
    try {
        const tex = `\\usepackage{chemfig}
\\begin{document}
${input}
\\end{document}`;

        // 启用 showConsole: true 以便捕获 TikZJax 内部的 LaTeX 编译日志
        // 这些日志通常会通过 process.stdout 或 process.stderr 输出
        const svg = await tex2svg(tex, { showConsole: true });
        process.stdout.write(svg);
    } catch (err) {
        // 确保错误信息被完整写入 stderr
        process.stderr.write("\n--- TikZJax Execution Error ---\n");
        process.stderr.write(err.stack || err.toString());
        process.stderr.write("\n-------------------------------\n");
        process.exit(1);
    }
}

render();
