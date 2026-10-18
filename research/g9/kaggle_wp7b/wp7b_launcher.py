#!/usr/bin/env python3
"""Armed WP7b adapter entry point. Intended to be embedded by the offline builder."""
from __future__ import annotations
import copy, hashlib, json, os, platform, shutil, subprocess, sys, tempfile, time, struct
from pathlib import Path

ANCHOR = "f2c0be0ee2a33dad44f3f02d4b29222647a1554177e0c3c87f83cf2f660f7c49"
BUDGET_SECONDS = 10 * 60 * 60
FLAGS = ["-std=c++17", "-O0", "--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true", "-Xcompiler", "-O0,-ffp-contract=off,-fno-fast-math,-fPIC"]
POST_RUN_ONLY_IMAGE_FIELDS = ("kaggle_image", "image_manifest_sha256", "image_config_id", "image_name")

def sha(b): return hashlib.sha256(b).hexdigest()
def canonical(x): return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
def result(counters=None, identities=None, digests=None, status="ok", output=None):
    return {"counters": counters or {}, "identities": identities or {}, "digests": digests or {}, "status": status, "output": output if output is not None else {"status": status}}
def guard(clock, last):
    if clock() - START > BUDGET_SECONDS:
        raise RuntimeError("incomplete_budget:last_completed=" + last)

def incomplete_budget_receipt(last_completed, elapsed_seconds):
    return {"status": "incomplete_budget", "scientific_outputs": [],
            "last_completed_step": str(last_completed),
            "elapsed_seconds": max(0.0, float(elapsed_seconds)),
            "counters": {}, "identities": {}, "digests": {}}

def budget_receipt_for_error(error, elapsed_seconds):
    message = str(error)
    if "incomplete_budget" not in message:
        return None
    last = message.split("last_completed=", 1)[1] if "last_completed=" in message else "unknown"
    return incomplete_budget_receipt(last, elapsed_seconds)

def budgeted_reference(reference, clock, last_completed):
    def checked(*args, **kwargs):
        guard(clock, last_completed())
        # The opened seal is indexed by a coordinate mapping and encoding. WP3
        # supplies a frozen harness row, D015 pair and encoding; encode the row
        # into the seal's canonical coordinate schema and project its word and
        # reconstruction fields to the harness contract without evaluating it.
        if len(args) == 3 and isinstance(args[0], dict) and "coordinate" in args[0]:
            row, pair, encoding = args
            coordinate = {"family": str(row["family"]),
                "point": [int(axis) for axis in row["coordinate"]],
                "r_hex": float(row["r"]).hex(), "comparator": str(row["comparator"]),
                "grid": str(row["grid"]),
                "inactive_positive_zero": "yes" if row["inactive_positive_zero"] else "no",
                "c_h": int(pair[0]), "c_f": int(pair[1])}
            if "scale" in row: coordinate["scale"] = str(row["scale"])
            if "condition" in row: coordinate["condition"] = str(row["condition"])
            sealed = reference(coordinate, encoding)
            import struct
            projection = sealed["d015_d016_reconstruction"]
            projected = {key: projection[key] for key in
                         ("c_h", "c_f", "set_label", "tie_count", "x_e_size")}
            return {"energy_minimum_words": [struct.unpack(">d", bytes.fromhex(word))[0]
                                               for word in sealed["energy_minimum_words"]],
                    "canonical_minimum_index": sealed["canonical_minimum_index"],
                    "tie_flags": sealed["tie_flags"],
                    "reconstruction": json.dumps(projected, sort_keys=True,
                                                  separators=(",", ":"))}
        return reference(*args, **kwargs)
    return checked

def _wp3_host_worker(config):
    """Run the real full WP3 harness in an isolated host-emulation process."""
    global START
    from research.g9 import stage2_reference_seal as seal_api
    from research.g9 import stage2_section_b2_harness as harness
    from research.g9 import stage2_production_identity as identity_api
    root=Path.cwd()
    seal_inputs=config["seal_inputs"]
    sealed=(root/config["seal_path"]).read_bytes()
    reference=seal_api.open_for_session(sealed,{
        **seal_inputs["input_hashes"],
        "production_identity_hash":seal_inputs["production_identity_hash"],
        "coordinates":seal_inputs["coordinates"]})
    START=time.monotonic()
    backend=Wp7bDeviceBackend(Path(config["compiled_core_library"]),
        Path(config["compiled_d013_library"]),config["verified_d013_release_token"],
        fixture_only=True,frame_table=config.get("device_frames",{}))
    coords=[{**row,"coordinate":tuple(row["coordinate"])} for row in config["coordinates"]]
    repeats=[{**row,"coordinate":tuple(row["coordinate"])}
             for row in config.get("d013_coordinates",[])]
    record=harness.run_section_b2(backend,
        budgeted_reference(reference,time.monotonic,lambda:"section_b_item_1_recheck_synthetic"),
        coords,accepted_identity=config["accepted_identity"],
        session_identity=config["production_identity"],
        validate_identity=identity_api.validate_production_identity,
        exact_match=identity_api.exact_match,
        accepted_identity_sha256=config["accepted_identity_sha256"],
        protocol_identity_sha256=config["protocol_identity_sha256"],
        d013_fired=bool(config.get("d013_fired",False)),d013_coordinates=repeats)
    harness.validate_section_b2_record(record)
    return record

