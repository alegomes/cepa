#!/usr/bin/env python3
"""Contract test: `maestro-prune` remove Space + worktree só das slices que
ATERRISSARAM (LANDED), nunca das outras — e nunca confia na palavra do herdr
sem conferir pelo git.

## Por que este teste existe

O `/maestro:run` cria um Space do herdr por slice (`herdr worktree create`).
Sem prune, cada onda deixa esse tanto de Space na barra lateral do herdr — em
2026-08-24 havia 11 sobrando de duas ondas. `maestro-prune` é o comando que o
passo 9 do `run.md` chama ao final da onda para tirar isso do caminho, SÓ das
slices aterrissadas: DONE-não-aterrissada, FAIL, TIMEOUT, ESCALADA, pending e
running continuam precisando do worktree (evidência ou re-fork).

## O que este teste segura (mecânico, com repo git real + herdr fake)

- worktree real criada com `git worktree add`, wave-state real escrito à mão;
- um `herdr` FAKE (`MAESTRO_HERDR`) que implementa só o suficiente de
  `worktree list --json` e `worktree remove --workspace ID --trust-repository`
  para os casos abaixo — e loga cada chamada para conferência de argv;
- LANDED com Space aberto -> remove via `--workspace <id>` (nunca `--force`);
  o fake imita o herdr real e só lista o repo pedido em `--cwd` — sem ele,
  devolve o repo do Space em foco, e o prune cairia no git puro deixando o
  Space na barra lateral (o defeito que a primeira versão tinha e só o teste
  ao vivo pegou);
- DONE (não aterrissada) e FAIL continuam com o worktree no disco;
- formato antigo `landed:` (lista solta) conta como aterrissado;
- LANDED sem Space aberto (`open_workspace_id` ausente) -> cai para
  `git worktree remove` puro;
- LANDED com worktree suja -> falha (dirty_worktree_requires_force), nunca
  força, o worktree continua lá;
- herdr fake que devolve sucesso sem de fato remover -> falha (a conferência
  pelo git é o que segura, não a palavra da ferramenta);
- `--dry-run` não remove nada;
- `run.md` cita `maestro-prune` no passo 9 e trocou a receita fantasma
  `herdr worktree remove <path>` (forma posicional, inválida no herdr 0.9.1)
  por `herdr worktree remove --workspace` no passo 6a.

Run: python3 tests/test_maestro_prune.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "maestro" / "commands" / "run.md"
PRUNE = REPO / "maestro" / "bin" / "maestro-prune"

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def flat(txt):
    return " ".join(txt.split())


def sh(argv, env=None, cwd=None):
    return subprocess.run([str(x) for x in argv], capture_output=True,
                          text=True, env=env, cwd=cwd)


FAKE_HERDR = """\
#!/usr/bin/env python3
import json, os, sys

LOG = os.environ["FAKE_HERDR_LOG"]
MAP = os.environ["FAKE_HERDR_MAP"]  # json: {realpath: workspace_id}
DIRTY = set(os.environ.get("FAKE_HERDR_DIRTY", "").split(os.pathsep)) - {""}
NOOP = set(os.environ.get("FAKE_HERDR_NOOP", "").split(os.pathsep)) - {""}

with open(LOG, "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")

argv = sys.argv[1:]

if argv[:2] == ["worktree", "list"]:
    # Como o herdr 0.9.1 real: sem `--cwd`, lista o repo do Space EM FOCO e
    # ignora o diretório corrente do processo (medido ao vivo em 2026-09-26 —
    # o prune rodado de dentro do repo recebeu a lista do clone do cepa, que
    # estava em foco, e caiu no git puro deixando o Space para trás).
    if "--cwd" not in argv:
        print(json.dumps({"result": {"type": "worktree_list",
                                     "source": {"repo_root": "/outro/repo/em/foco"},
                                     "worktrees": [{"branch": "main",
                                                    "path": "/outro/repo/em/foco",
                                                    "open_workspace_id": "wFOCO"}]}}))
        sys.exit(0)
    mapping = json.loads(open(MAP).read())
    cwd = os.path.realpath(argv[argv.index("--cwd") + 1])
    wts = []
    for path, wsid in mapping.items():
        entry = {"branch": "session/x", "path": path, "is_linked_worktree": True}
        if wsid:
            entry["open_workspace_id"] = wsid
        wts.append(entry)
    print(json.dumps({"result": {"type": "worktree_list",
                                 "source": {"repo_root": cwd},
                                 "worktrees": wts}}))
    sys.exit(0)

