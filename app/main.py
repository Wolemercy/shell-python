import os
import readline
import shlex
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import IO, Any, NamedTuple, Optional, TextIO, TypedDict


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
    write_history_on_exit()
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

def _handle_list_history(args: list[str], out: TextIO):
    history_length = readline.get_current_history_length()
    
    limit = int(args[0]) if len(args) else history_length
    start_index = max(1, history_length - limit + 1)

    for index in range(start_index, history_length + 1):
        history_item = readline.get_history_item(index)
        print(f"{index:>5}  {history_item}", file=out)
    return

def _handle_read_history(file_path: str):
    with open(file_path, "r") as f:
        for l in f.readlines():
            line = l.strip("\n")
            if not line: continue
            readline.add_history(line)
    return

def _write_history_from(file_path: str, mode: str, start: int):
    with open(file_path, mode) as f:
        for i in range(start, readline.get_current_history_length() + 1):
            f.write(f"{readline.get_history_item(i)}\n")

def _handle_write_history(file_path: str):
    _write_history_from(file_path, "w", 1)
    return

LAST_APPENDED_HISTORY_INDEX = 0

def _handle_append_history(file_path: str):
    global LAST_APPENDED_HISTORY_INDEX

    _write_history_from(file_path, "a", LAST_APPENDED_HISTORY_INDEX + 1)
    LAST_APPENDED_HISTORY_INDEX = readline.get_current_history_length()
    return

def read_history_on_startup():
    history_file = os.getenv("HISTFILE")
    if not history_file:
        return
    _handle_read_history(history_file)
    LAST_APPENDED_HISTORY_INDEX = readline.get_current_history_length()
    return

def write_history_on_exit():
    history_file = os.getenv("HISTFILE")
    if not history_file:
        return
    _handle_write_history(history_file)
    return


def handle_history(command: str, args: list[str], out: TextIO, err: TextIO):
    token, *token_args = args or [None]

    if token == "-r" and token_args:
        _handle_read_history(token_args[0])
    elif token == "-w" and token_args:
        _handle_write_history(token_args[0])
    elif token == "-a" and token_args:
        _handle_append_history(token_args[0])
    else:
        _handle_list_history(args, out)
    return


class JobInfo(TypedDict):
    argv: list[str]
    process: subprocess.Popen


class Redirect(NamedTuple):
    filename: str
    mode: str


class Stage(NamedTuple):
    argv: list[str]
    redirects: dict[str, Redirect]
    background: bool


REDIRECTS = {
    ">": ("stdout", "w"),
    "1>": ("stdout", "w"),
    ">>": ("stdout", "a"),
    "1>>": ("stdout", "a"),
    "2>": ("stderr", "w"),
    "2>>": ("stderr", "a"),
}


JOBS: dict[int, JobInfo] = {}


def _build_job_output(job_id: int, job_info: JobInfo, status: str, marker: str):
    return f"[{job_id}]{marker}  {status:<24}{' '.join(job_info['argv'])}"


def _get_job_status(job_info: JobInfo):
    process = job_info["process"]
    return "Done" if process.poll() is not None else "Running"


def _get_next_job_id():
    return max(JOBS.keys(), default=0) + 1


def _report_jobs(out: TextIO, only_done: bool):
    jobs_count = len(JOBS)
    for index, [job_id, job] in enumerate(JOBS.copy().items()):
        marker = ""
        if index == jobs_count - 1:
            marker = "+"
        elif index == jobs_count - 2:
            marker = "-"

        status = _get_job_status(job)
        job_str = _build_job_output(job_id, job, status, marker)

        if status == "Done":
            print(job_str, file=out)
            JOBS.pop(job_id, None)
        elif not only_done:
            print(job_str, file=out)

    return


def handle_jobs(command: str, args: list[str], out: TextIO, err: TextIO):
    _report_jobs(out, False)

def _handle_missing_variables(token_args, out: TextIO):
    variable, *_ = token_args or [None]
    if variable:
        print(f"declare: {variable}: not found", file=out)
    pass

def handle_declare(command: str, args: list[str], out: TextIO, err: TextIO):
    token, *token_args = args or [None]

    if token == "-p":
        _handle_missing_variables(token_args, out)
    return


