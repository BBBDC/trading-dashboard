import subprocess
import sys
from pathlib import Path

prompt_path = Path("/home/admin/trading/knowledge_base/opus_audit_prompt.txt")
prompt = prompt_path.read_text(encoding="utf-8")

claude_bin = "/home/admin/.local/bin/claude"
cmd = [claude_bin, "-p", "--model", "opus", "--effort", "high", prompt]

print("Launching Claude Opus 5.5 with high effort...")
res = subprocess.run(cmd, capture_output=True, text=True)

if res.returncode != 0:
    print("Error calling Claude Opus:", res.stderr, file=sys.stderr)
    sys.exit(res.returncode)

report_path = Path("/home/admin/trading/knowledge_base/opus_audit_report.md")
report_path.write_text(res.stdout, encoding="utf-8")
print(f"Audit completed successfully! Report written to {report_path}")
print("Preview:")
print(res.stdout[:500])