def require_wp2_passed(passed):
    if passed is not True:
        raise RuntimeError("WP2 identity recheck refused")

def _section_b1_identity_view(identity):
    """Project WP1's pinned identity into WP2's declared recheck fields."""
    qualification = identity["qualification_identity"]
    platform = dict(qualification["platform"])
    reported = identity["image_build_evidence"]["fields"]
    platform["kaggle_image"] = identity["image_build_evidence"]["kaggle_image_reported_string"]
    platform["kaggle_image_build"] = reported["kaggle_saved_version_build_platform_reported"]
    source = dict(qualification["source_sha256"])
    return {"production_identity": identity, "platform": platform,
            "compiler": {"version": qualification["platform"]["nvcc_version"],
                         "flags": list(qualification["compiler_flags"])},
            "source_sha256": source}

def _load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

def _platform_probe_source():
    # The child verifies the staged module's reviewed hash before this load.
    qualification = Path(__file__).resolve().parents[3] / "research/g9/cuda_qualification/stage2_cuda_core_qualification.py"
    return _load(qualification, "wp7b_platform_probe_qualification").PLATFORM_PROBE

def build_probes(pin):
    """Observe the 13 in-session fields through the accepted v1 sources.

    The four version-bound image values are intentionally absent here and are
    audited from pulled metadata after the run. Missing observations remain
    None, which makes the frozen session's exact pin comparison refuse.
    """
    nvcc = shutil.which("nvcc")
    gpu = {"gpu_name": None, "compute_capability": None,
           "cuda_driver_version": None, "cuda_runtime_version": None}
    nvcc_release = None
    if nvcc:
        version = subprocess.run([nvcc, "--version"], capture_output=True,
                                 text=True, timeout=30)
        if version.returncode == 0:
            import re
            match = re.search(r"release\s+(\d+\.\d+),\s+V(\d+\.\d+\.\d+)", version.stdout)
            if match:
                nvcc_release = f"{match.group(1)}, V{match.group(2)}"
        probe_source = _platform_probe_source()
        with tempfile.TemporaryDirectory(prefix="wp7b-platform-probe-") as td:
            source, binary = Path(td)/"platform_probe.cu", Path(td)/"platform_probe"
            source.write_text(probe_source, encoding="ascii")
            compiled = subprocess.run([nvcc, *FLAGS, str(source), "-o", str(binary)],
                                      capture_output=True, text=True, timeout=180)
            if compiled.returncode == 0:
                queried = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
                if queried.returncode == 0:
                    try:
                        candidate = json.loads(queried.stdout)
                        if set(candidate) == set(gpu) and all(type(v) is str and v for v in candidate.values()):
                            gpu = candidate
                    except (ValueError, TypeError):
                        pass
                else:
                    print(f"platform probe run failed: rc={queried.returncode}; stderr tail={queried.stderr[-2000:]}", file=sys.stderr)
            else:
                print(f"platform probe compile failed: rc={compiled.returncode}; stderr tail={compiled.stderr[-2000:]}", file=sys.stderr)
    import numpy as np
    platform_reported = {
      **gpu,
      "nvcc_version_release": nvcc_release,
      "python_version": platform.python_version(),
      "numpy_version": np.__version__,
    }
    image_reported = {
      "build_env": {k: os.environ.get(k) for k in ("BUILD_DATE", "COLAB_IMAGE_TYPE", "CUDA_VERSION", "GIT_COMMIT")},
      "cuda_home": os.environ.get("CUDA_HOME"),
      "nvcc_path": nvcc,
    }
    return {"platform_reported": lambda: platform_reported, "image_reported": lambda: image_reported}

def environment_comparison_pin(pin):
    """Return the complete pin with only the fixed post-run image keys removed."""
    if not isinstance(pin, dict) or not isinstance(pin.get("image_reported"), dict):
        raise RuntimeError("environment pin must contain an image_reported mapping")
    selected = copy.deepcopy(pin)
    for name in POST_RUN_ONLY_IMAGE_FIELDS:
        if name not in selected["image_reported"]:
            raise RuntimeError("post-run image field absent from pin: " + name)
        del selected["image_reported"][name]
    return selected

