#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import posixpath
import shutil
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


HOST = "127.0.0.1"
DEFAULT_PORT = 8787
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TOOLS_DIR = PROJECT_DIR / "tools"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "local_outputs"
BUNDLED_PYTHON = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"


ALLOWED_CODEX_READ_FILES = [
    "sanitized_trades.csv",
    "privacy_guard_report.json",
    "cleaned_trades.csv",
    "metrics.json",
    "trade_lifecycle.json",
    "behavior_flags.json",
    "counterfactual_report.json",
    "trade_review_report.html",
]


class ProcessingError(Exception):
    def __init__(self, title, messages, privacy_status="未完成", status_code=400):
        super().__init__(title)
        self.title = title
        self.messages = messages
        self.privacy_status = privacy_status
        self.status_code = status_code


def safe_output_dir(path):
    output_dir = Path(path).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def make_run_dir(base_output_dir):
    run_name = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    run_dir = safe_output_dir(Path(base_output_dir) / run_name)
    return run_name, run_dir


def is_relative_to(child, parent):
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def can_import_pdfplumber(python_executable):
    result = subprocess.run(
        [str(python_executable), "-c", "import pdfplumber"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def choose_python():
    candidates = [Path(sys.executable)]
    if BUNDLED_PYTHON.exists():
        candidates.append(BUNDLED_PYTHON)
    system_python = shutil.which("python3")
    if system_python:
        candidates.append(Path(system_python))
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if can_import_pdfplumber(candidate):
            return key
    return str(candidates[0])


PYTHON = choose_python()


def run_command(args, cwd=PROJECT_DIR):
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args)
    return result


def parse_multipart_pdf(body, content_type):
    marker = "boundary="
    if marker not in content_type:
        raise ProcessingError("上传格式错误", ["请求不是 multipart/form-data。"])
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ProcessingError("上传格式错误", ["缺少 multipart boundary。"])
    delimiter = ("--" + boundary).encode("utf-8")
    for part in body.split(delimiter):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        header_blob, sep, payload = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        if 'name="pdf"' not in headers:
            continue
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        if not payload:
            raise ProcessingError("上传文件为空", ["请选择一个 PDF 文件。"])
        if not payload.startswith(b"%PDF"):
            raise ProcessingError("文件类型错误", ["上传文件不像 PDF。请确认选择的是券商交割单 PDF。"])
        return payload
    raise ProcessingError("未找到 PDF", ["表单中没有名为 pdf 的文件字段。"])


def load_privacy_summary(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return "隐私检查失败", ["无法读取 privacy_guard_report.json。"]
    errors = data.get("errors", [])
    warnings = data.get("warnings", [])
    if errors:
        kinds = sorted({item.get("risk_type", "unknown") for item in errors})
        return "失败", [f"发现 {len(errors)} 个隐私风险类型：{', '.join(kinds)}。", "为避免泄露，页面不显示原始单元格内容。"]
    if warnings:
        kinds = sorted({item.get("risk_type", "unknown") for item in warnings})
        return "通过但有警告", [f"发现非阻断隐私警告 {len(warnings)} 个：{', '.join(kinds)}。"]
    return "通过", ["未发现身份、账号、手机号、银行卡或地址类敏感信息。"]


def process_pdf(pdf_bytes, output_dir):
    base_output_dir = safe_output_dir(output_dir)
    run_name, run_dir = make_run_dir(base_output_dir)
    temp_pdf_deleted = False
    messages = ["原始 PDF 已保存到系统临时目录。"]
    with tempfile.TemporaryDirectory(prefix="stock_trade_pdf_") as tmpdir:
        tmp_path = Path(tmpdir) / f"upload-{uuid.uuid4().hex}.pdf"
        tmp_path.write_bytes(pdf_bytes)
        if not is_relative_to(tmp_path, tempfile.gettempdir()):
            raise ProcessingError("临时目录异常", ["原始 PDF 未写入系统临时目录，已停止处理。"], status_code=500)

        sanitized = run_dir / "sanitized_trades.csv"
        sanitize_report = run_dir / "sanitize_pdf_report.json"
        privacy_report = run_dir / "privacy_guard_report.json"
        cleaned = run_dir / "cleaned_trades.csv"
        metrics = run_dir / "metrics.json"
        lifecycle = run_dir / "trade_lifecycle.json"
        behavior = run_dir / "behavior_flags.json"
        counterfactual = run_dir / "counterfactual_report.json"
        markdown = run_dir / "trade_review_report.md"
        html_report = run_dir / "trade_review_report.html"
        mapping = run_dir / "field_mapping_suggestions.json"

        try:
            run_command([
                PYTHON, str(SCRIPT_DIR / "sanitize_pdf_statement.py"),
                str(tmp_path), "-o", str(sanitized), "--report", str(sanitize_report),
            ])
        except subprocess.CalledProcessError:
            if tmp_path.exists():
                tmp_path.unlink()
                temp_pdf_deleted = True
            raise ProcessingError("PDF 脱敏失败", ["可能是扫描版 PDF，或表格字段无法识别。请使用本地 OCR 或检查 PDF 格式。"])

        if tmp_path.exists():
            tmp_path.unlink()
            temp_pdf_deleted = True
        messages.append("原始 PDF 已在脱敏后删除。")

        try:
            run_command([PYTHON, str(SCRIPT_DIR / "privacy_guard.py"), str(sanitized), "-o", str(privacy_report)])
        except subprocess.CalledProcessError:
            privacy_status, privacy_messages = load_privacy_summary(privacy_report)
            raise ProcessingError("隐私检查失败", privacy_messages + ["已停止后续复盘流程。"], privacy_status=privacy_status)

        privacy_status, privacy_messages = load_privacy_summary(privacy_report)
        messages.extend(privacy_messages)

        steps = [
            [PYTHON, str(SCRIPT_DIR / "parse_statement.py"), str(sanitized), "-o", str(cleaned), "--suggestions-out", str(mapping)],
            [PYTHON, str(SCRIPT_DIR / "compute_metrics.py"), str(cleaned), "-o", str(metrics)],
            [PYTHON, str(SCRIPT_DIR / "build_trade_lifecycle.py"), str(cleaned), "-o", str(lifecycle)],
            [PYTHON, str(SCRIPT_DIR / "detect_behavior_patterns.py"), str(cleaned), str(metrics), str(lifecycle), "-o", str(behavior)],
            [PYTHON, str(SCRIPT_DIR / "counterfactual_simulator.py"), str(metrics), str(lifecycle), "-o", str(counterfactual)],
            [PYTHON, str(SCRIPT_DIR / "generate_review_report.py"), str(cleaned), str(metrics), str(lifecycle), str(behavior), str(counterfactual), "-o", str(markdown)],
            [PYTHON, str(SCRIPT_DIR / "generate_html_report.py"), str(metrics), str(lifecycle), str(behavior), str(counterfactual), "--markdown", str(markdown), "-o", str(html_report)],
        ]
        try:
            for step in steps:
                run_command(step)
        except subprocess.CalledProcessError:
            raise ProcessingError("复盘流程失败", ["脱敏和隐私检查已完成，但后续指标或报告生成失败。"], privacy_status=privacy_status, status_code=500)

    messages.append(f"临时 PDF 删除状态：{'已删除' if temp_pdf_deleted else '无需删除'}。")
    report_url = f"/local_outputs/{run_name}/trade_review_report.html"
    return {
        "status": "ok",
        "title": "处理完成",
        "privacy_status": privacy_status,
        "messages": messages,
        "paths": {
            "sanitized_trades": str(sanitized),
            "html_report": str(html_report),
            "html_report_relative": str(Path("local_outputs") / run_name / "trade_review_report.html"),
        },
        "report_url": report_url,
        "allowed_codex_read_files": ALLOWED_CODEX_READ_FILES,
    }


class PrivacyUploadHandler(BaseHTTPRequestHandler):
    server_version = "StockTradePrivacyRunner/1.0"

    def log_message(self, fmt, *args):
        # Keep terminal logs free of uploaded filenames or data-derived content.
        print(f"[local-runner] {self.command} {self.path.split('?', 1)[0]}")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type=None):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/tools/privacy-upload.html"):
            self.send_file(TOOLS_DIR / "privacy-upload.html", "text/html; charset=utf-8")
            return
        if path.startswith("/local_outputs/"):
            parts = [part for part in posixpath.normpath(path).split("/") if part]
            if len(parts) != 3 or parts[0] != "local_outputs":
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            run_name, requested = parts[1], parts[2]
            if not run_name.startswith("run_") or requested not in ALLOWED_CODEX_READ_FILES:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            target = self.server.output_dir / run_name / requested
            if not is_relative_to(target, self.server.output_dir):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            content_type = "text/html; charset=utf-8" if requested.endswith(".html") else None
            self.send_file(target, content_type)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if urlparse(self.path).path != "/upload":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > self.server.max_upload_bytes:
                raise ProcessingError("文件大小不合法", ["PDF 为空或超过大小限制。"])
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            pdf_bytes = parse_multipart_pdf(body, content_type)
            result = process_pdf(pdf_bytes, self.server.output_dir)
            report_http_url = f"http://{HOST}:{self.server.server_port}{result['report_url']}"
            html_report_path = result.get("paths", {}).get("html_report", "")
            print("处理完成。")
            print(f"本地服务地址：http://{HOST}:{self.server.server_port}")
            print(f"HTML 报告 HTTP 地址：{report_http_url}")
            print(f"HTML 报告本地文件路径：{html_report_path}")
            print(f"如果 127.0.0.1 无法访问，可直接执行：open {html_report_path}")
            self.send_json(HTTPStatus.OK, result)
        except ProcessingError as exc:
            print(f"处理失败：{exc.title}")
            self.send_json(exc.status_code, {
                "status": "error",
                "title": exc.title,
                "privacy_status": exc.privacy_status,
                "messages": exc.messages,
                "paths": {},
            })
        except Exception:
            print("本地服务异常：处理请求失败。")
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "status": "error",
                "title": "本地服务异常",
                "privacy_status": "未完成",
                "messages": ["处理失败。为避免泄露，错误响应不包含上传文件内容。"],
                "paths": {},
            })


class PrivacyRunnerServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_cls, output_dir, max_upload_bytes):
        super().__init__(server_address, handler_cls)
        self.output_dir = safe_output_dir(output_dir)
        self.max_upload_bytes = max_upload_bytes


def main():
    parser = argparse.ArgumentParser(description="启动股票交割单隐私交互模式本地服务")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-mb", type=int, default=50)
    args = parser.parse_args()

    server = PrivacyRunnerServer((HOST, args.port), PrivacyUploadHandler, Path(args.output_dir), args.max_mb * 1024 * 1024)
    url = f"http://{HOST}:{args.port}"
    print(f"本地隐私交互页面已启动：{url}")
    print("仅监听 127.0.0.1；真实 PDF 只在本机临时目录处理。按 Ctrl+C 退出。")
    print(f"子脚本解释器：{PYTHON}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地服务已停止。")
    except Exception as exc:
        print(f"本地服务异常退出：{type(exc).__name__}")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
