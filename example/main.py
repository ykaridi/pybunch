from submodule import motd
from fibonnaci import fibonacci


print("Example run as <%s>" % __name__)
if __name__ == '__main__':
    print(fibonacci(8))
    print(motd.MOTD)
