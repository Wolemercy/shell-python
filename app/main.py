import os
import readline
import shlex
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple, Optional, TextIO


def get_path_directories() -> list[str]:
    return os.environ.get("PATH").split(os.pathsep)


def find_executable(command: str, path_dirs: list[str]) -> Optional[Path]:
    for dir in path_dirs:
        cmd_path: Path = Path(dir) / command
        if cmd_path.is_file() and os.access(cmd_path, os.X_OK):
            return cmd_path
    return None


def get_cmd_names_in_path(text: str) -> set:
    cmd_names = set()
    for dir in get_path_directories():
        dir_path = Path(dir)
        try:
            entries = dir_path.iterdir()
            files = [
                p
                for p in entries
                if p.is_file() and os.access(p, os.X_OK) and p.name.startswith(text)
            ]
        except OSError:
            continue
        for file in files:
            cmd_names.add(file.name)
    return cmd_names


def handle_exit(command: str, args: list[str], out: TextIO, err: TextIO):
    raise SystemExit()


def handle_echo(command: str, args: list[str], out: TextIO, err: TextIO):
    print(" ".join(args), file=out)


def handle_pwd(command: str, args: list[str], out: TextIO, err: TextIO):
    print(os.getcwd(), file=out)


def handle_cd(command: str, args: list[str], out: TextIO, err: TextIO):
    dir = args[0]
    if dir == "~":
        os.chdir(os.getenv("HOME"))
    elif os.path.isdir(dir):
        os.chdir(dir)
    else:
        print(f"cd: {dir}: No such file or directory", file=err)


def handle_type(command: str, args: list[str], out: TextIO, err: TextIO):
    cmd = args[0]
    if cmd in COMMAND_DISPATCH:
        print(f"{cmd} is a shell builtin", file=out)
        return

    path = find_executable(cmd, get_path_directories())

    if path:
        return print(f"{cmd} is {path}", file=out)

    return print(f"{cmd}: not found", file=out)


def handle_external_program(command: str, args: list[str], out: TextIO, err: TextIO):

    path = find_executable(command, get_path_directories())

    if path:
        subprocess.run([command] + args, stdout=out, stderr=err, check=False)
    else:
        print(f"{command}: command not found", file=err)


COMMAND_DISPATCH = {
    "echo": handle_echo,
    "type": handle_type,
    "pwd": handle_pwd,
    "cd": handle_cd,
    "exit": handle_exit,
}


def split_command_args(raw_input: str):
    args = shlex.split(raw_input)
    if not args:
        return None
    return args[0], args[1:]


class Redirect(NamedTuple):
    filename: str
    mode: str


REDIRECTS = {
    ">": ("stdout", "w"),
    "1>": ("stdout", "w"),
    ">>": ("stdout", "a"),
    "1>>": ("stdout", "a"),
    "2>": ("stderr", "w"),
    "2>>": ("stderr", "a"),
}


def parse_redirects(tokens: list[str]) -> tuple[list[str], dict[str, Redirect]]:
    argv, redirects = [], {}
    i = 0

    while i < len(tokens):
        if tokens[i] in REDIRECTS and i + 1 < len(tokens):
            stream, mode = REDIRECTS[tokens[i]]
            redirects[stream] = Redirect(tokens[i + 1], mode)
            i += 2
        else:
            argv.append(tokens[i])
            i += 1
    return argv, redirects

def get_command_completion_options(text: str) -> list[str]:
    options = get_cmd_names_in_path(text)
    for command in COMMAND_DISPATCH:
        if command.startswith(text):
            options.add(command)

    return list(options)

def get_file_completion_options(text: str) -> list[str]:
    p = Path('./')
    files = [f.name for f in p.iterdir() if f.is_file() and f.name.startswith(text)]

    return files

def completer(text: str, state: int) -> Optional[str]:
    text_index_start = readline.get_begidx()

    if text_index_start == 0:
        options =  get_command_completion_options(text)
    else:
        options = get_file_completion_options(text)
    
    sorted_options = sorted(options)
    
    if state < len(sorted_options):
        return f"{sorted_options[state]} "
    return None

def setup():
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    return


def main():

    setup()

    while True:
        raw_input = input("$ ")

        split_args = split_command_args(raw_input.strip())
        if not split_args:
            continue
        command, args = split_args

        args, redirects = parse_redirects(args)

        with ExitStack() as cm:
            std_dict = {
                "stdout": sys.stdout,
                "stderr": sys.stderr,
            }

            for std, (filename, mode) in redirects.items():
                std_dict[std] = cm.enter_context(open(filename, mode))

            command_handler = COMMAND_DISPATCH.get(command)
            if not command_handler:
                command_handler = handle_external_program

            command_handler(command, args, std_dict["stdout"], std_dict["stderr"])


if __name__ == "__main__":
    main()
