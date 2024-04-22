from example.submodule import motd
from .fibonnaci import fibonacci


if __name__ == '__main__':
    print(fibonacci(8))
    print(motd.MOTD)