if argv[:2] == ["worktree", "remove"]:
    if "--force" in argv:
        print(json.dumps({"error": {"code": "unexpected_force",
                                    "message": "maestro-prune nunca deve pedir --force"}}))
        sys.exit(1)
    wsid = argv[argv.index("--workspace") + 1]
    mapping = json.loads(open(MAP).read())
    path = next((p for p, w in mapping.items() if w == wsid), None)
    if path is None:
        print(json.dumps({"error": {"code": "unknown_workspace", "message": wsid}}))
        sys.exit(1)
    if path in DIRTY:
        print(json.dumps({"error": {"code": "dirty_worktree_requires_force",
                                    "message": f"{path} tem alteracoes nao commitadas"}}))
        sys.exit(1)
    if path in NOOP:
        # Reporta sucesso mas NAO remove de fato -- e a conferencia pelo
        # git que tem de pegar isto.
        print(json.dumps({"result": {"forced": False, "path": path,
                                     "type": "worktree_removed",
                                     "workspace_id": wsid}}))
        sys.exit(0)
    r = os.system(f"git -C {json.dumps(os.environ['FAKE_HERDR_REPO'])} "
                  f"worktree remove {json.dumps(path)}")
    if r != 0:
        print(json.dumps({"error": {"code": "git_remove_failed", "message": "git falhou"}}))
        sys.exit(1)
    print(json.dumps({"result": {"forced": False, "path": path,
                                 "type": "worktree_removed", "workspace_id": wsid}}))
    sys.exit(0)

