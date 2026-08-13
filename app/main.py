import os
import shlex
import subprocess
import sys
from typing import NamedTuple, Optional, TextIO
from pathlib import Path
from contextlib import ExitStack
import readline

REDIRECTS = {
    ">": ("stdout", "w"),
    "1>": ("stdout", "w"),
    ">>": ("stdout", "a"),
    "1>>": ("stdout", "a"),
    "2>": ("stderr", "w"),
    "2>>": ("stderr", "a"),
}


def _handle_exit(command: str, args: list[str], out: TextIO, err: TextIO):
    raise SystemExit()


def _handle_echo(command: str, args: list[str], out: TextIO, err: TextIO):
    print(" ".join(args), file=out)


def _handle_pwd(command: str, args: list[str], out: TextIO, err: TextIO):
    print(os.getcwd(), file=out)


def _handle_cd(command: str, args: list[str], out: TextIO, err: TextIO):
    dir = args[0]
    if dir == "~":
        os.chdir(os.getenv("HOME"))
    elif os.path.isdir(dir):
        os.chdir(dir)
    else:
        print(f"cd: {dir}: No such file or directory", file=err)


def _handle_type(command: str, args: list[str], out: TextIO, err: TextIO):
    cmd = args[0]
    if cmd in COMMAND_DISPATCH:
        print(f"{cmd} is a shell builtin", file=out)
        return

    path = find_executable(cmd, _get_path_directories())

    if path:
        return print(f"{cmd} is {path}", file=out)

    return print(f"{cmd}: not found", file=out)


def _handle_external_program(
    command: str, args: list[str], out: TextIO, err: TextIO
):

    path = find_executable(command, _get_path_directories())

    if path:
        subprocess.run([command] + args, stdout=out, stderr=err, check=False)
    else:
        print(f"{command}: command not found", file=err)


COMMAND_DISPATCH = {
    "echo": _handle_echo,
    "type": _handle_type,
    "pwd": _handle_pwd,
    "cd": _handle_cd,
    "exit": _handle_exit,
}

def _get_path_directories() -> list[str]:
    return os.environ.get("PATH").split(os.pathsep)


def find_executable(command: str, path_dirs: list[str]) -> Optional[Path]:
    for dir in path_dirs:
        cmd_path: Path = Path(dir) / command
        if cmd_path.is_file() and os.access(cmd_path, os.X_OK):
            return cmd_path
    return None


def _split_command_args(raw_input: str):
    args = shlex.split(raw_input)
    if not args:
        return None
    return args[0], args[1:]


class Redirect(NamedTuple):
    filename: str
    mode: str


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

def _get_cmd_names_in_path(text: str):
    cmd_names = set()
    for dir in _get_path_directories():
        dir_path = Path(dir)
        try:
            entries = dir_path.iterdir()
            files = [p for p in entries if p.is_file() and os.access(p, os.X_OK) and p.name.startswith(text)]
        except OSError:
            continue
        for file in files:
            cmd_names.add(file.name)
    return cmd_names


def completer(text: str, state: int) -> Optional[str]:
    options = _get_cmd_names_in_path(text)
    for command in COMMAND_DISPATCH:
        if command.startswith(text):
            options.add(command)

    sorted_options = sorted(list(options))

    if state < len(sorted_options):
        return f"{sorted_options[state]} "
    return None


def main():

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    while True:
        raw_input = input("$ ")

        split_args = _split_command_args(raw_input.strip())
        if not split_args:
            continue
        command, args = split_args

        args, redirects = parse_redirects(args)

        with ExitStack() as cm:
            out = sys.stdout
            err = sys.stderr

            if "stdout" in redirects:
                out_filename, out_mode = redirects["stdout"].filename, redirects["stdout"].mode
                out = cm.enter_context(open(out_filename, out_mode))

            if "stderr" in redirects:
                err_filename, err_mode = redirects["stderr"].filename, redirects["stderr"].mode
                err = cm.enter_context(open(err_filename, err_mode))

            command_handler = COMMAND_DISPATCH.get(command)
            if not command_handler:
                command_handler = _handle_external_program

            command_handler(command, args, out, err)


if __name__ == "__main__":
    main()
