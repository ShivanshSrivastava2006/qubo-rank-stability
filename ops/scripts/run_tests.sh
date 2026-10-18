#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1
run_cmd() {
    echo "Running: $1"
    eval "$1"
    echo "Exit code: $?"
    echo "----------------------------------------"
}

run_cmd "python3 research/g5/verify_domain_cache.py"
run_cmd "python3 -O research/g5/verify_domain_cache.py"
run_cmd "python3 research/g5/verify_runner.py"
run_cmd "python3 -O research/g5/verify_runner.py"
run_cmd "python3 research/g5/test_machinery.py"
run_cmd "python3 -O research/g5/test_machinery.py"
run_cmd "python3 research/g5/verify_python_repair.py"
run_cmd "python3 -O research/g5/verify_python_repair.py"
run_cmd "python3 research/g5/verify_worker.py"
run_cmd "python3 -O research/g5/verify_worker.py"
run_cmd "python3 05_certification/g5/review_g5_domain_cache_corrective.py"
run_cmd "python3 -O 05_certification/g5/review_g5_domain_cache_corrective.py"
run_cmd "python3 05_certification/g5/review_g5_amortisation_v2.py src.g5.runner:run_amortisation_contract"
run_cmd "python3 -O 05_certification/g5/review_g5_amortisation_v2.py src.g5.runner:run_amortisation_contract"
