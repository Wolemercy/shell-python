import sys


def main():
    while True:
        sys.stdout.write("$ ")

        command = input()

        if command == 'exit':
            break

        if len(command) >= 4 and command[:4] == 'echo':
            print(command[4:].lstrip())
            continue

        print(f"{command}: command not found")


if __name__ == "__main__":
    main()
