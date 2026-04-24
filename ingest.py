"""CLI entry point for PDF ingest pipeline."""

import argparse
import io
import sys

# Windows 터미널 UTF-8 강제 (Korean output)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config

config.setup_logging("ingest")

from src.ingest.pipeline import run_pipeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="PDF 인제스트 — rag_data/ 폴더의 PDF를 Pinecone에 업로드")
    parser.add_argument(
        "--dir",
        default=str(config.RAG_DATA_DIR),
        help="PDF 디렉토리 경로 (기본: rag_data/)",
    )
    args = parser.parse_args()

    print(f"인제스트 시작: {args.dir}")
    try:
        report = run_pipeline(args.dir)
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as e:
        print(f"환경 변수 오류: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n인제스트 완료:")
    print(f"  처리됨:   {report['processed']}개 파일")
    print(f"  스킵됨:   {report['skipped']}개 파일 (이미 인덱스됨)")
    print(f"  실패:     {len(report['failed'])}개 파일")
    print(f"  총 청크:  {report['total_chunks']}개")

    if report["failed"]:
        print(f"\n실패한 파일:")
        for f in report["failed"]:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
