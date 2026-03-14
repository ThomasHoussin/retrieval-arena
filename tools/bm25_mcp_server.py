"""Custom BM25s MCP server with English stemmer support.

The upstream bm25s MCP server (bm25s.mcp.server) does not pass a stemmer
when tokenizing queries, but our index was built with Stemmer("english").
This wrapper fixes that mismatch.
"""

import sys

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

import argparse

import bm25s
import Stemmer
from mcp.server.fastmcp import FastMCP

from config import load_config

def create_mcp_server(index_dir: str, stemmer_language: str = "english"):
    mcp = FastMCP("bm25s")
    stemmer = Stemmer.Stemmer(stemmer_language)

    print(f"Loading index from {index_dir}...", file=sys.stderr)
    print(f"Stemmer language: {stemmer_language}", file=sys.stderr)
    retriever = bm25s.BM25.load(index_dir, load_corpus=True)
    print("Index loaded successfully.", file=sys.stderr)

    @mcp.tool()
    def retrieve(query: str, k: int = 10) -> str:
        """
        Retrieve documents from the index based on the query.

        Args:
            query: The search query string.
            k: The number of documents to retrieve.
        """
        if not query.strip():
            return "Error: query must not be empty."

        query_tokens = bm25s.tokenize(query, stemmer=stemmer)
        effective_k = min(k, retriever.scores["num_docs"])

        results = retriever.retrieve(query_tokens, k=effective_k)

        output = []
        for i, (doc, score) in enumerate(zip(results.documents[0], results.scores[0])):
            output.append(f"Rank {i + 1} (Score: {score:.4f}):\n{doc}\n")

        return "\n".join(output)

    @mcp.tool()
    def get_info() -> str:
        """
        Get information about the loaded index.
        """
        return (
            f"BM25S Index Info:\n"
            f"- Vocab Size: {len(retriever.vocab_dict)}\n"
            f"- Num Docs: {retriever.scores['num_docs']}\n"
            f"- Backend: {retriever.backend}"
        )

    return mcp


def main():
    parser = argparse.ArgumentParser(description="BM25s MCP Server (with stemmer)")
    parser.add_argument("--index-dir", help="Path to the BM25s index directory")
    parser.add_argument("--config", help="Path to search_bench.json config file")
    args = parser.parse_args()

    if args.index_dir:
        index_dir = args.index_dir
        stemmer_language = "english"
    else:
        cfg = load_config(args.config)
        index_dir = str(cfg["bm25_index_dir"])
        stemmer_language = cfg["stemmer_language"]

    mcp = create_mcp_server(index_dir, stemmer_language)
    mcp.run()


if __name__ == "__main__":
    main()
