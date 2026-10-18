"""Synthetic-only, non-writing adapter fixtures; run with -B and bytecode env."""
import builtins
import copy
import hashlib
import hmac
import json as json_mod
import os
import sys
from pathlib import Path

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 required")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.g9 import stage2_commitment_adapter as adapter
from research.g9 import stage2_sampled_verification as sampled


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(sampled.canonical(value)).hexdigest()


def independent_digest(value):
    """sha256 over the same canonical JSON bytes, WITHOUT `sampled.canonical`.

    `sampled.canonical` refuses a structure nested past MAX_CANONICAL_DEPTH, so
    `digest()` cannot produce the expected hash for exactly the descriptors the
    depth fixtures need a correct hash for.  This reproduces the encoding
    directly (sorted keys, no whitespace, ASCII-only) so the fixture can pin the
    CORRECT descriptor hash and make depth the only remaining reason to refuse.
    """
    encoded = json_mod.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def inputs():
    roster = [{"synthetic_slot": i} for i in range(3)]
    descriptor = {"campaign": "fixture-only", "coordinate_order": "slot-ascending"}
    schema = {"energy": "binary64", "count": "int", "valid": "bool", "label": "str"}
    return dict(expected_coordinates=roster,
                expected_coordinate_root=sampled.coordinate_root(roster).hex(),
                descriptor=descriptor, expected_descriptor_sha256=digest(descriptor),
                result_schema=schema, expected_schema_sha256=digest(schema),
                producer_records=[{"coordinates": c, "result": {
                    "energy": -0.0 if i == 0 else float(i), "count": i,
                    "valid": True, "label": "synthetic"}}
                    for i, c in enumerate(roster)])


