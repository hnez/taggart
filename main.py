#!/usr/bin/env python3

import argparse

from taggart.database import Database


def main():
    parser = argparse.ArgumentParser(description="Taggart - The interactive tagging tool")
    parser.add_argument("--database", default="taggart.db", help="Path to the database file (default: taggart.db)")
    parser.add_argument("--cpu", action="store_true", help="Use CPU instead of GPU")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available subcommands")

    add_parser = subparsers.add_parser("add", help="Add a list of directories")
    add_parser.add_argument("directories", nargs="+", help="List of directories to add")

    serve_parser = subparsers.add_parser("serve", help="Start the server")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host address to bind the server (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8080, help="Port number to run the server on (default: 8080)"
    )

    embeddings_parser = subparsers.add_parser("embeddings", help="Run the embedding generation process")
    embeddings_parser.add_argument("--batch-size", type=int, default=48, help="Number of images to process at once")
    embeddings_parser.add_argument(
        "--workers", type=int, default=10, help="Number of worker processes for decompressing images"
    )

    args = parser.parse_args()

    db = Database(args.database, cpu=args.cpu)

    if args.command == "add":
        for dir in args.directories:
            db.add_images_from_dir(dir)

    elif args.command == "serve":
        from taggart.server import Server

        Server(db).run(host=args.host, port=args.port)

    elif args.command == "embeddings":
        from taggart.embeddings import add_embeddings

        add_embeddings(db, batch_size=args.batch_size, num_workers=args.workers)


if __name__ == "__main__":
    main()
