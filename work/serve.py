"""Local development server. Use launcher.py to build the page and open a browser."""
import argparse
from http.server import ThreadingHTTPServer
from review_server import Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8778)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.allowed_hosts = {'127.0.0.1', 'localhost'}
        print(f'照片整理器：http://127.0.0.1:{args.port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
