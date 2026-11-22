"""允许 python3 -m conceptwatch 直接运行命令行。"""

from .pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
