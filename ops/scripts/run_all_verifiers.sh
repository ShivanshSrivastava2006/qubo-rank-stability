set -e
echo "verify_g4_conformance.py"
PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_g4_conformance.py
echo "verify_g4_conformance.py -O"
PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_g4_conformance.py
echo "verify_m5_conformance.py"
PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_m5_conformance.py
echo "verify_m5_conformance.py -O"
PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_m5_conformance.py
echo "13 frozen verifiers + others"
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_gate1_math.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_g2_canonical.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_g2_d005.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_amendment_001.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_gate0_review_findings.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_gate0_facts.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_u15.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_u16.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_u17.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_u18a.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/check_retractions.py --self-test
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/check_retractions.py
PYTHONDONTWRITEBYTECODE=1 python3 02_data/canonical/audit_g2_batch3_delta.py
PYTHONDONTWRITEBYTECODE=1 python3 research/audit/validate_adnye_output.py --root 03_ground_truth/adnye
(cd 02_data/canonical && sed "s|\.\./audit/|../../08_audit/audit/|" DIGESTS.txt | sha256sum -c)
(cd research/ground_truth && sha256sum -c DIGESTS.txt)
echo "ALL SEQUENTIAL DONE"
