from __future__ import print_function

import json

from .config import build_arg_parser, config_from_args
from .db import EventDB
from .http_api import serve
from .status import status


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    if args.once:
        db = EventDB(config["db_path"])
        try:
            print(json.dumps(status(config, db), sort_keys=True, indent=2))
        finally:
            db.close()
        return 0
    serve(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
