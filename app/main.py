import os, subprocess, sys
from pathlib import Path

built_in_commands = { "cd", "echo", "exit", "pwd", "type", }

def find_executable(command, path_dirs):
    for dir in path_dirs:
        cmd_path: Path = Path(dir) / command
        if cmd_path.is_file() and os.access(cmd_path, os.X_OK):
            return cmd_path
    return None

def _handle_type(command):
    if command in built_in_commands:
        return f"{command} is a shell builtin\n"
    
    path = find_executable(command, os.environ.get("PATH").split(os.pathsep))

    if path:
        return f"{command} is {path}\n"
    
    return f"{command}: not found\n"

def _handle_external_program(command):
    args = command.split()
    program_name = args[0]

    path = find_executable(program_name, os.environ.get("PATH").split(os.pathsep))

    if path:
        subprocess.run(args)
    else:
        sys.stdout.write(f"{command}: command not found\n")
    return

def _handle_pwd():
    sys.stdout.write(f"{os.getcwd()}\n")

def _handle_cd(dir):
    if os.path.isdir(dir):
        os.chdir(dir)
    else:
        sys.stdout.write(f"cd: {dir}: No such file or directory\n")


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
        elif command == "pwd":
            _handle_pwd()
        elif command.startswith("cd "):
            _handle_cd(command[3:])
        else:
            _handle_external_program(command)


if __name__ == "__main__":
    main()
