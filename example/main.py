from submodule import motd
from fibonnaci import fibonacci


print("Example run as <%s>" % __name__)
if __name__ == '__main__':
    print(fibonacci(8))
    message_of_the_day = motd.MOTD
    print(message_of_the_day)
    # Stacktrace will show up correctly!
    1 / 0
