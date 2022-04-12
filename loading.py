from time import sleep

for i in range(0, 10):
    print("[{}{}]".format("-" * i, " " * (10 - i)), end="\r", flush=True)
    sleep(1)
