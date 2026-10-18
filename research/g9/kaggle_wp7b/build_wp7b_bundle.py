#!/usr/bin/env python3
"""Offline WP7b bundle builder with owner-record arming gate."""
from __future__ import annotations
import argparse, base64, hashlib, json, lzma, re, sys
from pathlib import Path
import os, tempfile

ROOT=Path(__file__).resolve().parents[3]
PKG=ROOT/"research/g9/kaggle_wp7b"
ANCHOR="f2c0be0ee2a33dad44f3f02d4b29222647a1554177e0c3c87f83cf2f660f7c49"
TABLE="research/g9/kaggle_wp7/wp7_reviewed_dependencies.json"
SESSION="research/g9/kaggle_wp7/wp7_session.py"
PIN="research/g9/kaggle_wp7/wp7_environment_pin.json"
CHILD="research/g9/kaggle_wp7b/wp7b_child_entry.py"
TABLE_KEYS=("dependencies","package_files_sha256")
EXTRAS={
 "research/g9/stage2_beacon_nonce.py":"d855129fb6096d6939203b7f55cb707b0f9a06b2870204e6aaddc57ba6840426",
 "research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py":"ab0c906017fa7555ee5a00f8ba02cc15e8a467f046008d427be018c318382c5c",
 "research/g9/cuda_qualification/stage2_cuda_reconstruct.py":"f776435b42bbd4fd250523a78c1be33d835df6a8c899e70349fa695755571da8",
 "research/g9/cuda_qualification/stage2_cuda_core_bridge_v2.py":"ba6cbdba170d67f3d262dbbc67e9b45170add4c7b627512125438e44bc0ce65b",
 "research/g9/stage2_generator.py":"38d2f73a3e6c0e8b07ff469a46ef63e5c8dab6cd286dd828b1ab9bf685981e1a",
 "research/g9/stage2_sampled_verification.py":"6f57ac363d39cfe4df10bfaa672e927553bbae7fd9a9fdbdb982019b10c68960",
 "research/g9/verify_stage2_cuda_d013_inactive_host_emulation.py":"b223206b9490fb7fe8ac12b829291a73d7ffbb1663b5cdab939bf9db4da98f4a",
 "research/g9/cuda_qualification/GATE_9_D013_CUDA_RELEASE_DRAFT.json":"e73a4ff4a38cb6b0cfbc35713b7ce727c6cb8b94b2c38310277a1dac372b0721",
 "research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json":"585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9",
 "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json":"50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9",
 "src/g4/__init__.py":"ce71102f51064425027c2999709eb9a003095bc432ba2f861a9e1cf44de32c67",
 "src/g4/classification.py":"9a35f0829de8216ff47e6b1dd257e5dbc5a0dd96c9a051dd058bfe54bd672da1",
 "src/g4/constraints.py":"dac9b0b10f7ee2e3e79d224fd66e16799f574ffd515289339ce419ebf5a97a96",
 "src/g4/energy.py":"0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
 "src/g4/generate_ledger.py":"a8ba50cf45ab5634c715929d7d4d887a57c45103bbc931f6930d32d86f134134",
 "src/g4/instance.py":"645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
 "src/g4/objective.py":"8fbf424695586ee0a4879aaaccc97f2128baf662e358e2375b2c4ee09e913d54",
 "src/g4/parameters.py":"cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
 "src/g4/quadratic.py":"ade40007e7c0f536d0136e9963765e0d66c958a4d2e228402d53afad99f6bb80",
 "src/g4/slack.py":"5ab5f677d9150bfb63c9bf5afcd79b2fe8a80202c8c2821c282522cc5a8f4d72",
 "src/g4/unbalanced.py":"83849bb1fc22680aaa789145e9c0a54ee4efa36624e814feec40dbce0c6b1ab6",
 "src/g5/certify.py":"018b0a67ae1d1fdf8cf797cd38296ed0a98ec3bd0d2e5c1124dc51e36e614d64",
 "src/g5/core_pass.py":"25df3804ecd703daabf249d21c6b023b6b2691bc4f22d135e849b09d0e98739a",
 "src/g5/domains.py":"89d3b1cadf660ec7ea4a127af09a73073afb03d5c78a74e7a15b5808999dadf7",
 "src/g5/make_self_test.py":"1c4196a7261d09677bd3b9ccdeac478e2edfae333258a495076f3e3a9c2013c4",
 "src/g5/runner.py":"262fda09db033cc3195c8447042836274b195907b772f827f3f21a9311f963cd",
 "src/g6/__init__.py":"18f52c87ce06f8916889fe953163e0a5116881c499b68e78a973cbce1f9da5b4",
 "src/g6/d011_matched_subgrid.py":"0285509848d0ea06d954f6d485c1eada07be07468ba0ff5f4813a214b3ce4067",
 "src/g6/d011_runner.py":"1ba537f228dbf806d0b7b7932d919c123093c9f7139bdd73370a47e11df3b79f",
 "src/g6/d011_transition_output.py":"196881bcc4b2b3104ba5243844b8b55a4537a9e83f422249c8b0cada196025e5",
 "src/g6/g5_digest_registry.py":"ed80f784a1c13da0dae27393efa0c1f95c3811f35551748f60833fbf38e65e60",
 "src/g6/g5_input.py":"4584aa39f893dc4aaf79444818d7c7b60c6a707426bb6ae36dbaaff41868cb50",
 "src/g6/ledgers.py":"40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
 "src/g6/ratified_g5_input.py":"5ab9974a48cefc270658cf895c6caff01fccc81a427e4a0595737f8e0d1d525b",
 "src/g6/trial_runner.py":"0ce9ce3b964433ff7c7a3c2501eb6acc2bf3da948ff537e9c342f6b48d2a04b9",
 "research/g9/kaggle_wp7b/wp7b_identity_binding.py":"2a2aa3be4fc8ff448162ece292c9eabd69a9273b275c72127763bb00b6bbe34c",
}
HEX=re.compile(r"[0-9a-f]{64}\Z")
SCRIPT_SIZE_LIMIT=950_000
MAX_DECOMPRESSED_SIZE=400_000_000
class BuildError(RuntimeError): pass