print(json.dumps({"error": {"code": "unhandled", "message": " ".join(argv)}}))
sys.exit(2)
"""


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _setup_repo(tmp):
    repo = Path(tmp) / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _add_worktree(repo, branch, subdir):
    wt = Path(repo).parent / subdir
    r = _git(repo, "worktree", "add", "-b", branch, str(wt))
    assert r.returncode == 0, r.stderr
    return wt


def _wave_state(pd, slices, landed_legacy=None):
    import yaml
    ws = {
        "program": "t", "wave": 1, "landed": landed_legacy or [],
        "slices": slices,
    }
    Path(pd).mkdir(parents=True, exist_ok=True)
    (Path(pd) / "wave-state.yaml").write_text(
        yaml.safe_dump(ws, allow_unicode=True, sort_keys=False))


def _fake_herdr_env(tmp, mapping, dirty=None, noop=None, repo=None):
    fake = Path(tmp) / "fake-herdr"
    fake.write_text(FAKE_HERDR)
    fake.chmod(0o755)
    mapfile = Path(tmp) / "map.json"
    mapfile.write_text(json.dumps(mapping))
    logfile = Path(tmp) / "herdr.log"
    logfile.write_text("")
    env = dict(os.environ)
    env["MAESTRO_HERDR"] = str(fake)
    env["FAKE_HERDR_MAP"] = str(mapfile)
    env["FAKE_HERDR_LOG"] = str(logfile)
    env["FAKE_HERDR_REPO"] = str(repo)
    if dirty:
        env["FAKE_HERDR_DIRTY"] = os.pathsep.join(dirty)
    if noop:
        env["FAKE_HERDR_NOOP"] = os.pathsep.join(noop)
    return env, logfile


def test_landed_com_space_remove_via_workspace(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s1", "wt-s1")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S1": {"status": "LANDED", "worktree": str(wt)}})
    mapping = {os.path.realpath(wt): "w2A"}
    env, logfile = _fake_herdr_env(tmp, mapping, repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    check("prune (LANDED com Space) roda com exit 0", r.returncode == 0, r.stderr + r.stdout)
    out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("S1 aparece em removed", any(x["slice"] == "S1" for x in out.get("removed", [])), out)
    check("worktree sumiu do `git worktree list`",
          os.path.realpath(wt) not in git_paths(repo), git_paths(repo))
    calls = [json.loads(l) for l in logfile.read_text().splitlines() if l.strip()]
    remove_calls = [c for c in calls if c[:2] == ["worktree", "remove"]]
    check("removeu chamando `--workspace w2A`",
          any("--workspace" in c and "w2A" in c for c in remove_calls), remove_calls)
    check("nunca passou --force em nenhuma chamada ao herdr",
          all("--force" not in c for c in calls), calls)


def git_paths(repo):
    r = _git(repo, "worktree", "list", "--porcelain")
    return {os.path.realpath(l[len("worktree "):])
            for l in r.stdout.splitlines() if l.startswith("worktree ")}


def test_done_e_fail_sao_mantidas(tmp):
    repo = _setup_repo(tmp)
    wt_done = _add_worktree(repo, "session/s2", "wt-s2")
    wt_fail = _add_worktree(repo, "session/s3", "wt-s3")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {
        "S2": {"status": "DONE", "worktree": str(wt_done)},
        "S3": {"status": "FAIL", "worktree": str(wt_fail)},
    })
    mapping = {os.path.realpath(wt_done): "w1", os.path.realpath(wt_fail): "w2"}
    env, logfile = _fake_herdr_env(tmp, mapping, repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    check("prune com só DONE/FAIL roda exit 0 (nada para remover != falha)",
          r.returncode == 0, r.stderr + r.stdout)
    out = json.loads(r.stdout)
    kept_slices = {k["slice"]: k["status"] for k in out["kept"]}
    check("S2 (DONE, não aterrissada) fica em kept com status DONE",
          kept_slices.get("S2") == "DONE", kept_slices)
    check("S3 (FAIL) fica em kept com status FAIL",
          kept_slices.get("S3") == "FAIL", kept_slices)
    check("nenhuma chamada de `worktree remove` foi feita",
          not any(json.loads(l)[:2] == ["worktree", "remove"]
                  for l in logfile.read_text().splitlines() if l.strip()))
    check("worktree de S2 continua no git", os.path.realpath(wt_done) in git_paths(repo))
    check("worktree de S3 continua no git", os.path.realpath(wt_fail) in git_paths(repo))


def test_landed_formato_antigo(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s4", "wt-s4")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S4": {"status": "DONE", "worktree": str(wt)}},
                landed_legacy=["S4"])
    mapping = {os.path.realpath(wt): "w9"}
    env, _ = _fake_herdr_env(tmp, mapping, repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    out = json.loads(r.stdout)
    check("slice DONE listada no `landed:` legado é tratada como aterrissada",
          any(x["slice"] == "S4" for x in out["removed"]), out)
    check("worktree do formato antigo saiu do git", os.path.realpath(wt) not in git_paths(repo))


def test_landed_sem_space_cai_para_git(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s5", "wt-s5")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S5": {"status": "LANDED", "worktree": str(wt)}})
    mapping = {os.path.realpath(wt): None}  # sem Space aberto
    env, logfile = _fake_herdr_env(tmp, mapping, repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    check("LANDED sem Space aberto ainda remove (fallback git)", r.returncode == 0, r.stdout + r.stderr)
    out = json.loads(r.stdout)
    check("S5 aparece em removed via fallback git",
          any(x["slice"] == "S5" and "git" in x["via"] for x in out["removed"]), out)
    check("worktree sumiu do git", os.path.realpath(wt) not in git_paths(repo))
    check("nenhuma chamada `worktree remove` foi feita ao herdr (não havia Space)",
          not any(json.loads(l)[:2] == ["worktree", "remove"]
                  for l in logfile.read_text().splitlines() if l.strip()))


def test_landed_suja_falha_sem_forcar(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s6", "wt-s6")
    (wt / "untracked.txt").write_text("oops")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S6": {"status": "LANDED", "worktree": str(wt)}})
    mapping = {os.path.realpath(wt): "w7"}
    env, logfile = _fake_herdr_env(tmp, mapping, dirty=[os.path.realpath(wt)], repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    check("worktree LANDED suja: exit 1", r.returncode == 1, r.stdout + r.stderr)
    out = json.loads(r.stdout)
    check("S6 aparece em failed", any(f["slice"] == "S6" for f in out["failed"]), out)
    check("worktree suja continua no git (não forçou)",
          os.path.realpath(wt) in git_paths(repo))
    calls = [json.loads(l) for l in logfile.read_text().splitlines() if l.strip()]
    check("nunca passou --force tentando resolver a sujeira",
          all("--force" not in c for c in calls), calls)


def test_herdr_reporta_sucesso_sem_remover(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s7", "wt-s7")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S7": {"status": "LANDED", "worktree": str(wt)}})
    mapping = {os.path.realpath(wt): "w8"}
    env, _ = _fake_herdr_env(tmp, mapping, noop=[os.path.realpath(wt)], repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--json"], env=env)
    check("herdr mentiroso (sucesso sem remover) é pego pela conferência do git: exit 1",
          r.returncode == 1, r.stdout + r.stderr)
    out = json.loads(r.stdout)
    check("S7 vira failed, não removed", any(f["slice"] == "S7" for f in out["failed"]), out)
    check("worktree ainda está lá de fato", os.path.realpath(wt) in git_paths(repo))


def test_dry_run_nao_remove(tmp):
    repo = _setup_repo(tmp)
    wt = _add_worktree(repo, "session/s8", "wt-s8")
    pd = Path(tmp) / "prog"
    _wave_state(pd, {"S8": {"status": "LANDED", "worktree": str(wt)}})
    mapping = {os.path.realpath(wt): "w3"}
    env, logfile = _fake_herdr_env(tmp, mapping, repo=repo)

    r = sh([sys.executable, PRUNE, pd, "--repo", repo, "--dry-run", "--json"], env=env)
    check("--dry-run roda exit 0", r.returncode == 0, r.stdout + r.stderr)
    out = json.loads(r.stdout)
    check("--dry-run reporta S8 em removed (marcado dry-run)",
          any(x["slice"] == "S8" for x in out["removed"]), out)
    check("worktree continua no git depois de --dry-run",
          os.path.realpath(wt) in git_paths(repo))
    check("nenhuma chamada `worktree remove` foi feita ao herdr em --dry-run",
          not any(json.loads(l)[:2] == ["worktree", "remove"]
                  for l in logfile.read_text().splitlines() if l.strip()))


def test_run_md_cita_prune_e_troca_receita_fantasma():
    run = RUN.read_text(encoding="utf-8")
    fr = flat(run)
    check("passo 9 nomeia `maestro-prune`", "maestro-prune" in fr)
    check("passo 6a não tem mais a forma posicional inválida "
          "`herdr worktree remove <path>`",
          "herdr worktree remove <path>" not in fr)
    check("passo 6a usa `herdr worktree remove --workspace`",
          "herdr worktree remove --workspace" in fr)
    check("passo 2 (gc) lista as worktrees com `--cwd`, não pelo Space em foco",
          "herdr worktree list --cwd <raiz-principal> --json" in fr)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_landed_com_space_remove_via_workspace(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_done_e_fail_sao_mantidas(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_landed_formato_antigo(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_landed_sem_space_cai_para_git(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_landed_suja_falha_sem_forcar(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_herdr_reporta_sucesso_sem_remover(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_dry_run_nao_remove(tmp)
    test_run_md_cita_prune_e_troca_receita_fantasma()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
