#!/usr/bin/env bash
# Ephemeral GitHub-hosted runner only. Never use this initializer on a workstation.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]
[[ ! -e .env && ! -e .tools/service-keys ]]
export COMPOSE_PARALLEL_LIMIT=1 F22_SUBNET_PREFIX=10.245.34
export F22_MANAGER_DIR=./.tools/f22/opspilot-full-test-f22-ci/manager
project=opspilot-full-test-f22-ci
export F22_PROJECT=$project
report=docs/full/evidence/f22/ci
mkdir -p "$report"
pwsh -NoProfile -File scripts/new-full-env.ps1
uv sync --frozen --python 3.12
python=.venv/bin/python
"$python" -m ruff check src/opspilot/evals/full.py src/opspilot/evals/token_guard.py tests/f22_lab.py tests/unit/test_full_eval.py tests/unit/test_eval_token_guard.py
"$python" -m mypy src/opspilot/evals/full.py src/opspilot/evals/token_guard.py --follow-imports=silent
"$python" -m opspilot.cli.service_keys .tools/service-keys
"$python" scripts/setup-full-f15-cache.py --test
"$python" scripts/setup-full-f16-observability.py --test
docker build --target runtime -t opspilot-full/app:f19 .
docker build --target tests -t opspilot-full/tests:f19 .
docker build --target postgres -f infra/full/Dockerfile -t opspilot-full/postgres:f01 infra/full
docker build --target redis -f infra/full/Dockerfile -t opspilot-full/redis:f15 infra/full
pwsh -NoProfile -File scripts/build-full-f17-manager.ps1
c=(docker compose --env-file .env -p "$project" -f compose.full.yaml -f compose.full.test.yaml
   -f compose.full.f13-checks.yaml -f compose.full.f16-checks.yaml
   -f compose.full.f17-checks.yaml -f compose.full.f22-checks.yaml)
stop_lab() {
  "${c[@]}" stop || true
  if [[ -e "$F22_MANAGER_DIR/compose.json" ]]; then
    docker compose -f "$F22_MANAGER_DIR/compose.json" stop || true
  fi
}
trap stop_lab EXIT
"${c[@]}" up -d --wait --no-build postgres redis
"$python" scripts/setup-full-f22-manager.py --project "$project"
# The containers run as UID10001; keys stay private to that identity.
sudo chown -R 10001:10001 .tools/observability-test .tools/service-keys/private
chmod a+rwx docs/full/evidence/f22 "$report"
"${c[@]}" run --rm --no-deps admin
"${c[@]}" run --rm --no-deps admin python -m opspilot.cli.seed
"${c[@]}" run --rm --no-deps admin python -m opspilot.cli.bootstrap_identity
"${c[@]}" run --rm --no-deps telemetry-init
"${c[@]}" up -d --wait --no-build collector mcp
"${c[@]}" run --rm --no-deps tests python -m pytest -p no:cacheprovider -q \
  tests/unit/test_full_eval.py tests/unit/test_eval_safety.py tests/unit/test_eval_token_guard.py \
  --junitxml=/reports/ci/unit.xml
"${c[@]}" run --rm --no-deps -e F22_COMMIT="$GITHUB_SHA" -e F22_REPORT_DIR=/reports/ci \
  tests python -m tests.f22_lab
"${c[@]}" run --rm --no-deps tests python -m opspilot.evals.runner --mode scripted \
  --commit "$GITHUB_SHA" --dirty --output /reports/ci/mvp-regression
"$python" scripts/scan-full-f22-secrets.py
cp docs/full/evidence/f22/secret-scan.json "$report/secret-scan.json"
# Fresh scans use exported images; no Docker socket enters the scanner container.
mkdir -p .tools/f22-ci-images "$report/security"
chmod a+rwx "$report/security"
scanner=aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c
for pair in app:f19 manager:f17 postgres:f01 redis:f15; do
  name=${pair%:*}
  docker save "opspilot-full/$pair" -o ".tools/f22-ci-images/$name.tar"
  docker run --rm --memory 768m -v "$PWD/.tools/f22-ci-images:/images:ro" \
    -v "$PWD/$report/security:/reports" "$scanner" --quiet image \
    --db-repository public.ecr.aws/aquasecurity/trivy-db:2 --timeout 20m \
    --input "/images/$name.tar" --scanners vuln --format json --output "/reports/$name.json"
done
"${c[@]}" run --rm --no-deps --user root tests uv tool run pip-audit==2.10.1 \
  --path /app/.venv/lib/python3.12/site-packages --format json --output /reports/ci/security/python.json
"$python" - <<'PY'
import json
from pathlib import Path
root = Path('docs/full/evidence/f22/ci/security')
blocking = []
for path in root.glob('*.json'):
    if path.name == 'python.json':
        continue
    data = json.loads(path.read_text())
    blocking.extend((path.name, v['VulnerabilityID']) for r in data.get('Results', [])
                    for v in r.get('Vulnerabilities', []) if v['Severity'] in {'HIGH', 'CRITICAL'})
(root / 'gate.json').write_text(json.dumps(dict(passed=not blocking, blocking=blocking), indent=2))
raise SystemExit(bool(blocking))
PY
# Real/human/live gates remain separate. Known manager HIGH must fail this job.