def require_fixture_approval(fixture_mode, draft, approval_record):
 if fixture_mode and (draft or approval_record is None):
  raise BuildError('fixture-mode build requires an armed test approval record')
 return True
def sha(b): return hashlib.sha256(b).hexdigest()
def canon(o): return json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")
def read(root,rel):
 p=root/rel
 if p.is_symlink(): raise BuildError("symlink input: "+rel)
 if not p.is_file(): raise BuildError("missing input: "+rel)
 return p.read_bytes()
def payload_hash(blobs): return sha(canon([[n,d] for n,d,_ in sorted(blobs)]))
def validate_payload_blobs(blobs, expected_names):
 names=[n for n,_,_ in blobs]
 if len(names)!=len(set(names)): raise BuildError("duplicate payload name")
 if set(names)!=set(expected_names): raise BuildError("payload closure mismatch")
 for name,digest,data in blobs:
  if not isinstance(name,str): raise BuildError("blob name must be text")
  if not (name.startswith("research/") or name.startswith("src/")): raise BuildError("blob name must be repo-relative")
  if ".." in name.split("/"): raise BuildError("blob name may not traverse parents")
  if sha(data)!=digest: raise BuildError("blob digest mismatch: "+str(name))
 return True
def derive_runtime_closure(blobs):
 """Resolve the bundled Python import graph plus every explicit runtime file input."""
 import ast
 payload={n:b for n,_,b in blobs}
 table_raw=payload.get(TABLE)
 if table_raw is None: raise BuildError("dependency table absent from closure")
 table=json.loads(table_raw)
 closure={TABLE,SESSION,PIN,"research/g9/kaggle_wp7/wp7_reviewed_dependencies.json",
          CHILD,
          "research/g9/kaggle_wp7b/wp7b_launcher.py",
          "research/g9/kaggle_wp7b/instance.json","research/g9/kaggle_wp7b/prepared_record.json",
          "research/g9/kaggle_wp7b/seal.json","research/g9/kaggle_wp7b/seal_inputs.json",
          "research/g9/kaggle_wp7b/runtime_config.json"}
 closure.update(("research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md",
                 "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md",
                 "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md",
                 "research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md",
                 "research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_V3_VERSION1_RECEIPT.json"))
 closure.update(table.get("dependencies",{}))
 closure.update("research/g9/kaggle_wp7/"+n for n in table.get("package_files_sha256",{}))
 closure.update(EXTRAS)
 def module_paths(module):
  base=module.replace(".","/")
  return [base+".py",base+"/__init__.py"]
 queue=[name for name in closure if name.endswith(".py")]
 seen=set()
 while queue:
  name=queue.pop()
  if name in seen: continue
  seen.add(name)
  data=payload.get(name)
  if data is None: continue
  try: tree=ast.parse(data.decode("utf-8"),filename=name)
  except (UnicodeError,SyntaxError): continue
  package=name.rsplit("/",1)[0].replace("/", ".")
  for node in ast.walk(tree):
   modules=[]
   if isinstance(node,ast.Import): modules=[alias.name for alias in node.names]
   elif isinstance(node,ast.ImportFrom):
    if node.level:
     prefix=package.split(".")[:max(0,len(package.split("."))-node.level+1)]
     base=".".join(prefix+([node.module] if node.module else []))
    else: base=node.module or ""
    if any(candidate in payload for candidate in module_paths(base)):
     modules.append(base)
     if node.module is None:
      # A module-less ImportFrom is necessarily relative in valid Python ASTs.
      modules.extend((base+"."+alias.name).strip(".") for alias in node.names if alias.name!="*")
    else:
     modules.extend((base+"."+alias.name).strip(".") for alias in node.names if alias.name!="*")
   for module in modules:
    if not module.startswith(("research.g9.","src.")): continue
    candidates=module_paths(module)
    found=next((candidate for candidate in candidates if candidate in payload),None)
    if found is None:
     # Include the canonical expected source path in closure so build refuses visibly.
     found=candidates[0]
    if found not in closure:
     closure.add(found); queue.append(found)
 return closure

