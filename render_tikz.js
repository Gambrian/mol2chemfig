const { default: tex2svg } = require('node-tikzjax');

function readStdin() {
    return new Promise((resolve, reject) => {
        const chunks = [];
        process.stdin.on('data', (chunk) => chunks.push(chunk));
        process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
        process.stdin.on('error', reject);
    });
}

async function render() {
    const stdinInput = process.stdin.isTTY ? '' : await readStdin();
    let input = stdinInput.trim() || process.argv[2] || '\\chemfig{C1=CC=CC=C1}';
    let tex = '';

    try {
        tex = `\\usepackage{chemfig}
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
        process.stderr.write("\n--- Input Code ---\n");
        process.stderr.write(input);
        process.stderr.write("\n--- Expanded TeX ---\n");
        process.stderr.write(tex || '[TeX template was not fully created]');
        process.stderr.write("\n-------------------------------\n");
        process.exit(1);
    }
}

render();
