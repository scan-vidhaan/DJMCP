"""Entry point: python -m djmcp"""

import uvicorn

from djmcp.config import HOST, PORT


def main() -> None:
    uvicorn.run("djmcp.server:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    main()
