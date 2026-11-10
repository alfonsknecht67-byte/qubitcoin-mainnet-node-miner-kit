#!/usr/bin/env python3
"""Only the optional kit node; status RPCs are strictly read-only."""
import argparse
import json
import os
from node_support import NodeError, NodeRuntime

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'status', 'run', 'request-stop'])
    parser.add_argument('--session')
    args = parser.parse_args(argv)
    os.umask(0o077)
    runtime = NodeRuntime()
    try:
        if args.action == 'check':
            runtime.verify()
            print(json.dumps({'node_build_verified': True}))
        elif args.action == 'status':
            print(json.dumps(runtime.status()))
        elif args.action == 'request-stop':
            print(json.dumps({'stop_requested': runtime.stop_request(args.session or '')}))
        else:
            return runtime.supervise(args.session or '')
        return 0
    except NodeError as error:
        print(json.dumps({'error': str(error)}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
