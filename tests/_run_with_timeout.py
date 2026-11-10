#!/usr/bin/env python3
"""Roda um comando com teto de tempo, matando o grupo de processos inteiro.

    python3 tests/_run_with_timeout.py SEGUNDOS comando [args...]

Existe porque o macOS não traz `timeout` (GNU) e o bash é o 3.2. O comando roda
num grupo de processos próprio; ao estourar, o grupo todo recebe SIGKILL, então
os filhos que um teste de pty abre não sobrevivem como órfãos.

Saída: o código do comando, ou 124 se estourou o tempo (mesma convenção do GNU
timeout). stdout/stderr do comando passam direto.
"""
import os
import signal
import subprocess
import sys

TIMEOUT_RC = 124


def main(argv):
    if len(argv) < 3:
        print("uso: _run_with_timeout.py SEGUNDOS comando [args...]", file=sys.stderr)
        return 2
    segundos = float(argv[1])
    proc = subprocess.Popen(argv[2:], start_new_session=True)

    def matar_e_sair(signum, _frame):
        # um supervisor que mata o run-all.sh não pode deixar a sessão do teste órfã
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os._exit(128 + signum)

    signal.signal(signal.SIGTERM, matar_e_sair)
    signal.signal(signal.SIGHUP, matar_e_sair)
    try:
        return proc.wait(timeout=segundos)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return TIMEOUT_RC
    except KeyboardInterrupt:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv))
