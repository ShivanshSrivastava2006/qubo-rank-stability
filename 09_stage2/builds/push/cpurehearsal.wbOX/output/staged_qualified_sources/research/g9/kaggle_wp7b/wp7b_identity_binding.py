"""Shared, fail-closed mapping from the approved WP7 pin to WP1 identity fields.

The session supplies observations to this exact function; the offline seal
builder supplies the approved pin's expected observations. Values classified as
post-run-only or fixed are declared here so they cannot be silently omitted.
"""
from __future__ import annotations
import hashlib
import json

PIN_SHA256 = "c0c57c774380ed025cf00925512ff57c6185ff0b4955669d5282bd1bdda0cadc"
PIN_PATH = "research/g9/kaggle_wp7/wp7_environment_pin.json"
POST_RUN_ONLY = ("kaggle_image", "image_manifest_sha256", "image_config_id", "image_name")
POST_RUN_AUDITED_IDENTITY_FIELDS = (
    "kaggle_saved_version_build_platform_reported",
    "kaggle_kernel_version_platform_reported",
)
FIXED_IMAGE_EVIDENCE = {
    "kaggle_saved_version_build_platform_reported": "saved-version build: audited after run [platform_reported]",
    "kaggle_kernel_version_platform_reported": "kernel version: audited after run [platform_reported]",
    "kaggle_environment_pinning_platform_reported": "requested pinned image digest; verify by probe [platform_reported]",
}

def load_pin(path):
    raw = open(path, "rb").read()
    if hashlib.sha256(raw).hexdigest() != PIN_SHA256:
        raise ValueError("WP7 environment pin sha256 mismatch")
    value = json.loads(raw)
    if value.get("schema") != "decisions_os/g9_wp7_environment_pin/v1":
        raise ValueError("WP7 environment pin schema mismatch")
    return value

def expected_observations(pin):
    """Build the 13 expected in-session values solely from the checked pin."""
    p = pin["platform_reported"]
    image = pin["image_reported"]
    env = image["build_env"]
    return {
        "gpu_name": p["gpu_name"], "compute_capability": p["compute_capability"],
        "cuda_driver_version": p["cuda_driver_version"],
        "cuda_runtime_version": p["cuda_runtime_version"],
        "nvcc_version_release": p["nvcc_version_release"],
        "python_version": p["python_version"], "numpy_version": p["numpy_version"],
        "BUILD_DATE": env["BUILD_DATE"], "COLAB_IMAGE_TYPE": env["COLAB_IMAGE_TYPE"],
        "CUDA_VERSION": env["CUDA_VERSION"], "GIT_COMMIT": env["GIT_COMMIT"],
        "CUDA_HOME": image["cuda_home"], "nvcc_path": image["nvcc_path"],
    }

def build_identity_mapping(pin, observed):
    """Return ``(platform, image_build, provenance)`` for seal or session.

    Session observations are passed in explicitly and all 13 keys are exact;
    the seal builder passes :func:`expected_observations` for reproducibility.
    """
    expected = expected_observations(pin)
    if type(observed) is not dict or set(observed) != set(expected):
        raise ValueError("WP7 identity observation keys differ from the 13-field pin")
    if any(type(observed[k]) is not str or not observed[k] for k in expected):
        raise ValueError("WP7 identity observation is missing or not a string")
    platform = {k: observed[k] for k in (
        "gpu_name", "compute_capability", "cuda_driver_version", "cuda_runtime_version",
        "python_version", "numpy_version")}
    platform["nvcc_version"] = observed["nvcc_version_release"]
    platform["kaggle_image"] = pin["image_reported"]["kaggle_image"]
    suffix = " [platform_reported]"
    image = pin["image_reported"]
    image_build = {
        "kaggle_docker_image_platform_reported": image["kaggle_image"] + suffix,
        "kaggle_saved_version_build_platform_reported": FIXED_IMAGE_EVIDENCE["kaggle_saved_version_build_platform_reported"],
        "kaggle_image_manifest_digest_platform_reported": image["image_manifest_sha256"] + suffix,
        "kaggle_image_config_digest_platform_reported": image["image_config_id"] + suffix,
        "kaggle_kernel_version_platform_reported": FIXED_IMAGE_EVIDENCE["kaggle_kernel_version_platform_reported"],
        "runtime_build_observed_platform_reported": (
            "BUILD_DATE=" + observed["BUILD_DATE"] + ";COLAB_IMAGE_TYPE=" + observed["COLAB_IMAGE_TYPE"] +
            ";CUDA_VERSION=" + observed["CUDA_VERSION"] + ";GIT_COMMIT=" + observed["GIT_COMMIT"] +
            ";CUDA_HOME=" + observed["CUDA_HOME"] + ";nvcc_path=" + observed["nvcc_path"] + suffix),
        "kaggle_environment_pinning_platform_reported": FIXED_IMAGE_EVIDENCE["kaggle_environment_pinning_platform_reported"],
    }
    provenance = {
        **{f"platform.{k}": "observed probe; compared against pin" for k in platform if k != "kaggle_image"},
        "platform.kaggle_image": "pin constant; post-run metadata audit",
        **{f"image_build.{k}": "pin constant; post-run metadata audit" for k in (
            "kaggle_docker_image_platform_reported", "kaggle_image_manifest_digest_platform_reported",
            "kaggle_image_config_digest_platform_reported")},
        "image_build.kaggle_saved_version_build_platform_reported": "fixed declared constant; post-run audited",
        "image_build.kaggle_kernel_version_platform_reported": "fixed declared constant; post-run audited",
        "image_build.runtime_build_observed_platform_reported": "composed only from six observed pin-probe fields",
        "image_build.kaggle_environment_pinning_platform_reported": "fixed declared constant; pin request is separately checked",
    }
    return platform, image_build, provenance
