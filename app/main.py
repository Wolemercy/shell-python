import os
import shlex
import subprocess
import sys
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
        return f"{command} is a shell builtin"
    
    path = find_executable(command, os.environ.get("PATH").split(os.pathsep))

    if path:
        return f"{command} is {path}"
    
    return f"{command}: not found"

def _handle_external_program(command, args, stdout):
    
    path = find_executable(command, os.environ.get("PATH").split(os.pathsep))

    if path:
        subprocess.run([command] + args, stdout=stdout)    
    else:
        print(f"{command}: command not found")
    return

def _handle_pwd():
    print(os.getcwd())

def _handle_cd(dir):
    if dir == "~":
        os.chdir(os.getenv("HOME"))
    elif os.path.isdir(dir):
        os.chdir(dir)
    else:
        print(f"cd: {dir}: No such file or directory")

def _split_command_args(raw_input: str):
    args = shlex.split(raw_input)
    return args[0], args[1:]

def get_stdout_delim_index(args: list[str]) -> int:
    if ">" in args:
        return args.index(">")
    if "1>" in args:
        return args.index("1>")

    return

def main():
    
    while True:
        raw_input = input("$ ")

        command, args = _split_command_args(raw_input.strip())

        stdout_redirect = None
        default_stdout = sys.stdout

        if ">" in args or "1>" in args:
            # get delimiter index
            delim_index = get_stdout_delim_index(args)
            args, stdout_redirect = args[:delim_index], args[delim_index + 1:]
            
            # set sys.out to file
            stdout_redirect = open(stdout_redirect[0], "w")
            sys.stdout = stdout_redirect
        
        output = stdout_redirect or default_stdout

        if command == "exit":
            break
        elif command == "echo":
            print(" ".join(args))
        elif command == "type":
            print(_handle_type(args[0]))
        elif command == "pwd":
            _handle_pwd()
        elif command == "cd":
            _handle_cd(args[0])
        else:
            _handle_external_program(command, args, output)

        if stdout_redirect:
            sys.stdout = default_stdout
            stdout_redirect.close()


if __name__ == "__main__":
    main()
