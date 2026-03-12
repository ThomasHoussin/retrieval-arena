"""Extract a single page from a PDF using pymupdf4llm."""

import argparse
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf4llm


def main():
    parser = argparse.ArgumentParser(description="Extract a page from a PDF")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("page", type=int, help="Page number (1-indexed)")
    args = parser.parse_args()

    pages = pymupdf4llm.to_markdown(args.pdf, pages=[args.page - 1], page_chunks=True)
    if pages:
        print(pages[0]["text"])
    else:
        print("No content extracted.", file=sys.stderr)


if __name__ == "__main__":
    main()
