#!/usr/bin/env python3

from taggart.database import Database


def main(argv):
    cmd = argv[1:2]
    args = argv[2:]

    db = Database("taggart.db", use_torch=True)

    if cmd == ["add"]:
        for dir in args:
            db.add_images_from_dir(dir)

    elif cmd == ["embeddings"]:
        from taggart.embeddings import add_embeddings

        add_embeddings(db)

    elif cmd == ["serve"]:
        from taggart.server import Server

        Server(db).run()


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