def load_payload(root, inputs):
 table_raw=read(root,TABLE)
 if sha(table_raw)!=ANCHOR: raise BuildError("reviewed dependency anchor mismatch")
 table=json.loads(table_raw)
 deps=table["dependencies"]
 blobs={TABLE:(sha(table_raw),table_raw),SESSION:(sha(read(root,SESSION)),read(root,SESSION)),PIN:(sha(read(root,PIN)),read(root,PIN)),"research/g9/kaggle_wp7/wp7_reviewed_dependencies.json":(sha(table_raw),table_raw)}
 # Runtime package files from the pinned inventory, checked against the table anchor.
 for n,h in table["package_files_sha256"].items():
  data=read(root,"research/g9/kaggle_wp7/"+n)
  if sha(data)!=h: raise BuildError("pinned WP7 package file mismatch: "+n)
  blobs["research/g9/kaggle_wp7/"+n]=(h,data)
 for n,h in deps.items():
  data=read(root,n)
  if sha(data)!=h: raise BuildError("dependency differs from reviewed anchor: "+n)
  blobs[n]=(h,data)
 for n,h in EXTRAS.items():
  data=read(root,n)
  if sha(data)!=h: raise BuildError("declared extra differs from reviewed hash: "+n)
  blobs[n]=(h,data)
 for n in ("research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md",
           "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md",
           "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md",
           "research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md",
           "research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_V3_VERSION1_RECEIPT.json"):
  data=read(root,n); blobs[n]=(sha(data),data)

 for key in ("instance","prepared_record","seal","seal_inputs","runtime_config"):
  rel=inputs[key]
  data=Path(rel).read_bytes()
  if sha(data)!=inputs[key+"_sha256"]: raise BuildError("input digest mismatch: "+key)
  embed={"instance":"research/g9/kaggle_wp7b/instance.json","prepared_record":"research/g9/kaggle_wp7b/prepared_record.json","seal":"research/g9/kaggle_wp7b/seal.json","seal_inputs":"research/g9/kaggle_wp7b/seal_inputs.json","runtime_config":"research/g9/kaggle_wp7b/runtime_config.json"}[key]
  blobs[embed]=(sha(data),data)
 launcher=read(root,"research/g9/kaggle_wp7b/wp7b_launcher.py")
 blobs["research/g9/kaggle_wp7b/wp7b_launcher.py"]=(sha(launcher),launcher)
 child=read(root,CHILD)
 blobs[CHILD]=(sha(child),child)
 closure=derive_runtime_closure([(n,d,b) for n,(d,b) in blobs.items()])
 absent=sorted(set(closure)-set(blobs))
 if absent: raise BuildError("armed runtime closure is not embedded: "+", ".join(absent))
 print("DERIVED RUNTIME CLOSURE:")
 for item in sorted(closure): print("  "+item)
 return sorted((n,d,b) for n,(d,b) in blobs.items())