def main():
    source = inputs()
    output = adapter.build_campaign_commitment(**source)
    require(output == adapter.build_campaign_commitment(**inputs()), "nondeterministic binding")
    positive = inputs()
    positive["producer_records"][0]["result"]["energy"] = 0.0
    require(adapter.build_campaign_commitment(**positive).get("campaign_binding_digest", adapter.build_campaign_commitment(**positive).get("binding_sha256")) !=
            output.get("campaign_binding_digest", output.get("binding_sha256")), "signed zero lost")
    require(sampled.leaf_hash(source["expected_coordinates"][0], {
        "energy": sampled.encode_float(-0.0), "count": 0, "valid": True,
        "label": "synthetic"}).hex() == output["commitment"]["leaf_hashes"][0],
        "result encoding drift")
    source["expected_coordinates"][0]["synthetic_slot"] = 99
    require(output["commitment"]["coordinates"][0]["synthetic_slot"] == 0,
            "output retained caller-owned roster")
    mutations = [
        lambda x: x["producer_records"].pop(),
        lambda x: x["producer_records"].append(copy.deepcopy(x["producer_records"][0])),
        lambda x: x["producer_records"].reverse(),
        lambda x: x["producer_records"].__setitem__(1, copy.deepcopy(x["producer_records"][0])),
        lambda x: x["expected_coordinates"].__setitem__(1, x["expected_coordinates"][0]),
        lambda x: x.__setitem__("expected_coordinate_root", "0" * 64),
        lambda x: x["descriptor"].__setitem__("campaign", "changed"),
        lambda x: x.__setitem__("expected_schema_sha256", "0" * 64),
        lambda x: x["producer_records"][0]["result"].pop("count"),
        lambda x: x["producer_records"][0]["result"].__setitem__("extra", 1),
        lambda x: x["producer_records"][0]["result"].__setitem__("count", True),
        lambda x: x["producer_records"][0]["result"].__setitem__("energy", 0),
        lambda x: x["producer_records"][0]["result"].__setitem__("energy", float("nan")),
        lambda x: x["producer_records"][0]["result"].__setitem__("energy", float("inf")),
        lambda x: x["producer_records"][0].__setitem__("coordinates", {"synthetic_slot": 0.0}),
    ]
    for index, mutate in enumerate(mutations):
        value = inputs()
        mutate(value)
        try:
            adapter.build_campaign_commitment(**value)
        except adapter.CommitmentAdapterError:
            continue
        raise RuntimeError(f"mutation {index} accepted")
    # Builder must not run on even one invalid producer record.
    original = sampled.build_commitment
    called = []
    def sentinel(*args):
        called.append(True)
        raise RuntimeError("builder reached invalid input")
    sampled.build_commitment = sentinel
    try:
        invalid = inputs()
        invalid["producer_records"][-1]["result"]["count"] = False
        try:
            adapter.build_campaign_commitment(**invalid)
        except adapter.CommitmentAdapterError:
            pass
        require(not called, "builder called before complete validation")
    finally:
        sampled.build_commitment = original
    # Review regression: coordinate_root raising inside `sampled` must surface
    # as CommitmentAdapterError, never as a raw VerificationError.
    prepared = inputs()   # built BEFORE patching: inputs() itself calls coordinate_root
    original_root = sampled.coordinate_root
    def oversized(*args):
        raise sampled.VerificationError("encoded coordinate too large")
    sampled.coordinate_root = oversized
    try:
        try:
            adapter.build_campaign_commitment(**prepared)
        except adapter.CommitmentAdapterError:
            pass
        except sampled.VerificationError as exc:
            raise RuntimeError(f"untyped VerificationError escaped the adapter: {exc}")
        else:
            raise RuntimeError("oversized coordinate accepted")
    finally:
        sampled.coordinate_root = original_root

    # NEW FIXTURES
    val = inputs()
    out = adapter.build_campaign_commitment(**val)
    require("campaign_binding_digest" in out, "D1: no clearly named binding digest published")

    # D2: the verifier is exercised BEHAVIOURALLY only.  A `hasattr` existence
    # check proves nothing -- a no-op body, or a function that returns instead
    # of raising, would satisfy it -- so it is deliberately absent here and the
    # honest-pass below plus the eleven tampered-argument refusals below are the
    # only things that make this function load-bearing.
    verify_args = dict(
        binding_digest=out["campaign_binding_digest"],
        merkle_root=out["commitment"]["merkle_root"],
        grid_point_count=len(val["expected_coordinates"]),
        expected_descriptor_sha256=val["expected_descriptor_sha256"],
        expected_schema_sha256=val["expected_schema_sha256"],
        expected_coordinate_root=val["expected_coordinate_root"],
    )
    # Honest verification must pass
    adapter.verify_campaign_commitment(**verify_args)

    # Test failure modes of verify
    verify_mutations = [
        ("binding_digest", "0" * 64),
        ("binding_digest", "é" * 64),
        ("merkle_root", "é" * 64),
        ("expected_descriptor_sha256", "é" * 64),
        ("expected_schema_sha256", "é" * 64),
        ("expected_coordinate_root", "é" * 64),
        ("merkle_root", "0" * 64),
        ("grid_point_count", 999),
        ("expected_descriptor_sha256", "0" * 64),
        ("expected_schema_sha256", "0" * 64),
        ("expected_coordinate_root", "0" * 64),
    ]
    for k, v in verify_mutations:
        margs = dict(verify_args)
        margs[k] = v
        try:
            adapter.verify_campaign_commitment(**margs)
            require(False, f"verify accepted tampered {k}")
        except adapter.CommitmentAdapterError:
            pass
        except TypeError as exc:
            # The non-ASCII "é" cases reach here if the `_sha` pre-validation
            # of the digests is removed: hmac.compare_digest rejects non-ASCII
            # str operands with an untyped TypeError.  That escape is a defect
            # here, so the fixture must report it as one, not as a pass.
            raise RuntimeError(
                f"verify raised an untyped TypeError on tampered {k}: {exc}")

    # D2-stub: a verifier whose body has been replaced by a no-op must be
    # KILLED by the refusal loop above.  Asserted here by mutation, not by
    # mocking: replacing the function here would only test this file's own
    # stub, which is the round-2 defect (a dead check nothing could fail).
    # Mutation: `def verify_campaign_commitment(*a, **k): return None` ->
    #   RuntimeError: verify accepted tampered binding_digest
    
    # D3: nesting depth, with the descriptor hash CORRECT.
    #
    # Round 2 rebuilt the descriptor but left `expected_descriptor_sha256`
    # pointing at the original two-key descriptor, so the build was refused by
    # the identity check long before any depth bound applied: the fixture proved
    # nothing about depth.  Pinning the hash to the deep descriptor makes depth
    # the only remaining reason to refuse.  The companion assertion below makes
    # that self-evident: with the depth bound removed from `sampled`, the SAME
    # deep descriptor (hash still correct) must be accepted, and this fixture
    # fails when it is.
    deep = {}
    current = deep
    for _ in range(200):
        current["a"] = {}
        current = current["a"]
    val = inputs()
    val["descriptor"] = deep
    val["expected_descriptor_sha256"] = independent_digest(deep)
    thrown = False
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError as exc:
        require("descriptor identity mismatch" not in str(exc),
                f"D3: refused on descriptor identity, not depth: {exc}")
        thrown = True
    require(thrown, "D3: should have rejected deeply nested")

    # Counterfactual: with the depth bound widened, the identical input (hash
    # still correct) must be accepted, proving depth is the only cause.
    original_depth = sampled.MAX_CANONICAL_DEPTH
    sampled.MAX_CANONICAL_DEPTH = 10 ** 9
    try:
        counterfactual = inputs()
        counterfactual["descriptor"] = deep
        counterfactual["expected_descriptor_sha256"] = independent_digest(deep)
        accepted = adapter.build_campaign_commitment(**counterfactual)
        require(accepted["descriptor"] == deep,
                "D3: unbounded-depth counterfactual did not reproduce the descriptor")
    finally:
        sampled.MAX_CANONICAL_DEPTH = original_depth

    # D4: TOCTOU
    val = inputs()
    orig_encode = sampled.encode_float
    def mock_encode(v):
        val["producer_records"][0]["result"]["label"] = "hacked"
        return orig_encode(v)
    sampled.encode_float = mock_encode
    try:
        out = adapter.build_campaign_commitment(**val)
        sampled.encode_float = orig_encode
        clean_out = adapter.build_campaign_commitment(**inputs())
        require(out["commitment"]["leaf_hashes"][0] == clean_out["commitment"]["leaf_hashes"][0], 
                "D4: TOCTOU record mutated during execution")
    finally:
        sampled.encode_float = orig_encode

    # D5: snapshotting without json.loads
    import json as json_mod
    original_loads = json_mod.loads
    called_loads = False
    def mock_loads(*args, **kwargs):
        nonlocal called_loads
        called_loads = True
        return original_loads(*args, **kwargs)
    json_mod.loads = mock_loads
    try:
        adapter.build_campaign_commitment(**inputs())
        require(not called_loads, "D5: json.loads used for snapshotting")
    finally:
        json_mod.loads = original_loads

    # D6: exact bounds testing
    val = inputs()
    val["producer_records"][0]["result"]["label"] = "a" * 4096
    adapter.build_campaign_commitment(**val) # Should accept exact bound
    val["producer_records"][0]["result"]["label"] = "a" * 4097
    try:
        adapter.build_campaign_commitment(**val)
        require(False, "D6: accepted >4096 str")
    except adapter.CommitmentAdapterError:
        pass
        
    val = inputs()
    # Create a descriptor slightly under 65536 bytes
    val["descriptor"]["padding"] = "a" * (65536 - 150)
    val["expected_descriptor_sha256"] = digest(val["descriptor"])
    adapter.build_campaign_commitment(**val) # Should accept
    val["descriptor"]["padding"] = "a" * 65536
    val["expected_descriptor_sha256"] = digest(val["descriptor"])
    try:
        adapter.build_campaign_commitment(**val)
        require(False, "D6: accepted >65536 descriptor")
    except adapter.CommitmentAdapterError:
        pass

    # D7: Error message canonical
    val = inputs()
    val["producer_records"][0]["coordinates"] = {"wrong": 1}
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError as e:
        require("canonical" in str(e), "D7: error message does not clarify canonical-equal")

    # D8: the deep freeze, pinned on a NESTED object.
    #
    # The round-1 check only mutated a TOP-LEVEL roster element
    # (`roster[0]["synthetic_slot"] = 99`), which a shallow `dict(...)`-style
    # snapshot of the outer container would survive; the mutation table showed a
    # `dict(descriptor)` mutant passing everything.  This mutates (a) a nested
    # value two levels down inside the caller's descriptor, and (b) a nested
    # value inside the caller's result dict, BOTH AFTER the call has returned.
    # A shallow copy shares the inner dicts, so either mutation would be visible
    # in the returned commitment.
    val = inputs()
    val["descriptor"] = {"meta": {"origin": {"stage": "synthetic-fixture"}}}
    val["expected_descriptor_sha256"] = digest(val["descriptor"])
    frozen = adapter.build_campaign_commitment(**val)
    nested_descriptor = val["descriptor"]["meta"]["origin"]
    nested_result = val["producer_records"][0]["result"]
    nested_descriptor["stage"] = "post-call-mutation"
    nested_result["label"] = "post-call-mutation"
    require(frozen["descriptor"] == {"meta": {"origin": {"stage": "synthetic-fixture"}}},
            "D8: returned descriptor shares a nested object with the caller")
    require(frozen["descriptor_sha256"] == val["expected_descriptor_sha256"],
            "D8: returned descriptor hash disagrees with the frozen descriptor")
    require(frozen["commitment"]["leaf_hashes"][0]
            == sampled.leaf_hash(val["expected_coordinates"][0], {
                "energy": sampled.encode_float(-0.0), "count": 0, "valid": True,
                "label": "synthetic"}).hex(),
            "D8: returned commitment shares a nested result object with the caller")

    # D9: an `int` result field that `json.dumps` refuses inside `sampled`
    # (more than 4300 decimal digits).  It passes every type check in the
    # adapter, so it reaches `sampled.build_commitment`; the call must come
    # back as CommitmentAdapterError, not as a raw VerificationError.
    val = inputs()
    val["producer_records"][0]["result"]["count"] = 10 ** 4300
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError:
        pass
    except sampled.VerificationError as exc:
        raise RuntimeError(f"D9: untyped VerificationError escaped: {exc}")
    else:
        raise RuntimeError("D9: unencodable oversized int was committed")
    # The mirror image: a large-but-encodable int must still be committed, so
    # D9 cannot be satisfied by refusing every large integer.
    val = inputs()
    val["producer_records"][0]["result"]["count"] = 10 ** 400
    require(adapter.build_campaign_commitment(**val)["campaign_binding_digest"],
            "D9: a 401-digit int was refused")

    # D10: `_bytes`'s second `except` clause, one fixture per member.
    #
    # `sampled.canonical` already converts TypeError and ValueError into
    # VerificationError, so with an honest `sampled` only a defect in `sampled`
    # reaches this clause.  The fixtures therefore inject one at a time and
    # require the adapter to re-type it.  Mutations that delete any one of the
    # four names are killed by the corresponding line; the clause is kept
    # because dropping it would re-open the D9 untyped escape.
    for exc_name in ("TypeError", "ValueError", "OverflowError", "RecursionError"):
        # Built BEFORE patching: inputs() itself calls sampled.coordinate_root,
        # which calls sampled.canonical, and must not be the thing that trips.
        prepared = inputs()
        original_canonical = sampled.canonical
        exc_class = getattr(builtins, exc_name)
        def injected(value, _cls=exc_class):
            raise _cls(f"injected {exc_name} from sampled.canonical")
        sampled.canonical = injected
        try:
            try:
                adapter.build_campaign_commitment(**prepared)
            except adapter.CommitmentAdapterError as exc:
                require("unencodable input" in str(exc),
                        f"D10: {exc_name} was re-typed but not labelled: {exc}")
            except BaseException as exc:
                raise RuntimeError(f"D10: untyped {exc_name} escaped _bytes: {exc!r}")
            else:
                raise RuntimeError(f"D10: injected {exc_name} was swallowed")
        finally:
            sampled.canonical = original_canonical

    # D11: the natural boundary case for RecursionError.  The `sampled` depth
    # bound is what stops a producer-supplied container from recursing off the
    # interpreter stack, and the adapter must surface that refusal as its own
    # error.  It is reached through the COPY path first (a list nested past
    # `MAX_CANONICAL_DEPTH` is refused by depth, and a list nested past
    # `sys.getrecursionlimit()` frames would be refused by RecursionError), so
    # the fixture asserts only the property it can actually prove: the adapter
    # never lets a raw RecursionError out, whatever the depth.
    val = inputs()
    cursor = val["descriptor"].setdefault("chain", [])
    for _ in range(sampled.MAX_CANONICAL_DEPTH + 8):
        nested_list = []
        cursor.append(nested_list)
        cursor = nested_list
    val["expected_descriptor_sha256"] = independent_digest(val["descriptor"])
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError:
        pass
    except RecursionError as exc:
        raise RuntimeError(f"D11: RecursionError escaped: {exc}")
    else:
        raise RuntimeError("D11: over-deep list descriptor was committed")

    # D12: the snapshot must be re-typed, not merely attempted.  A
    # producer-supplied object whose `__deepcopy__` raises makes the snapshot
    # itself fail, before any `sampled` call; under a bare `except Exception:
    # pass` that RuntimeError would escape the module's typed contract.  The
    # value is nested inside the descriptor, so the snapshot really is the
    # thing that trips -- the descriptor is copied before it is ever encoded.
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("producer object refuses to be snapshotted")
    val = inputs()
    val["descriptor"] = {"untrusted_payload": Uncopyable()}
    val["expected_descriptor_sha256"] = "0" * 64
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError as exc:
        require("snapshot failed" in str(exc),
                f"D12: snapshot failure was re-typed but not labelled: {exc}")
    except RuntimeError as exc:
        raise RuntimeError(f"D12: untyped RuntimeError escaped the snapshot: {exc}")
    else:
        raise RuntimeError("D12: uncopyable descriptor was accepted")

    # D13: the roster's own distinctness, checked by the ADAPTER.  Two
    # identical coordinates both reach the commitment, where `sampled` refuses
    # them itself; what the adapter's check adds is that the refusal is typed
    # and happens before the builder is called at all.  Detected by replacing
    # `sampled.build_commitment` with a sentinel: a non-no-op distinctness
    # check must not have reached it.
    val = inputs()
    val["expected_coordinates"][1] = val["expected_coordinates"][0]
    val["expected_coordinate_root"] = sampled.coordinate_root(
        val["expected_coordinates"]).hex()
    val["producer_records"][1]["coordinates"] = val["expected_coordinates"][0]
    original_builder = sampled.build_commitment
    sentinel_reached = []
    def builder_sentinel(*args):
        sentinel_reached.append(True)
        raise RuntimeError("D13: builder reached a duplicate-coordinate roster")
    sampled.build_commitment = builder_sentinel
    try:
        try:
            adapter.build_campaign_commitment(**val)
        except adapter.CommitmentAdapterError as exc:
            require("duplicate coordinate" in str(exc),
                    f"D13: duplicate roster refused, but not by the distinctness check: {exc}")
        else:
            raise RuntimeError("D13: duplicate coordinates accepted")
        require(not sentinel_reached, "D13: builder ran on a duplicate roster")
    finally:
        sampled.build_commitment = original_builder

    # D14: `grid_point_count` is a field of the binding payload, so a verifier
    # that omitted it would re-derive a DIFFERENT digest.  The mutation that
    # removes the field from both sides is killed by the honest-verify call
    # above, so a digest swap cannot detect it here.  What this pins is the
    # property the omission would break: no legitimate binding digest can equal
    # the digest of a payload that has no count in it, so a verifier rebuilt
    # without the field is arithmetically forced to reject.  A guard-only check
    # here would be dead -- `_sha` already turns bool/0/-1 into typed refusals
    # that are the same refusals the digest comparison yields.
    reduced_payload = {
        "domain": adapter.SCHEMA + "/binding",
        "merkle_root": verify_args["merkle_root"],
        "coordinate_root": verify_args["expected_coordinate_root"],
        "descriptor_sha256": verify_args["expected_descriptor_sha256"],
        "schema_sha256": verify_args["expected_schema_sha256"],
        "schema_version": adapter.SCHEMA,
    }
    reduced_digest = hashlib.sha256(
        json_mod.dumps(reduced_payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode("ascii")).hexdigest()
    require(not hmac.compare_digest(verify_args["binding_digest"], reduced_digest),
            "D14: the binding digest does not actually bind grid_point_count")
    require(adapter.SCHEMA in reduced_payload["domain"],
            "D14: the binding payload is not domain-separated")

    # D15: a producer record is a CLOSED schema.  An extra field is not
    # cosmetic: the record would be accepted and the extra field silently
    # ignored, so a producer could ship a record carrying an unbound claim
    # alongside a commitment that never saw it.  Removing the field-set check
    # lets exactly that through.
    val = inputs()
    val["producer_records"][0]["producer_signature"] = "unbound-claim"
    try:
        adapter.build_campaign_commitment(**val)
    except adapter.CommitmentAdapterError as exc:
        require("wrong fields" in str(exc),
                f"D15: extra record field refused, but not by the field check: {exc}")
    else:
        raise RuntimeError("D15: producer record carried an extra, unbound field")

    print("PASS synthetic commitment adapter; 39 adversarial refusals; no writes")

if __name__ == "__main__":
    main()
