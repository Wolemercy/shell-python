import os
import readline
import shlex
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple, Optional, TextIO, TypedDict


def get_path_directories() -> list[str]:
    return os.environ.get("PATH").split(os.pathsep)


def find_executable(command: str, path_dirs: list[str]) -> Optional[Path]:
    for dir in path_dirs:
        cmd_path: Path = Path(dir) / command
        if cmd_path.is_file() and os.access(cmd_path, os.X_OK):
            return cmd_path
    return None


def get_cmd_names_in_path(prefix: str) -> set[str]:
    cmd_names = set()
    for dir in get_path_directories():
        dir_path = Path(dir)
        try:
            entries = dir_path.iterdir()
            files = [
                p
                for p in entries
                if p.is_file() and os.access(p, os.X_OK) and p.name.startswith(prefix)
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


COMPLETIONS = {}


def handle_complete(command: str, args: list[str], out: TextIO, err: TextIO):
    token, token_args = args[0], args[1:]
    if token == "-p":
        if len(token_args) < 1:
            return
        completion_cmd = token_args[0]
        completion_script = COMPLETIONS.get(completion_cmd)
        if completion_script:
            return print(
                f"complete -C '{completion_script}' {completion_cmd}", file=out
            )
        else:
            return print(
                f"{command}: {completion_cmd}: no completion specification", file=err
            )
    elif token == "-C":
        if len(token_args) < 2:
            return
        completion_script, completion_cmd = token_args[0], token_args[1]
        COMPLETIONS[completion_cmd] = completion_script
    elif token == "-r":
        if len(token_args) < 1:
            return
        COMPLETIONS.pop(token_args[0], None)

class JobInfo(TypedDict):
    job_id: int
    pid: int
    command_str: str
    process: subprocess.Popen

JOB_ID = 0
JOBS: dict[int, JobInfo] = {}

def is_background_job(args: list[str]) -> bool:
    if args and args[-1] == "&":
        return True
    return False

def _build_job_output(job_info: JobInfo, marker: str):
    status = _get_job_status(job_info)
    status_padding = 24 - len(status)
    return f"[{job_info.get("job_id")}]{marker}  {status:<{status_padding}}{" ".join(job_info.get("command_str"))}"

def _get_job_status(job_info: JobInfo):
    process = job_info.get("process")
    return "Done" if process.poll() is not None else "Running"


def handle_jobs(command: str, args: list[str], out: TextIO, err: TextIO):
    jobs_count = len(JOBS)
    completed_job_ids = set()
    for index, [job_id, job] in enumerate(JOBS.items()):
        marker = ""
        if index == jobs_count - 1:
            marker = "+"
        elif index == jobs_count - 2:
            marker = "-"
        job_str = _build_job_output(job, marker)
        print(job_str, file=out)

        status = _get_job_status(job)
        if status == "Done":
            completed_job_ids.add(job_id)

    for id in completed_job_ids:
        JOBS.pop(id, None)

    return

def reap_completed_jobs():
    jobs_count = len(JOBS)
    completed_job_ids = set()
    for index, [job_id, job] in enumerate(JOBS.items()):
        marker = ""
        if index == jobs_count - 1:
            marker = "+"
        elif index == jobs_count - 2:
            marker = "-"

        status = _get_job_status(job)
        if status == "Done":
            job_str = _build_job_output(job, marker)
            print(job_str)
            completed_job_ids.add(job_id)

    for id in completed_job_ids:
        JOBS.pop(id, None)

    return

def run_background_job(command: str, args: list[str], out: TextIO, err: TextIO):
    global JOB_ID
    if not is_background_job(args):
        return

    command_str = [command] + args[:-1]

    JOB_ID += 1

    process = subprocess.Popen(command_str, stdout=out, stderr=err)
    print(f"[{JOB_ID}] {process.pid}", file=out)
    JOBS[JOB_ID] = JobInfo(job_id=JOB_ID, pid=process.pid, command_str=command_str, process=process)
    return
    

COMMAND_DISPATCH = {
    "echo": handle_echo,
    "type": handle_type,
    "pwd": handle_pwd,
    "cd": handle_cd,
    "exit": handle_exit,
    "complete": handle_complete,
    "jobs": handle_jobs,
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
    cmd_names = get_cmd_names_in_path(text)
    options = [f"{cmd_name} " for cmd_name in cmd_names]
    for command in COMMAND_DISPATCH:
        if command.startswith(text):
            options.append(f"{command} ")

    return options


def get_file_completion_options(text: str) -> list[str]:
    head, prefix = os.path.split(text)
    parent = Path(head)

    files = []

    try:
        for f in parent.iterdir():
            if not f.name.startswith(prefix):
                continue
            if f.is_file():
                files.append(f"{f} ")
            if f.is_dir():
                files.append(f"{f}/")
    except OSError:
        pass

    return files


def get_registered_completion_options(text: str, state: int) -> Optional[list[str]]:
    options = None
    try:
        line = readline.get_line_buffer()
        end_index = readline.get_endidx()
        cmd_split = line.split()
        cmd, args = cmd_split[0], cmd_split
        completion_script = COMPLETIONS.get(cmd)

        if text:
            penultimate_word = "" if len(args) <= 1 else args[-2]
        else:
            penultimate_word = args[-1] if len(args) > 0 else ""

        env = os.environ | {"COMP_LINE": line, "COMP_POINT": str(end_index)}

        if completion_script:
            output = subprocess.run(
                [completion_script, cmd, text, penultimate_word],
                capture_output=True,
                text=True,
                env=env,
            ).stdout
            options = [f"{option} " for option in output.splitlines()]

    except Exception:
        pass

    return options


def custom_display_hook(substitution, matches: list[str], longest_match_length):
    line = readline.get_line_buffer()
    output = ""
    for match in matches:
        output += f"{match.strip()}  "

    print(f"\n{output.strip()}")
    print(f"$ {line}", end="", flush=True)


def completer(text: str, state: int) -> Optional[str]:
    text_index_start = readline.get_begidx()

    if text_index_start == 0:
        options = get_command_completion_options(text)
    else:
        options = get_registered_completion_options(text, state)
        if options is None:
            options = get_file_completion_options(text)

    sorted_options = sorted(options)

    if state < len(sorted_options):
        return sorted_options[state]
    return None


def setup():
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completion_display_matches_hook(custom_display_hook)

    return

def main():

    setup()

    while True:
        reap_completed_jobs()
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

            if is_background_job(args):
                command_handler = run_background_job
            elif COMMAND_DISPATCH.get(command):
                command_handler = COMMAND_DISPATCH.get(command)
            else:
                command_handler = handle_external_program

            command_handler(command, args, std_dict["stdout"], std_dict["stderr"])


if __name__ == "__main__":
    main()