def validate_record(record, expected):
 keys={"bundle_sha256","reviewed_table_anchor","seal_sha256","kernel_id","account","action","expiry","nonce"}
 if type(record) is not dict: raise BuildError("approval record must be an exact dict")
 if set(record)!=keys: raise BuildError("approval record fields differ from exact required schema")
 for k,v in expected.items():
  if record.get(k)!=v: raise BuildError("approval record mismatch: "+k)
 if not isinstance(record["nonce"],str) or not record["nonce"]: raise BuildError("approval nonce absent")
 try: expiry=__import__("datetime").date.fromisoformat(record["expiry"])
 except (TypeError,ValueError) as exc: raise BuildError("approval expiry is not a calendar date") from exc
 if expiry.isoformat()!=record["expiry"]: raise BuildError("approval expiry is not canonical ISO date")
 if expiry<__import__("datetime").date.today(): raise BuildError("owner approval record has expired")
def make_archive(blobs):
 data=bytearray(); index=[]
 for n,d,b in sorted(blobs):
  if sha(b)!=d: raise BuildError("blob digest mismatch: "+n)
  index.append([n,d,len(data),len(b)]); data.extend(b)
 encoded=canon(index)
 return len(encoded).to_bytes(8,"big")+encoded+bytes(data)
def script_source(blobs, bundle_sha, approval_sha, approval_fields, draft, fixture_mode=False):
 seal_raw=next((b for n,_,b in blobs if n=="research/g9/kaggle_wp7b/seal.json"),None)
 if seal_raw is None: raise BuildError("raw seal is absent")
 archive=make_archive(blobs)
 packed=lzma.compress(archive,format=lzma.FORMAT_XZ,check=lzma.CHECK_SHA256,preset=9|lzma.PRESET_EXTREME)
 archive_sha=sha(packed); encoded=base64.b85encode(packed).decode("ascii")
 chunks="("+",\n".join(repr(encoded[i:i+76]) for i in range(0,len(encoded),76))+",)"
 expected_index=[[n,d] for n,d,_ in sorted(blobs)]
 return '''#!/usr/bin/env python3
import base64,hashlib,json,os,shutil,sys,tempfile,datetime,subprocess,lzma
from pathlib import Path
ARCHIVE_CHUNKS='''+chunks+'''\nARCHIVE_SHA='''+repr(archive_sha)+'''\nEXPECTED_INDEX='''+repr(expected_index)+'''\nMAX_DECOMPRESSED_SIZE='''+str(MAX_DECOMPRESSED_SIZE)+'''\nBUNDLE_SHA='''+repr(bundle_sha)+'''\nAPPROVAL_SHA='''+repr(approval_sha)+'''\nAPPROVAL_FIELDS='''+repr(approval_fields)+'''\nDRAFT='''+repr(draft)+'''\nFIXTURE_MODE='''+repr(bool(fixture_mode))+'''\nSTAGE_INDEX_SHA='''+repr(sha(canon(expected_index)))+'''\nSELF_SHA='''+repr("0"*64)+'''
ANCHOR='''+repr(ANCHOR)+'''
SEAL_RAW_SHA='''+repr(sha(seal_raw))+'''
def sha(b): return hashlib.sha256(b).hexdigest()
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def refuse(msg):
 print('REFUSED: '+str(msg),file=sys.stderr); raise SystemExit(2)
def atomic_write(path,data):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
class TransportError(ValueError): pass
def decode_archive(chunks=None, archive_sha=ARCHIVE_SHA, max_size=MAX_DECOMPRESSED_SIZE):
 try:
  packed=base64.b85decode(''.join(ARCHIVE_CHUNKS if chunks is None else chunks).encode('ascii'))
  if sha(packed)!=archive_sha: raise TransportError('archive sha256 mismatch')
  dec=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=256*1024*1024)
  raw=dec.decompress(packed,max_length=max_size+1)
  if len(raw)>max_size or not dec.eof or dec.unused_data: raise TransportError('archive size or framing invalid')
  if len(raw)<8: raise TransportError('archive header truncated')
  size=int.from_bytes(raw[:8],'big')
  if size>len(raw)-8: raise TransportError('archive index length invalid')
  index_bytes=raw[8:8+size]; data=raw[8+size:]
  index=json.loads(index_bytes.decode('ascii'))
  if type(index) is not list or canonical(index)!=index_bytes: raise TransportError('archive index is not canonical')
  names=[]; decoded={}; cursor=0; expected=dict(EXPECTED_INDEX)
  for row in index:
   if type(row) is not list or len(row)!=4: raise TransportError('archive index entry malformed')
   name,digest,offset,length=row
   if type(name) is not str or type(digest) is not str or type(offset) is not int or type(length) is not int or offset<0 or length<0: raise TransportError('archive index field malformed')
   if name in names: raise TransportError('duplicate archive entry')
   names.append(name)
   if name not in expected or digest!=expected[name]: raise TransportError('archive entry differs from expected payload')
   if offset!=cursor or length>len(data)-cursor: raise TransportError('archive offsets are not contiguous and in range')
   blob=data[offset:offset+length]
   if sha(blob)!=digest: raise TransportError('blob digest mismatch: '+name)
   decoded[name]=blob; cursor+=length
  if names!=[name for name,_ in EXPECTED_INDEX] or cursor!=len(data): raise TransportError('archive payload closure or trailing bytes invalid')
  seal=decoded.get('research/g9/kaggle_wp7b/seal.json')
  if seal is None or sha(seal)!=SEAL_RAW_SHA: raise TransportError('raw seal sha256 mismatch')
  return decoded
 except TransportError: raise
 except Exception as exc: raise TransportError('malformed archive: '+str(exc)) from exc
def verify_payload(payload=None):
 approval_name='research/g9/kaggle_wp7b/owner_approval_record.json'
 decoded=decode_archive()
 if sha(canonical([[n,d] for n,d in EXPECTED_INDEX if n!=approval_name]))!=BUNDLE_SHA: raise TransportError('bundle payload hash mismatch')
 table=json.loads(decoded['research/g9/kaggle_wp7/wp7_reviewed_dependencies.json'])
 if sha(decoded['research/g9/kaggle_wp7/wp7_reviewed_dependencies.json'])!=ANCHOR: raise TransportError('reviewed table anchor mismatch')
 if set(table)!={'dependencies','package_files_sha256'} or len(table.get('dependencies',{}))!=29: raise TransportError('dependency closure count mismatch')
 for n,d in table['dependencies'].items():
  if n not in decoded or sha(decoded[n])!=d: raise TransportError('reviewed dependency mismatch: '+n)
 for n,d in table['package_files_sha256'].items():
  rel='research/g9/kaggle_wp7/'+n
  if rel not in decoded or sha(decoded[rel])!=d: raise TransportError('reviewed package mismatch: '+n)
 return decoded
def verify_launcher_bytes(source):
 marker=b"SELF_SHA='"+SELF_SHA.encode('ascii')+b"'"
 if source.count(marker)!=1: raise ValueError('launcher self-hash marker mismatch')
 if sha(source.replace(marker,b"SELF_SHA='"+b"0"*64+b"'",1))!=SELF_SHA: raise ValueError('launcher edited after build')
 return True
def validate_approval(decoded, platform_date=None):
 approval_name='research/g9/kaggle_wp7b/owner_approval_record.json'
 if approval_name not in decoded or sha(decoded[approval_name])!=APPROVAL_SHA: raise ValueError('approval record hash mismatch')
 approval=json.loads(decoded[approval_name])
 if set(approval)!={'bundle_sha256','reviewed_table_anchor','seal_sha256','kernel_id','account','action','expiry','nonce'}: raise ValueError('approval fields differ from exact schema')
 for k,v in APPROVAL_FIELDS.items():
  if approval.get(k)!=v: raise ValueError('approval field mismatch: '+k)
 if not isinstance(approval.get('nonce'),str) or not approval['nonce']: raise ValueError('approval nonce absent')
 today=platform_date or datetime.date.today()
 if today.isoformat()>approval['expiry']: raise ValueError('approval expired')
 return approval
def child_environment():
 # Probe inputs plus the CUDA toolchain/runtime loader's executable and library paths.
 allowed={'PATH','LD_LIBRARY_PATH','CUDA_HOME','CUDA_VERSION','CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER','BUILD_DATE','COLAB_IMAGE_TYPE','GIT_COMMIT','HOME','LANG','TMPDIR'}
 env={k:os.environ[k] for k in os.environ if (k in allowed or k.startswith('LC_') or k.startswith('NVIDIA_')) and not k.startswith('KAGGLE_') and not k.startswith('PYTHON')}
 env['PYTHONDONTWRITEBYTECODE']='1'
 if FIXTURE_MODE:
  for key in ('WP7B_TEST_PROBES_JSON','WP7B_TEST_CHILD_ENV_JSON','WP7B_TEST_CHILD_SLEEP','WP7B_TEST_FORCE_BUDGET','WP7B_TEST_CHILD_STARTED_FILE'):
   if key in os.environ: env[key]=os.environ[key]
 return env
def main():
 out_base=Path('/kaggle/working'); root=None
 try:
  verify_launcher_bytes(Path(__file__).read_bytes())
  decoded=verify_payload()
  if DRAFT: refuse('DRAFT bundle is intentionally non-runnable')
  out_base=Path(os.environ.pop('KAGGLE_WORKING_DIR','/kaggle/working'))
  approval=validate_approval(decoded)
  out_base.mkdir(parents=True,exist_ok=True)
  nonce_marker=out_base/('wp7b_nonce_'+sha(approval['nonce'].encode('utf-8'))+'.consumed')
  try: marker_fd=os.open(str(nonce_marker),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  except FileExistsError: raise ValueError('one-use owner approval nonce was already consumed')
  else:
   with os.fdopen(marker_fd,'wb') as marker_stream: marker_stream.write(BUNDLE_SHA.encode('ascii'))
  root=Path(tempfile.mkdtemp(prefix='wp7b-stage-',dir=str(out_base)))
  for n,b in decoded.items():
   p=root/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
   if sha(p.read_bytes())!=sha(b): raise ValueError('staged hash mismatch: '+n)
  index_path=root/'.wp7b_archive_index.json'
  atomic_write(index_path,canonical(EXPECTED_INDEX))
  # This fixture-only seam exercises the child's independent re-hash after the outer hash pass.
  if FIXTURE_MODE and os.environ.get('WP7B_TEST_TAMPER_STAGED'):
   target=root/os.environ['WP7B_TEST_TAMPER_STAGED']
   with target.open('ab') as stream: stream.write(b'fixture tamper')
  import site as _site
  site_dirs=[]
  candidates=list(_site.getsitepackages())
  candidates.extend(item for item in sys.path if 'site-packages' in item or 'dist-packages' in item)
  for item in candidates:
   try:
    candidate=Path(item)
    if candidate.is_absolute() and candidate.is_dir() and str(candidate) not in site_dirs: site_dirs.append(str(candidate))
   except (TypeError,OSError): pass
  if FIXTURE_MODE and os.environ.get('WP7B_TEST_SITE_DIRS_JSON'):
   site_dirs=json.loads(os.environ['WP7B_TEST_SITE_DIRS_JSON'])
  env=child_environment()
  for name in ('wp7b_receipt.json','wp7b_difference.json'):
   try: (out_base/name).unlink()
   except FileNotFoundError: pass
  child=root/'research/g9/kaggle_wp7b/wp7b_child_entry.py'
  command=[sys.executable,'-I','-S','-B',str(child),str(root),str(index_path),STAGE_INDEX_SHA,str(out_base),json.dumps(site_dirs,separators=(',',':')),BUNDLE_SHA,APPROVAL_SHA,'1' if FIXTURE_MODE else '0']
  timeout=36300
  if FIXTURE_MODE and os.environ.get('WP7B_TEST_CHILD_TIMEOUT'): timeout=float(os.environ['WP7B_TEST_CHILD_TIMEOUT'])
  try:
   done=subprocess.run(command,cwd=str(out_base),env=env,timeout=timeout,check=False)
   code=done.returncode
   failure={'kind':'child_exit','exit_code':code}
  except subprocess.TimeoutExpired:
   code=124; failure={'kind':'child_timeout','timeout_seconds':timeout}
  receipt=out_base/'wp7b_receipt.json'; difference=out_base/'wp7b_difference.json'
  if code!=0 and not receipt.exists() and not difference.exists():
   row={'status':'refused','difference':json.dumps(failure,sort_keys=True),
        'error_type':'ChildSignalError' if code<0 else ('ChildTimeoutError' if code==124 else 'ChildProcessError'),
        'last_completed_step':'isolated_child','scientific_outputs':[]}
   atomic_write(difference,(json.dumps(row,sort_keys=True)+'\\n').encode())
  if code==0 and not receipt.exists() and not difference.exists():
   row={'status':'refused','difference':'isolated child exited without writing a receipt',
        'error_type':'MissingChildReceiptError',
        'last_completed_step':'isolated_child','scientific_outputs':[]}
   atomic_write(difference,(json.dumps(row,sort_keys=True)+'\\n').encode())
  shutil.rmtree(root,ignore_errors=True)
  if code!=0: return code
  if difference.exists(): return 2
  return 0
 except Exception as e:
  try:
   row={'status':'refused','difference':str(e),'error_type':type(e).__name__,
        'last_completed_step':None,'scientific_outputs':[]}
   atomic_write(out_base/'wp7b_difference.json',(json.dumps(row,sort_keys=True)+'\\n').encode())
  except Exception: pass
  refuse(e)
if __name__=='__main__': raise SystemExit(main())
'''

