import sys

def handle_type_command(arg):
    built_in_commands = { "echo", "exit", "type" }

    if arg in built_in_commands:
        print(f"{arg} is a shell builtin")
    else:
        print(f"{arg}: not found")
    
    return

def main():
    while True:
        sys.stdout.write("$ ")

        command = input()

        if command == "exit":
            break
        elif command.startswith("echo "):
            print(command[5:])
            continue
        elif command.startswith("type "):
            handle_type_command(command[5:])
        else:
            print(f"{command}: command not found")


if __name__ == "__main__":
    main()