def post_run_image_expectations(pin):
    image = pin.get("image_reported")
    if not isinstance(image, dict) or any(name not in image for name in POST_RUN_ONLY_IMAGE_FIELDS):
        raise RuntimeError("post-run image expectations are incomplete")
    return {name: image[name] for name in POST_RUN_ONLY_IMAGE_FIELDS}



class NvccUnavailableError(RuntimeError):
    """The first GPU-dependent stage cannot start without the CUDA compiler."""


class Wp7bDeviceBackend:
    """WP3 backend bound to the approved compiled core and D013 ABIs."""
    supports_inactive_positive_zero = True

    def __init__(self, core_library, d013_library, verified_release_token, *,
                 fixture_only=False, abi_boundary=None, frame_table=None):
        if abi_boundary is not None and fixture_only is not True:
            raise RuntimeError("ABI injection is fixture-only")
        if not isinstance(core_library, Path) or not isinstance(d013_library, Path):
            raise RuntimeError("WP3 backend requires compiled library paths")
        if not core_library.is_file() or not d013_library.is_file():
            raise RuntimeError("WP3 compiled core/D013 library is missing")
        self._core_path=core_library
        self._d013_path=d013_library
        self._token=verified_release_token
        self._frames=frame_table if frame_table is not None else {}
        self._boundary=abi_boundary
        self._fixture_only=fixture_only is True
        self._row_cache={}
        self._active_offsets={}
        self._classifiers={}
        self._identity_slack=None
        from research.g9.cuda_qualification import stage2_cuda_core_bridge as core_bridge
        from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013_bridge
        self._core_bridge=core_bridge
        self._d013_bridge=d013_bridge
        core_bridge._load_checked_abi(core_library)
        d013_bridge._load_checked_abi(d013_library,verified_release=verified_release_token)

    @staticmethod
    def _key(row, pair, encoding):
        return json.dumps([row,list(pair),encoding],sort_keys=True,separators=(",",":"))

    @staticmethod
    def _row_key(row):
        return json.dumps([row.get("family"),row.get("condition"),row.get("coordinate"),
                           row.get("r"),row.get("grid"),row.get("comparator")],
                          sort_keys=True,separators=(",",":"),default=str)

    @staticmethod
    def _offsets_for_frame(frame, condition):
        """Build base slack offsets from frozen structural residual/lift rules only."""
        import struct
        from array import array
        from src.g4 import energy as canonical_energy
        from src.g5.domains import BinaryDomain, _register_minimizers
        payload=frame["payload"]
        # _residuals_from_bits consumes the frozen prepared-instance shape; the
        # frame's canonical instance is supplied by the backend builder.
        from src.g4.instance import Instance
        from src.g4.energy import prepare_instance
        source=frame.get("instance")
        if not isinstance(source,dict): raise RuntimeError("structural D013 offsets require the frozen G4 instance")
        instance=Instance(tickers=tuple(source["tickers"]),sectors=tuple(tuple(v) for v in source["sectors"]),
            mu=tuple(source["mu"]),sigma=tuple(tuple(v) for v in source["sigma"]),
            prices=tuple(source["prices"]),kappa_risk=float(source["kappa_risk"]),
            K=int(source["K"]),C=int(source["C"]),B=float(source["B"]))
        prepared=prepare_instance(instance)
        active_sector=condition in ("CS","CSB")
        active_budget=condition in ("CB","CSB")
        offsets=array("Q",[0]); total=0
        for x in BinaryDomain(20):
            _, hs, hb=canonical_energy._residuals_from_bits(prepared.instance,tuple(float(bit) for bit in x))
            count=1
            if active_sector:
                for residual in hs:
                    count*=len(_register_minimizers(residual,3))
            if active_budget:
                count*=len(_register_minimizers(hb,2047))
            total+=count; offsets.append(total)
        raw=offsets.tobytes()
        return tuple(offsets),total,hashlib.sha256(raw).hexdigest()

    def _construct_classifiers(self, frame, condition):
        cache_key=(self._row_key(frame.get("row",{})),condition)
        if cache_key in self._classifiers: return self._classifiers[cache_key]
        from src.g4.classification import DecodedClassifier, OriginalObjectiveService
        from src.g4 import objective as original_objective
        from src.g4 import constraints
        source=frame.get("instance")
        if not isinstance(source,dict): raise RuntimeError("frozen classifier requires its validated G4 instance")
        from src.g4.instance import Instance
        instance=Instance(tickers=tuple(source["tickers"]),sectors=tuple(tuple(v) for v in source["sectors"]),
            mu=tuple(source["mu"]),sigma=tuple(tuple(v) for v in source["sigma"]),
            prices=tuple(source["prices"]),kappa_risk=float(source["kappa_risk"]),
            K=int(source["K"]),C=int(source["C"]),B=float(source["B"]))
        lam=float(frame["lambda_ref"]); f_star=float(frame["f_star"])
        def feasible(x):
            if sum(x)!=int(instance.K): return False
            if condition in ("CS","CSB") and any(value<0.0 for value in constraints.sector(instance,x)): return False
            if condition in ("CB","CSB") and constraints.budget(instance,x)<0.0: return False
            return True
        objective=lambda x: original_objective.value(instance,x)
        groups={cf:DecodedClassifier(OriginalObjectiveService(objective,lam,float(cf)),feasible)
                for cf in (1024,2048,4096)}
        self._classifiers[cache_key]=(groups,f_star,lam)
        return groups,f_star,lam

    def _run_core_with_offsets(self, frame):
        """Capture g9_core_copy_offsets_v1 inside the bridge's checked call."""
        captured={}
        original=self._core_bridge._load_checked_abi
        def checked(path):
            run,copy_offsets,backend=original(path)
            captured["backend"]=backend
            def copy_and_capture(destination,count):
                status=copy_offsets(destination,count)
                if status==1:
                    raw=ctypes.string_at(ctypes.addressof(destination),ctypes.sizeof(destination))
                    captured["offsets"]=tuple(struct.unpack_from("<Q",raw,i*8)[0] for i in range(count))
                return status
            return run,copy_and_capture,backend
        import ctypes
        self._core_bridge._load_checked_abi=checked
        try:
            expected_backend=0 if self._fixture_only else 1
            raw=self._core_bridge._run_compiled_frame(frame["input_frame"],self._core_path,require_backend=expected_backend)
        finally:
            self._core_bridge._load_checked_abi=original
        if "offsets" not in captured: raise RuntimeError("validated core call did not expose copied offsets")
        raw["backend"]=captured["backend"]
        return raw,captured["offsets"]

    @staticmethod
    def _seal_reconstruction(reconstructed, pair, encoding):
        ch,cf=pair
        if pair==(2048,2048): summary=reconstructed["primary_c_h_2048"][encoding]
        else: summary=reconstructed["d015_diagnostics"][f"c_H={ch}__c_f={cf}"][encoding]
        # T_E_size/X_E_size are the reconstructor's exact, internally checked
        # census.  The four unused diagnostic commitments/counters are omitted
        # by the seal's documented five-field projection.
        projected={"c_h":summary["c_H"],"c_f":summary["c_f"],
                   "set_label":summary["set_label"],"tie_count":summary["T_E_size"],
                   "x_e_size":summary["X_E_size"]}
        return json.dumps(projected,sort_keys=True,separators=(",",":"),ensure_ascii=True)

    def _device_result(self, row, pair, encoding):
        key=self._key(row,pair,encoding)
        row_key=self._row_key(row)
        if row_key in self._frames: frame=self._frames[row_key]
        elif key in self._frames: frame=self._frames[key]
        else:
            raise RuntimeError("WP3 device frame is absent for sealed unit: "+key)
        if row_key not in self._row_cache:
            frame.setdefault("row",row)
            from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon
            self._recon=recon
            if self._identity_slack is None:
                self._identity_slack=recon.SlackIndexMap(range(recon.STATE_COUNT+1),recon.STATE_COUNT)
        inactive=(row.get("family")=="d013_repeat" and row.get("condition") in ("C","CB","CS"))
        if row_key not in self._row_cache and inactive:
            if self._boundary is None:
                raw=self._d013_bridge.run_host_emulated_frame(
                    frame["payload"],frame["records"],frame["condition"],self._d013_path,
                    frame["feasible_count"],verified_release=self._token)
            else:
                raw=self._boundary["d013"](self._d013_bridge,frame,self._d013_path,self._token)
            expected_backend=0 if self._fixture_only else 1
            if type(raw.get("backend")) is not int or raw["backend"]!=expected_backend:
                raise RuntimeError("D013 frame backend differs from armed/fixture mode")
            record=next(item for item in raw["records"] if item["encoding"]==encoding)
            frame_raw=raw
            offsets,lift_total,offset_sha=self._offsets_for_frame(frame,row.get("condition","CSB"))
            if lift_total!=raw["counters"]["lift_total_base"]:
                raise RuntimeError("host structural lift_total differs from D013 lift_total_base")
            # The unbalanced stream indexes decoded states directly. Its
            # reconstruction receives the identity map and never builds or
            # consults structural D013 offsets.
            encoding_maps={"unbalanced":self._identity_slack}
            encoding_maps["slack"]=self._recon.SlackIndexMap(offsets,lift_total)
            core_results={}
            for rec in raw["records"]:
                core_results[rec["encoding"]]={"word_count":rec["word_count"],"minimum":rec["minimum"],
                    "minimum_index":rec["minimum_index"],"per_ch":rec["per_ch"],
                    "compacted_count":rec["compacted_count"],"compacted_entries":rec["compacted_entries"],
                    "illegal":rec["illegal"],"nesting":rec["nesting"]}
            reconstruct_per_encoding=True
        elif row_key not in self._row_cache:
            if self._boundary is None:
                raw,offsets=self._run_core_with_offsets(frame)
            else:
                raw=self._boundary["core"](self._core_bridge,frame,self._core_path)
                offsets=raw.get("captured_offsets")
                if offsets is None: raise RuntimeError("fixture core boundary omitted captured ABI offsets")
            expected_backend=0 if self._fixture_only else 1
            if type(raw.get("backend")) is not int or raw["backend"]!=expected_backend:
                raise RuntimeError("core frame backend differs from armed/fixture mode")
            instance_key=hashlib.sha256(json.dumps(frame["payload"],sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
            prior_active=self._active_offsets.get(instance_key)
            self._active_offsets[instance_key]=(offsets,raw["offsets_sha256"])
            if row.get("family")=="d013_repeat" and row.get("condition")=="CSB":
                host_offsets,host_total,host_sha=self._offsets_for_frame(frame,"CSB")
                if host_total!=raw["core_result"]["lift_total"] or host_sha!=raw["offsets_sha256"] or host_offsets!=offsets:
                    raise RuntimeError("host CSB structural offsets differ from validated device offsets")
                if prior_active is None or prior_active[0]!=host_offsets or prior_active[1]!=host_sha:
                    raise RuntimeError("host CSB structural offsets differ from active core offsets")
            slack=self._recon.SlackIndexMap(offsets,raw["core_result"]["lift_total"])
            encoding_maps={"unbalanced":slack,"slack":slack}
            reconstruct_per_encoding=False
            core_results={enc:{"word_count":s["word_count"],"minimum":s["minimum"],
                "minimum_index":s["minimum_index"],"per_ch":s["per_ch"],
                "compacted_count":s["compacted_count"],"compacted_entries":s["compacted_entries"],
                "illegal":s["illegal"],"nesting":s["nesting"]}
                for (slot,enc),s in raw["core_result"]["summaries"].items() if slot==frame.get("slot",0)}
        if row_key not in self._row_cache:
            groups,f_star,lam=self._construct_classifiers(frame,row.get("condition","CSB"))
            if reconstruct_per_encoding:
                streams={encoding:recon.reconstruct_stream(encoding,
                    core_results[encoding]["minimum"],core_results[encoding]["minimum_index"],
                    core_results[encoding]["compacted_entries"],encoding_maps[encoding],
                    groups,f_star,lam) for encoding in ("unbalanced","slack")}
                reconstructed={"primary_c_h_2048":{},"d015_diagnostics":{}}
                # Keep the requested encoding argument intact.  Reusing that
                # name here silently changed an earlier unbalanced request to
                # the final loop value (slack) before the device minimum was
                # selected below.
                for stream_encoding,stream in streams.items():
                    reconstructed["primary_c_h_2048"][stream_encoding]=stream["primary_c_h_2048"]
                    for diagnostic,summary in stream["d015_diagnostics"].items():
                        reconstructed["d015_diagnostics"].setdefault(diagnostic,{})[stream_encoding]=summary
            else:
                reconstructed=recon.reconstruct_pair(core_results,slack,groups,f_star,lam)
            self._row_cache[row_key]={"reconstructed":reconstructed,"core_results":core_results}
        cached=self._row_cache[row_key]
        summary=cached["core_results"][encoding]
        flags=[0]*(summary["minimum_index"]+1)
        for packed in summary["compacted_entries"]:
            position=int(packed)&0xffffffff
            if position<=summary["minimum_index"]: flags[position]=(int(packed)>>32)&7
        if flags[summary["minimum_index"]]!=7:
            raise RuntimeError("device compacted output omitted its canonical minimum flags")
        return {"energy_minimum_words":[summary["minimum"]],"canonical_minimum_index":summary["minimum_index"],
                "tie_flags":flags,"reconstruction":self._seal_reconstruction(cached["reconstructed"],pair,encoding)}

    def __call__(self,row,comparator_pair,encoding):
        return self._device_result(row,comparator_pair,encoding)


def run_adapters(root, instance, prepared, seal_inputs, config, clock=time.monotonic, emulation_hooks=None,
                 fixture_only=False):
    global START
    START = clock()
    out = root / "wp7b-output"; out.mkdir(exist_ok=True)
    step_times = {}
    def timed(name, fn):
        def call(*args):
            guard(clock, _last[0]); t=clock()
            try: return fn(*args)
            finally: step_times[name]=max(0.0, clock()-t)
        return call
    _last=["none"]
    if emulation_hooks is not None and not fixture_only:
        raise RuntimeError("emulation_hooks are fixture-only")
    hooks=emulation_hooks or {}
    def synthetic():
        from research.g9.kaggle_wp7 import wp7_session as s
        checked=s.assert_synthetic_instance(instance)
        _last[0]="synthetic_instance_gate"
        return result(identities={"instance":checked}, digests={"instance_sha256":sha(canonical(instance))})
    def qualify():
        td=Path(tempfile.mkdtemp(prefix="wp7b-cuda-", dir=str(root)))
        if "wp6b" in hooks:
            observed=hooks["wp6b"](root,td,config)
            _last[0]="wp6b_section_a_qualification_plan"
            return observed
        nvcc=shutil.which("nvcc")
        if not nvcc: raise NvccUnavailableError("nvcc unavailable: no nvcc compiler found")
        src=root/"research/g9/cuda_qualification"
        common=[nvcc,*FLAGS]
        core_test=td/"stage2_cuda_core_stream_engine"; core=td/"stage2_cuda_core_bridge.so"; d013=td/"stage2_cuda_d013_inactive.so"
        for source,target in [(src/"stage2_cuda_core_stream_engine.cu",core_test),
                              (src/"stage2_cuda_core_bridge.cu",core),
                              (src/"stage2_cuda_d013_inactive.cu",d013)]:
            extra=["-shared"]
            if source.name == "stage2_cuda_core_stream_engine.cu": extra=[]
            cp=subprocess.run(common+extra+[str(source),"-o",str(target)],capture_output=True,text=True,timeout=900)
            if cp.returncode: raise RuntimeError("nvcc compile failed: "+cp.stderr[-2000:])
        core_self_test=subprocess.run([str(core_test),"--self-test"],capture_output=True,text=True,timeout=300)
        if core_self_test.returncode: raise RuntimeError("compiled v1 core self-test failed: "+core_self_test.stderr[-2000:])
        # Load each just-built shared library through its reviewed ABI bridge;
        # the files are thereby consumed, not merely left in the temp directory.
        core_bridge=_load(src/"stage2_cuda_core_bridge.py","wp7b_core_abi")
        core_bridge._load_checked_abi(core)
        d013_bridge=_load(src/"stage2_cuda_d013_inactive.py","wp7b_d013_abi")
        d013_bridge._load_checked_abi(d013)
        config["compiled_core_library"]=str(core)
        config["compiled_d013_library"]=str(d013)
        q=_load(src/"stage2_cuda_core_corruption_qualification.py","wp7b_core_corruption_qualification")
        core_report=(q.build_plan() if fixture_only else
                     q.run_qualification(config["corruption_release_sha256"]))
        d013_q=_load(src/"stage2_cuda_d013_inactive_corruption_qualification.py","wp7b_d013_corruption_qualification")
        d013_report=(d013_q.build_plan() if fixture_only else
                     d013_q.run_qualification(config["d013_corruption_release_sha256"]))
        if fixture_only:
            d013_report=dict(d013_report)
            d013_report["verified_release_token"]={"host_emulation_plan_only":True}
        config["verified_d013_release_token"]=d013_report.get("verified_release_token")
        _last[0]="wp6b_section_a_qualification_plan"
        return result(counters={"cuda_compile_count":3,
                                "core_corruption_mutations":len(core_report.get("mutations",[])),
                                "d013_corruption_mutations":len(d013_report.get("mutations",[]))},
                      digests={"qualification_sha256":sha(canonical({"core":core_report,"d013":d013_report})),
                               "compiled_core_library_sha256":sha(core.read_bytes()),
                               "compiled_d013_library_sha256":sha(d013.read_bytes())})
    def wp1():
        if "wp1" in hooks:
            identity=hooks["wp1"](root,instance,prepared,config)
            config["production_identity"]=identity
            ih=sha(canonical(identity)); _last[0]="wp1_production_identity_candidate"
            return result(identities={"production_identity_sha256":ih},digests={"production_identity_sha256":ih})
        m=_load(root/"research/g9/stage2_production_identity.py","wp7b_wp1")
        probe_functions=config.get("runtime_probes")
        if not isinstance(probe_functions,dict) or set(probe_functions)!={"platform_reported","image_reported"}:
            raise RuntimeError("WP1 runtime platform probes are absent")
        observed_platform=probe_functions["platform_reported"]()
        observed_image=probe_functions["image_reported"]()
        if type(observed_platform) is not dict or type(observed_image) is not dict:
            raise RuntimeError("WP1 runtime observations are malformed")
        build_env=observed_image.get("build_env")
        if type(build_env) is not dict:
            raise RuntimeError("WP1 image build environment observations are absent")
        observed={**observed_platform, **build_env,
                  "CUDA_HOME":observed_image.get("cuda_home"),
                  "nvcc_path":observed_image.get("nvcc_path")}
        binding=_load(root/"research/g9/kaggle_wp7b/wp7b_identity_binding.py","wp7b_identity_binding")
        pin=binding.load_pin(root/binding.PIN_PATH)
        platform_identity,image_build,_provenance=binding.build_identity_mapping(pin,observed)
        # Config identity fields are checked as seal-fixed declarations, but do
        # not supply any observed value used to construct this session identity.
        if config.get("image_build") != image_build and observed == binding.expected_observations(pin):
            raise RuntimeError("WP1 generated image/build mapping differs from shared pin mapping")
        identity=m.build_production_identity(repo_root=str(root),role_paths=config["role_paths"],platform=platform_identity,image_build=image_build,compiler_flags=config["compiler_flags"])
        ih=m.validate_production_identity(identity); config["production_identity"]=identity; _last[0]="wp1_production_identity_candidate"
        return result(identities={"production_identity_sha256":ih},digests={"production_identity_sha256":ih})
    def wp2():
        if "wp2" in hooks:
            rec=hooks["wp2"](instance,config["production_identity"],config)
            require_wp2_passed(rec.get("gate_passed",True))
            _last[0]="section_b_item_1_recheck_synthetic"
            return result(counters={"wp2_checks":int(rec.get("checks_passed",1))},digests={"wp2_validation_sha256":sha(canonical(rec))})
        m=_load(root/"research/g9/stage2_section_b1_recheck.py","wp7b_wp2")
        identity_module=_load(root/"research/g9/stage2_production_identity.py","wp7b_wp1_wp2")
        accepted=_section_b1_identity_view(config["accepted_identity"])
        session=_section_b1_identity_view(config["production_identity"])
        def validate_view(value):
            if not isinstance(value,dict) or "production_identity" not in value:
                raise RuntimeError("WP2 identity wrapper is malformed")
            return identity_module.validate_production_identity(value["production_identity"])
        def match_views(left,right):
            return identity_module.exact_match(left["production_identity"],right["production_identity"])
        rec,passed=m.recheck_before_first_write(
            accepted_identity=accepted,
            validate_identity=validate_view,
            exact_match=match_views,
            observed_approval_sha256=config["observed_approval_sha256"],
            expected_approval_sha256=config["expected_approval_sha256"],
            session_identity=session,
            generator_implementation_record_sha256=config["generator_implementation_record_sha256"],
            expected_generator_implementation_record_sha256=config["expected_generator_implementation_record_sha256"],
            ground_truth_provenance_sha256=config["ground_truth_provenance_sha256"],
            expected_ground_truth_provenance_sha256=config["expected_ground_truth_provenance_sha256"])
        require_wp2_passed(passed)
        _last[0]="section_b_item_1_recheck_synthetic"
        return result(counters={"wp2_checks":int(rec.get("counters",{}).get("checks_passed",1))},digests={"wp2_validation_sha256":sha(canonical(rec))})
    def wp3(reference):
        checked_reference=budgeted_reference(reference,clock,lambda:_last[0])
        if "wp3" in hooks:
            rec=hooks["wp3"](checked_reference,instance,config["production_identity"],config)
            _last[0]="section_b_item_2_full_domain_synthetic"
            return result(counters={"wp3_rows":int(rec.get("rows_visited",1))},digests={"wp3_validation_sha256":sha(canonical(rec))})
        m=_load(root/"research/g9/stage2_section_b2_harness.py","wp7b_wp3")
        if "compiled_core_library" not in config or "compiled_d013_library" not in config:
            raise RuntimeError("WP3 device backend has no compiled core/D013 libraries")
        if config.get("device_backend") is not None or config.get("device_backend_factory") is not None:
            raise RuntimeError("JSON-supplied backend callables are fixture-only")
        token=config.get("verified_d013_release_token")
        if not isinstance(token,dict):
            raise RuntimeError("WP3 requires the approved D013 VerifiedReleaseToken")
        coords=[{**row,"coordinate":tuple(row["coordinate"])}
                for row in config["coordinates"]]
        d013_rows=[{**row,"coordinate":tuple(row["coordinate"])}
                   for row in config.get("d013_coordinates",[])]
        if fixture_only:
            # Isolate host-emulation ABI storage from the earlier gate probes;
            # the child executes this same real backend and harness against
            # the opened seal and returns the validated harness record.
            worker_config={k:v for k,v in config.items() if k!="runtime_probes"}
            worker_config["seal_inputs"]=seal_inputs
            code=("import json,sys; from research.g9.kaggle_wp7b.wp7b_launcher "
                  "import _wp3_host_worker; "
                  "print(json.dumps(_wp3_host_worker(json.load(sys.stdin)),sort_keys=True,"
                  "separators=(',',':')))" )
            command=[sys.executable,"-B"]+(["-O"] if sys.flags.optimize else [])+["-c",code]
            worker_env=os.environ.copy(); worker_env["PYTHONDONTWRITEBYTECODE"]="1"
            done=subprocess.run(command,cwd=root,input=json.dumps(worker_config,sort_keys=True),
                env=worker_env,capture_output=True,text=True,timeout=BUDGET_SECONDS)
            if done.returncode:
                raise RuntimeError("isolated host WP3 worker refused: "+done.stderr[-2000:])
            rec=json.loads(done.stdout)
        else:
            backend=Wp7bDeviceBackend(Path(config["compiled_core_library"]),
                                      Path(config["compiled_d013_library"]),token,
                                      fixture_only=False,
                                      frame_table=config.get("device_frames",{}))
            identity_module=_load(root/"research/g9/stage2_production_identity.py","wp7b_wp1_matchers")
            rec=m.run_section_b2(backend,checked_reference,coords,
                accepted_identity=config["accepted_identity"],session_identity=config["production_identity"],
                validate_identity=identity_module.validate_production_identity,exact_match=identity_module.exact_match,
                accepted_identity_sha256=config["accepted_identity_sha256"],
                protocol_identity_sha256=config["protocol_identity_sha256"],
                d013_fired=bool(config.get("d013_fired",False)),d013_coordinates=d013_rows)
        _last[0]="section_b_item_2_full_domain_synthetic"
        return result(counters={"wp3_rows":int(rec["counters"]["coordinate_rows"]),
                                "wp3_d013_repeat_rows":int(rec["counters"]["d013_repeat_rows"])},
                      digests={"wp3_validation_sha256":sha(canonical(rec))})
    def wp4():
        if "wp4b" in hooks:
            rec=hooks["wp4b"](out,instance,config["production_identity"],prepared,config)
            _last[0]="wp4b_writer_synthetic_ranges"
            return result(counters={"synthetic_ranges_written":int(rec.get("ranges_written",1))},digests={"wp4b_validation_sha256":sha(canonical(rec))})
        batch_ids=config.get("batch_ids")
        if not isinstance(batch_ids,list): raise RuntimeError("WP4b sealed batch list must be a list")
        if not batch_ids: raise RuntimeError("WP4b sealed batch list absent")
        guard(clock,_last[0])
        m=_load(root/"research/g9/stage2_production_writer.py","wp7b_wp4")
        writer_root=root/config.get("writer_root","wp7b-output")
        identity_module=_load(root/"research/g9/stage2_production_identity.py","wp7b_wp4_identity")
        writer_identity=type("WP7bWriterIdentity",(),{
            "accepted":config["accepted_identity"],
            "validate":staticmethod(identity_module.validate_production_identity),
            "exact_match":staticmethod(identity_module.exact_match)})()
        plan=m.seal_range_plan(writer_root,family=config["writer_family"],
            total_coordinates=config["writer_total_coordinates"],identity=writer_identity,
            session=config["production_identity"])
        if [row["batch_id"] for row in plan["ranges"]] != batch_ids:
            raise RuntimeError("WP4b generated batch list differs from the sealed plan")
        manifests=[]
        for batch_id in batch_ids:
            guard(clock,_last[0])
            rec=m.write_range(writer_root,batch_id,config["records_by_batch"][batch_id],
                result_schema=config["result_schema"],identity=writer_identity,
                session=config["production_identity"])
            manifests.append(rec)
        rec={"ranges_written":len(manifests),"manifest_sha256":sha(canonical(manifests))}
        _last[0]="wp4b_writer_synthetic_ranges"
        return result(counters={"synthetic_ranges_written":int(rec.get("ranges_written",0))},digests={"wp4b_validation_sha256":sha(canonical(rec))})
    steps={"synthetic_instance_gate":timed("synthetic_instance_gate",synthetic),"wp6b_section_a_qualification_plan":timed("wp6b",qualify),"wp1_production_identity_candidate":timed("wp1",wp1),"section_b_item_1_recheck_synthetic":timed("wp2",wp2),"section_b_item_2_full_domain_synthetic":timed("wp3",wp3),"wp4b_writer_synthetic_ranges":timed("wp4b",wp4)}
    return steps, out, step_times

def main():
    raise SystemExit("Use the generated armed bundle entrypoint; this adapter module is not directly runnable.")
if __name__ == "__main__": main()