def enforce_script_size(source, limit=SCRIPT_SIZE_LIMIT):
 size=len(source.encode("utf-8"))
 if size>=limit: raise BuildError("generated script size "+str(size)+" is at or above limit "+str(limit))
 return size

def atomic_write(path, data):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--kaggle-user',required=True); p.add_argument('--instance',required=True); p.add_argument('--instance-sha256',required=True); p.add_argument('--prepared-record',required=True); p.add_argument('--prepared-record-sha256',required=True); p.add_argument('--seal',required=True); p.add_argument('--seal-sha256',required=True); p.add_argument('--seal-inputs',required=True); p.add_argument('--seal-inputs-sha256',required=True); p.add_argument('--runtime-config',required=True); p.add_argument('--runtime-config-sha256',required=True); p.add_argument('--owner-approval-record',type=Path); p.add_argument('--owner-approval-record-sha256'); p.add_argument('--draft',action='store_true'); p.add_argument('--fixture-mode',action='store_true'); a=p.parse_args(argv)
 try:
  require_fixture_approval(a.fixture_mode, a.draft, a.owner_approval_record)
  user=a.kaggle_user
  if user!="shivanshsrivastava06": raise BuildError("WP7b account is pinned to shivanshsrivastava06")
  inputs={"instance":a.instance,"prepared_record":a.prepared_record,"seal":a.seal,"seal_inputs":a.seal_inputs,"runtime_config":a.runtime_config}
  for n in tuple(inputs): inputs[n+"_sha256"]=getattr(a,n+"_sha256")
  blobs=load_payload(ROOT,inputs)
  validate_payload_blobs(blobs,[n for n,_,_ in blobs])
  bh=payload_hash(blobs); sealsha=inputs['seal_sha256']
  kernel=f"{user}/g9-wp7-nonscientific-dry-run-{bh[:8]}"
  expected={"bundle_sha256":bh,"reviewed_table_anchor":ANCHOR,"seal_sha256":sealsha,"kernel_id":kernel,"account":user,"action":"push_and_run_wp7_dry_run"}
  if a.draft:
   if a.owner_approval_record is not None: raise BuildError('draft mode cannot carry an approval record')
   if a.owner_approval_record_sha256 is not None: raise BuildError('draft mode cannot carry an approval hash')
   appsha=None; fields={}
  else:
   if a.owner_approval_record is None: raise BuildError('armed build requires owner approval record')
   if not a.owner_approval_record_sha256: raise BuildError('armed build requires owner approval sha256')
   rb=a.owner_approval_record.read_bytes()
   if sha(rb)!=a.owner_approval_record_sha256: raise BuildError('owner approval record sha256 mismatch')
   rec=json.loads(rb); validate_record(rec,expected); appsha=sha(rb); fields=expected|{"expiry":rec['expiry'],"nonce":rec['nonce']};
   blobs.append(("research/g9/kaggle_wp7b/owner_approval_record.json",appsha,rb)); blobs.sort()
  # Hash over payload excluding approval-record blob and approval hash by spec.
  bh=payload_hash([x for x in blobs if x[0]!="research/g9/kaggle_wp7b/owner_approval_record.json"])
  source=script_source(blobs,bh,appsha,fields,a.draft,a.fixture_mode)
  marker="SELF_SHA='"+"0"*64+"'"
  if source.count(marker)!=1: raise BuildError('launcher self-hash marker missing')
  self_digest=sha(source.replace(marker,"SELF_SHA='"+"0"*64+"'",1).encode('utf-8'))
  source=source.replace(marker,"SELF_SHA='"+self_digest+"'",1)
  script_size=enforce_script_size(source)
  code=f"g9_wp7_nonscientific_dry_run_{bh[:8]}{'.DRAFT' if a.draft else ''}.py"
  meta={"id":kernel,"title":"G9 WP7 Nonscientific Dry Run "+bh[:8],"code_file":code,"language":"python","kernel_type":"script","is_private":True,"enable_gpu":True,"enable_tpu":False,"enable_internet":False,"machine_shape":"NvidiaTeslaT4","keywords":[],"dataset_sources":[],"competition_sources":[],"kernel_sources":[],"model_sources":[]}
  out=a.output_dir
  atomic_write(out/code,source.encode('utf-8')); atomic_write(out/'kernel-metadata.json',(json.dumps(meta,sort_keys=True,indent=2)+'\n').encode())
  embedded=[{"name":n,"sha256":d} for n,d,_ in blobs]
  manifest={"bundle_sha256":bh,"blobs":embedded,"reviewed_table_anchor":ANCHOR,"seal_sha256":sealsha,"approval_record_sha256":appsha,"kernel_id":kernel,"script_size_bytes":script_size,"blob_count":len(blobs),"push_command":f"/home/shivansh-srivastava/venv/bin/kaggle kernels push -p {out} --accelerator NvidiaTeslaT4 -t 36600"}
  atomic_write(out/'wp7b_bundle_manifest.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())
  print(json.dumps(manifest,sort_keys=True,indent=2)); return 0
 except Exception as e:
  print('BUILD REFUSED: '+str(e),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
