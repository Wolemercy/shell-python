import os, shutil, sys
from pathlib import Path

built_in_commands = { "echo", "exit", "type" }

def _handle_type(command):
    if command in built_in_commands:
        return f"{command} is a shell builtin\n"
    
    path = os.environ.get("PATH")
    path_list = path.split(os.pathsep)

    for dir in path_list:
        cmd_path: Path = Path(dir) / command
        if cmd_path.is_file() and os.access(cmd_path, os.X_OK):
            return f"{command} is {cmd_path}\n"
    
    return f"{command}: not found\n"

def main():
    
    while True:
        sys.stdout.write("$ ")

        command = input()

        if command == "exit":
            break
        elif command.startswith("echo "):
            sys.stdout.write(f"{command[5:]}\n")
        elif command.startswith("type "):
            cmd = command[5:]
            sys.stdout.write(_handle_type(cmd))
        else:
            sys.stdout.write(f"{command}: command not found\n")


if __name__ == "__main__":
    main()