def reap_completed_jobs():
    _report_jobs(sys.stdout, True)


def run_background_job(command: str, args: list[str], out: TextIO, err: TextIO):
    job_id = _get_next_job_id()

    argv = [command] + args

    process = subprocess.Popen(argv, stdout=out, stderr=err)
    print(f"[{job_id}] {process.pid}", file=out)
    JOBS[job_id] = JobInfo(argv=argv, process=process)
    return


def split_stages(argv: list[str]) -> list[list[str]]:
    stages = []
    current_stage = []
    for token in argv:
        if token == "|":
            stages.append(current_stage)
            current_stage = []
        else:
            current_stage.append(token)

    if current_stage:
        stages.append(current_stage)
    return stages


def run_pipeline(stages: list[Stage], cm: ExitStack):

    current_input: Optional[IO[Any]] = None
    processes: list[subprocess.Popen[Any]] = []

    for index, stage in enumerate(stages):
        is_last = index == len(stages) - 1

        if not is_last:
            r, w = os.pipe()
            pipe_out = os.fdopen(w, "w")
            default_out = pipe_out
        else:
            default_out = sys.stdout
            pipe_out = None

        std_dict = open_stage_streams(stage, cm, default_out, sys.stderr)
        stdout, stderr = std_dict["stdout"], std_dict["stderr"]

        command, args = stage.argv[0], stage.argv[1:]
        if COMMAND_DISPATCH.get(command):
            handler = COMMAND_DISPATCH.get(command)
            handler(command, args, stdout, stderr)
        else:
            p = subprocess.Popen(
                stage.argv,
                stdin=current_input,
                stdout=stdout,
                stderr=stderr,
            )

            processes.append(p)

        if current_input:
            current_input.close()

        if not is_last:
            current_input = os.fdopen(r)

        if pipe_out:
            pipe_out.close()

    for p in processes:
        p.wait()

    return


COMMAND_DISPATCH = {
    "echo": handle_echo,
    "type": handle_type,
    "pwd": handle_pwd,
    "cd": handle_cd,
    "exit": handle_exit,
    "complete": handle_complete,
    "jobs": handle_jobs,
    "history": handle_history,
    "declare": handle_declare,
}


def tokenize(raw_input: str):
    argv = shlex.split(raw_input)
    return argv


def parse_stage(tokens: list[str]) -> Stage:
    argv, redirects, is_background_job = [], {}, False
    i = 0

    while i < len(tokens):
        if tokens[i] in REDIRECTS and i + 1 < len(tokens):
            stream, mode = REDIRECTS[tokens[i]]
            redirects[stream] = Redirect(tokens[i + 1], mode)
            i += 2
        elif tokens[i] == "&" and i == len(tokens) - 1:
            is_background_job = True
            i += 1
        else:
            argv.append(tokens[i])
            i += 1
    return Stage(argv, redirects, is_background_job)


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


def open_stage_streams(stage: Stage, cm, default_out, default_err):
    std_dict = {
        "stdout": default_out,
        "stderr": default_err,
    }
    for std, (filename, mode) in stage.redirects.items():
        std_dict[std] = cm.enter_context(open(filename, mode))

    return std_dict


def setup():
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completion_display_matches_hook(custom_display_hook)

    return


def main():

    setup()
    read_history_on_startup()

    while True:
        reap_completed_jobs()
        raw_input = input("$ ")

        argv = tokenize(raw_input.strip())
        if not argv:
            continue

        stage_tokens = split_stages(argv)

        stages = [parse_stage(stage) for stage in stage_tokens]

        with ExitStack() as cm:
            if len(stages) == 1:
                stage = stages[0]
                std_dict = open_stage_streams(stage, cm, sys.stdout, sys.stderr)

                command, args = stage.argv[0], stage.argv[1:]

                if stage.background:
                    command_handler = run_background_job
                elif COMMAND_DISPATCH.get(command):
                    command_handler = COMMAND_DISPATCH.get(command)
                else:
                    command_handler = handle_external_program

                command_handler(command, args, std_dict["stdout"], std_dict["stderr"])
            else:
                run_pipeline(stages, cm)


if __name__ == "__main__":
    main()
